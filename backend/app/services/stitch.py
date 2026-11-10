"""Draw colony boxes and stitch tiles into one plate image."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.services.layout import slots

MAX_MOSAIC_SIDE = 8192
_FONT = None


def open_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _font(size: int) -> ImageFont.ImageFont:
    global _FONT
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    if _FONT is None:
        _FONT = ImageFont.load_default()
    return _FONT


def annotate(image: Image.Image, detections: list[dict]) -> Image.Image:
    bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    height, width = bgr.shape[:2]
    thickness = max(2, round(width / 900))
    font_scale = max(0.45, width / 1800)
    color = (56, 92, 184)  # copper, in BGR
    show_index = len(detections) <= 80
    for det in detections:
        x1 = int(max(0, min(width - 1, det["x1"])))
        y1 = int(max(0, min(height - 1, det["y1"])))
        x2 = int(max(0, min(width - 1, det["x2"])))
        y2 = int(max(0, min(height - 1, det["y2"])))
        cv2.rectangle(bgr, (x1, y1), (x2, y2), color, thickness, lineType=cv2.LINE_AA)
        if show_index:
            label = str(det["index"])
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            ly = max(th + 6, y1)
            cv2.rectangle(bgr, (x1, ly - th - 8), (x1 + tw + 10, ly + 4), color, -1)
            cv2.putText(
                bgr,
                label,
                (x1 + 5, ly - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 248, 243),
                1,
                cv2.LINE_AA,
            )
    banner = f"{len(detections)} colonies"
    scale = max(0.7, width / 1400)
    (tw, th), _ = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    pad = 14
    x, y = 16, height - 16
    cv2.rectangle(bgr, (x, y - th - pad * 2), (x + tw + pad * 2, y), (28, 36, 32), -1)
    cv2.putText(
        bgr,
        banner,
        (x + pad, y - pad),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (244, 241, 234),
        2,
        cv2.LINE_AA,
    )
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def save_jpeg(image: Image.Image, path: Path, quality: int = 90) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=quality, optimize=True)


def stitch(
    paths: list[Path],
    rows: int,
    cols: int,
    layout: str,
    dest: Path,
    number_tiles: bool = False,
) -> tuple[int, int, bool]:
    if len(paths) != rows * cols:
        raise ValueError("Every grid cell needs an image.")
    images = [open_image(path) for path in paths]
    cell_w = max(image.width for image in images)
    cell_h = max(image.height for image in images)
    scale = min(1.0, MAX_MOSAIC_SIDE / max(cols * cell_w, rows * cell_h))
    cell_w = max(1, int(cell_w * scale))
    cell_h = max(1, int(cell_h * scale))
    canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (236, 232, 223))
    order = slots(rows, cols, layout)
    for index, path_image in enumerate(images):
        row, col = order[index]
        tile = path_image.copy()
        tile.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
        sheet = Image.new("RGB", (cell_w, cell_h), (236, 232, 223))
        left = (cell_w - tile.width) // 2
        top = (cell_h - tile.height) // 2
        sheet.paste(tile, (left, top))
        if number_tiles:
            _draw_index(sheet, index + 1)
        canvas.paste(sheet, (col * cell_w, row * cell_h))
    save_jpeg(canvas, dest, quality=85)
    return canvas.width, canvas.height, scale < 0.999


def _draw_index(image: Image.Image, number: int) -> None:
    draw = ImageDraw.Draw(image)
    label = str(number)
    size = max(16, image.width // 28)
    font = _font(size)
    box = draw.textbbox((0, 0), label, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad = 8
    rect = (10, 10, 10 + tw + pad * 2, 10 + th + pad * 2)
    draw.rounded_rectangle(rect, radius=8, fill=(28, 36, 32))
    draw.text((10 + pad, 10 + pad - 1), label, fill=(244, 241, 234), font=font)
