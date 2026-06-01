"""Path constants and storage layout for the bounding-box annotation feature.

These values are imported by server.py and any future submodule. Keeping them
in one file makes it obvious where Markhub writes runtime data and avoids
duplicate ``Path`` literals scattered across the package.
"""

from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
FEATURE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BACKEND_DIR / "static"
DATASETS_DIR = BACKEND_DIR / "datasets"
BOUNDING_BOX_DIR = DATASETS_DIR / "bounding_box"
IMAGES_DIR = BOUNDING_BOX_DIR / "images"
ANNOTATIONS_DIR = BOUNDING_BOX_DIR / "annotations"
DATASETS_INDEX_FILE = BOUNDING_BOX_DIR / "datasets_index.json"


__all__ = [
    "BACKEND_DIR",
    "FEATURE_DIR",
    "STATIC_DIR",
    "DATASETS_DIR",
    "BOUNDING_BOX_DIR",
    "IMAGES_DIR",
    "ANNOTATIONS_DIR",
    "DATASETS_INDEX_FILE",
]
