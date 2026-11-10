from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.database import engine
from app.services.detector import model_status

router = APIRouter(prefix="/api", tags=["health"])


def _database_ok() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
def health():
    database = _database_ok()
    model = model_status()
    return {
        "status": "ok" if database else "degraded",
        "database": database,
        "model": model,
    }


@router.get("/ready")
def ready():
    database = _database_ok()
    model = model_status()
    if not database or not model["loaded"]:
        raise HTTPException(status_code=503, detail="The service is not ready.")
    return {"ready": True}
