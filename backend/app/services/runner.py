"""Run a saved analysis outside the request that created it."""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import Analysis, AnalysisImage
from app.services.detector import AnalysisError, detect, detector_label
from app.services.stitch import annotate, open_image, save_jpeg, stitch

logger = logging.getLogger("colony.runner")
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="colony")


def enqueue(analysis_id: uuid.UUID) -> None:
    _pool.submit(execute, analysis_id)


def execute(analysis_id: uuid.UUID) -> None:
    db = SessionLocal()
    started = time.perf_counter()
    try:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            return
        _run(db, analysis, started)
    except AnalysisError as exc:
        logger.warning("Analysis %s rejected: %s", analysis_id, exc)
        _mark_failed(db, analysis_id, str(exc))
    except Exception:
        logger.exception("Analysis %s failed", analysis_id)
        _mark_failed(db, analysis_id, "The run failed before it could finish.")
    finally:
        db.close()


def _mark_failed(db, analysis_id: uuid.UUID, message: str) -> None:
    db.rollback()
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.status == "complete":
        return
    analysis.status = "failed"
    analysis.error = message
    analysis.progress_message = "Failed"
    db.commit()


def _run(db, analysis: Analysis, started: float) -> None:
    root = Path(settings.data_dir)
    sources = (
        db.query(AnalysisImage)
        .filter(AnalysisImage.analysis_id == analysis.id, AnalysisImage.role == "source")
        .order_by(AnalysisImage.tile_index.asc())
        .all()
    )
    if len(sources) != analysis.file_count:
        raise AnalysisError("The uploaded frames are incomplete.")

    analysis.status = "processing"
    analysis.progress = 4
    analysis.progress_message = "Opening frames"
    analysis.detector_label = detector_label()
    db.commit()

    annotated_paths: list[Path] = []
    source_paths: list[Path] = []
    all_scores: list[float] = []
    total = 0

    for position, source in enumerate(sources):
        analysis.progress = 8 + int(80 * position / max(1, len(sources)))
        analysis.progress_message = f"Detecting frame {position + 1} of {len(sources)}"
        db.commit()

        image = open_image(root / source.storage_key)
        source.width = image.width
        source.height = image.height
        detections = detect(image, analysis.confidence, analysis.imgsz)
        drawn = annotate(image, detections)
        relative = str(Path(source.storage_key).parent / f"annotated_{position:02d}.jpg")
        save_jpeg(drawn, root / relative, quality=90)
        annotated_paths.append(root / relative)
        source_paths.append(root / source.storage_key)
        count = len(detections)
        total += count
        all_scores.extend(item["confidence"] for item in detections)
        db.add(
            AnalysisImage(
                analysis_id=analysis.id,
                role="annotated",
                tile_index=position,
                colony_count=count,
                width=drawn.width,
                height=drawn.height,
                storage_key=relative,
                detections=detections,
            )
        )
        db.commit()

    hero_key = str(Path(sources[0].storage_key).parent / "annotated_00.jpg")
    if analysis.mode == "grid":
        analysis.progress = 92
        analysis.progress_message = "Stitching the plate"
        db.commit()
        folder = Path(sources[0].storage_key).parent
        mosaic_key = str(folder / "mosaic.jpg")
        raw_key = str(folder / "mosaic_original.jpg")
        width, height, _scaled = stitch(
            annotated_paths,
            analysis.rows,
            analysis.cols,
            analysis.layout or "row",
            root / mosaic_key,
            number_tiles=True,
        )
        raw_w, raw_h, _ = stitch(
            source_paths,
            analysis.rows,
            analysis.cols,
            analysis.layout or "row",
            root / raw_key,
            number_tiles=True,
        )
        db.add(
            AnalysisImage(
                analysis_id=analysis.id,
                role="mosaic",
                tile_index=None,
                colony_count=total,
                width=width,
                height=height,
                storage_key=mosaic_key,
                detections=None,
            )
        )
        db.add(
            AnalysisImage(
                analysis_id=analysis.id,
                role="mosaic_raw",
                tile_index=None,
                colony_count=None,
                width=raw_w,
                height=raw_h,
                storage_key=raw_key,
                detections=None,
            )
        )
        hero_key = mosaic_key

    analysis.colony_count = total
    analysis.mean_confidence = round(sum(all_scores) / len(all_scores), 4) if all_scores else None
    analysis.status = "complete"
    analysis.progress = 100
    analysis.progress_message = "Complete"
    analysis.error = None
    analysis.completed_at = datetime.now(timezone.utc)
    analysis.duration_ms = int((time.perf_counter() - started) * 1000)
    db.commit()
    logger.info(
        "Analysis %s complete colonies=%s duration_ms=%s hero=%s",
        analysis.id,
        total,
        analysis.duration_ms,
        hero_key,
    )
