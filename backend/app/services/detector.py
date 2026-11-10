"""YOLO colony detector. The weights file is loaded once per process."""

import logging
import threading
from pathlib import Path

from PIL import Image

from app.config import settings

logger = logging.getLogger("colony.detector")

_model = None
_model_error: str | None = None
_names: dict = {}
_lock = threading.Lock()
_label: str = Path(settings.model_path).name


class AnalysisError(Exception):
    """A failure that is safe to show to the signed-in user."""


def model_status() -> dict:
    return {
        "loaded": _model is not None,
        "label": _label,
        "error": _model_error,
        "classes": list(_names.values()) if isinstance(_names, dict) else list(_names),
    }


def load_model() -> None:
    global _model, _model_error, _names, _label
    path = Path(settings.model_path)
    _label = path.name
    if not path.is_file():
        _model = None
        _model_error = f"Weights not found at {path}"
        logger.error(_model_error)
        return
    try:
        from ultralytics import YOLO

        model = YOLO(str(path))
        blank = Image.new("RGB", (64, 64), (244, 241, 234))
        model.predict(blank, verbose=False, conf=0.25, imgsz=64)
        _model = model
        _names = model.names or {}
        _model_error = None
        logger.info("Loaded %s classes=%s", path.name, _names)
    except Exception as exc:
        _model = None
        _model_error = "The detection weights could not be loaded."
        logger.exception("Model load failed: %s", exc)


def detect(image: Image.Image, confidence: float, imgsz: int) -> list[dict]:
    if _model is None:
        raise AnalysisError(_model_error or "The detection model is not loaded.")
    with _lock:
        results = _model.predict(
            image,
            verbose=False,
            conf=confidence,
            imgsz=imgsz,
            iou=0.5,
        )
    boxes = results[0].boxes
    names = results[0].names or _names
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    classes = boxes.cls.cpu().numpy().astype(int)
    detections = []
    for index, (coords, score, class_id) in enumerate(zip(xyxy, confs, classes), start=1):
        x1, y1, x2, y2 = [float(v) for v in coords]
        class_name = names.get(int(class_id), str(int(class_id))) if isinstance(names, dict) else str(int(class_id))
        detections.append(
            {
                "index": index,
                "class_id": int(class_id),
                "class_name": str(class_name),
                "confidence": round(float(score), 4),
                "x1": round(x1, 1),
                "y1": round(y1, 1),
                "x2": round(x2, 1),
                "y2": round(y2, 1),
            }
        )
    return detections


def detector_label() -> str:
    return _label
