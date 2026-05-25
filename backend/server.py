#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local PDF layout-analysis preview system.

Run with:
    python backend/server.py --port 8787
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlparse

try:
    import fitz  # type: ignore
    from PIL import Image
    from openai import OpenAI
except Exception as exc:  # pragma: no cover - startup guard
    print("Missing dependency. Please use the conda python that has fitz/openai installed.", file=sys.stderr)
    raise


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
JOBS_DIR = APP_DIR / "jobs"
ENV_FILE = APP_DIR / ".env"
PROMPT_TEMPLATES_FILE = APP_DIR / "prompt_templates.json"

BLOCK_TYPES = {
    "doc_title",
    "paragraph_title",
    "text",
    "table",
    "figure_title",
    "image",
    "vision_footnote",
}
LEVELS = {"H1", "H2", "H3"}

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = ""
ENV_CONFIG_KEYS = [
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT",
    "LAYOUT_RENDER_DPI",
    "LAYOUT_MAX_PAGES",
    "QWEN_RESIZE_PRESET",
    "QWEN_RESIZED_WIDTH",
    "QWEN_RESIZED_HEIGHT",
]
RESIZE_PRESETS = {
    "speed": (1216, 1728),
    "default": (1536, 2176),
    "high": (2048, 2912),
}

LAYOUT_PROMPT = """你是一个专业的文档版面分析模型。现在给你一张文档页面图片，请识别页面中的所有主要版面块，并按照阅读顺序输出结构化 JSON。

你的任务不是总结页面内容，而是进行版面结构解析，包括标题、正文、表格、图片、图题、脚注等区域。

请严格只使用以下 block_type 类型，不允许创造新类型：

1. doc_title：文档总标题，通常出现在封面或首页中央，表示整份文档的名称。
2. paragraph_title：章节标题、段落标题、小节标题，例如“第一节 重要提示”“1、公司简介”“（一）公司的主营业务”。
3. text：普通正文、列表项、编号段落、普通说明文字。
4. table：表格区域，包括财务表格、信息表、带网格线或明显行列结构的内容。若表格内部含文字，请尽量输出为 HTML table。
5. figure_title：图片、产品图、图表上方或下方的标题，例如“好人家主要产品一览”。
6. image：纯图片、产品图、照片、图示、流程图、图表主体等非文本视觉区域。
7. vision_footnote：视觉相关脚注或表格/图表单位说明，例如“单位：元 币种：人民币”。

请输出以下 JSON 格式：

{
  "image_path": "<当前图片路径或空字符串>",
  "blocks": [
    {
      "id": "p{page_no:03d}_b{block_no:03d}",
      "text": "<该区域中的文字；如果是 image 且无可读文字，则为空字符串；如果是 table，则尽量输出 HTML table>",
      "bbox": [x1, y1, x2, y2],
      "page_id": <页码，从0开始>,
      "block_type": "<必须是上述7类之一>",
      "weak_heading": <true 或 false>,
      "level": "<H1/H2/H3 或 null>"
    }
  ],
  "context_before": "",
  "context_after": ""
}

坐标要求：
- bbox 必须使用 Qwen3-VL grounding 的 0–1000 相对坐标系，不要输出原始像素坐标。
- bbox 格式为 [左上角x, 左上角y, 右下角x, 右下角y]，每个值都必须在 0 到 1000 之间。
- 坐标必须覆盖完整版面块，不要只框住单行文字。
- 对连续正文段落，如果语义和版面连续，可以合并为一个 text 块。
- 对标题和正文要分开，不要把标题合并进正文。
- 对表格标题、表格单位说明和表格主体要尽量分开：
  - 表格标题：figure_title 或 paragraph_title，视其是否是图/表说明标题；
  - 单位说明：vision_footnote；
  - 表格主体：table。

标题层级判断：
- 必须为每个 doc_title / paragraph_title 判断 level，只能输出 H1、H2、H3 或 null。
- doc_title 的 level 必须为 H1。
- paragraph_title 需要根据视觉强度、编号层级、标题语义综合判断 H1/H2/H3，不要全部写成 H1 或全部写成 H2。
- H1：文档级标题或章级标题，通常字号最大、居中/单独成行/加粗，或编号形如“第一节”“第二节”“第三节”“一、”“二、”“三、”“第X章”。财报中如“第一节 重要提示”“第二节 公司基本情况”“第三节 重要事项”应为 H1。
- H2：章内一级小节标题，通常编号形如“1、”“2、”“3、”“1.”“2.”，或标题语义是某章下的主要条目。财报中如“1、公司简介”“2、报告期公司主要业务简介”“3、公司主要会计数据和财务指标”“4、股东情况”应为 H2。
- H3：更低层级标题，通常编号形如“（一）”“（二）”“1）”“2）”“3.1”“4.1”，或出现在 H2 下面的局部模式/分项标题。财报中如“（一）公司的主营业务”“1、采购模式”“2、生产模式”“3、销售模式”“3.1 近3年的主要会计数据和财务指标”“3.2 报告期分季度的主要会计数据”“4.1 报告期末...”应为 H3。
- 如果同一页标题视觉明显但编号弱，按其所在位置和语义层级判断；如果标题视觉不明显但根据编号、位置或语义应为标题，则 block_type=paragraph_title 且 weak_heading=true。
- 如果标题视觉明显，例如居中、加粗、字号较大、单独成行，则 weak_heading=false。
- 普通正文、表格、图片、图题、脚注的 level 必须为 null。
- figure_title、table、image、vision_footnote 即使包含编号，也不要设置 H1/H2/H3，level 必须为 null。
- 不确定层级时，优先保持保守：章级用 H1，章内主条目用 H2，主条目下的模式/分项用 H3。

阅读顺序要求：
- 按从上到下、从左到右的自然阅读顺序输出 blocks。
- 页眉、页脚、页码如果不是正文核心内容，可忽略；如果包含重要文本，可标为 text 或 vision_footnote。
- 不要输出解释文字，不要输出 Markdown，只输出合法 JSON。"""

