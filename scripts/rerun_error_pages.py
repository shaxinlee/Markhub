#!/usr/bin/env python3
"""Rerun only failed layout-analysis pages in a Markhub first-annotation dataset.

This intentionally reuses Markhub's normal inference, normalization and JSONL
writers so the repaired pages keep the same prompt/config format as the
original dataset.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from features.layout_analysis.prompts_store import resolve_prompt_template  # noqa: E402
from features.layout_analysis.schemas import LLMConfig, PageImage, VisionResizeConfig  # noqa: E402
from features.layout_analysis.service import (  # noqa: E402
    build_heading_context,
    call_layout_llm,
    collect_done_blocks,
    layout_jsonl_path,
    layout_page_from_analysis,
    normalize_blocks,
    qa_jsonl_path,
    qna_entry_from_page,
    resize_page_for_model,
    upsert_jsonl_record,
)
from features.layout_analysis.storage import (  # noqa: E402
    count_finished_pages,
    job_asset_path,
    read_job_result,
    relative_job_url,
    write_job_result,
)
from features.layout_analysis.utils import load_dotenv  # noqa: E402


DEFAULT_DATASET_DIR = Path(
    "/data/pansoft-ai-llm-v2/Markhub/backend/datasets/first_annotations/"
    "distillation_sft_rl_qwen3_5_bf16"
)


def as_int(value: Any, default: int) -> int:
    try:
        return int(str(value))
    except Exception:
        return default


def build_llm_config(state: Dict[str, Any]) -> LLMConfig:
    public = state.get("config") if isinstance(state.get("config"), dict) else {}
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "EMPTY"
    return LLMConfig(
        base_url=str(public.get("base_url") or os.getenv("LLM_BASE_URL") or "http://127.0.0.1:8001/v1"),
        model=str(public.get("model") or os.getenv("LLM_MODEL") or ""),
        api_key=api_key,
        timeout=as_int(public.get("timeout") or os.getenv("LLM_TIMEOUT"), 180),
        max_tokens=as_int(public.get("max_tokens") or os.getenv("LLM_MAX_TOKENS"), 20000),
    )


def build_resize_config(state: Dict[str, Any]) -> VisionResizeConfig:
    resize = state.get("resize") if isinstance(state.get("resize"), dict) else {}
    return VisionResizeConfig(
        width=as_int(resize.get("width") or os.getenv("QWEN_RESIZED_WIDTH"), 1536),
        height=as_int(resize.get("height") or os.getenv("QWEN_RESIZED_HEIGHT"), 2176),
        preset=str(resize.get("preset") or os.getenv("QWEN_RESIZE_PRESET") or "default"),
        factor=as_int(resize.get("factor"), 32),
        image_profile=str(resize.get("image_profile") or os.getenv("QWEN_IMAGE_PROFILE") or "qwen3_6"),
    )


def prompt_template_id(state: Dict[str, Any]) -> str:
    template = state.get("prompt_template")
    if isinstance(template, dict):
        return str(template.get("id") or "")
    return ""


def page_image_from_state(job_dir: Path, page_state: Dict[str, Any]) -> PageImage:
    page_id = as_int(page_state.get("page_id"), 0)
    image_path: Optional[Path] = None
    image_url = str(page_state.get("image_url") or "")
    if image_url.startswith("/jobs/"):
        image_path = job_asset_path(image_url.removeprefix("/jobs/"))
    if not image_path or not image_path.exists():
        candidate = job_dir / "pages" / f"page_{page_id:03d}.png"
        if candidate.exists():
            image_path = candidate
    if not image_path or not image_path.exists():
        raise FileNotFoundError(f"page image not found: job={job_dir.name} page={page_id}")
    if not image_url:
        image_url = relative_job_url(image_path)
    return PageImage(
        page_id=page_id,
        width=as_int(page_state.get("width"), 0),
        height=as_int(page_state.get("height"), 0),
        image_path=image_path,
        image_url=image_url,
    )


def prior_done_blocks(state: Dict[str, Any], before_page_id: int) -> List[Dict[str, Any]]:
    prior: List[Dict[str, Any]] = []
    for page in sorted(state.get("pages", []), key=lambda item: as_int(item.get("page_id"), 0)):
        if not isinstance(page, dict):
            continue
        page_id = as_int(page.get("page_id"), 0)
        if page_id >= before_page_id:
            break
        if page.get("status") == "done" and isinstance(page.get("blocks"), list):
            prior.extend(block for block in page["blocks"] if isinstance(block, dict))
    return prior


def clean_page_errors(errors: Iterable[Any], page_id: int, old_error: Any) -> List[Any]:
    prefix = f"第 {page_id + 1} 页分析失败:"
    cleaned = []
    for item in errors:
        text = str(item)
        if old_error and text == str(old_error):
            continue
        if text.startswith(prefix):
            continue
        cleaned.append(item)
    return cleaned


def error_pages(state: Dict[str, Any], selected_pages: Optional[set[int]] = None) -> List[int]:
    pages: List[int] = []
    for page in state.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = as_int(page.get("page_id"), 0)
        if selected_pages is not None and page_id not in selected_pages:
            continue
        if page.get("status") == "error":
            pages.append(page_id)
    return pages


def iter_job_result_files(dataset_dir: Path, selected_jobs: Optional[set[str]] = None) -> Iterable[Path]:
    for result_file in sorted(dataset_dir.glob("*/result.json")):
        if selected_jobs is not None and result_file.parent.name not in selected_jobs:
            continue
        yield result_file


def rerun_page(job_dir: Path, job_id: str, page_id: int, dry_run: bool = False) -> Tuple[str, str]:
    state = read_job_result(job_id)
    pages = state.get("pages", [])
    if page_id < 0 or page_id >= len(pages) or not isinstance(pages[page_id], dict):
        raise IndexError(f"invalid page_id: {page_id}")
    page_state = pages[page_id]

    llm_config = build_llm_config(state)
    resize_config = build_resize_config(state)
    prompt_template = resolve_prompt_template(prompt_template_id(state))
    page = page_image_from_state(job_dir, page_state)
    prior_blocks = prior_done_blocks(state, page_id)
    heading_context = build_heading_context(prior_blocks)

    if dry_run:
        return ("dry-run", f"{job_id} p{page_id + 1}")

    state["pages"][page_id]["status"] = "processing"
    write_job_result(job_id, state)

    model_page = None
    try:
        model_page = resize_page_for_model(page, job_dir=job_dir, config=resize_config)
        payload, model_input, model_response = call_layout_llm(
            model_page,
            original_page=page,
            config=llm_config,
            prompt_template=prompt_template,
            heading_context=heading_context,
            image_profile=resize_config.image_profile,
        )
        blocks, block_warnings = normalize_blocks(
            payload,
            model_page=model_page,
            original_page=page,
            prior_blocks=prior_blocks,
            image_profile=resize_config.image_profile,
        )
        layout_page = layout_page_from_analysis(page, model_page, blocks, job_dir)
        upsert_jsonl_record(
            qa_jsonl_path(job_id),
            qna_entry_from_page(page_id, layout_page["model_image_path"], model_input, model_response),
        )
        upsert_jsonl_record(layout_jsonl_path(job_id), layout_page)

        state = read_job_result(job_id)
        old_error = state["pages"][page_id].get("error")
        state["pages"][page_id].update(
            {
                "status": "done",
                "blocks": layout_page["blocks"],
                "raw": payload,
                "model_input": model_input,
                "model_image_url": layout_page["model_image_url"],
                "model_width": layout_page["model_width"],
                "model_height": layout_page["model_height"],
                "model_content_bbox": layout_page["model_content_bbox"],
            }
        )
        state["pages"][page_id].pop("error", None)
        state["result"]["blocks"] = collect_done_blocks(state["pages"])
        state["warnings"].extend(block_warnings)
        state["errors"] = clean_page_errors(state.get("errors", []), page_id, old_error)
        state["completed_pages"] = count_finished_pages(state["pages"])
        if not any(isinstance(p, dict) and p.get("status") == "error" for p in state.get("pages", [])):
            state["status"] = "complete"
        write_job_result(job_id, state)
        return ("done", f"{job_id} p{page_id + 1} blocks={len(blocks)}")
    except Exception as exc:
        err = f"第 {page_id + 1} 页分析失败: {type(exc).__name__}: {exc}"
        state = read_job_result(job_id)
        old_error = state["pages"][page_id].get("error")
        update = {"status": "error", "blocks": [], "raw": None, "error": err}
        if model_page is not None:
            update.update(
                {
                    "model_image_url": model_page.image_url,
                    "model_width": model_page.width,
                    "model_height": model_page.height,
                    "model_content_bbox": [
                        model_page.content_x,
                        model_page.content_y,
                        model_page.content_x + model_page.content_width,
                        model_page.content_y + model_page.content_height,
                    ],
                }
            )
        state["pages"][page_id].update(update)
        state["errors"] = clean_page_errors(state.get("errors", []), page_id, old_error)
        state["errors"].append(err)
        state["completed_pages"] = count_finished_pages(state["pages"])
        state["result"]["blocks"] = collect_done_blocks(state["pages"])
        write_job_result(job_id, state)
        return ("error", f"{job_id} p{page_id + 1}: {err}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--job-id", action="append", help="Only rerun selected job id; repeatable.")
    parser.add_argument("--page-id", action="append", type=int, help="Only rerun selected 0-based page id; repeatable.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    dataset_dir = args.dataset_dir
    selected_jobs = set(args.job_id) if args.job_id else None
    selected_pages = set(args.page_id) if args.page_id else None

    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"dataset dir not found: {dataset_dir}")

    planned: List[Tuple[Path, str, int]] = []
    for result_file in iter_job_result_files(dataset_dir, selected_jobs):
        job_id = result_file.parent.name
        state = read_job_result(job_id)
        for page_id in error_pages(state, selected_pages):
            planned.append((result_file.parent, job_id, page_id))

    print(f"dataset={dataset_dir}")
    print(f"planned_error_pages={len(planned)}")
    for job_dir, job_id, page_id in planned:
        print(f"RUN {job_id} page_id={page_id} page_no={page_id + 1} file={job_dir.name}")

    done = 0
    failed = 0
    for job_dir, job_id, page_id in planned:
        status, message = rerun_page(job_dir, job_id, page_id, dry_run=args.dry_run)
        print(f"{status.upper()} {message}", flush=True)
        if status == "done":
            done += 1
        elif status == "error":
            failed += 1

    print(f"summary planned={len(planned)} done={done} failed={failed} dry_run={args.dry_run}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
