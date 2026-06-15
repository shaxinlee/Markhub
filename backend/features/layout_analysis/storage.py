"""Persistence and path helpers for the layout-analysis feature.

This module owns every disk-touching operation: PDF job results, dataset
state files, convert-task records, atomic JSON I/O, and the model-name to
directory layout helpers. Nothing here imports from ``service.py`` or
``server.py`` — those are downstream consumers.

By convention, ``ensure_dataset_storage()`` is *defined* here but should be
called from ``server.main()``, never at import time.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .paths import (
    CONVERT_TASKS_DIR,
    DATASETS_DIR,
    FIRST_ANNOTATIONS_DIR,
    JOBS_DIR,
    LEGACY_JOBS_DIR,
    LLAMAFACTORY_DATASETS_DIR,
    PROMPTS_DIR,
    SECOND_ANNOTATIONS_DIR,
    SWIFT_DATASETS_DIR,
)
from .schemas import LLMConfig, VisionResizeConfig
from .utils import safe_path_name, sanitize_saved_text, write_env_file


CONVERT_TASKS: Dict[str, Dict[str, Any]] = {}
REMOVED_LAYOUT_OUTPUT_KEYS = {
    "_".join(("context", "before")),
    "_".join(("context", "after")),
    "_".join(("weak", "heading")),
}


def strip_removed_layout_output_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key in REMOVED_LAYOUT_OUTPUT_KEYS:
            value.pop(key, None)
        for child in value.values():
            strip_removed_layout_output_keys(child)
    elif isinstance(value, list):
        for child in value:
            strip_removed_layout_output_keys(child)


def iso_to_sort_value(value: Any) -> str:
    return str(value or "")


def now_timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def public_llm_config(config: LLMConfig) -> Dict[str, str]:
    return {
        "base_url": config.base_url,
        "model": config.model,
        "has_api_key": "true" if config.api_key else "false",
        "timeout": str(config.timeout),
        "max_tokens": str(config.max_tokens),
    }


def result_model_name(payload: Dict[str, Any]) -> str:
    config = payload.get("config")
    if isinstance(config, dict):
        model = str(config.get("model") or "").strip()
        if model:
            return model
    model = str(payload.get("model") or payload.get("model_name") or "").strip()
    return model or "未知"


def model_dir_name(model: str) -> str:
    name = str(model or "").strip() or "未知"
    name = re.sub(r"[\\/:\0]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "未知"


def job_dir_for_model(job_id: str, model: str) -> Path:
    return JOBS_DIR / model_dir_name(model) / job_id


def ensure_dataset_storage() -> None:
    for path in (FIRST_ANNOTATIONS_DIR, SECOND_ANNOTATIONS_DIR, SWIFT_DATASETS_DIR, LLAMAFACTORY_DATASETS_DIR, PROMPTS_DIR, CONVERT_TASKS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def job_storage_roots() -> List[Path]:
    roots = [JOBS_DIR]
    if LEGACY_JOBS_DIR != JOBS_DIR and LEGACY_JOBS_DIR.exists():
        roots.append(LEGACY_JOBS_DIR)
    return roots


def relative_job_url(path: Path) -> str:
    return "/jobs/" + path.relative_to(JOBS_DIR).as_posix()


def job_asset_path(relative_path: str) -> Path:
    candidate = JOBS_DIR / relative_path
    if candidate.exists():
        return candidate
    legacy_candidate = LEGACY_JOBS_DIR / relative_path
    if legacy_candidate.exists():
        return legacy_candidate

    parts = Path(relative_path).parts
    if len(parts) >= 2:
        legacy_job_id = parts[0]
        resolved_job_dir = find_job_dir(legacy_job_id)
        if resolved_job_dir != JOBS_DIR / legacy_job_id and resolved_job_dir != LEGACY_JOBS_DIR / legacy_job_id:
            return resolved_job_dir.joinpath(*parts[1:])

    return candidate


def public_resize_config(config: VisionResizeConfig) -> Dict[str, Any]:
    return {
        "preset": config.preset,
        "image_profile": config.image_profile,
        "factor": config.factor,
        "width": config.width,
        "height": config.height,
        "pixels": config.pixels,
        "min_pixels": config.min_pixels,
        "max_pixels": config.max_pixels,
    }


def persist_runtime_config(
    llm_config: LLMConfig,
    resize_config: VisionResizeConfig,
    dpi: int,
    max_pages: int,
) -> None:
    import os

    updates = {
        "LLM_BASE_URL": llm_config.base_url,
        "LLM_MODEL": llm_config.model,
        "LLM_TIMEOUT": str(llm_config.timeout),
        "LLM_MAX_TOKENS": str(llm_config.max_tokens),
        "LAYOUT_RENDER_DPI": str(dpi),
        "LAYOUT_MAX_PAGES": str(max_pages),
        "QWEN_RESIZE_PRESET": resize_config.preset,
        "QWEN_IMAGE_PROFILE": resize_config.image_profile,
        "QWEN_RESIZED_WIDTH": str(resize_config.width),
        "QWEN_RESIZED_HEIGHT": str(resize_config.height),
    }
    if llm_config.api_key:
        updates["LLM_API_KEY"] = llm_config.api_key
    write_env_file(updates)
    os.environ.update(updates)


def iter_result_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for root in job_storage_roots():
        for pattern in ("*/result.json", "*/*/result.json"):
            for result_file in root.glob(pattern):
                resolved = result_file.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield result_file


def clean_old_jobs(max_age_hours: int = 24) -> None:
    # 历史版本把分析任务当作临时缓存清理；现在它们是 datasets 下的 Completed 数据集资产，必须持久保留。
    ensure_dataset_storage()


def result_path(job_id: str) -> Path:
    return find_job_dir(job_id) / "result.json"


def find_job_dir(job_id: str) -> Path:
    for root in job_storage_roots():
        legacy_dir = root / job_id
        if (legacy_dir / "result.json").exists():
            return legacy_dir
        matches = list(root.glob(f"*/{job_id}/result.json"))
        if matches:
            return matches[0].parent
    return JOBS_DIR / job_id


def read_job_result(job_id: str) -> Dict[str, Any]:
    path = result_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"job not found: {job_id}")
    return normalize_job_payload(job_id, json.loads(path.read_text(encoding="utf-8")))


def normalize_job_payload(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from .prompts import PROMPT_TEMPLATES
    from .schemas import DEFAULT_PROMPT_TEMPLATE_ID

    strip_removed_layout_output_keys(payload)
    payload.setdefault("job_id", job_id)
    payload.setdefault("filename", "未知文件")
    payload.setdefault("status", "complete")
    payload.setdefault("completed_pages", count_finished_pages(payload.get("pages", [])))
    payload.setdefault("pages", [])
    payload.setdefault("result", {"image_path": "", "blocks": []})
    payload.setdefault("warnings", [])
    payload.setdefault("errors", [])
    config = payload.get("config")
    if not isinstance(config, dict):
        config = {}
        payload["config"] = config
    config["model"] = result_model_name(payload)
    config.setdefault("model_dir", model_dir_name(config["model"]))
    template = payload.get("prompt_template")
    if not isinstance(template, dict):
        payload["prompt_template"] = {
            "id": DEFAULT_PROMPT_TEMPLATE_ID,
            "name": PROMPT_TEMPLATES[DEFAULT_PROMPT_TEMPLATE_ID]["name"],
            "category": PROMPT_TEMPLATES[DEFAULT_PROMPT_TEMPLATE_ID].get("category", "layout"),
        }
    return payload


def list_job_summaries() -> List[Dict[str, Any]]:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for result_file in iter_result_files():
        job_id = result_file.parent.name
        try:
            payload = read_job_result(job_id)
        except Exception:
            continue
        stat = result_file.stat()
        blocks = payload.get("result", {}).get("blocks", [])
        pages = payload.get("pages", [])
        first_page_url = ""
        if isinstance(pages, list) and pages:
            first_page = pages[0]
            if isinstance(first_page, dict):
                first_page_url = str(first_page.get("image_url") or "")
        items.append(
            {
                "job_id": job_id,
                "filename": payload.get("filename") or "未知文件",
                "model": result_model_name(payload),
                "model_dir": payload.get("config", {}).get("model_dir") if isinstance(payload.get("config"), dict) else "",
                "status": payload.get("status") or "complete",
                "page_count": payload.get("page_count") or len(pages),
                "completed_pages": payload.get("completed_pages") or count_finished_pages(pages),
                "block_count": len(blocks) if isinstance(blocks, list) else 0,
                "error_count": len(payload.get("errors", [])) if isinstance(payload.get("errors"), list) else 0,
                "prompt_template": payload.get("prompt_template") if isinstance(payload.get("prompt_template"), dict) else {},
                "first_page_url": first_page_url,
                "updated_at": int(stat.st_mtime),
            }
        )
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items


def dataset_dir(job_id: str) -> Path:
    return find_job_dir(job_id)


def legacy_dataset_dir(job_id: str) -> Path:
    return DATASETS_DIR / safe_path_name(job_id)


def second_annotation_dir(job_id: str) -> Path:
    return SECOND_ANNOTATIONS_DIR / safe_path_name(job_id)


def first_annotation_path(job_id: str) -> Path:
    return dataset_dir(job_id) / "annotations" / "first_annotation" / "annotation.json"


def resolve_dataset_job_id(dataset_id: str) -> str:
    candidate = str(dataset_id or "").strip()
    if not candidate:
        raise FileNotFoundError("missing dataset id")
    if result_path(candidate).is_file():
        return candidate
    for item in list_job_summaries():
        job_id = str(item.get("job_id") or "")
        if candidate in {job_id, str(item.get("dataset_id") or ""), str(item.get("filename") or "")}:
            return job_id
    raise FileNotFoundError(f"dataset not found: {candidate}")


def read_json_file(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp_path.write_text(sanitize_saved_text(json.dumps(payload, ensure_ascii=False, indent=2)), encoding="utf-8")
    tmp_path.replace(path)


def dataset_state_path(job_id: str) -> Path:
    return dataset_dir(job_id) / "dataset_state.json"


def convert_task_path(task_id: str) -> Path:
    return CONVERT_TASKS_DIR / f"{safe_path_name(task_id)}.json"


def write_convert_task(task: Dict[str, Any]) -> None:
    task_id = str(task.get("task_id") or "")
    if not task_id:
        return
    CONVERT_TASKS[task_id] = task
    write_json_file(convert_task_path(task_id), task)


def update_convert_task(task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    task = CONVERT_TASKS.get(task_id) or read_json_file(convert_task_path(task_id), {})
    if not isinstance(task, dict) or not task:
        task = {"task_id": task_id}
    task.update(updates)
    write_convert_task(task)
    return task


def read_convert_task(task_id: str) -> Optional[Dict[str, Any]]:
    task = CONVERT_TASKS.get(task_id)
    if task:
        return task
    task = read_json_file(convert_task_path(task_id), None)
    if not isinstance(task, dict):
        return None
    if task.get("status") == "converting":
        task["status"] = "failed"
        task["message"] = "转换任务已中断"
        task["error"] = "后端服务重启，后台转换线程已停止，请重新发起转换。"
        write_convert_task(task)
    else:
        CONVERT_TASKS[str(task.get("task_id") or task_id)] = task
    return task


def legacy_dataset_state_path(job_id: str) -> Path:
    return legacy_dataset_dir(job_id) / "dataset_state.json"


def default_dataset_state(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    created_at = int(result_path(job_id).stat().st_mtime) if result_path(job_id).exists() else int(time.time())
    return {
        "dataset_id": job_id,
        "annotation_status": "first_annotated" if payload.get("status") == "complete" else "none",
        "convert_status": "none",
        "convert_error": "",
        "converted_formats": [],
        "first_annotated_at": created_at,
        "second_annotated_at": None,
        "updated_at": created_at,
        "convert_records": [],
    }


def read_dataset_state(job_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if payload is None:
        payload = read_job_result(job_id)
    first_annotated_at = int(result_path(job_id).stat().st_mtime) if result_path(job_id).exists() else None
    state = read_json_file(dataset_state_path(job_id), None)
    if not isinstance(state, dict):
        state = read_json_file(legacy_dataset_state_path(job_id), None)
    if not isinstance(state, dict):
        state = default_dataset_state(job_id, payload)
        write_dataset_state(job_id, state)
    state.setdefault("dataset_id", job_id)
    state.setdefault("annotation_status", "first_annotated" if payload.get("status") == "complete" else "none")
    state.setdefault("convert_status", "none")
    state.setdefault("convert_error", "")
    state.setdefault("converted_formats", [])
    state.setdefault("convert_records", [])
    state.setdefault("first_annotated_at", first_annotated_at)
    state.setdefault("second_annotated_at", None)
    state.setdefault("updated_at", int(time.time()))
    if str(payload.get("status") or "").lower() in {"complete", "completed", "done"} and state.get("annotation_status") in {None, "", "none"}:
        # Older dataset_state files may predate explicit annotation stages. A completed layout-analysis result is the first annotation version.
        state["annotation_status"] = "first_annotated"
        state["first_annotated_at"] = state.get("first_annotated_at") or first_annotated_at
        write_dataset_state(job_id, state)
    return state


def write_dataset_state(job_id: str, state: Dict[str, Any]) -> None:
    state["updated_at"] = int(time.time())
    write_json_file(dataset_state_path(job_id), state)


def annotation_file_for(job_id: str, version: str = "latest") -> Optional[Path]:
    if version == "draft":
        path = second_annotation_dir(job_id) / "draft.json"
        if path.is_file():
            return path
        path = legacy_dataset_dir(job_id) / "annotations" / "second_annotation" / "draft.json"
        return path if path.is_file() else None
    if version == "second":
        files = sorted(second_annotation_dir(job_id).glob("annotation_v2_*.json"))
        if not files:
            files = sorted((legacy_dataset_dir(job_id) / "annotations" / "second_annotation").glob("annotation_v2_*.json"))
        return files[-1] if files else None
    first = first_annotation_path(job_id)
    if first.is_file():
        return first
    first = legacy_dataset_dir(job_id) / "annotations" / "first_annotation" / "annotation.json"
    return first if first.is_file() else None


def count_finished_pages(pages: Iterable[Dict[str, Any]]) -> int:
    return sum(1 for page in pages if isinstance(page, dict) and page.get("status") in {"done", "error"})


def write_job_result(job_id: str, payload: Dict[str, Any]) -> None:
    model = result_model_name(payload)
    config = payload.setdefault("config", {})
    if isinstance(config, dict):
        config.setdefault("model_dir", model_dir_name(model))
    path = job_dir_for_model(job_id, model) / "result.json"
    legacy_path = JOBS_DIR / job_id / "result.json"
    if legacy_path.exists() and not path.exists():
        path = legacy_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
