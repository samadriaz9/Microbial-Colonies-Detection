import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.security import hash_password

logger = logging.getLogger("colony.bootstrap")


def bootstrap() -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    _warn_secret()
    _seed_admin()


def _warn_secret() -> None:
    secret = settings.jwt_secret
    if secret in {"change-me", "change-me-before-deploying"} or len(secret) < 16:
        logger.warning("JWT_SECRET is weak. Set a long random value before this service is exposed.")


def _seed_admin() -> None:
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""
    if not email or not password:
        return
    if len(password.encode("utf-8")) > 72 or len(password) < 8:
        logger.warning("ADMIN_PASSWORD must be 8 to 72 bytes. Administrator was not created.")
        return
    db: Session = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            return
        db.add(
            User(
                email=email,
                name=(settings.admin_name or "Administrator")[:120],
                password_hash=hash_password(password),
            )
        )
        db.commit()
        logger.info("Created administrator account for %s", email)
    finally:
        db.close()
