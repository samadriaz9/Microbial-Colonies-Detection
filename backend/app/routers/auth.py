"""Auth routes. Passwords and Google ID tokens both become an httpOnly session."""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import RefreshToken, User
from app.schemas import GoogleIn, LoginIn, RegisterIn, UserOut
from app.security import (
    clear_auth_cookies,
    create_access_token,
    hash_password,
    hash_refresh,
    new_refresh_token,
    set_auth_cookies,
    verify_password,
)

logger = logging.getLogger("colony.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
_attempts: dict[str, list[float]] = defaultdict(list)


def _limit(key: str, limit: int, window: int) -> None:
    now = time.time()
    recent = [stamp for stamp in _attempts[key] if now - stamp < window]
    if len(recent) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    recent.append(now)
    _attempts[key] = recent


def _client(request: Request) -> str:
    return request.client.host if request.client else "local"


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        has_password=bool(user.password_hash),
        created_at=user.created_at,
    )


def _issue(response: Response, db: Session, user: User) -> UserOut:
    raw, digest, expires = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=digest, expires_at=expires))
    existing = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .order_by(RefreshToken.created_at.desc())
        .all()
    )
    for stale in existing[9:]:
        stale.revoked = True
    db.commit()
    set_auth_cookies(response, create_access_token(user.id), raw)
    return _user_out(user)


@router.get("/config")
def auth_config():
    return {
        "google_client_id": settings.google_client_id or None,
        "password_login": True,
        "product": "Microbial Colonies",
        "docs": settings.env != "production",
    }


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _limit(f"register:{_client(request)}", 8, 3600)
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists. Sign in, or continue with Google.",
        )
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue(response, db, user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _limit(f"login:{_client(request)}", 10, 60)
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return _issue(response, db, user)


@router.post("/google", response_model=UserOut)
def google_login(body: GoogleIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Google sign-in is not configured on this server.")
    _limit(f"google:{_client(request)}", 15, 60)
    try:
        info = id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        logger.info("Rejected Google credential")
        raise HTTPException(status_code=401, detail="Google sign-in was rejected.") from exc
    if not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="That Google account has no verified email.")
    email = str(info["email"]).lower()
    sub = str(info["sub"])
    user = db.query(User).filter(User.google_sub == sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                name=(info.get("name") or email.split("@")[0])[:120],
                google_sub=sub,
                avatar_url=info.get("picture"),
            )
            db.add(user)
        else:
            user.google_sub = sub
            if info.get("picture"):
                user.avatar_url = info["picture"]
        db.commit()
        db.refresh(user)
    return _issue(response, db, user)


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(status_code=401, detail="Sign in again to continue.")
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh(raw)).first()
    now = datetime.now(timezone.utc)
    if row is None or row.revoked or row.expires_at < now:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Sign in again to continue.")
    row.revoked = True
    user = db.get(User, row.user_id)
    if user is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Sign in again to continue.")
    db.commit()
    return _issue(response, db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get("refresh_token")
    if raw:
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh(raw)).first()
        if row is not None:
            row.revoked = True
            db.commit()
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)
