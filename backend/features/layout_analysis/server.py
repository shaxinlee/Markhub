#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF layout-analysis annotation service.

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
from urllib.parse import parse_qs, unquote, urlparse

try:
    import fitz  # type: ignore
    from PIL import Image
    from openai import OpenAI
except Exception as exc:  # pragma: no cover - startup guard
    print("Missing dependency. Please use the conda python that has fitz/openai installed.", file=sys.stderr)
    raise


BACKEND_DIR = Path(__file__).resolve().parents[2]
FEATURE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BACKEND_DIR / "static"
DATASETS_DIR = BACKEND_DIR / "datasets"
FIRST_ANNOTATIONS_DIR = DATASETS_DIR / "first_annotations"
SECOND_ANNOTATIONS_DIR = DATASETS_DIR / "second_annotations"
SWIFT_DATASETS_DIR = DATASETS_DIR / "swift_datasets"
LLAMAFACTORY_DATASETS_DIR = DATASETS_DIR / "llamafactory_datasets"
PROMPTS_DIR = DATASETS_DIR / "prompt_templates"
PROMPTS_STORE_FILE = PROMPTS_DIR / "prompts.json"
JOBS_DIR = FIRST_ANNOTATIONS_DIR
LEGACY_JOBS_DIR = BACKEND_DIR / "jobs"
ENV_FILE = BACKEND_DIR / ".env"
PROMPT_TEMPLATES_FILE = BACKEND_DIR / "prompt_templates.json"