PROMPT_TEMPLATES = {
    "default_template_1": {
        "id": "default_template_1",
        "name": "默认模板 1",
        "category": "layout",
        "prompt": LAYOUT_PROMPT,
    }
}
DEFAULT_PROMPT_TEMPLATE_ID = "default_template_1"
PROMPT_TEMPLATE_CATEGORIES = {"bounding_box", "polygon", "layout", "keypoints", "text_transcription"}


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


load_dotenv()


@dataclass
class PageImage:
    page_id: int
    width: int
    height: int
    image_path: Path
    image_url: str


@dataclass
class ModelPageImage:
    page_id: int
    width: int
    height: int
    image_path: Path
    image_url: str
    content_x: int
    content_y: int
    content_width: int
    content_height: int
    original_width: int
    original_height: int


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int


@dataclass
class VisionResizeConfig:
    width: int = 1536
    height: int = 2176
    preset: str = "default"
    factor: int = 32

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def min_pixels(self) -> int:
        return self.pixels

    @property
    def max_pixels(self) -> int:
        return self.pixels


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    name: str
    prompt: str
    category: str


def normalize_prompt_template_id(value: Any) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return normalized or DEFAULT_PROMPT_TEMPLATE_ID


def public_prompt_template(template: Dict[str, Any], include_prompt: bool = True) -> Dict[str, str]:
    payload = {
        "id": str(template["id"]),
        "name": str(template["name"]),
        "category": str(template.get("category") or "layout"),
    }
    if include_prompt:
        payload["prompt"] = str(template.get("prompt") or "")
    return payload


def prompt_template_options(include_prompt: bool = True) -> List[Dict[str, str]]:
    return [
        public_prompt_template(template, include_prompt=include_prompt)
        for template in PROMPT_TEMPLATES.values()
    ]


