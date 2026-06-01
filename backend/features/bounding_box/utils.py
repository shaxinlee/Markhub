"""Pure helpers shared across the bounding-box feature: path sanitization,
string utilities. Nothing in here imports from sibling modules with
side effects, so it is safe to use during module initialization.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


def now_timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def generate_id(prefix: str = "") -> str:
    timestamp = time.strftime("%Y%m%d%H%M%S")
    random_part = uuid.uuid4().hex[:6]
    if prefix:
        return f"{prefix}_{timestamp}_{random_part}"
    return f"{timestamp}_{random_part}"


def sanitize_path_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.\-]+", "_", str(value or "").strip())
    return text.strip("._ ") or "dataset"


def parse_image_id(filename: str) -> str:
    """Recover the stable per-file id from a stored image filename.

    Uploads are stored as ``{generate_id}_{original_name}`` where ``generate_id``
    is ``{prefix}_{timestamp14}_{rand6}`` — note it already contains underscores,
    so naively splitting on the first ``_`` collapses every image to the same id.
    This recovers the full id prefix, falling back to the stem so each file still
    gets a unique, stable id.
    """
    match = re.match(r"^([A-Za-z]+_\d{14}_[0-9a-f]{6})(?:_|$)", filename)
    if match:
        return match.group(1)
    return Path(filename).stem


def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(str(value))
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def normalize_bbox(bbox: Any) -> tuple[float, float, float, float]:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    try:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (ValueError, TypeError):
        return (0.0, 0.0, 0.0, 0.0)


def bbox_to_percentage(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 / width * 100, y1 / height * 100, x2 / width * 100, y2 / height * 100)


def percentage_to_bbox(percentage: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    px1, py1, px2, py2 = percentage
    return (int(px1 * width / 100), int(py1 * height / 100), int(px2 * width / 100), int(py2 * height / 100))
