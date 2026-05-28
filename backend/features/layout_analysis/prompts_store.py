"""Prompt CRUD store backed by ``backend/datasets/prompt_templates/prompts.json``.

This is the **single source of truth** for prompt templates. The legacy
``backend/prompt_templates.json`` is read once during ``bootstrap_prompt_store``
to migrate older deployments, but is never written from runtime code paths.

Naming: ``prompts.py`` already owns ``LAYOUT_PROMPT`` and the read-only
``PROMPT_TEMPLATES`` constant registry. ``prompts_store.py`` owns the dynamic
JSON store, mirroring how ``storage.py`` sits beside ``schemas.py``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .paths import PROMPTS_STORE_FILE, PROMPT_TEMPLATES_FILE
from .prompts import LAYOUT_PROMPT, PROMPT_TEMPLATES
from .schemas import (
    BUILTIN_LAYOUT_PROMPT_REVISION,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROMPT_TEMPLATE_ID,
    LLMConfig,
    PROMPT_STATUS,
    PROMPT_TASK_TYPES,
    PROMPT_TEMPLATE_CATEGORIES,
    PROMPT_TYPES,
    PromptTemplate,
)
from .storage import iso_now, iso_to_sort_value, read_json_file, write_json_file
from .utils import clamp_int, clean_text, max_pdf_bytes


# --------------------------------------------------------------------------
# Identifiers and serialization helpers
# --------------------------------------------------------------------------

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


def prompt_now() -> str:
    return iso_now()


def legacy_prompt_category(prompt: Dict[str, Any]) -> str:
    task_type = str(prompt.get("task_type") or "")
    if task_type == "layout_analysis":
        return "layout"
    return "layout" if prompt.get("type") == "data_annotation" else "text_transcription"


# --------------------------------------------------------------------------
# Store-level IO
# --------------------------------------------------------------------------

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
        "description": "系统内置的文档版面分析 Prompt，识别标题、正文、目录、表格、公式、图表、图片、页眉页脚、脚注、手写字和印章。",
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
        "notes": f"系统默认提示词，可复制后创建自定义版本。revision={BUILTIN_LAYOUT_PROMPT_REVISION}",
        "usage_scenarios": ["数据自动标注", "文档版面分析"],
        "versions": [],
        "operation_logs": [],
    }
    record["versions"] = [version_record(record, "初始化默认提示词", "system")]
    return record


def save_prompts(prompts: List[Dict[str, Any]]) -> None:
    payload = prompt_store_payload()
    payload["prompts"] = prompts
    write_prompt_store(payload)


# --------------------------------------------------------------------------
# Validation and version bookkeeping
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Query and CRUD
# --------------------------------------------------------------------------

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


def enforce_default_constraints(prompts: List[Dict[str, Any]], default_prompt_id: Optional[str] = None) -> None:
    seen_defaults: set = set()
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


# --------------------------------------------------------------------------
# Variable rendering and ad-hoc test execution
# --------------------------------------------------------------------------

def render_prompt(content: str, values: Dict[str, Any]) -> str:
    def replace(match: "re.Match[str]") -> str:
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


# --------------------------------------------------------------------------
# Resolution helpers consumed by the analyzer service
# --------------------------------------------------------------------------

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
        "max_pdf_bytes": str(max_pdf_bytes()),
        "qwen_preset": os.getenv("QWEN_RESIZE_PRESET", "default"),
        "qwen_width": os.getenv("QWEN_RESIZED_WIDTH", "1536"),
        "qwen_height": os.getenv("QWEN_RESIZED_HEIGHT", "2176"),
        "prompt_template_id": str((default_layout_prompt or {}).get("id") or DEFAULT_PROMPT_TEMPLATE_ID),
    }


# --------------------------------------------------------------------------
# Bootstrap: idempotent migration + builtin upgrade.
# Call from server.main(), never at import time.
# --------------------------------------------------------------------------

def _migrate_legacy_template_file(path: Path = PROMPT_TEMPLATES_FILE) -> None:
    """Pull templates from the deprecated ``backend/prompt_templates.json`` into
    ``prompts.json`` once. Reads the legacy file but never writes it back.
    """
    if not path.is_file():
        return
    try:
        legacy_payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read legacy prompt templates: {exc}", file=sys.stderr)
        return
    items = legacy_payload.get("prompt_templates") if isinstance(legacy_payload, dict) else legacy_payload
    if not isinstance(items, list):
        return

    payload = prompt_store_payload()
    prompts = payload.setdefault("prompts", [])
    existing_ids = {str(item.get("id")) for item in prompts if isinstance(item, dict)}

    changed = False
    for item in items:
        if not isinstance(item, dict):
            continue
        template_id = normalize_prompt_template_id(item.get("id"))
        if not template_id or template_id in existing_ids:
            continue
        category = clean_text(item.get("category"), "layout")
        if category not in PROMPT_TEMPLATE_CATEGORIES:
            category = "layout"
        prompt_text = clean_text(item.get("prompt"), LAYOUT_PROMPT if template_id == DEFAULT_PROMPT_TEMPLATE_ID else "")
        if not prompt_text:
            continue
        record = normalize_prompt_record(
            {
                "id": template_id,
                "name": item.get("name") or template_id,
                "description": "从旧提示词模板迁移而来。",
                "type": "data_annotation",
                "task_type": "layout_analysis" if category == "layout" else "custom",
                "model_name": "all",
                "content": prompt_text,
                "status": "enabled",
                "is_default": template_id == DEFAULT_PROMPT_TEMPLATE_ID,
                "created_by": "system",
            },
            is_new=True,
        )
        prompts.append(record)
        existing_ids.add(template_id)
        changed = True

    if changed:
        enforce_default_constraints(prompts)
        write_prompt_store(payload)


def _migrate_builtin_registry() -> None:
    """Ensure every entry in the read-only ``PROMPT_TEMPLATES`` registry exists
    in ``prompts.json``. Run on first start of older deployments.
    """
    payload = prompt_store_payload()
    prompts = payload.setdefault("prompts", [])
    existing_ids = {str(item.get("id")) for item in prompts if isinstance(item, dict)}
    changed = False
    for template in PROMPT_TEMPLATES.values():
        template_id = str(template.get("id") or "")
        if not template_id or template_id in existing_ids:
            continue
        record = normalize_prompt_record(
            {
                "id": template_id,
                "name": template.get("name") or template_id,
                "description": "从内置模板初始化。",
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
        changed = True
    if changed:
        enforce_default_constraints(prompts)
        write_prompt_store(payload)


def _upgrade_builtin_default_prompt() -> None:
    payload = prompt_store_payload()
    prompts = payload.setdefault("prompts", [])
    changed = False
    for prompt in prompts:
        if not isinstance(prompt, dict) or prompt.get("id") != DEFAULT_PROMPT_TEMPLATE_ID or prompt.get("deleted_at"):
            continue
        notes = str(prompt.get("notes") or "")
        if BUILTIN_LAYOUT_PROMPT_REVISION in notes and prompt.get("content") == LAYOUT_PROMPT:
            return
        prompt["description"] = "系统内置的文档版面分析 Prompt，主动识别标题、正文、目录、表格、公式、图表、图片、页眉页脚、脚注、手写字和印章。"
        prompt["content"] = LAYOUT_PROMPT
        prompt["variables"] = "输入为当前页面图片；模型必须逐类扫描并输出严格 JSON。"
        prompt["version"] = next_prompt_version(str(prompt.get("version") or "v1.0"))
        prompt["updated_at"] = prompt_now()
        prompt["notes"] = f"系统默认提示词，可复制后创建自定义版本。revision={BUILTIN_LAYOUT_PROMPT_REVISION}"
        prompt.setdefault("versions", []).append(version_record(prompt, "升级内置默认提示词：将 list 标签替换为 table_of_contents 目录标签", "system"))
        log_prompt_operation(prompt, "upgrade", f"升级到 {BUILTIN_LAYOUT_PROMPT_REVISION}", "system")
        changed = True
        break
    if changed:
        write_prompt_store(payload)


def bootstrap_prompt_store() -> None:
    """Idempotent. Run once during server startup."""
    _migrate_builtin_registry()
    _migrate_legacy_template_file()
    _upgrade_builtin_default_prompt()
