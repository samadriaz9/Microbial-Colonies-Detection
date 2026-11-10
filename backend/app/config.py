"""Runtime configuration. Environment variables override the defaults."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _env_files() -> tuple[str, ...]:
    found = []
    for path in (REPO_ROOT / ".env", BACKEND_ROOT / ".env"):
        if path.is_file():
            found.append(str(path))
    return tuple(found)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = "development"
    database_url: str = "postgresql+psycopg://colony:colony@localhost:5432/colony"
    jwt_secret: str = "change-me-before-deploying"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    cookie_secure: bool = False
    app_origin: str = "http://localhost:8000"
    google_client_id: str = ""
    google_client_secret: str = ""
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrator"
    model_path: str = str(REPO_ROOT / "best.pt")
    data_dir: str = str(REPO_ROOT / "data")
    max_upload_bytes: int = 25 * 1024 * 1024
    max_images: int = 64


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
