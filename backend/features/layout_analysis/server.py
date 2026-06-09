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

from .paths import (
    BACKEND_DIR,
    CONVERT_TASKS_DIR,
    DATASETS_DIR,
    ENV_FILE,
    FEATURE_DIR,
    FIRST_ANNOTATIONS_DIR,
    JOBS_DIR,
    LEGACY_JOBS_DIR,
    LLAMAFACTORY_DATASETS_DIR,
    PROMPTS_DIR,
    PROMPTS_STORE_FILE,
    PROMPT_TEMPLATES_FILE,
    SECOND_ANNOTATIONS_DIR,
    STATIC_DIR,
    SWIFT_DATASETS_DIR,
)
from .schemas import (
    BLOCK_TYPE_ALIASES,
    BLOCK_TYPES,
    BUILTIN_LAYOUT_PROMPT_REVISION,
    DATASET_LABEL_TYPES,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_PDF_BYTES,
    DEFAULT_MODEL,
    DEFAULT_PROMPT_TEMPLATE_ID,
    ENV_CONFIG_KEYS,
    LEVELS,
    LLMConfig,
    ModelPageImage,
    PROMPT_STATUS,
    PROMPT_TASK_TYPES,
    PROMPT_TEMPLATE_CATEGORIES,
    PROMPT_TYPES,
    PageImage,
    PromptTemplate,
    RESIZE_PRESETS,
    VisionResizeConfig,
)
from .prompts import LAYOUT_PROMPT, PROMPT_TEMPLATES
from .prompts_store import (
    bootstrap_prompt_store,
    copy_prompt,
    create_prompt,
    default_prompt_for_task,
    enforce_default_constraints,
    env_config,
    get_prompt,
    legacy_prompt_category,
    list_prompts,
    log_prompt_operation,
    next_prompt_version,
    normalize_prompt_record,
    normalize_prompt_template_id,
    prompt_now,
    prompt_public,
    prompt_store_payload,
    prompt_template_options,
    public_prompt_template,
    render_prompt,
    resolve_prompt_template,
    rollback_prompt,
    save_prompts,
    set_default_prompt,
    set_prompt_status,
    soft_delete_prompt,
    test_prompt,
    update_prompt,
    validate_prompt_payload,
    validate_prompt_variables,
    version_record,
    write_prompt_store,
)
from .service import (
    build_annotation_payload,
    call_layout_llm,
    collect_done_blocks,
    dataset_summary,
    delete_dataset,
    delete_datasets,
    dimensions_for_page,
    ensure_first_annotation,
    extract_first_json_object,
    image_path_from_page_url,
    image_to_data_url,
    infer_heading_level,
    job_block_from_annotation,
    list_dataset_summaries,
    normalize_annotation_block,
    normalize_bbox,
    normalize_blocks,
    normalize_export_block,
    normalize_heading_level,
    normalize_qwen_bbox,
    overwrite_job_blocks,
    parse_model_json,
    prepare_portable_image_ref,
    process_job_pages,
    qwen_bbox_to_model_pixels,
    read_annotation_payload,
    render_pdf_to_images,
    resize_page_for_model,
    resolve_convert_output_dir,
    run_convert_task,
    samples_from_annotation,
    save_second_annotation,
    scale_bbox,
    start_analysis_job,
    start_convert_task,
    write_dataset_info,
    write_split_files,
)
from .storage import (
    CONVERT_TASKS,
    annotation_file_for,
    clean_old_jobs,
    convert_task_path,
    count_finished_pages,
    dataset_dir,
    dataset_state_path,
    default_dataset_state,
    ensure_dataset_storage,
    find_job_dir,
    first_annotation_path,
    iso_now,
    iso_to_sort_value,
    iter_result_files,
    job_asset_path,
    job_dir_for_model,
    job_storage_roots,
    legacy_dataset_dir,
    legacy_dataset_state_path,
    list_job_summaries,
    model_dir_name,
    normalize_job_payload,
    now_timestamp,
    persist_runtime_config,
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
    align_to_factor,
    clamp_int,
    clean_text,
    load_dotenv,
    max_pdf_bytes,
    normalize_block_type,
    portable_path_ref,
    read_env_file,
    safe_path_name,
    sanitize_saved_text,
    write_env_file,
)

from features.bounding_box import register as register_bounding_box

load_dotenv()


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
            layout_datasets = list_dataset_summaries()
            for ds in layout_datasets:
                ds["annotation_type"] = "layout"
            try:
                from features.bounding_box.storage import list_bounding_box_datasets
                bbox_datasets = list_bounding_box_datasets()
                for ds in bbox_datasets:
                    ds["annotation_type"] = "bounding_box"
                all_datasets = layout_datasets + bbox_datasets
                all_datasets.sort(key=lambda x: x.get("updated_at", 0) or x.get("created_at", ""), reverse=True)
                self.write_json({"datasets": all_datasets})
            except Exception:
                self.write_json({"datasets": layout_datasets})
            return
        convert_match = re.fullmatch(r"/api/datasets/convert/([A-Za-z0-9_-]+)", path)
        if convert_match:
            task_id = convert_match.group(1)
            task = read_convert_task(task_id)
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


def parse_resize_config(fields: Dict[str, Any]) -> VisionResizeConfig:
    preset = clean_text(fields.get("qwen_preset"), env_config()["qwen_preset"])
    if preset not in RESIZE_PRESETS and preset != "custom":
        preset = "default"
    image_profile = clean_text(fields.get("qwen_image_profile"), env_config().get("qwen_image_profile", "qwen3_6"))
    if image_profile not in {"qwen3_6", "qwen3_5"}:
        image_profile = "qwen3_6"

    if preset in RESIZE_PRESETS:
        width, height = RESIZE_PRESETS[preset]
    else:
        width = clamp_int(fields.get("qwen_width"), default=int(env_config()["qwen_width"]), minimum=1024, maximum=4096)
        height = clamp_int(fields.get("qwen_height"), default=int(env_config()["qwen_height"]), minimum=1024, maximum=6144)

    width = align_to_factor(width, 32)
    height = align_to_factor(height, 32)
    if width * height <= 0:
        raise ValueError("invalid Qwen resize dimensions")
    return VisionResizeConfig(width=width, height=height, preset=preset, factor=32, image_profile=image_profile)


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF layout analysis preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    ensure_dataset_storage()
    bootstrap_prompt_store()
    register_bounding_box(LayoutAnalyzerHandler)
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
