"""Create, list, and read colony analyses. Every query is scoped to the signed-in user."""

import csv
import io
import mimetypes
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.deps import get_current_user, get_owned_analysis
from app.models import Analysis, AnalysisImage, User
from app.schemas import (
    AnalysisList,
    AnalysisListItem,
    AnalysisOut,
    CreatedOut,
    DashboardOut,
    DetectionOut,
    TileOut,
)
from app.services.layout import natural_key
from app.services.runner import enqueue

router = APIRouter(prefix="/api/analyses", tags=["analyses"])
dashboard_router = APIRouter(prefix="/api", tags=["workspace"])

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


def _image_url(analysis_id: uuid.UUID, image_id: uuid.UUID) -> str:
    return f"/api/analyses/{analysis_id}/images/{image_id}"


def _safe_path(storage_key: str) -> Path:
    root = Path(settings.data_dir).resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found.") from exc
    return path


def _mean(detections: list | None) -> float | None:
    if not detections:
        return None
    return round(sum(float(item["confidence"]) for item in detections) / len(detections), 4)


def _thumb(analysis: Analysis) -> str | None:
    mosaic = next((image for image in analysis.images if image.role == "mosaic"), None)
    if mosaic:
        return _image_url(analysis.id, mosaic.id)
    annotated = next((image for image in analysis.images if image.role == "annotated"), None)
    if annotated:
        return _image_url(analysis.id, annotated.id)
    return None


def _list_item(analysis: Analysis) -> AnalysisListItem:
    return AnalysisListItem(
        id=analysis.id,
        title=analysis.title,
        organism=analysis.organism,
        mode=analysis.mode,
        layout=analysis.layout,
        rows=analysis.rows,
        cols=analysis.cols,
        file_count=analysis.file_count,
        status=analysis.status,
        progress=analysis.progress,
        colony_count=analysis.colony_count,
        created_at=analysis.created_at,
        thumb_url=_thumb(analysis),
    )


def _detail(analysis: Analysis) -> AnalysisOut:
    by_index_source = {
        image.tile_index: image for image in analysis.images if image.role == "source"
    }
    tiles = []
    for image in sorted(
        (item for item in analysis.images if item.role == "annotated"),
        key=lambda item: item.tile_index or 0,
    ):
        source = by_index_source.get(image.tile_index)
        tiles.append(
            TileOut(
                index=image.tile_index or 0,
                colony_count=image.colony_count or 0,
                mean_confidence=_mean(image.detections),
                width=image.width,
                height=image.height,
                annotated_url=_image_url(analysis.id, image.id),
                original_url=_image_url(analysis.id, source.id) if source else None,
                detections=[DetectionOut(**item) for item in (image.detections or [])],
            )
        )
    mosaic = next((image for image in analysis.images if image.role == "mosaic"), None)
    mosaic_raw = next((image for image in analysis.images if image.role == "mosaic_raw"), None)
    annotated_url = _image_url(analysis.id, mosaic.id) if mosaic else (tiles[0].annotated_url if tiles else None)
    if mosaic_raw:
        original_url = _image_url(analysis.id, mosaic_raw.id)
    elif tiles and tiles[0].original_url:
        original_url = tiles[0].original_url
    else:
        original_url = None
    return AnalysisOut(
        id=analysis.id,
        title=analysis.title,
        notes=analysis.notes,
        organism=analysis.organism,
        mode=analysis.mode,
        layout=analysis.layout,
        rows=analysis.rows,
        cols=analysis.cols,
        file_count=analysis.file_count,
        confidence=analysis.confidence,
        imgsz=analysis.imgsz,
        status=analysis.status,
        progress=analysis.progress,
        progress_message=analysis.progress_message,
        colony_count=analysis.colony_count,
        mean_confidence=analysis.mean_confidence,
        error=analysis.error,
        detector_label=analysis.detector_label,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
        duration_ms=analysis.duration_ms,
        operator=analysis.user.name if analysis.user else "",
        annotated_url=annotated_url,
        original_url=original_url,
        tiles=tiles,
    )


def _filtered(db: Session, user: User, q: str | None, mode: str | None):
    query = db.query(Analysis).filter(Analysis.user_id == user.id)
    if mode in {"single", "grid"}:
        query = query.filter(Analysis.mode == mode)
    if q:
        term = q.strip()
        if term:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            query = query.filter(
                or_(
                    Analysis.title.ilike(like, escape="\\"),
                    Analysis.organism.ilike(like, escape="\\"),
                    Analysis.notes.ilike(like, escape="\\"),
                )
            )
    return query


@dashboard_router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = db.query(Analysis).filter(Analysis.user_id == user.id)
    complete = base.filter(Analysis.status == "complete")
    analyses = complete.count()
    colonies = db.query(func.coalesce(func.sum(Analysis.colony_count), 0)).filter(
        Analysis.user_id == user.id, Analysis.status == "complete"
    ).scalar()
    mean = db.query(func.avg(Analysis.colony_count)).filter(
        Analysis.user_id == user.id, Analysis.status == "complete"
    ).scalar()
    processing = base.filter(Analysis.status == "processing").count()
    recent_rows = (
        base.options(selectinload(Analysis.images))
        .order_by(Analysis.created_at.desc())
        .limit(6)
        .all()
    )
    return DashboardOut(
        analyses=analyses,
        colonies=int(colonies or 0),
        mean_colonies=round(float(mean), 1) if mean is not None else None,
        processing=processing,
        recent=[_list_item(row) for row in recent_rows],
    )


