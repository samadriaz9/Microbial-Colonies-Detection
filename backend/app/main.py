import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from sqlalchemy.exc import OperationalError

from app.bootstrap import bootstrap
from app.config import settings
from app.routers import analyses, auth, health
from app.services.detector import load_model

logger = logging.getLogger("colony")
Image.MAX_IMAGE_PIXELS = 48_000_000
WEB_DIR = Path(__file__).resolve().parent / "web"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' blob: data: https://lh3.googleusercontent.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' https://accounts.google.com https://apis.google.com; "
        "frame-src https://accounts.google.com https://apis.google.com; "
        "connect-src 'self' https://accounts.google.com https://apis.google.com; "
        "base-uri 'self'; form-action 'self'"
    ),
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bootstrap()
    load_model()
    yield


def _docs(path: str | None) -> str | None:
    return None if settings.env == "production" else path


app = FastAPI(
    title="Microbial Colonies API",
    version="1.0.0",
    summary="Accounts, plate mosaics, and YOLO colony counts.",
    docs_url=_docs("/docs"),
    redoc_url=_docs("/redoc"),
    lifespan=lifespan,
)

_origins = list(
    dict.fromkeys(
        [
            settings.app_origin,
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error request_id=%s", request_id)
        response = JSONResponse(status_code=500, content={"detail": "The server could not complete that request."})
    response.headers["X-Request-Id"] = request_id
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response


@app.exception_handler(OperationalError)
async def database_down(_request: Request, _exc: OperationalError):
    return JSONResponse(status_code=503, content={"detail": "The database is unavailable."})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    messages = []
    for item in exc.errors():
        messages.append(item.get("msg", "Invalid value"))
    return JSONResponse(status_code=422, content={"detail": " ".join(messages)})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(analyses.dashboard_router)
app.include_router(analyses.router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/{full_path:path}", include_in_schema=False)
def web_files(full_path: str):
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="Not found.")
    candidate = (WEB_DIR / full_path).resolve()
    try:
        candidate.relative_to(WEB_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    if candidate.is_file():
        headers = {"Cache-Control": "no-cache"} if candidate.suffix in {".js", ".css", ".html"} else None
        return FileResponse(candidate, headers=headers)
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})
