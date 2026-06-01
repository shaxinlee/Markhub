"""HTTP handler and API endpoints for the bounding-box annotation feature.

This module handles all HTTP routing and JSON serialization for the
bounding-box feature. It imports from service, storage, and schemas
but follows the rule that handlers should not directly touch files.
"""

from __future__ import annotations

import base64
import json
import re
import traceback
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse, unquote

from .paths import IMAGES_DIR
from .service import (
    add_images,
    create_dataset,
    create_label,
    delete_annotation,
    get_annotations,
    get_dataset,
    get_default_labels,
    get_job,
    list_datasets,
    list_labels,
    remove_dataset,
    remove_image,
    remove_label,
    save_annotation,
    save_draft,
    submit_version,
    update_dataset,
    update_label,
)
from .storage import dataset_dir, ensure_dataset_storage, images_dir_for_dataset


class BoundingBoxHandler:
    def __init__(self, handler: Any) -> None:
        self._h = handler

    def write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._h.send_response(status)
        self._h.send_header("Content-Type", "application/json; charset=utf-8")
        self._h.send_header("Cache-Control", "no-store")
        self._h.send_header("Content-Length", str(len(data)))
        self._h.end_headers()
        self._h.wfile.write(data)

    def write_file(self, content: bytes, content_type: str = "application/octet-stream") -> None:
        self._h.send_response(HTTPStatus.OK)
        self._h.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self._h.send_header("Cache-Control", "no-store")
        self._h.send_header("Content-Length", str(len(content)))
        self._h.end_headers()
        self._h.wfile.write(content)

    def handle(self, path: str) -> bool:
        parsed = urlparse(path)
        route_path = unquote(parsed.path)

        ensure_dataset_storage()

        if route_path == "/api/bounding-box/datasets" and self._h.command == "GET":
            self._list_datasets()
            return True

        datasets_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)", route_path)
        if datasets_match and self._h.command == "GET":
            self._get_dataset(datasets_match.group(1))
            return True

        datasets_post_match = re.fullmatch(r"/api/bounding-box/datasets", route_path)
        if datasets_post_match and self._h.command == "POST":
            self._create_dataset()
            return True

        datasets_update_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)", route_path)
        if datasets_update_match and self._h.command in ("PATCH", "PUT"):
            self._update_dataset(datasets_update_match.group(1))
            return True

        datasets_delete_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)", route_path)
        if datasets_delete_match and self._h.command == "DELETE":
            self._delete_dataset(datasets_delete_match.group(1))
            return True

        jobs_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/job", route_path)
        if jobs_match and self._h.command == "GET":
            self._get_job(jobs_match.group(1))
            return True

        images_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/images", route_path)
        if images_match and self._h.command == "POST":
            self._add_images(images_match.group(1))
            return True

        image_delete_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/images/([A-Za-z0-9_-]+)", route_path)
        if image_delete_match and self._h.command == "DELETE":
            self._delete_image(image_delete_match.group(1), image_delete_match.group(2))
            return True

        image_serve_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/images/(.+)", route_path)
        if image_serve_match and self._h.command == "GET":
            self._serve_image(image_serve_match.group(1), image_serve_match.group(2))
            return True

        annotations_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/annotations", route_path)
        if annotations_match and self._h.command == "GET":
            self._get_annotations(annotations_match.group(1))
            return True

        annotation_save_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/images/([A-Za-z0-9_-]+)/annotations", route_path)
        if annotation_save_match and self._h.command == "POST":
            self._save_annotation(annotation_save_match.group(1), annotation_save_match.group(2))
            return True

        annotation_delete_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/images/([A-Za-z0-9_-]+)/annotations/([A-Za-z0-9_-]+)", route_path)
        if annotation_delete_match and self._h.command == "DELETE":
            self._delete_annotation(annotation_delete_match.group(1), annotation_delete_match.group(2), annotation_delete_match.group(3))
            return True

        draft_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/draft", route_path)
        if draft_match and self._h.command == "PUT":
            self._save_draft(draft_match.group(1))
            return True

        submit_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/submit", route_path)
        if submit_match and self._h.command == "POST":
            self._submit_version(submit_match.group(1))
            return True

        labels_match = re.fullmatch(r"/api/bounding-box/labels", route_path)
        if labels_match and self._h.command == "GET":
            self._get_labels()
            return True

        labels_list_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/labels", route_path)
        if labels_list_match and self._h.command == "GET":
            self._list_labels(labels_list_match.group(1))
            return True

        labels_create_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/labels", route_path)
        if labels_create_match and self._h.command == "POST":
            self._create_label(labels_create_match.group(1))
            return True

        label_update_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/labels/([A-Za-z0-9_-]+)", route_path)
        if label_update_match and self._h.command in ("PATCH", "PUT"):
            self._update_label(label_update_match.group(1), label_update_match.group(2))
            return True

        label_delete_match = re.fullmatch(r"/api/bounding-box/datasets/([A-Za-z0-9_-]+)/labels/([A-Za-z0-9_-]+)", route_path)
        if label_delete_match and self._h.command == "DELETE":
            self._delete_label(label_delete_match.group(1), label_delete_match.group(2))
            return True

        return False

    def _list_datasets(self) -> None:
        try:
            datasets = list_datasets()
            self.write_json({"datasets": datasets})
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _get_dataset(self, dataset_id: str) -> None:
        try:
            dataset = get_dataset(dataset_id)
            self.write_json(dataset)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _create_dataset(self) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body)

            name = data.get("name", "新建数据集")
            description = data.get("description", "")
            labels = data.get("labels")

            dataset = create_dataset(name, description, labels)
            self.write_json(dataset, status=HTTPStatus.CREATED)
        except json.JSONDecodeError:
            self.write_json({"error": "invalid JSON body"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _update_dataset(self, dataset_id: str) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body)

            dataset = update_dataset(dataset_id, data)
            self.write_json(dataset)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _delete_dataset(self, dataset_id: str) -> None:
        try:
            result = remove_dataset(dataset_id)
            self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _get_job(self, dataset_id: str) -> None:
        try:
            job = get_job(dataset_id)
            self.write_json(job)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _add_images(self, dataset_id: str) -> None:
        try:
            content_type = self._h.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                self._handle_multipart_images(dataset_id)
            else:
                content_length = int(self._h.headers.get("Content-Length", 0))
                body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                data = json.loads(body)
                files = data.get("files", [])
                result = add_images(dataset_id, files)
                self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _handle_multipart_images(self, dataset_id: str) -> None:
        content_length = int(self._h.headers.get("Content-Length", 0))
        body = self._h.rfile.read(content_length)

        boundary_match = re.search(rb'boundary=(.+)', self._h.headers.get("Content-Type", "").encode())
        if not boundary_match:
            self.write_json({"error": "no boundary found"}, status=HTTPStatus.BAD_REQUEST)
            return

        boundary = boundary_match.group(1).decode()
        parts = body.split(f"--{boundary}".encode())

        files = []
        for part in parts:
            if b"filename=" not in part or b"Content-Type:" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue

            header = part[:header_end].decode("utf-8", errors="replace")
            filename_match = re.search(r'filename="([^"]+)"', header)
            if not filename_match:
                continue
            filename = filename_match.group(1)

            file_content = part[header_end + 4:]
            if file_content.endswith(b"\r\n"):
                file_content = file_content[:-2]

            files.append({
                "filename": filename,
                "content": file_content,
            })

        if files:
            result = add_images(dataset_id, files)
            self.write_json(result)
        else:
            self.write_json({"added": [], "total": 0})

    def _delete_image(self, dataset_id: str, image_id: str) -> None:
        try:
            result = remove_image(dataset_id, image_id)
            self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "image not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _serve_image(self, dataset_id: str, filename: str) -> None:
        try:
            img_dir = images_dir_for_dataset(dataset_id)
            image_path = img_dir / filename

            if not image_path.exists():
                self.write_json({"error": "image not found"}, status=HTTPStatus.NOT_FOUND)
                return

            content = image_path.read_bytes()
            suffix = Path(filename).suffix.lower()

            content_types = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
            }
            content_type = content_types.get(suffix, "application/octet-stream")

            self._h.send_response(HTTPStatus.OK)
            self._h.send_header("Content-Type", content_type)
            self._h.send_header("Cache-Control", "max-age=86400")
            self._h.send_header("Content-Length", str(len(content)))
            self._h.end_headers()
            self._h.wfile.write(content)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _get_annotations(self, dataset_id: str) -> None:
        try:
            annotations = get_annotations(dataset_id)
            self.write_json({"annotations": annotations})
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _save_annotation(self, dataset_id: str, image_id: str) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body)

            annotation = save_annotation(dataset_id, image_id, data)
            self.write_json(annotation)
        except FileNotFoundError:
            self.write_json({"error": "annotation or dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _delete_annotation(self, dataset_id: str, image_id: str, annotation_id: str) -> None:
        try:
            result = delete_annotation(dataset_id, image_id, annotation_id)
            self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "annotation not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _save_draft(self, dataset_id: str) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body)

            annotations = data.get("annotations", {})
            result = save_draft(dataset_id, annotations)
            self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _submit_version(self, dataset_id: str) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body) if body.strip() else {}
            annotations = data.get("annotations") if isinstance(data, dict) else None
            result = submit_version(dataset_id, annotations)
            self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _get_labels(self) -> None:
        try:
            labels = get_default_labels()
            self.write_json({"labels": labels})
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _list_labels(self, dataset_id: str) -> None:
        try:
            labels = list_labels(dataset_id)
            self.write_json({"labels": labels})
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _create_label(self, dataset_id: str) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body)
            label = create_label(dataset_id, data)
            self.write_json(label, status=HTTPStatus.CREATED)
        except FileNotFoundError:
            self.write_json({"error": "dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _update_label(self, dataset_id: str, label_id: str) -> None:
        try:
            content_length = int(self._h.headers.get("Content-Length", 0))
            body = self._h.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            data = json.loads(body)
            label = update_label(dataset_id, label_id, data)
            self.write_json(label)
        except FileNotFoundError:
            self.write_json({"error": "label or dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _delete_label(self, dataset_id: str, label_id: str) -> None:
        try:
            result = remove_label(dataset_id, label_id)
            self.write_json(result)
        except FileNotFoundError:
            self.write_json({"error": "label or dataset not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)


def register(handler_class: type) -> None:
    original_do_GET = getattr(handler_class, 'do_GET', None)
    original_do_POST = getattr(handler_class, 'do_POST', None)
    original_do_PUT = getattr(handler_class, 'do_PUT', None)
    original_do_PATCH = getattr(handler_class, 'do_PATCH', None)
    original_do_DELETE = getattr(handler_class, 'do_DELETE', None)

    def wrapped_do_GET(self: Any) -> None:
        bbox_handler = BoundingBoxHandler(self)
        if bbox_handler.handle(self.path):
            return
        if original_do_GET:
            original_do_GET(self)
        else:
            self.send_error(405, 'Method Not Allowed')

    def wrapped_do_POST(self: Any) -> None:
        bbox_handler = BoundingBoxHandler(self)
        if bbox_handler.handle(self.path):
            return
        if original_do_POST:
            original_do_POST(self)
        else:
            self.send_error(405, 'Method Not Allowed')

    def wrapped_do_PUT(self: Any) -> None:
        bbox_handler = BoundingBoxHandler(self)
        if bbox_handler.handle(self.path):
            return
        if original_do_PUT:
            original_do_PUT(self)
        else:
            self.send_error(405, 'Method Not Allowed')

    def wrapped_do_PATCH(self: Any) -> None:
        bbox_handler = BoundingBoxHandler(self)
        if bbox_handler.handle(self.path):
            return
        if original_do_PATCH:
            original_do_PATCH(self)
        else:
            self.send_error(405, 'Method Not Allowed')

    def wrapped_do_DELETE(self: Any) -> None:
        bbox_handler = BoundingBoxHandler(self)
        if bbox_handler.handle(self.path):
            return
        if original_do_DELETE:
            original_do_DELETE(self)
        else:
            self.send_error(405, 'Method Not Allowed')

    handler_class.do_GET = wrapped_do_GET
    handler_class.do_POST = wrapped_do_POST
    handler_class.do_PUT = wrapped_do_PUT
    handler_class.do_PATCH = wrapped_do_PATCH
    handler_class.do_DELETE = wrapped_do_DELETE


def main() -> None:
    print("BoundingBox API registered", file=__import__("sys").stderr)
