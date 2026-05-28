"""Path constants and storage layout for the layout-analysis feature.

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
FIRST_ANNOTATIONS_DIR = DATASETS_DIR / "first_annotations"
SECOND_ANNOTATIONS_DIR = DATASETS_DIR / "second_annotations"
SWIFT_DATASETS_DIR = DATASETS_DIR / "swift_datasets"
LLAMAFACTORY_DATASETS_DIR = DATASETS_DIR / "llamafactory_datasets"
PROMPTS_DIR = DATASETS_DIR / "prompt_templates"
CONVERT_TASKS_DIR = DATASETS_DIR / "convert_tasks"
PROMPTS_STORE_FILE = PROMPTS_DIR / "prompts.json"
JOBS_DIR = FIRST_ANNOTATIONS_DIR
LEGACY_JOBS_DIR = BACKEND_DIR / "jobs"
ENV_FILE = BACKEND_DIR / ".env"
PROMPT_TEMPLATES_FILE = BACKEND_DIR / "prompt_templates.json"


__all__ = [
    "BACKEND_DIR",
    "FEATURE_DIR",
    "STATIC_DIR",
    "DATASETS_DIR",
    "FIRST_ANNOTATIONS_DIR",
    "SECOND_ANNOTATIONS_DIR",
    "SWIFT_DATASETS_DIR",
    "LLAMAFACTORY_DATASETS_DIR",
    "PROMPTS_DIR",
    "CONVERT_TASKS_DIR",
    "PROMPTS_STORE_FILE",
    "JOBS_DIR",
    "LEGACY_JOBS_DIR",
    "ENV_FILE",
    "PROMPT_TEMPLATES_FILE",
]
