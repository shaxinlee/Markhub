"""Pure helpers shared across the feature: env parsing, path sanitization,
small string utilities. Nothing in here imports from sibling modules with
side effects, so it is safe to use during module initialization.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .paths import BACKEND_DIR, DATASETS_DIR, ENV_FILE
from .schemas import BLOCK_TYPE_ALIASES, DEFAULT_MAX_PDF_BYTES, ENV_CONFIG_KEYS


def parse_env_line(line: str) -> Optional[Tuple[str, str]]:
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    key, value = text.split("=", 1)
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if '"' in line:
        value = value.replace(r"\n", "\n").replace(r"\"", '"').replace(r"\\", "\\")
    return key, value


def normalize_block_type(value: Any, default: str = "text") -> str:
    label = str(value or default).strip()
    return BLOCK_TYPE_ALIASES.get(label, label)


def portable_path_ref(path: Optional[Path]) -> str:
    if not path:
        return ""
    candidates = [
        (DATASETS_DIR, "datasets"),
        (BACKEND_DIR, "backend"),
        (BACKEND_DIR.parent, "."),
    ]
    resolved = path.resolve()
    for root, prefix in candidates:
        try:
            relative = resolved.relative_to(root.resolve()).as_posix()
            return f"{prefix}/{relative}" if prefix != "." else relative
        except ValueError:
            continue
    return path.as_posix() if not path.is_absolute() else path.name


def sanitize_saved_text(text: str) -> str:
    replacements = [
        (DATASETS_DIR, "datasets"),
        (BACKEND_DIR, "backend"),
        (BACKEND_DIR.parent, "."),
    ]
    sanitized = text
    for root, prefix in replacements:
        root_text = root.resolve().as_posix()
        replacement_prefix = "" if prefix == "." else f"{prefix}/"
        sanitized = sanitized.replace(f"{root_text}/", replacement_prefix)
        sanitized = sanitized.replace(root_text, prefix)
    return sanitized


def read_env_file(path: Path = ENV_FILE) -> Dict[str, str]:
    if not path.is_file():
        return {}
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(line)
        if parsed:
            key, value = parsed
            values[key] = value
    return values


def max_pdf_bytes() -> int:
    return clamp_int(os.getenv("LAYOUT_MAX_PDF_BYTES"), default=DEFAULT_MAX_PDF_BYTES, minimum=1024 * 1024, maximum=2 * 1024 * 1024 * 1024)


def load_dotenv(path: Path = ENV_FILE) -> None:
    for key, value in read_env_file(path).items():
        os.environ.setdefault(key, value)


def dotenv_value(value: str) -> str:
    if value == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', r"\"").replace("\n", r"\n")
    return f'"{escaped}"'


def write_env_file(updates: Dict[str, str], path: Path = ENV_FILE) -> None:
    values = read_env_file(path)
    for key, value in updates.items():
        if key in ENV_CONFIG_KEYS:
            values[key] = value

    lines = [
        "# Local configuration for PDF layout analysis.",
        "# This file is ignored by Git because it may contain API keys.",
    ]
    for key in ENV_CONFIG_KEYS:
        lines.append(f"{key}={dotenv_value(values.get(key, ''))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(str(value))
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def align_to_factor(value: int, factor: int) -> int:
    return max(factor, int(round(value / factor)) * factor)


def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def safe_path_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.\-一-鿿]+", "_", str(value or "").strip())
    return text.strip("._ ") or "dataset"