BLOCK_TYPES = {
    "doc_title",
    "paragraph_title",
    "text",
    "table",
    "figure_title",
    "image",
    "vision_footnote",
    "handwriting",
    "seal",
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

你的任务不是总结页面内容，而是进行版面结构解析，包括标题、正文、表格、图片、图题、脚注、手写字、印章等区域。

请严格只使用以下 block_type 类型，不允许创造新类型：

1. doc_title：文档总标题，通常出现在封面或首页中央，表示整份文档的名称。
2. paragraph_title：章节标题、段落标题、小节标题，例如“第一节 重要提示”“1、公司简介”“（一）公司的主营业务”。
3. text：普通正文、列表项、编号段落、普通说明文字。
4. table：表格区域，包括财务表格、信息表、带网格线或明显行列结构的内容。若表格内部含文字，请尽量输出为 HTML table。
5. figure_title：图片、产品图、图表上方或下方的标题，例如“好人家主要产品一览”。
6. image：纯图片、产品图、照片、图示、流程图、图表主体等非文本视觉区域。
7. vision_footnote：视觉相关脚注或表格/图表单位说明，例如“单位：元 币种：人民币”。
8. handwriting：手写字、手写批注、手写签名、手写日期或人工填写的手写内容。如果能辨认文字，请写入 text；无法辨认时 text 可为空字符串。
9. seal：印章、签章、骑缝章、公司章、个人章等盖章区域。如果印章文字可辨认，请写入 text；无法辨认时 text 可为空字符串。

请输出以下 JSON 格式：

{
  "image_path": "<当前图片路径或空字符串>",
  "blocks": [
    {
      "id": "p{page_no:03d}_b{block_no:03d}",
      "text": "<该区域中的文字；如果是 image/seal/handwriting 且无可读文字，则为空字符串；如果是 table，则尽量输出 HTML table>",
      "bbox": [x1, y1, x2, y2],
      "page_id": <页码，从0开始>,
      "block_type": "<必须是上述9类之一>",
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
- figure_title、table、image、vision_footnote、handwriting、seal 即使包含编号，也不要设置 H1/H2/H3，level 必须为 null。
- 不确定层级时，优先保持保守：章级用 H1，章内主条目用 H2，主条目下的模式/分项用 H3。

手写字与印章识别要求：
- 不要忽略手写签名、手写日期、手写金额、手写批注、手写勾画旁的文字；这类内容统一标为 handwriting。
- 不要把印章误标为 image。圆形章、椭圆章、方章、红章、蓝章、骑缝章等统一标为 seal。
- handwriting 和 seal 的 bbox 必须覆盖完整手写/盖章区域；如果区域内同时有印刷文字和手写字，请拆成独立块。

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
PROMPT_TYPES = {
    "data_annotation",
    "second_review",
    "data_cleaning",
    "data_conversion",
    "model_inference",
    "system_role",
    "custom",
}
PROMPT_TASK_TYPES = {
    "layout_analysis",
    "weak_heading_detection",
    "table_recognition",
    "image_captioning",
    "data_quality_check",
    "llamafactory_conversion",
    "swift_conversion",
    "second_manual_review",
    "auto_annotation",
    "custom",
}
PROMPT_STATUS = {"enabled", "disabled"}
DATASET_LABEL_TYPES = {
    "doc_title",
    "title",
    "paragraph_title",
    "text",
    "table",
    "figure",
    "chart",
    "formula",
    "seal",
    "header",
    "footer",
    "footnote",
    "reference",
    "caption",
    "list",
    "other",
    "figure_title",
    "image",
    "vision_footnote",
    "handwriting",
}
CONVERT_TASKS: Dict[str, Dict[str, Any]] = {}


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
        public_prompt_template(
            {"id": prompt["id"], "name": prompt["name"], "category": legacy_prompt_category(prompt), "prompt": prompt.get("content", "")},
            include_prompt=include_prompt,
        )
        for prompt in list_prompts({"status": "enabled"})
        if prompt.get("task_type") in {"layout_analysis", "custom"} and not prompt.get("deleted_at")
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
    # Backward-compatible export for older tools; the canonical store is PROMPTS_STORE_FILE.
    payload = {"prompt_templates": prompt_template_options(include_prompt=True)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iso_to_sort_value(value: Any) -> str:
    return str(value or "")


def prompt_now() -> str:
    return iso_now()


def legacy_prompt_category(prompt: Dict[str, Any]) -> str:
    task_type = str(prompt.get("task_type") or "")
    if task_type == "layout_analysis":
        return "layout"
    return "layout" if prompt.get("type") == "data_annotation" else "text_transcription"


def prompt_store_payload() -> Dict[str, Any]:
    if PROMPTS_STORE_FILE.is_file():
        payload = read_json_file(PROMPTS_STORE_FILE, {})
        if isinstance(payload, dict) and isinstance(payload.get("prompts"), list):
            return payload
    prompts = [default_prompt_record()]
    payload = {"prompts": prompts, "operation_logs": []}
    write_prompt_store(payload)
    return payload


def write_prompt_store(payload: Dict[str, Any]) -> None:
    PROMPTS_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(PROMPTS_STORE_FILE, payload)


def default_prompt_record() -> Dict[str, Any]:
    now = prompt_now()
    record = {
        "id": DEFAULT_PROMPT_TEMPLATE_ID,
        "name": "默认版面分析提示词",
        "description": "系统内置的文档版面分析 Prompt，识别标题、正文、表格、图片、脚注、手写字和印章。",
        "type": "data_annotation",
        "task_type": "layout_analysis",
        "model_name": "all",
        "content": LAYOUT_PROMPT,
        "variables": "输入为当前页面图片；模型应输出严格 JSON。",
        "default_values": {},
        "version": "v1.0",
        "status": "enabled",
        "is_default": True,
        "created_by": "system",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "notes": "系统默认提示词，可复制后创建自定义版本。",
        "usage_scenarios": ["数据自动标注", "文档版面分析"],
        "versions": [],
        "operation_logs": [],
    }
    record["versions"] = [version_record(record, "初始化默认提示词", "system")]
    return record


def migrate_legacy_prompt_templates() -> None:
    payload = prompt_store_payload()
    prompts = payload.setdefault("prompts", [])
    existing_ids = {str(item.get("id")) for item in prompts if isinstance(item, dict)}
    for template in PROMPT_TEMPLATES.values():
        template_id = str(template.get("id") or "")
        if not template_id or template_id in existing_ids:
            continue
        record = normalize_prompt_record(
            {
                "id": template_id,
                "name": template.get("name") or template_id,
                "description": "从旧提示词模板迁移而来。",
                "type": "data_annotation",
                "task_type": "layout_analysis",
                "model_name": "all",
                "content": template.get("prompt") or LAYOUT_PROMPT,
                "status": "enabled",
                "is_default": template_id == DEFAULT_PROMPT_TEMPLATE_ID,
                "created_by": "system",
            },
            is_new=True,
        )
        prompts.append(record)
        existing_ids.add(template_id)
    enforce_default_constraints(prompts)
    write_prompt_store(payload)


def normalize_prompt_record(raw: Dict[str, Any], is_new: bool = False) -> Dict[str, Any]:
    now = prompt_now()
    prompt_id = normalize_prompt_template_id(raw.get("id") or uuid.uuid4().hex[:12])
    prompt_type = clean_text(raw.get("type"), "custom")
    if prompt_type not in PROMPT_TYPES:
        prompt_type = "custom"
    task_type = clean_text(raw.get("task_type"), "custom")
    if task_type not in PROMPT_TASK_TYPES:
        task_type = "custom"
    status = clean_text(raw.get("status"), "enabled")
    if status not in PROMPT_STATUS:
        status = "enabled"
    default_values = raw.get("default_values")
    if isinstance(default_values, str):
        try:
            parsed = json.loads(default_values) if default_values.strip() else {}
            default_values = parsed if isinstance(parsed, dict) else {}
        except Exception:
            default_values = {}
    if not isinstance(default_values, dict):
        default_values = {}
    record = {
        "id": prompt_id,
        "name": clean_text(raw.get("name"), prompt_id),
        "description": clean_text(raw.get("description"), ""),
        "type": prompt_type,
        "task_type": task_type,
        "model_name": clean_text(raw.get("model_name"), "all"),
        "content": clean_text(raw.get("content") if raw.get("content") is not None else raw.get("prompt"), ""),
        "variables": raw.get("variables") if isinstance(raw.get("variables"), (str, list, dict)) else "",
        "default_values": default_values,
        "version": clean_text(raw.get("version"), "v1.0"),
        "status": status,
        "is_default": bool(raw.get("is_default", False)),
        "created_by": clean_text(raw.get("created_by"), "system"),
        "created_at": clean_text(raw.get("created_at"), now),
        "updated_at": clean_text(raw.get("updated_at"), now),
        "deleted_at": raw.get("deleted_at"),
        "notes": clean_text(raw.get("notes"), ""),
        "usage_scenarios": raw.get("usage_scenarios") if isinstance(raw.get("usage_scenarios"), list) else [],
        "versions": raw.get("versions") if isinstance(raw.get("versions"), list) else [],
        "operation_logs": raw.get("operation_logs") if isinstance(raw.get("operation_logs"), list) else [],
    }
    if is_new and not record["versions"]:
        record["versions"] = [version_record(record, "创建提示词", record["created_by"])]
    return record


def validate_prompt_payload(payload: Dict[str, Any], existing_id: Optional[str] = None) -> Dict[str, Any]:
    record = normalize_prompt_record({**payload, "id": existing_id or payload.get("id") or uuid.uuid4().hex[:12]}, is_new=existing_id is None)
    if not record["name"]:
        raise ValueError("提示词名称不能为空")
    if not record["content"]:
        raise ValueError("Prompt 内容不能为空")
    validate_prompt_variables(record["content"])
    if record["is_default"] and record["status"] != "enabled":
        raise ValueError("已停用提示词不能被设置为默认提示词")
    return record


def validate_prompt_variables(content: str) -> None:
    for raw in re.findall(r"{{(.*?)}}", content, flags=re.DOTALL):
        name = raw.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"变量格式不规范: {{{{{raw}}}}}")
    if "{{" in re.sub(r"{{.*?}}", "", content, flags=re.DOTALL) or "}}" in re.sub(r"{{.*?}}", "", content, flags=re.DOTALL):
        raise ValueError("变量格式必须使用 {{variable_name}}")


def version_record(prompt: Dict[str, Any], change_log: str = "", created_by: str = "") -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "prompt_template_id": prompt["id"],
        "version": prompt.get("version") or "v1.0",
        "content": prompt.get("content") or "",
        "variables": prompt.get("variables") if isinstance(prompt.get("variables"), (str, list, dict)) else "",
        "default_values": prompt.get("default_values") if isinstance(prompt.get("default_values"), dict) else {},
        "change_log": change_log,
        "created_by": created_by or prompt.get("created_by") or "system",
        "created_at": prompt_now(),
    }


def next_prompt_version(version: str) -> str:
    match = re.fullmatch(r"v(\d+)\.(\d+)", str(version or "v1.0"))
    if not match:
        return "v1.1"
    major, minor = int(match.group(1)), int(match.group(2))
    return f"v{major}.{minor + 1}"


def prompt_public(prompt: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_prompt_record(prompt)


def list_prompts(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    payload = prompt_store_payload()
    prompts = [prompt_public(item) for item in payload.get("prompts", []) if isinstance(item, dict)]
    filters = filters or {}
    include_deleted = str(filters.get("include_deleted") or "").lower() == "true"
    if not include_deleted:
        prompts = [item for item in prompts if not item.get("deleted_at")]

    def matches(item: Dict[str, Any]) -> bool:
        search = clean_text(filters.get("search"), "").lower()
        if search and search not in f"{item.get('name')} {item.get('description')} {item.get('content')}".lower():
            return False
        for key in ("type", "task_type", "model_name", "status"):
            value = clean_text(filters.get(key), "")
            if value and value != "all" and str(item.get(key) or "") != value:
                return False
        is_default = clean_text(filters.get("is_default"), "")
        if is_default in {"true", "false"} and bool(item.get("is_default")) != (is_default == "true"):
            return False
        return True

    prompts = [item for item in prompts if matches(item)]
    sort_by = clean_text(filters.get("sort_by"), "updated_at")
    if sort_by not in {"created_at", "updated_at", "name"}:
        sort_by = "updated_at"
    reverse = clean_text(filters.get("sort_order"), "desc") != "asc"
    prompts.sort(key=lambda item: iso_to_sort_value(item.get(sort_by)), reverse=reverse)
    return prompts


def get_prompt(prompt_id: str, include_deleted: bool = True) -> Optional[Dict[str, Any]]:
    prompt_id = normalize_prompt_template_id(prompt_id)
    for prompt in list_prompts({"include_deleted": "true"}):
        if prompt.get("id") == prompt_id:
            if prompt.get("deleted_at") and not include_deleted:
                return None
            return prompt
    return None


def default_prompt_for_task(task_type: str) -> Optional[Dict[str, Any]]:
    enabled = list_prompts({"status": "enabled", "task_type": task_type})
    for prompt in enabled:
        if prompt.get("is_default"):
            return prompt
    return enabled[0] if enabled else None


def save_prompts(prompts: List[Dict[str, Any]]) -> None:
    payload = prompt_store_payload()
    payload["prompts"] = prompts
    write_prompt_store(payload)


def enforce_default_constraints(prompts: List[Dict[str, Any]], default_prompt_id: Optional[str] = None) -> None:
    seen_defaults: set[str] = set()
    for prompt in prompts:
        if prompt.get("status") != "enabled":
            prompt["is_default"] = False
            continue
        task_type = str(prompt.get("task_type") or "custom")
        if default_prompt_id and prompt.get("id") == default_prompt_id:
            prompt["is_default"] = True
            seen_defaults.add(task_type)
            continue
        if task_type in seen_defaults:
            prompt["is_default"] = False
        elif prompt.get("is_default"):
            seen_defaults.add(task_type)


def log_prompt_operation(prompt: Dict[str, Any], action: str, detail: str = "", operator: str = "") -> None:
    prompt.setdefault("operation_logs", []).append(
        {"action": action, "detail": detail, "operator": operator or "system", "created_at": prompt_now()}
    )


def create_prompt(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompts = list_prompts({"include_deleted": "true"})
    record = validate_prompt_payload(payload)
    if any(item.get("id") == record["id"] for item in prompts):
        raise ValueError(f"prompt id already exists: {record['id']}")
    log_prompt_operation(record, "create", "新增提示词", record.get("created_by", "system"))
    prompts.append(record)
    if record.get("is_default"):
        enforce_default_constraints(prompts, record["id"])
    save_prompts(prompts)
    return record


def update_prompt(prompt_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompts = list_prompts({"include_deleted": "true"})
    for index, prompt in enumerate(prompts):
        if prompt.get("id") != normalize_prompt_template_id(prompt_id):
            continue
        if prompt.get("deleted_at"):
            raise FileNotFoundError("prompt not found")
        merged = {**prompt, **payload, "id": prompt["id"], "created_at": prompt["created_at"], "created_by": prompt.get("created_by", "system")}
        updated = validate_prompt_payload(merged, existing_id=prompt["id"])
        content_changed = any(updated.get(key) != prompt.get(key) for key in ("content", "variables", "default_values"))
        metadata_changed = any(updated.get(key) != prompt.get(key) for key in ("name", "description", "type", "task_type", "model_name", "notes", "status", "is_default"))
        if not (content_changed or metadata_changed):
            return prompt
        if updated.get("is_default") and updated.get("status") != "enabled":
            raise ValueError("已停用提示词不能被设置为默认提示词")
        updated["updated_at"] = prompt_now()
        if content_changed:
            updated["version"] = next_prompt_version(prompt.get("version", "v1.0"))
            updated["versions"] = list(prompt.get("versions") or []) + [
                version_record(updated, clean_text(payload.get("change_log"), "编辑提示词"), clean_text(payload.get("updated_by"), "system"))
            ]
        else:
            updated["versions"] = prompt.get("versions") or []
        updated["operation_logs"] = prompt.get("operation_logs") or []
        log_prompt_operation(updated, "update", clean_text(payload.get("change_log"), "编辑提示词"), clean_text(payload.get("updated_by"), "system"))
        prompts[index] = updated
        if updated.get("is_default"):
            enforce_default_constraints(prompts, updated["id"])
        save_prompts(prompts)
        return updated
    raise FileNotFoundError("prompt not found")


def soft_delete_prompt(prompt_id: str) -> Dict[str, Any]:
    prompts = list_prompts({"include_deleted": "true"})
    for index, prompt in enumerate(prompts):
        if prompt.get("id") == normalize_prompt_template_id(prompt_id) and not prompt.get("deleted_at"):
            prompt["deleted_at"] = prompt_now()
            prompt["status"] = "disabled"
            prompt["is_default"] = False
            prompt["updated_at"] = prompt_now()
            log_prompt_operation(prompt, "delete", "软删除提示词")
            prompts[index] = prompt
            save_prompts(prompts)
            return prompt
    raise FileNotFoundError("prompt not found")


def copy_prompt(prompt_id: str) -> Dict[str, Any]:
    source = get_prompt(prompt_id, include_deleted=False)
    if not source:
        raise FileNotFoundError("prompt not found")
    copied = {
        **source,
        "id": f"{normalize_prompt_template_id(source['name'])}_copy_{uuid.uuid4().hex[:6]}",
        "name": f"{source['name']}_副本",
        "is_default": False,
        "version": "v1.0",
        "created_at": prompt_now(),
        "updated_at": prompt_now(),
        "created_by": "system",
        "deleted_at": None,
        "versions": [],
        "operation_logs": [],
    }
    copied["versions"] = [version_record(copied, f"复制自 {source['name']}", "system")]
    return create_prompt(copied)


def set_prompt_status(prompt_id: str, status: str) -> Dict[str, Any]:
    prompt = get_prompt(prompt_id, include_deleted=False)
    if not prompt:
        raise FileNotFoundError("prompt not found")
    if status == "disabled" and prompt.get("is_default"):
        raise ValueError("默认提示词不能直接停用，请先取消默认或指定新的默认提示词")
    return update_prompt(prompt_id, {"status": status, "updated_by": "system", "change_log": f"设置为 {status}"})


def set_default_prompt(prompt_id: str) -> Dict[str, Any]:
    prompts = list_prompts({"include_deleted": "true"})
    selected: Optional[Dict[str, Any]] = None
    for prompt in prompts:
        if prompt.get("id") == normalize_prompt_template_id(prompt_id) and not prompt.get("deleted_at"):
            selected = prompt
            break
    if not selected:
        raise FileNotFoundError("prompt not found")
    if selected.get("status") != "enabled":
        raise ValueError("已停用提示词不能被设置为默认提示词")
    for prompt in prompts:
        if prompt.get("task_type") == selected.get("task_type") and not prompt.get("deleted_at"):
            prompt["is_default"] = prompt.get("id") == selected.get("id")
            prompt["updated_at"] = prompt_now()
    log_prompt_operation(selected, "set_default", "设置为任务默认提示词")
    save_prompts(prompts)
    return selected


def rollback_prompt(prompt_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    prompt = get_prompt(prompt_id, include_deleted=False)
    if not prompt:
        raise FileNotFoundError("prompt not found")
    version_key = clean_text(body.get("version") or body.get("version_id"), "")
    target = None
    for version in prompt.get("versions") or []:
        if version_key in {str(version.get("id")), str(version.get("version"))}:
            target = version
            break
    if not target:
        raise FileNotFoundError("version not found")
    return update_prompt(
        prompt_id,
        {
            "content": target.get("content", ""),
            "variables": target.get("variables", ""),
            "default_values": target.get("default_values", {}),
            "change_log": f"回滚到 {target.get('version')}",
            "updated_by": clean_text(body.get("updated_by"), "system"),
        },
    )


def render_prompt(content: str, values: Dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = values.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return re.sub(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", replace, content)


def test_prompt(prompt_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    prompt = get_prompt(prompt_id, include_deleted=False)
    if not prompt:
        raise FileNotFoundError("prompt not found")
    inputs = body.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    values = {**(prompt.get("default_values") or {}), **inputs}
    started = time.time()
    rendered = render_prompt(str(prompt.get("content") or ""), values)
    call_model = bool(body.get("call_model", False))
    output = "未调用模型：已完成变量渲染测试。"
    success = True
    error = ""
    model_name = clean_text(body.get("model_name"), clean_text(prompt.get("model_name"), env_config().get("model", "")))
    token_usage: Optional[Dict[str, Any]] = None
    if call_model:
        try:
            llm_config = LLMConfig(
                base_url=clean_text(body.get("base_url"), env_config()["base_url"]),
                model=model_name,
                api_key=clean_text(body.get("api_key"), os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""),
                timeout=clamp_int(body.get("timeout"), default=int(os.getenv("LLM_TIMEOUT", "180")), minimum=10, maximum=900),
            )
            if not llm_config.model:
                raise ValueError("missing model name")
            client = OpenAI(api_key=llm_config.api_key or "EMPTY", base_url=llm_config.base_url)
            completion = client.chat.completions.create(
                model=llm_config.model,
                messages=[{"role": "user", "content": rendered}],
                temperature=0,
                timeout=llm_config.timeout,
            )
            output = completion.choices[0].message.content if completion.choices else ""
            usage = getattr(completion, "usage", None)
            if usage is not None:
                token_usage = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
        except Exception as exc:
            success = False
            error = f"{type(exc).__name__}: {exc}"
            output = ""
    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "success": success,
        "inputs": inputs,
        "rendered_prompt": rendered,
        "model_output": output,
        "model_name": model_name,
        "elapsed_ms": elapsed_ms,
        "token_usage": token_usage,
        "error": error,
    }


def resolve_prompt_template(template_id: Any) -> PromptTemplate:
    normalized = clean_text(template_id, DEFAULT_PROMPT_TEMPLATE_ID)
    prompt = get_prompt(normalized, include_deleted=False)
    if not prompt or prompt.get("status") != "enabled":
        prompt = default_prompt_for_task("layout_analysis")
    if prompt:
        return PromptTemplate(
            template_id=str(prompt["id"]),
            name=str(prompt["name"]),
            prompt=str(prompt["content"]),
            category=legacy_prompt_category(prompt),
        )
    template = PROMPT_TEMPLATES.get(normalized) or PROMPT_TEMPLATES[DEFAULT_PROMPT_TEMPLATE_ID]
    return PromptTemplate(
        template_id=str(template["id"]),
        name=str(template["name"]),
        prompt=str(template["prompt"]),
        category=str(template.get("category") or "layout"),
    )


def env_config() -> Dict[str, str]:
    default_layout_prompt = default_prompt_for_task("layout_analysis")
    return {
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
        "has_api_key": "true" if (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")) else "false",
        "render_dpi": os.getenv("LAYOUT_RENDER_DPI", "180"),
        "max_pages": os.getenv("LAYOUT_MAX_PAGES", "50"),
        "qwen_preset": os.getenv("QWEN_RESIZE_PRESET", "default"),
        "qwen_width": os.getenv("QWEN_RESIZED_WIDTH", "1536"),
        "qwen_height": os.getenv("QWEN_RESIZED_HEIGHT", "2176"),
        "prompt_template_id": str((default_layout_prompt or {}).get("id") or DEFAULT_PROMPT_TEMPLATE_ID),
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


def ensure_dataset_storage() -> None:
    for path in (FIRST_ANNOTATIONS_DIR, SECOND_ANNOTATIONS_DIR, SWIFT_DATASETS_DIR, LLAMAFACTORY_DATASETS_DIR, PROMPTS_DIR):
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
    # 历史版本把分析任务当作临时缓存清理；现在它们是 datasets 下的一次标注资产，必须持久保留。
    ensure_dataset_storage()


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


def now_timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


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


def safe_path_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", str(value or "").strip())
    return text.strip("._ ") or "dataset"


def read_json_file(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def dataset_state_path(job_id: str) -> Path:
    return dataset_dir(job_id) / "dataset_state.json"


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
    state.setdefault("first_annotated_at", int(result_path(job_id).stat().st_mtime) if result_path(job_id).exists() else None)
    state.setdefault("second_annotated_at", None)
    state.setdefault("updated_at", int(time.time()))
    return state


def write_dataset_state(job_id: str, state: Dict[str, Any]) -> None:
    state["updated_at"] = int(time.time())
    write_json_file(dataset_state_path(job_id), state)


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
    items: List[Dict[str, Any]] = []
    # 以已经稳定使用的 job summary 为基准增强数据集状态，避免新数据集状态文件异常时漏掉旧标注结果。
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
    label = str(block.get("label") or block.get("block_type") or block.get("type") or "text")
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

    # 保存二次标注时始终生成完整页面快照，避免草稿只保存当前页造成数据丢失。
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
    # 覆盖保存会写回一次标注结果，这是高风险操作，前端已做二次确认。
    write_job_result(job_id, payload)


def job_block_from_annotation(block: Dict[str, Any]) -> Dict[str, Any]:
    label = str(block.get("label") or block.get("block_type") or "text")
    return {
        "id": block.get("id"),
        "text": block.get("text", ""),
        "bbox": block.get("bbox", [0, 0, 1, 1]),
        "page_id": block.get("page_id", 0),
        "block_type": label if label in BLOCK_TYPES else "text",
        "weak_heading": bool(block.get("weak_heading", False)),
        "level": block.get("level") if block.get("level") in {"H1", "H2", "H3"} else None,
    }


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
    CONVERT_TASKS[task_id] = task
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
    task = CONVERT_TASKS[task_id]
    logs: List[str] = []
    output_dir: Optional[Path] = None
    skipped = 0
    try:
        output_dir = resolve_convert_output_dir(dataset_ids, target_format, merge, output_name)
        if output_dir.exists() and not overwrite:
            raise FileExistsError(f"输出路径已存在: {output_dir}")
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
            "output_path": str(output_dir),
            "script_version": "markhub-converter-v2",
        }
        write_json_file(output_dir / "convert_config.json", config)
        (output_dir / "convert_log.txt").write_text("\n".join(logs) + f"\nskipped_samples={skipped}\n", encoding="utf-8")

        status = "partial_success" if skipped else "success"
        task.update({"status": status, "output_path": str(output_dir), "message": "转换完成", "skipped_samples": skipped})
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
                    "output_path": str(output_dir),
                    "created_at": config["created_at"],
                    "skipped_samples": skipped,
                }
            )
            write_dataset_state(dataset_id, state)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        task.update({"status": "failed", "error": error, "message": "转换失败", "skipped_samples": skipped})
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "convert_log.txt").write_text("\n".join(logs + [error]), encoding="utf-8")
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
                        "output_path": str(output_dir or ""),
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
            target_image = output_dir / "images" / safe_path_name(dataset_id) / source_image.name
            target_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_image, target_image)
            image_ref = str(target_image.resolve())
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


DEFAULT_SWIFT_USER_PROMPT = "<image>\n请识别图片中的所有主要版面块，并按照阅读顺序输出严格合法的 JSON。"
DEFAULT_LLAMAFACTORY_INSTRUCTION = "<image>\n请识别图片中的所有主要版面块，并按照阅读顺序输出严格合法的 JSON。"


def image_path_from_page_url(dataset_id: str, image_url: str) -> Optional[Path]:
    if image_url.startswith("/jobs/"):
        return job_asset_path(image_url.removeprefix("/jobs/"))
    job_dir = find_job_dir(dataset_id)
    candidate = job_dir / image_url.lstrip("/")
    return candidate if candidate.exists() else None


def normalize_export_block(block: Dict[str, Any]) -> Dict[str, Any]:
    label = str(block.get("label") or block.get("block_type") or "text")
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
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
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
        if path == "/api/prompts":
            filters = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
            self.write_json({"prompts": list_prompts(filters)})
            return
        prompt_versions_match = re.fullmatch(r"/api/prompts/([A-Za-z0-9_-]+)/versions", path)
        if prompt_versions_match:
            prompt = get_prompt(prompt_versions_match.group(1), include_deleted=False)
            if not prompt:
                self.write_json({"error": "prompt not found"}, status=HTTPStatus.NOT_FOUND)
            else:
                self.write_json({"versions": prompt.get("versions", [])})
            return
        prompt_match = re.fullmatch(r"/api/prompts/([A-Za-z0-9_-]+)", path)
        if prompt_match:
            prompt = get_prompt(prompt_match.group(1), include_deleted=False)
            if not prompt:
                self.write_json({"error": "prompt not found"}, status=HTTPStatus.NOT_FOUND)
            else:
                self.write_json({"prompt": prompt})
            return
        if path == "/api/jobs":
            self.write_json({"jobs": list_job_summaries()})
            return
        if path == "/api/datasets":
            self.write_json({"datasets": list_dataset_summaries()})
            return
        convert_match = re.fullmatch(r"/api/datasets/convert/([A-Za-z0-9_-]+)", path)
        if convert_match:
            task_id = convert_match.group(1)
            task = CONVERT_TASKS.get(task_id)
            if not task:
                self.write_json({"error": "convert task not found"}, status=HTTPStatus.NOT_FOUND)
            else:
                self.write_json(task)
            return
        annotation_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)/annotations", path)
        if annotation_match:
            try:
                self.write_json(read_annotation_payload(annotation_match.group(1)))
            except FileNotFoundError:
                self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        records_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)/convert-records", path)
        if records_match:
            try:
                state = read_dataset_state(records_match.group(1))
                self.write_json({"records": state.get("convert_records", [])})
            except FileNotFoundError:
                self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
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
        if path.startswith("/datasets/"):
            self.serve_file(DATASETS_DIR / path.removeprefix("/datasets/"))
            return
        if path == "/" or path == "/index.html":
            self.serve_file(STATIC_DIR / "index.html")
            return
        self.serve_file(STATIC_DIR / path.lstrip("/"))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        prompt_match = re.fullmatch(r"/api/prompts/([A-Za-z0-9_-]+)", path)
        if prompt_match:
            try:
                self.write_json({"prompt": soft_delete_prompt(prompt_match.group(1))})
            except FileNotFoundError:
                self.write_json({"error": "prompt not found"}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        dataset_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)", path)
        if dataset_match:
            try:
                self.write_json({"deleted": [delete_dataset(dataset_match.group(1))], "failed": [], "count": 1})
            except FileNotFoundError:
                self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        job_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)", path)
        if not job_match:
            self.write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        job_id = job_match.group(1)
        try:
            delete_dataset(job_id)
            self.write_json({"ok": True, "job_id": job_id})
        except FileNotFoundError:
            self.write_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/prompts":
            try:
                self.write_json({"prompt": create_prompt(self.read_json_body())}, status=HTTPStatus.CREATED)
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        prompt_action_match = re.fullmatch(r"/api/prompts/([A-Za-z0-9_-]+)/(copy|enable|disable|set-default|rollback|test)", parsed.path)
        if prompt_action_match:
            prompt_id, action = prompt_action_match.group(1), prompt_action_match.group(2)
            try:
                body = self.read_json_body()
                if action == "copy":
                    self.write_json({"prompt": copy_prompt(prompt_id)})
                elif action == "enable":
                    self.write_json({"prompt": set_prompt_status(prompt_id, "enabled")})
                elif action == "disable":
                    self.write_json({"prompt": set_prompt_status(prompt_id, "disabled")})
                elif action == "set-default":
                    self.write_json({"prompt": set_default_prompt(prompt_id)})
                elif action == "rollback":
                    self.write_json({"prompt": rollback_prompt(prompt_id, body)})
                elif action == "test":
                    self.write_json(test_prompt(prompt_id, body))
            except FileNotFoundError:
                self.write_json({"error": "prompt not found"}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/datasets/delete":
            try:
                self.write_json(delete_datasets(self.read_json_body()))
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/datasets/convert":
            try:
                self.write_json(start_convert_task(self.read_json_body()))
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        draft_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)/annotations/second/draft", parsed.path)
        if draft_match:
            try:
                self.write_json(save_second_annotation(draft_match.group(1), self.read_json_body(), "draft"))
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        submit_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)/annotations/second/submit", parsed.path)
        if submit_match:
            try:
                self.write_json(save_second_annotation(submit_match.group(1), self.read_json_body(), "submit"))
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        overwrite_match = re.fullmatch(r"/api/datasets/([A-Za-z0-9_-]+)/annotations/overwrite", parsed.path)
        if overwrite_match:
            try:
                self.write_json(save_second_annotation(overwrite_match.group(1), self.read_json_body(), "overwrite"))
            except Exception as exc:
                traceback.print_exc()
                self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        template_match = re.fullmatch(r"/api/prompt-templates/([A-Za-z0-9_-]+)", parsed.path)
        if template_match:
            try:
                payload = self.read_json_body()
                template_id = normalize_prompt_template_id(template_match.group(1))
                existing = get_prompt(template_id, include_deleted=False)
                name = clean_text(payload.get("name"), str((existing or {}).get("name") or template_id))
                category = clean_text(payload.get("category"), legacy_prompt_category(existing) if existing else "layout")
                if category not in PROMPT_TEMPLATE_CATEGORIES:
                    raise ValueError("invalid prompt template category")
                prompt = clean_text(payload.get("prompt"), str((existing or {}).get("content") or ""))
                if len(prompt) < 20:
                    raise ValueError("prompt template is too short")
                record_payload = {
                    "id": template_id,
                    "name": name,
                    "type": "data_annotation",
                    "task_type": "layout_analysis" if category == "layout" else "custom",
                    "model_name": (existing or {}).get("model_name") or "all",
                    "content": prompt,
                    "status": (existing or {}).get("status") or "enabled",
                    "is_default": bool((existing or {}).get("is_default", template_id == DEFAULT_PROMPT_TEMPLATE_ID)),
                    "description": (existing or {}).get("description") or "",
                }
                prompt_record = update_prompt(template_id, record_payload) if existing else create_prompt(record_payload)
                PROMPT_TEMPLATES[template_id] = {"id": template_id, "name": name, "category": category, "prompt": prompt}
                save_prompt_templates()
                self.write_json({"prompt_template": public_prompt_template({"id": prompt_record["id"], "name": prompt_record["name"], "category": category, "prompt": prompt_record["content"]})})
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

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        prompt_match = re.fullmatch(r"/api/prompts/([A-Za-z0-9_-]+)", unquote(parsed.path))
        if not prompt_match:
            self.write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            self.write_json({"prompt": update_prompt(prompt_match.group(1), self.read_json_body())})
        except FileNotFoundError:
            self.write_json({"error": "prompt not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

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
            allowed_roots = [STATIC_DIR.resolve(), DATASETS_DIR.resolve()]
            if LEGACY_JOBS_DIR.exists():
                allowed_roots.append(LEGACY_JOBS_DIR.resolve())
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
migrate_legacy_prompt_templates()


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF layout analysis preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    ensure_dataset_storage()
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