@router.get("", response_model=AnalysisList)
def list_analyses(
    q: str | None = None,
    mode: str | None = None,
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _filtered(db, user, q, mode)
    total = query.count()
    rows = (
        query.options(selectinload(Analysis.images))
        .order_by(Analysis.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AnalysisList(items=[_list_item(row) for row in rows], total=total)


@router.post("", response_model=CreatedOut, status_code=202)
async def create_analysis(
    title: str = Form(""),
    notes: str = Form(""),
    organism: str = Form(""),
    mode: str = Form(...),
    layout: str = Form("scanner"),
    rows: int = Form(1),
    cols: int = Form(1),
    confidence: float = Form(0.25),
    imgsz: int = Form(1280),
    sort_by_name: str = Form("true"),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if mode not in {"single", "grid"}:
        raise HTTPException(status_code=400, detail="Choose a single plate or a mosaic.")
    if len(notes) > 4000:
        raise HTTPException(status_code=400, detail="Notes are limited to 4000 characters.")
    if not files:
        raise HTTPException(status_code=400, detail="Add at least one image.")

    incoming: list[tuple[str, bytes]] = []
    for upload in files:
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"{upload.filename or 'A file'} is empty.")
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename or 'A file'} is larger than {settings.max_upload_bytes // (1024 * 1024)} MB.",
            )
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename or 'A file'} is not a JPEG, PNG, WebP, BMP, or TIFF image.",
            )
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename or 'A file'} could not be read as an image.",
            ) from exc
        incoming.append((upload.filename or f"frame{suffix}", raw))

    if sort_by_name.lower() in {"1", "true", "yes", "on"}:
        incoming.sort(key=lambda item: natural_key(item[0]))
    if len(incoming) > settings.max_images:
        raise HTTPException(status_code=400, detail=f"Upload at most {settings.max_images} images at once.")

    if mode == "single":
        if len(incoming) != 1:
            raise HTTPException(status_code=400, detail="A single plate takes exactly one image.")
        rows, cols, layout_value = 1, 1, None
    else:
        if layout not in {"row", "scanner"}:
            raise HTTPException(status_code=400, detail="Choose row order or the scanner path.")
        if rows < 1 or cols < 1 or rows > 16 or cols > 16:
            raise HTTPException(status_code=400, detail="Rows and columns must be between 1 and 16.")
        if rows * cols != len(incoming):
            raise HTTPException(
                status_code=400,
                detail=f"The grid is {rows}×{cols} ({rows * cols} cells) but {len(incoming)} images were uploaded.",
            )
        layout_value = layout

    confidence = max(0.05, min(0.95, float(confidence)))
    imgsz = max(320, min(1600, int(imgsz)))
    clean_title = title.strip()[:200] or datetime.now(timezone.utc).strftime("Plate %Y-%m-%d %H:%M")

    analysis = Analysis(
        user_id=user.id,
        title=clean_title,
        notes=notes.strip(),
        organism=organism.strip()[:120],
        mode=mode,
        layout=layout_value,
        rows=rows,
        cols=cols,
        file_count=len(incoming),
        confidence=confidence,
        imgsz=imgsz,
        status="processing",
        progress=1,
        progress_message="Queued",
    )
    db.add(analysis)
    db.flush()

    folder = Path(settings.data_dir) / str(user.id) / str(analysis.id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for index, (filename, raw) in enumerate(incoming):
            suffix = Path(filename).suffix.lower()
            relative = Path(str(user.id)) / str(analysis.id) / f"source_{index:02d}{suffix}"
            (Path(settings.data_dir) / relative).write_bytes(raw)
            db.add(
                AnalysisImage(
                    analysis_id=analysis.id,
                    role="source",
                    tile_index=index,
                    storage_key=relative.as_posix(),
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        shutil.rmtree(folder, ignore_errors=True)
        raise

    enqueue(analysis.id)
    return CreatedOut(id=analysis.id, status=analysis.status)


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis: Analysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
):
    loaded = (
        db.query(Analysis)
        .options(selectinload(Analysis.images), selectinload(Analysis.user))
        .filter(Analysis.id == analysis.id)
        .one()
    )
    return _detail(loaded)


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(
    analysis: Analysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
):
    keys = [image.storage_key for image in analysis.images]
    folder = _safe_path(keys[0]).parent if keys else None
    db.delete(analysis)
    db.commit()
    if folder is not None and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return Response(status_code=204)


@router.get("/{analysis_id}/images/{image_id}")
def get_image(
    image_id: uuid.UUID,
    analysis: Analysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
):
    image = db.get(AnalysisImage, image_id)
    if image is None or image.analysis_id != analysis.id:
        raise HTTPException(status_code=404, detail="Image not found.")
    path = _safe_path(image.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{analysis_id}/export.csv")
def export_csv(analysis: Analysis = Depends(get_owned_analysis), db: Session = Depends(get_db)):
    images = (
        db.query(AnalysisImage)
        .filter(AnalysisImage.analysis_id == analysis.id, AnalysisImage.role == "annotated")
        .order_by(AnalysisImage.tile_index.asc())
        .all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["tile", "index", "class", "confidence", "x1", "y1", "x2", "y2"])
    for image in images:
        tile_number = (image.tile_index or 0) + 1
        for det in image.detections or []:
            writer.writerow(
                [
                    tile_number,
                    det["index"],
                    det["class_name"],
                    det["confidence"],
                    det["x1"],
                    det["y1"],
                    det["x2"],
                    det["y2"],
                ]
            )
    filename = f"colonies-{analysis.id}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
