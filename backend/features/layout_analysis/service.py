"""Business logic for layout analysis: PDF rendering, model calls, dataset
management, second-annotation editing, and dataset → training conversion.

This module imports ``storage`` for persistence primitives but never the other
way around. ``server.py`` re-exports the public callables from here for
backwards compatibility with existing handler dispatch.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fitz  # type: ignore
from PIL import Image
from openai import OpenAI

from .schemas import (
    BLOCK_TYPES,
    DATASET_LABEL_TYPES,
    LEVELS,
    LLMConfig,
    ModelPageImage,
    PageImage,
    PromptTemplate,
    VisionResizeConfig,
)
from .paths import LLAMAFACTORY_DATASETS_DIR, SWIFT_DATASETS_DIR
from .storage import (
    annotation_file_for,
    clean_old_jobs,
    count_finished_pages,
    ensure_dataset_storage,  # noqa: F401 — re-exported for legacy callers
    find_job_dir,
    first_annotation_path,
    iso_now,
    job_asset_path,
    job_dir_for_model,
    job_storage_roots,
    model_dir_name,
    now_timestamp,
    public_llm_config,
    public_resize_config,
    read_convert_task,
    read_dataset_state,
    read_job_result,
    read_json_file,
    relative_job_url,
    resolve_dataset_job_id,
    result_model_name,
    result_path,
    second_annotation_dir,
    update_convert_task,
    write_convert_task,
    write_dataset_state,
    write_job_result,
    write_json_file,
)
from .utils import (
    max_pdf_bytes,
    normalize_block_type,
    portable_path_ref,
    safe_path_name,
    sanitize_saved_text,
)


DEFAULT_SWIFT_USER_PROMPT = "<image>\n请识别图片中的所有主要版面块，并按照阅读顺序输出严格合法的 JSON。"
DEFAULT_LLAMAFACTORY_INSTRUCTION = "<image>\n请识别图片中的所有主要版面块，并按照阅读顺序输出严格合法的 JSON。"


# --------------------------------------------------------------------------
# PDF rendering and model invocation
# --------------------------------------------------------------------------

def render_pdf_to_images(pdf_path: Path, job_id: str, job_dir: Path, dpi: int, max_pages: int) -> List[PageImage]:
    images_dir = job_dir / "pages"
    images_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    pages: List[PageImage] = []
    try:
        page_count = min(len(doc), max_pages)
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        for page_id in range(page_count):
            page = doc.load_page(page_id)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out_path = images_dir / f"page_{page_id:03d}.png"
            pix.save(str(out_path))
            pages.append(
                PageImage(
                    page_id=page_id,
                    width=int(pix.width),
                    height=int(pix.height),
                    image_path=out_path,
                    image_url=relative_job_url(out_path),
                )
            )
    finally:
        doc.close()
    return pages


def dimensions_for_page(page: PageImage, config: VisionResizeConfig) -> Tuple[int, int]:
    width, height = config.width, config.height
    if page.width > page.height and height > width:
        width, height = height, width
    return width, height


def resize_page_for_model(page: PageImage, job_dir: Path, config: VisionResizeConfig) -> ModelPageImage:
    target_w, target_h = dimensions_for_page(page, config)
    model_dir = job_dir / "model_pages"
    model_dir.mkdir(parents=True, exist_ok=True)
    out_path = model_dir / f"page_{page.page_id:03d}_qwen.png"

    with Image.open(page.image_path) as image:
        image = image.convert("RGB")
        scale = min(target_w / page.width, target_h / page.height)
        content_w = max(1, int(round(page.width * scale)))
        content_h = max(1, int(round(page.height * scale)))
        content_x = (target_w - content_w) // 2
        content_y = (target_h - content_h) // 2
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        resized = image.resize((content_w, content_h), resampling)
        canvas = Image.new("RGB", (target_w, target_h), "white")
        canvas.paste(resized, (content_x, content_y))
        canvas.save(out_path, format="PNG")

    return ModelPageImage(
        page_id=page.page_id,
        width=target_w,
        height=target_h,
        image_path=out_path,
        image_url=relative_job_url(out_path),
        content_x=content_x,
        content_y=content_y,
        content_width=content_w,
        content_height=content_h,
        original_width=page.width,
        original_height=page.height,
    )


def image_to_data_url(image_path: Path) -> str:
    raw = image_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def call_layout_llm(model_page: ModelPageImage, original_page: PageImage, config: LLMConfig, prompt_template: PromptTemplate) -> Dict[str, Any]:
    client = OpenAI(api_key=config.api_key or "EMPTY", base_url=config.base_url)
    user_text = (
        f"当前页面 page_id={model_page.page_id}。你看到的是标准检查图，尺寸为 "
        f"{model_page.width}x{model_page.height} 像素。"
        "请严格输出 0-1000 相对坐标 bbox，不要输出像素坐标。"
        "页面内容可能在白色标准画布中等比居中，请只框文档内容区域内的版面块。"
    )
    image_item = {
        "type": "image_url",
        "image_url": {"url": image_to_data_url(model_page.image_path)},
        "resized_width": model_page.width,
        "resized_height": model_page.height,
        "min_pixels": model_page.width * model_page.height,
        "max_pixels": model_page.width * model_page.height,
    }
    completion = client.chat.completions.create(
        model=config.model,
        temperature=0,
        messages=[
            {"role": "system", "content": prompt_template.prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    image_item,
                ],
            },
        ],
        timeout=config.timeout,
        extra_body={"enable_thinking": False},
    )
    content = completion.choices[0].message.content if completion.choices else ""
    return parse_model_json(content or "")


def parse_model_json(content: str) -> Dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = json.loads(extract_first_json_object(cleaned), strict=False)

    if not isinstance(payload, dict):
        raise ValueError("model response is not a JSON object")
    return payload


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("model response does not contain JSON")
    depth = 0
    in_str = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("model response has an incomplete JSON object")


# --------------------------------------------------------------------------
# Block / bbox normalization
# --------------------------------------------------------------------------

def normalize_blocks(payload: Dict[str, Any], model_page: ModelPageImage, original_page: PageImage) -> Tuple[List[Dict[str, Any]], List[str]]:
    raw_blocks = payload.get("blocks", [])
    warnings: List[str] = []
    if not isinstance(raw_blocks, list):
        return [], ["模型返回的 blocks 不是数组"]

    blocks: List[Dict[str, Any]] = []
    for raw_index, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            warnings.append(f"page {original_page.page_id} block {raw_index}: 不是对象，已跳过")
            continue

        block_type = normalize_block_type(raw.get("block_type"), "")
        if block_type not in BLOCK_TYPES:
            warnings.append(f"page {original_page.page_id} block {raw_index}: 非法 block_type={block_type!r}，已跳过")
            continue

        bbox_1000 = normalize_qwen_bbox(raw.get("bbox") if raw.get("bbox") is not None else raw.get("bbox_2d"))
        if bbox_1000 is None:
            warnings.append(f"page {original_page.page_id} block {raw_index}: bbox 无效，已跳过")
            continue
        model_bbox = qwen_bbox_to_model_pixels(bbox_1000, model_page)
        bbox = scale_bbox(model_bbox, model_page, original_page)

        text = "" if raw.get("text") is None else str(raw.get("text"))
        level = normalize_heading_level(raw.get("level"), block_type, text)

        block_no = len(blocks)
        blocks.append(
            {
                "id": f"p{original_page.page_id:03d}_b{block_no:03d}",
                "text": text,
                "bbox": bbox,
                "bbox_1000": bbox_1000,
                "model_bbox": model_bbox,
                "page_id": original_page.page_id,
                "block_type": block_type,
                "weak_heading": bool(raw.get("weak_heading", False)),
                "level": level,
            }
        )

    blocks.sort(key=lambda b: (b["page_id"], b["bbox"][1], b["bbox"][0]))
    return blocks, warnings


def normalize_qwen_bbox(value: Any) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in value]
    except Exception:
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    x1 = max(0, min(1000, int(round(x1))))
    x2 = max(0, min(1000, int(round(x2))))
    y1 = max(0, min(1000, int(round(y1))))
    y2 = max(0, min(1000, int(round(y2))))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def normalize_heading_level(level: Any, block_type: str, text: str) -> Optional[str]:
    if block_type == "doc_title":
        return "H1"
    if block_type != "paragraph_title":
        return None
    if level in LEVELS:
        return str(level)
    return infer_heading_level(text)


def infer_heading_level(text: str) -> Optional[str]:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return None
    if re.match(r"^第[一二三四五六七八九十百\d]+[章节]", compact):
        return "H1"
    if re.match(r"^[一二三四五六七八九十]+[、.．]", compact):
        return "H1"
    if re.match(r"^\d+[、.．]", compact):
        if re.match(r"^\d+[.．]\d+", compact):
            return "H3"
        return "H2"
    if re.match(r"^（[一二三四五六七八九十\d]+）", compact):
        return "H3"
    if re.match(r"^\([一二三四五六七八九十\d]+\)", compact):
        return "H3"
    if re.match(r"^\d+[）)]", compact):
        return "H3"
    return None


def qwen_bbox_to_model_pixels(bbox_1000: List[int], model_page: ModelPageImage) -> List[int]:
    x1, y1, x2, y2 = bbox_1000
    return normalize_bbox(
        [
            x1 / 1000 * model_page.width,
            y1 / 1000 * model_page.height,
            x2 / 1000 * model_page.width,
            y2 / 1000 * model_page.height,
        ],
        model_page.width,
        model_page.height,
    ) or [0, 0, model_page.width, model_page.height]


def normalize_bbox(value: Any, width: int, height: int) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in value]
    except Exception:
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    x1 = max(0, min(width, int(round(x1))))
    x2 = max(0, min(width, int(round(x2))))
    y1 = max(0, min(height, int(round(y1))))
    y2 = max(0, min(height, int(round(y2))))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def scale_bbox(bbox: List[int], model_page: ModelPageImage, original_page: PageImage) -> List[int]:
    x1, y1, x2, y2 = bbox
    content_x2 = model_page.content_x + model_page.content_width
    content_y2 = model_page.content_y + model_page.content_height
    x1 = max(model_page.content_x, min(content_x2, x1))
    x2 = max(model_page.content_x, min(content_x2, x2))
    y1 = max(model_page.content_y, min(content_y2, y1))
    y2 = max(model_page.content_y, min(content_y2, y2))
    if x2 <= x1 or y2 <= y1:
        return [0, 0, original_page.width, original_page.height]
    sx = original_page.width / max(model_page.content_width, 1)
    sy = original_page.height / max(model_page.content_height, 1)
    return normalize_bbox(
        [
            (x1 - model_page.content_x) * sx,
            (y1 - model_page.content_y) * sy,
            (x2 - model_page.content_x) * sx,
            (y2 - model_page.content_y) * sy,
        ],
        original_page.width,
        original_page.height,
    ) or [0, 0, original_page.width, original_page.height]


# --------------------------------------------------------------------------
# Analysis job lifecycle
# --------------------------------------------------------------------------

def start_analysis_job(
    file_bytes: bytes,
    filename: str,
    dpi: int,
    max_pages: int,
    llm_config: LLMConfig,
    resize_config: VisionResizeConfig,
    prompt_template: PromptTemplate,
) -> Dict[str, Any]:
    clean_old_jobs()
    limit = max_pdf_bytes()
    if len(file_bytes) > limit:
        raise ValueError(f"PDF 文件过大：{len(file_bytes)} bytes，当前上限 {limit} bytes。可通过 LAYOUT_MAX_PDF_BYTES 调整。")
    job_id = uuid.uuid4().hex[:12]
    job_dir = job_dir_for_model(job_id, llm_config.model)
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename or "uploaded.pdf").name
    pdf_path = job_dir / safe_name
    pdf_path.write_bytes(file_bytes)

    pages = render_pdf_to_images(pdf_path, job_id=job_id, job_dir=job_dir, dpi=dpi, max_pages=max_pages)
    result = {
        "job_id": job_id,
        "filename": safe_name,
        "status": "running",
        "page_count": len(pages),
        "completed_pages": 0,
        "pages": [
            {
                "page_id": page.page_id,
                "image_url": page.image_url,
                "width": page.width,
                "height": page.height,
                "blocks": [],
                "raw": None,
                "status": "pending",
            }
            for page in pages
        ],
        "result": {
            "image_path": "",
            "blocks": [],
            "context_before": "",
            "context_after": "",
        },
        "warnings": [],
        "errors": [],
        "config": public_llm_config(llm_config),
        "resize": public_resize_config(resize_config),
        "prompt_template": {
            "id": prompt_template.template_id,
            "name": prompt_template.name,
            "category": prompt_template.category,
        },
    }
    result["config"]["model_dir"] = model_dir_name(llm_config.model)
    write_job_result(job_id, result)

    worker = threading.Thread(
        target=process_job_pages,
        args=(job_id, pages, llm_config, resize_config, prompt_template),
        daemon=True,
    )
    worker.start()
    return result


def process_job_pages(
    job_id: str,
    pages: List[PageImage],
    llm_config: LLMConfig,
    resize_config: VisionResizeConfig,
    prompt_template: PromptTemplate,
) -> None:
    for page in pages:
        state = read_job_result(job_id)
        state["pages"][page.page_id]["status"] = "processing"
        write_job_result(job_id, state)

        model_page: Optional[ModelPageImage] = None
        try:
            model_page = resize_page_for_model(page, job_dir=find_job_dir(job_id), config=resize_config)
            payload = call_layout_llm(model_page, original_page=page, config=llm_config, prompt_template=prompt_template)
            blocks, block_warnings = normalize_blocks(payload, model_page=model_page, original_page=page)

            state = read_job_result(job_id)
            state["pages"][page.page_id].update(
                {
                    "status": "done",
                    "blocks": blocks,
                    "raw": payload,
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
            state["result"]["blocks"] = collect_done_blocks(state["pages"])
            state["warnings"].extend(block_warnings)
            state["completed_pages"] = count_finished_pages(state["pages"])
            write_job_result(job_id, state)
        except Exception as exc:
            err = f"第 {page.page_id + 1} 页分析失败: {type(exc).__name__}: {exc}"
            state = read_job_result(job_id)
            page_update = {"status": "error", "blocks": [], "raw": None, "error": err}
            if model_page is not None:
                page_update.update(
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
            state["pages"][page.page_id].update(page_update)
            state["errors"].append(err)
            state["completed_pages"] = count_finished_pages(state["pages"])
            write_job_result(job_id, state)

    state = read_job_result(job_id)
    state["status"] = "complete"
    state["completed_pages"] = count_finished_pages(state["pages"])
    state["result"]["blocks"] = collect_done_blocks(state["pages"])
    write_job_result(job_id, state)


def collect_done_blocks(pages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for page in pages:
        if isinstance(page.get("blocks"), list):
            blocks.extend(page["blocks"])
    def sort_key(block: Dict[str, Any]) -> Tuple[int, int, int]:
        bbox = block.get("bbox")
        if not isinstance(bbox, list) or len(bbox) < 2:
            bbox = [0, 0]
        return int(block.get("page_id", 0)), int(bbox[1]), int(bbox[0])
    blocks.sort(key=sort_key)
    return blocks


# --------------------------------------------------------------------------
# Dataset management
# --------------------------------------------------------------------------

def delete_dataset(job_id: str) -> Dict[str, Any]:
    resolved_job_id = resolve_dataset_job_id(job_id)
    job_dir = find_job_dir(resolved_job_id).resolve()
    if not any(str(job_dir).startswith(str(root.resolve())) for root in job_storage_roots()) or not job_dir.is_dir():
        raise FileNotFoundError(f"dataset not found: {job_id}")
    shutil.rmtree(job_dir)
    shutil.rmtree(second_annotation_dir(resolved_job_id), ignore_errors=True)
    return {"dataset_id": resolved_job_id, "deleted": True}


def delete_datasets(body: Dict[str, Any]) -> Dict[str, Any]:
    delete_all = bool(body.get("delete_all", False))
    dataset_ids = body.get("dataset_ids")
    if delete_all:
        ids = [str(item.get("dataset_id") or item.get("job_id")) for item in list_dataset_summaries()]
    elif isinstance(dataset_ids, list):
        ids = [str(item) for item in dataset_ids if str(item).strip()]
    else:
        raise ValueError("missing dataset_ids")
    if not ids:
        return {"deleted": [], "failed": [], "count": 0}

    deleted: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for dataset_id in ids:
        try:
            deleted.append(delete_dataset(dataset_id))
        except Exception as exc:
            failed.append({"dataset_id": dataset_id, "error": f"{type(exc).__name__}: {exc}"})
    return {"deleted": deleted, "failed": failed, "count": len(deleted)}


def dataset_summary(job_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if payload is None:
        payload = read_job_result(job_id)
    state = read_dataset_state(job_id, payload)
    pages = payload.get("pages", [])
    blocks = payload.get("result", {}).get("blocks", [])
    first_page_url = ""
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        first_page_url = str(pages[0].get("image_url") or "")
    return {
        "dataset_id": job_id,
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
        "updated_at": max(int(result_path(job_id).stat().st_mtime) if result_path(job_id).exists() else 0, int(state.get("updated_at") or 0)),
        "annotation_status": state.get("annotation_status", "none"),
        "convert_status": state.get("convert_status", "none"),
        "convert_error": state.get("convert_error", ""),
        "converted_formats": state.get("converted_formats", []),
        "first_annotated_at": state.get("first_annotated_at"),
        "second_annotated_at": state.get("second_annotated_at"),
        "last_convert_record": (state.get("convert_records") or [None])[-1],
    }


def list_dataset_summaries() -> List[Dict[str, Any]]:
    from .storage import list_job_summaries

    items: List[Dict[str, Any]] = []
    for job in list_job_summaries():
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        try:
            payload = read_job_result(job_id)
            state = read_dataset_state(job_id, payload)
            job.update(
                {
                    "dataset_id": job_id,
                    "annotation_status": state.get("annotation_status", "none"),
                    "convert_status": state.get("convert_status", "none"),
                    "convert_error": state.get("convert_error", ""),
                    "converted_formats": state.get("converted_formats", []),
                    "first_annotated_at": state.get("first_annotated_at"),
                    "second_annotated_at": state.get("second_annotated_at"),
                    "last_convert_record": (state.get("convert_records") or [None])[-1],
                }
            )
        except Exception as exc:
            job.update(
                {
                    "dataset_id": job_id,
                    "annotation_status": "first_annotated" if job.get("status") == "complete" else "none",
                    "convert_status": "none",
                    "convert_error": f"{type(exc).__name__}: {exc}",
                    "converted_formats": [],
                    "first_annotated_at": job.get("updated_at"),
                    "second_annotated_at": None,
                    "last_convert_record": None,
                }
            )
        items.append(job)
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items


# --------------------------------------------------------------------------
# Second-annotation editor
# --------------------------------------------------------------------------

def ensure_first_annotation(job_id: str, payload: Optional[Dict[str, Any]] = None) -> Path:
    if payload is None:
        payload = read_job_result(job_id)
    target = first_annotation_path(job_id)
    if not target.is_file():
        write_json_file(target, build_annotation_payload(job_id, payload, "first_annotation"))
    return target


def build_annotation_payload(job_id: str, payload: Dict[str, Any], version: str, blocks_by_page: Optional[Dict[int, List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    pages_out: List[Dict[str, Any]] = []
    for page in payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = int(page.get("page_id") or 0)
        raw_blocks = blocks_by_page.get(page_id, []) if blocks_by_page is not None else page.get("blocks", [])
        pages_out.append(
            {
                "page_id": page_id,
                "image_url": page.get("image_url", ""),
                "width": page.get("width", 0),
                "height": page.get("height", 0),
                "blocks": [normalize_annotation_block(block, page_id) for block in raw_blocks if isinstance(block, dict)],
            }
        )
    return {
        "dataset_id": job_id,
        "job_id": job_id,
        "filename": payload.get("filename") or "",
        "version": version,
        "updated_at": iso_now(),
        "label_types": sorted(DATASET_LABEL_TYPES),
        "pages": pages_out,
    }


def normalize_annotation_block(block: Dict[str, Any], page_id: int) -> Dict[str, Any]:
    label = normalize_block_type(block.get("label") or block.get("block_type") or block.get("type"), "text")
    if label not in DATASET_LABEL_TYPES:
        label = "other"
    source = str(block.get("source") or "model")
    modified_fields = block.get("modified_fields")
    if not isinstance(modified_fields, list):
        modified_fields = []
    bbox = block.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        bbox = [0, 0, 1, 1]
    return {
        "id": str(block.get("id") or f"p{page_id:03d}_b{uuid.uuid4().hex[:8]}"),
        "bbox": [int(float(v)) for v in bbox],
        "label": label,
        "block_type": label,
        "text": str(block.get("text") or ""),
        "page_id": int(block.get("page_id") if block.get("page_id") is not None else page_id),
        "source": source,
        "modified": bool(block.get("modified", source == "manual")),
        "modified_fields": modified_fields,
        "updated_at": block.get("updated_at") or iso_now(),
        "updated_by": block.get("updated_by") or "",
        "weak_heading": bool(block.get("weak_heading", block.get("weakHeading", False))),
        "level": block.get("level") if block.get("level") in {"H1", "H2", "H3"} else None,
    }


def read_annotation_payload(job_id: str) -> Dict[str, Any]:
    job_id = resolve_dataset_job_id(job_id)
    payload = read_job_result(job_id)
    ensure_first_annotation(job_id, payload)
    second = annotation_file_for(job_id, "second")
    draft = annotation_file_for(job_id, "draft")
    source = draft or second or annotation_file_for(job_id, "first")
    annotation = read_json_file(source, {}) if source else {}
    if not isinstance(annotation, dict) or not annotation.get("pages"):
        annotation = build_annotation_payload(job_id, payload, "first_annotation")
    state = read_dataset_state(job_id, payload)
    annotation["state"] = state
    annotation["label_types"] = sorted(DATASET_LABEL_TYPES)
    annotation["active_version"] = "draft" if draft else "second_annotation" if second else "first_annotation"
    return annotation


def save_second_annotation(job_id: str, body: Dict[str, Any], mode: str) -> Dict[str, Any]:
    job_id = resolve_dataset_job_id(job_id)
    payload = read_job_result(job_id)
    pages = body.get("pages")
    if not isinstance(pages, list):
        raise ValueError("missing pages")
    blocks_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = int(page.get("page_id") or 0)
        blocks_by_page[page_id] = [normalize_annotation_block(block, page_id) for block in page.get("blocks", []) if isinstance(block, dict)]

    annotation = build_annotation_payload(job_id, payload, "second_annotation", blocks_by_page)
    annotation["updated_at"] = iso_now()
    if mode == "draft":
        target = second_annotation_dir(job_id) / "draft.json"
        state = read_dataset_state(job_id, payload)
        state["annotation_status"] = "second_annotating"
        write_dataset_state(job_id, state)
    elif mode == "overwrite":
        target = first_annotation_path(job_id)
        overwrite_job_blocks(job_id, payload, annotation)
        state = read_dataset_state(job_id, payload)
        state["annotation_status"] = "first_annotated"
        write_dataset_state(job_id, state)
    else:
        target = second_annotation_dir(job_id) / f"annotation_v2_{now_timestamp()}.json"
        state = read_dataset_state(job_id, payload)
        state["annotation_status"] = "second_annotated"
        state["second_annotated_at"] = int(time.time())
        write_dataset_state(job_id, state)
    write_json_file(target, annotation)
    return {"ok": True, "dataset_id": job_id, "path": str(target), "state": read_dataset_state(job_id, payload)}


def overwrite_job_blocks(job_id: str, payload: Dict[str, Any], annotation: Dict[str, Any]) -> None:
    blocks: List[Dict[str, Any]] = []
    pages_by_id = {int(page.get("page_id") or 0): page for page in annotation.get("pages", []) if isinstance(page, dict)}
    for page in payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = int(page.get("page_id") or 0)
        next_page = pages_by_id.get(page_id)
        if not next_page:
            continue
        page_blocks = [job_block_from_annotation(block) for block in next_page.get("blocks", []) if isinstance(block, dict)]
        page["blocks"] = page_blocks
        blocks.extend(page_blocks)
    payload.setdefault("result", {})["blocks"] = blocks
    write_job_result(job_id, payload)


def job_block_from_annotation(block: Dict[str, Any]) -> Dict[str, Any]:
    label = normalize_block_type(block.get("label") or block.get("block_type"), "text")
    return {
        "id": block.get("id"),
        "text": block.get("text", ""),
        "bbox": block.get("bbox", [0, 0, 1, 1]),
        "page_id": block.get("page_id", 0),
        "block_type": label if label in BLOCK_TYPES else "text",
        "weak_heading": bool(block.get("weak_heading", False)),
        "level": block.get("level") if block.get("level") in {"H1", "H2", "H3"} else None,
    }


# --------------------------------------------------------------------------
# Dataset → training format conversion
# --------------------------------------------------------------------------

def start_convert_task(body: Dict[str, Any]) -> Dict[str, Any]:
    dataset_ids = body.get("dataset_ids")
    if not isinstance(dataset_ids, list) or not dataset_ids:
        raise ValueError("missing dataset_ids")
    target_format = str(body.get("target_format") or "").strip()
    if target_format not in {"llamafactory", "swift"}:
        raise ValueError("target_format must be llamafactory or swift")
    merge = bool(body.get("merge", False))
    split_type = str(body.get("split_type") or "train")
    if split_type not in {"train", "val", "test", "all"}:
        raise ValueError("split_type must be train, val, test, or all")
    output_name = safe_path_name(str(body.get("output_name") or default_convert_output_name(target_format, merge)))
    overwrite = bool(body.get("overwrite", False))

    resolved_dataset_ids = [resolve_dataset_job_id(str(dataset_id)) for dataset_id in dataset_ids]

    for dataset_id in resolved_dataset_ids:
        payload = read_job_result(str(dataset_id))
        if payload.get("status") != "complete":
            raise ValueError(f"dataset {dataset_id} is not ready: {payload.get('status')}")
        state = read_dataset_state(str(dataset_id), payload)
        if state.get("annotation_status") not in {"first_annotated", "second_annotated"}:
            raise ValueError(f"dataset {dataset_id} annotation_status is {state.get('annotation_status')}")

    task_id = uuid.uuid4().hex[:12]
    task = {
        "task_id": task_id,
        "status": "converting",
        "target_format": target_format,
        "dataset_ids": resolved_dataset_ids,
        "output_path": "",
        "message": "转换任务已创建",
        "error": "",
        "skipped_samples": 0,
        "created_at": iso_now(),
    }
    write_convert_task(task)
    for dataset_id in resolved_dataset_ids:
        state = read_dataset_state(str(dataset_id))
        state["convert_status"] = "converting"
        state["convert_error"] = ""
        write_dataset_state(str(dataset_id), state)

    worker = threading.Thread(
        target=run_convert_task,
        args=(task_id, resolved_dataset_ids, target_format, merge, split_type, output_name, overwrite),
        daemon=True,
    )
    worker.start()
    return task


def default_convert_output_name(target_format: str, merge: bool) -> str:
    prefix = "merged_" if merge else ""
    middle = "swift" if target_format == "swift" else "llamafactory"
    return f"{prefix}{middle}_{now_timestamp()}"


def run_convert_task(task_id: str, dataset_ids: List[str], target_format: str, merge: bool, split_type: str, output_name: str, overwrite: bool) -> None:
    task = read_convert_task(task_id) or {"task_id": task_id}
    logs: List[str] = []
    output_dir: Optional[Path] = None
    skipped = 0
    try:
        output_dir = resolve_convert_output_dir(dataset_ids, target_format, merge, output_name)
        if output_dir.exists() and not overwrite:
            raise FileExistsError(f"输出路径已存在: {portable_path_ref(output_dir)}")
        if output_dir.exists() and overwrite:
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        samples: List[Dict[str, Any]] = []
        for dataset_id in dataset_ids:
            try:
                payload = read_job_result(dataset_id)
                ensure_first_annotation(dataset_id, payload)
                annotation = read_annotation_payload(dataset_id)
                dataset_samples, dataset_skipped = samples_from_annotation(dataset_id, payload, annotation, target_format, output_dir)
                logs.append(f"{dataset_id}: converted {len(dataset_samples)} samples, skipped {dataset_skipped}")
                samples.extend(dataset_samples)
                skipped += dataset_skipped
            except Exception as exc:
                logs.append(f"{dataset_id}: failed: {type(exc).__name__}: {exc}")
                skipped += 1

        if not samples:
            raise ValueError("没有可转换样本")

        split_files = write_split_files(output_dir, samples, split_type)
        write_dataset_info(output_dir, target_format, split_files)
        config = {
            "source_datasets": dataset_ids,
            "target_format": target_format,
            "merge": merge,
            "split_type": split_type,
            "created_at": iso_now(),
            "operator": "",
            "output_path": portable_path_ref(output_dir),
            "script_version": "markhub-converter-v2",
        }
        write_json_file(output_dir / "convert_config.json", config)
        log_text = "\n".join(logs) + f"\nskipped_samples={skipped}\n"
        if target_format == "swift":
            usage_note = (
                "\nms-swift usage note:\n"
                "  cd <converted_dataset_dir>\n"
                "  export ROOT_IMAGE_DIR=$PWD\n"
                "  swift sft --dataset train.jsonl\n"
                "The images field uses paths relative to this converted dataset directory.\n"
            )
            log_text += usage_note
            (output_dir / "README_ms_swift.txt").write_text(sanitize_saved_text(usage_note), encoding="utf-8")
        (output_dir / "convert_log.txt").write_text(sanitize_saved_text(log_text), encoding="utf-8")

        status = "partial_success" if skipped else "success"
        task = update_convert_task(task_id, {"status": status, "output_path": portable_path_ref(output_dir), "message": "转换完成", "error": "", "skipped_samples": skipped})
        for dataset_id in dataset_ids:
            state = read_dataset_state(dataset_id)
            state["convert_status"] = status
            state["convert_error"] = ""
            formats = set(state.get("converted_formats") or [])
            formats.add(target_format)
            state["converted_formats"] = sorted(formats)
            state.setdefault("convert_records", []).append(
                {
                    "task_id": task_id,
                    "target_format": target_format,
                    "status": status,
                    "output_path": portable_path_ref(output_dir),
                    "created_at": config["created_at"],
                    "skipped_samples": skipped,
                }
            )
            write_dataset_state(dataset_id, state)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        update_convert_task(task_id, {"status": "failed", "error": error, "message": "转换失败", "output_path": portable_path_ref(output_dir), "skipped_samples": skipped})
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "convert_log.txt").write_text(sanitize_saved_text("\n".join(logs + [error])), encoding="utf-8")
        for dataset_id in dataset_ids:
            try:
                state = read_dataset_state(dataset_id)
                state["convert_status"] = "failed"
                state["convert_error"] = error
                state.setdefault("convert_records", []).append(
                    {
                        "task_id": task_id,
                        "target_format": target_format,
                        "status": "failed",
                        "output_path": portable_path_ref(output_dir),
                        "created_at": iso_now(),
                        "error": error,
                        "skipped_samples": skipped,
                    }
                )
                write_dataset_state(dataset_id, state)
            except Exception:
                pass


def resolve_convert_output_dir(dataset_ids: List[str], target_format: str, merge: bool, output_name: str) -> Path:
    root = SWIFT_DATASETS_DIR if target_format == "swift" else LLAMAFACTORY_DATASETS_DIR
    return root / safe_path_name(output_name)


def samples_from_annotation(dataset_id: str, payload: Dict[str, Any], annotation: Dict[str, Any], target_format: str, output_dir: Path) -> Tuple[List[Dict[str, Any]], int]:
    samples: List[Dict[str, Any]] = []
    skipped = 0
    for page in annotation.get("pages", []):
        try:
            if not isinstance(page, dict):
                skipped += 1
                continue
            blocks = [normalize_export_block(block) for block in page.get("blocks", []) if isinstance(block, dict)]
            if not blocks:
                skipped += 1
                continue
            source_image = image_path_from_page_url(dataset_id, str(page.get("image_url") or ""))
            if not source_image or not source_image.is_file():
                raise FileNotFoundError(f"image not found for page {page.get('page_id')}")
            target_image = output_dir / "images" / safe_path_name(dataset_id) / f"page_{int(page.get('page_id') or 0):03d}.png"
            image_ref = prepare_portable_image_ref(source_image, target_image, output_dir)
            answer = json.dumps({"image_path": image_ref, "blocks": blocks, "context_before": "", "context_after": ""}, ensure_ascii=False, separators=(",", ":"))
            if target_format == "swift":
                samples.append(
                    {
                        "messages": [
                            {"role": "system", "content": "你是一个专业的文档版面分析模型。"},
                            {"role": "user", "content": DEFAULT_SWIFT_USER_PROMPT},
                            {"role": "assistant", "content": answer},
                        ],
                        "images": [image_ref],
                    }
                )
            else:
                samples.append(
                    {
                        "instruction": DEFAULT_LLAMAFACTORY_INSTRUCTION,
                        "input": "",
                        "output": answer,
                        "images": [image_ref],
                    }
                )
        except Exception:
            skipped += 1
    return samples, skipped


def prepare_portable_image_ref(source_image: Path, target_image: Path, output_dir: Path) -> str:
    """Normalize exported images and return a portable training path.

    Vision fine-tuning loaders treat ``images`` as paths/URLs. Absolute local paths
    break after the export folder is moved to a training machine, so JSONL stores
    paths relative to the conversion output directory.
    """
    target_image.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_image) as image:
        image.load()
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(target_image, format="PNG")
    return target_image.relative_to(output_dir).as_posix()


def image_path_from_page_url(dataset_id: str, image_url: str) -> Optional[Path]:
    if image_url.startswith("/jobs/"):
        return job_asset_path(image_url.removeprefix("/jobs/"))
    job_dir = find_job_dir(dataset_id)
    candidate = job_dir / image_url.lstrip("/")
    return candidate if candidate.exists() else None


def normalize_export_block(block: Dict[str, Any]) -> Dict[str, Any]:
    label = normalize_block_type(block.get("label") or block.get("block_type"), "text")
    return {
        "id": str(block.get("id") or ""),
        "text": str(block.get("text") or ""),
        "bbox": block.get("bbox") if isinstance(block.get("bbox"), list) else [0, 0, 1, 1],
        "page_id": int(block.get("page_id") or 0),
        "block_type": label,
        "weak_heading": bool(block.get("weak_heading", False)),
        "level": block.get("level") if block.get("level") in {"H1", "H2", "H3"} else None,
    }


def write_split_files(output_dir: Path, samples: List[Dict[str, Any]], split_type: str) -> List[str]:
    file_names: List[str] = []
    if split_type == "all":
        split_map = {"train.jsonl": samples}
    else:
        split_map = {f"{split_type}.jsonl": samples}
    for file_name, split_samples in split_map.items():
        with (output_dir / file_name).open("w", encoding="utf-8") as f:
            for sample in split_samples:
                f.write(sanitize_saved_text(json.dumps(sample, ensure_ascii=False)) + "\n")
        file_names.append(file_name)
    return file_names


def write_dataset_info(output_dir: Path, target_format: str, split_files: List[str]) -> None:
    info = {
        "format": target_format,
        "files": split_files,
        "columns": (
            {"messages": "messages", "images": "images"}
            if target_format == "swift"
            else {"prompt": "instruction", "query": "input", "response": "output", "images": "images"}
        ),
    }
    write_json_file(output_dir / "dataset_info.json", info)