def load_saved_prompt_templates(path: Path = PROMPT_TEMPLATES_FILE) -> None:
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read prompt templates: {exc}", file=sys.stderr)
        return

    items = payload.get("prompt_templates") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        template_id = normalize_prompt_template_id(item.get("id"))
        name = clean_text(item.get("name"), template_id)
        category = clean_text(item.get("category"), "layout")
        if category not in PROMPT_TEMPLATE_CATEGORIES:
            category = "layout"
        prompt = clean_text(item.get("prompt"), LAYOUT_PROMPT if template_id == DEFAULT_PROMPT_TEMPLATE_ID else "")
        if not prompt:
            continue
        PROMPT_TEMPLATES[template_id] = {
            "id": template_id,
            "name": name,
            "category": category,
            "prompt": prompt,
        }


def save_prompt_templates(path: Path = PROMPT_TEMPLATES_FILE) -> None:
    payload = {"prompt_templates": prompt_template_options(include_prompt=True)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_prompt_template(template_id: Any) -> PromptTemplate:
    normalized = clean_text(template_id, DEFAULT_PROMPT_TEMPLATE_ID)
    template = PROMPT_TEMPLATES.get(normalized) or PROMPT_TEMPLATES[DEFAULT_PROMPT_TEMPLATE_ID]
    return PromptTemplate(
        template_id=str(template["id"]),
        name=str(template["name"]),
        prompt=str(template["prompt"]),
        category=str(template.get("category") or "layout"),
    )


def env_config() -> Dict[str, str]:
    return {
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
        "has_api_key": "true" if (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")) else "false",
        "render_dpi": os.getenv("LAYOUT_RENDER_DPI", "180"),
        "max_pages": os.getenv("LAYOUT_MAX_PAGES", "50"),
        "qwen_preset": os.getenv("QWEN_RESIZE_PRESET", "default"),
        "qwen_width": os.getenv("QWEN_RESIZED_WIDTH", "1536"),
        "qwen_height": os.getenv("QWEN_RESIZED_HEIGHT", "2176"),
        "prompt_template_id": DEFAULT_PROMPT_TEMPLATE_ID,
    }


def public_llm_config(config: LLMConfig) -> Dict[str, str]:
    return {
        "base_url": config.base_url,
        "model": config.model,
        "has_api_key": "true" if config.api_key else "false",
        "timeout": str(config.timeout),
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


def relative_job_url(path: Path) -> str:
    return "/jobs/" + path.relative_to(JOBS_DIR).as_posix()


def job_asset_path(relative_path: str) -> Path:
    candidate = JOBS_DIR / relative_path
    if candidate.exists():
        return candidate

    parts = Path(relative_path).parts
    if len(parts) >= 2:
        legacy_job_id = parts[0]
        resolved_job_dir = find_job_dir(legacy_job_id)
        if resolved_job_dir != JOBS_DIR / legacy_job_id:
            return resolved_job_dir.joinpath(*parts[1:])

    return candidate


def public_resize_config(config: VisionResizeConfig) -> Dict[str, Any]:
    return {
        "preset": config.preset,
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
    updates = {
        "LLM_BASE_URL": llm_config.base_url,
        "LLM_MODEL": llm_config.model,
        "LLM_TIMEOUT": str(llm_config.timeout),
        "LAYOUT_RENDER_DPI": str(dpi),
        "LAYOUT_MAX_PAGES": str(max_pages),
        "QWEN_RESIZE_PRESET": resize_config.preset,
        "QWEN_RESIZED_WIDTH": str(resize_config.width),
        "QWEN_RESIZED_HEIGHT": str(resize_config.height),
    }
    if llm_config.api_key:
        updates["LLM_API_KEY"] = llm_config.api_key
    write_env_file(updates)
    os.environ.update(updates)


def iter_result_files() -> Iterable[Path]:
    yield from JOBS_DIR.glob("*/result.json")
    yield from JOBS_DIR.glob("*/*/result.json")


def clean_old_jobs(max_age_hours: int = 24) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - max_age_hours * 3600
    for result_file in list(iter_result_files()):
        try:
            job_dir = result_file.parent
            if job_dir.is_dir() and result_file.stat().st_mtime < cutoff:
                shutil.rmtree(job_dir)
        except Exception:
            pass


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
    """Return target width/height, swapping the preset for landscape pages."""
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

        block_type = str(raw.get("block_type", "")).strip()
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
    inferred = infer_heading_level(text)
    return inferred


def infer_heading_level(text: str) -> Optional[str]:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return None

    if re.match(r"^第[一二三四五六七八九十百\d]+[章节]", compact):
        return "H1"
    if re.match(r"^[一二三四五六七八九十]+[、.．]", compact):
        return "H1"

    if re.match(r"^\d+[、.．]", compact):
        # 财报里“3.1/4.2”常是 H3；“1、/2、/3、”常是 H2。
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


def result_path(job_id: str) -> Path:
    return find_job_dir(job_id) / "result.json"


def find_job_dir(job_id: str) -> Path:
    legacy_dir = JOBS_DIR / job_id
    if (legacy_dir / "result.json").exists():
        return legacy_dir
    matches = list(JOBS_DIR.glob(f"*/{job_id}/result.json"))
    if matches:
        return matches[0].parent
    return legacy_dir


def read_job_result(job_id: str) -> Dict[str, Any]:
    path = result_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"job not found: {job_id}")
    return normalize_job_payload(job_id, json.loads(path.read_text(encoding="utf-8")))


def normalize_job_payload(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("job_id", job_id)
    payload.setdefault("filename", "未知文件")
    payload.setdefault("status", "complete")
    payload.setdefault("completed_pages", count_finished_pages(payload.get("pages", [])))
    payload.setdefault("pages", [])
    payload.setdefault("result", {"image_path": "", "blocks": [], "context_before": "", "context_after": ""})
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


def parse_multipart(body: bytes, content_type: str) -> Dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    fields: Dict[str, Any] = {}
    if not message.is_multipart():
        raise ValueError("request must be multipart/form-data")

    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if not name:
            continue
        if filename:
            fields[name] = {"filename": filename, "content": payload, "content_type": part.get_content_type()}
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return fields


class LayoutAnalyzerHandler(BaseHTTPRequestHandler):
    server_version = "LayoutAnalyzer/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/config":
            self.write_json({"config": env_config(), "prompt_templates": prompt_template_options()})
            return
        if path == "/api/prompt-templates":
            self.write_json({"prompt_templates": prompt_template_options()})
            return
        if path == "/api/jobs":
            self.write_json({"jobs": list_job_summaries()})
            return
        job_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/result", path)
        if job_match:
            try:
                self.write_json(read_job_result(job_match.group(1)))
            except FileNotFoundError:
                self.write_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if path.startswith("/jobs/"):
            self.serve_file(job_asset_path(path.removeprefix("/jobs/")))
            return
        if path == "/" or path == "/index.html":
            self.serve_file(STATIC_DIR / "index.html")
            return
        self.serve_file(STATIC_DIR / path.lstrip("/"))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        job_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)", path)
        if not job_match:
            self.write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        job_id = job_match.group(1)
        job_dir = find_job_dir(job_id).resolve()
        if not str(job_dir).startswith(str(JOBS_DIR.resolve())) or not job_dir.is_dir():
            self.write_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            shutil.rmtree(job_dir)
            self.write_json({"ok": True, "job_id": job_id})
        except Exception as exc:
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        template_match = re.fullmatch(r"/api/prompt-templates/([A-Za-z0-9_-]+)", parsed.path)
        if template_match:
            try:
                payload = self.read_json_body()
                template_id = normalize_prompt_template_id(template_match.group(1))
                existing = PROMPT_TEMPLATES.get(template_id)
                if not existing:
                    self.write_json({"error": "prompt template not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                name = clean_text(payload.get("name"), str(existing.get("name") or template_id))
                category = clean_text(payload.get("category"), str(existing.get("category") or "layout"))
                if category not in PROMPT_TEMPLATE_CATEGORIES:
                    raise ValueError("invalid prompt template category")
                prompt = clean_text(payload.get("prompt"), str(existing.get("prompt") or ""))
                if len(prompt) < 20:
                    raise ValueError("prompt template is too short")
                PROMPT_TEMPLATES[template_id] = {
                    "id": template_id,
                    "name": name,
                    "category": category,
                    "prompt": prompt,
                }
                save_prompt_templates()
                self.write_json({"prompt_template": public_prompt_template(PROMPT_TEMPLATES[template_id])})
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            content_type = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("empty request body")
            fields = parse_multipart(self.rfile.read(length), content_type)
            uploaded = fields.get("file")
            if not isinstance(uploaded, dict):
                raise ValueError("missing file field")
            filename = str(uploaded.get("filename") or "uploaded.pdf")
            if not filename.lower().endswith(".pdf"):
                raise ValueError("only PDF files are supported")

            dpi = clamp_int(fields.get("dpi"), default=int(env_config()["render_dpi"]), minimum=72, maximum=300)
            max_pages = clamp_int(fields.get("max_pages"), default=int(env_config()["max_pages"]), minimum=1, maximum=200)
            timeout = clamp_int(fields.get("timeout"), default=int(os.getenv("LLM_TIMEOUT", "180")), minimum=10, maximum=900)
            llm_config = LLMConfig(
                base_url=clean_text(fields.get("base_url"), env_config()["base_url"]),
                model=clean_text(fields.get("model"), env_config()["model"]),
                api_key=clean_text(fields.get("api_key"), os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""),
                timeout=timeout,
            )
            resize_config = parse_resize_config(fields)
            if not llm_config.base_url:
                raise ValueError("missing model base URL")
            if not llm_config.model:
                raise ValueError("missing model name")
            persist_runtime_config(llm_config, resize_config, dpi, max_pages)
            prompt_template = resolve_prompt_template(fields.get("prompt_template_id"))
            result = start_analysis_job(
                uploaded["content"],
                filename=filename,
                dpi=dpi,
                max_pages=max_pages,
                llm_config=llm_config,
                resize_config=resize_config,
                prompt_template=prompt_template,
            )
            self.write_json(result)
        except Exception as exc:
            traceback.print_exc()
            self.write_json(
                {"error": f"{type(exc).__name__}: {exc}"},
                status=HTTPStatus.BAD_REQUEST,
            )

    def read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def serve_file(self, path: Path) -> None:
        try:
            real = path.resolve()
            allowed_roots = [STATIC_DIR.resolve(), JOBS_DIR.resolve()]
            if not any(str(real).startswith(str(root)) for root in allowed_roots):
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            if not real.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            content_type = mimetypes.guess_type(str(real))[0] or "application/octet-stream"
            data = real.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(str(value))
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def parse_resize_config(fields: Dict[str, Any]) -> VisionResizeConfig:
    preset = clean_text(fields.get("qwen_preset"), env_config()["qwen_preset"])
    if preset not in RESIZE_PRESETS and preset != "custom":
        preset = "default"

    if preset in RESIZE_PRESETS:
        width, height = RESIZE_PRESETS[preset]
    else:
        width = clamp_int(fields.get("qwen_width"), default=int(env_config()["qwen_width"]), minimum=1024, maximum=4096)
        height = clamp_int(fields.get("qwen_height"), default=int(env_config()["qwen_height"]), minimum=1024, maximum=6144)

    width = align_to_factor(width, 32)
    height = align_to_factor(height, 32)
    if width * height <= 0:
        raise ValueError("invalid Qwen resize dimensions")
    return VisionResizeConfig(width=width, height=height, preset=preset, factor=32)


def align_to_factor(value: int, factor: int) -> int:
    return max(factor, int(round(value / factor)) * factor)


def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


load_saved_prompt_templates()


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF layout analysis preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), LayoutAnalyzerHandler)
    print(f"Layout Analyzer running at http://{args.host}:{args.port}")
    print(f"LLM_BASE_URL={env_config()['base_url']}")
    print(f"LLM_MODEL={env_config()['model']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
