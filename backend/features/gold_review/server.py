"""HTTP adapter for the gold-standard review workspace."""

from __future__ import annotations

import json
import re
import traceback
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .service import get_summary, get_unit, list_units, update_unit, validate_unit


class GoldReviewHandler:
    def __init__(self, handler: Any) -> None:
        self._h = handler

    def _write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._h.send_response(status)
        self._h.send_header("Content-Type", "application/json; charset=utf-8")
        self._h.send_header("Cache-Control", "no-store")
        self._h.send_header("Content-Length", str(len(data)))
        self._h.end_headers()
        self._h.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self._h.headers.get("Content-Length", "0"))
        value = json.loads(self._h.rfile.read(length).decode("utf-8")) if length else {}
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def handle(self, raw_path: str) -> bool:
        parsed = urlparse(raw_path)
        path = unquote(parsed.path)
        if not path.startswith("/api/gold-review"):
            return False
        try:
            if self._h.command == "GET" and path == "/api/gold-review/summary":
                self._write_json(get_summary())
                return True
            if self._h.command == "GET" and path == "/api/gold-review/units":
                params = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
                self._write_json(list_units(params.get("document_id", ""), params.get("review_status", ""), params.get("q", "")))
                return True
            unit_match = re.fullmatch(r"/api/gold-review/units/([A-Za-z0-9_-]+)", path)
            if unit_match and self._h.command == "GET":
                self._write_json(get_unit(unit_match.group(1)))
                return True
            if unit_match and self._h.command == "PUT":
                self._write_json(update_unit(unit_match.group(1), self._read_json()))
                return True
            validate_match = re.fullmatch(r"/api/gold-review/units/([A-Za-z0-9_-]+)/validate", path)
            if validate_match and self._h.command == "POST":
                body = self._read_json()
                submitted = body.get("unit")
                if not isinstance(submitted, dict) or submitted.get("unit_id") != validate_match.group(1):
                    raise ValueError("unit payload does not match URL")
                unit = get_unit(validate_match.group(1))["unit"]
                unit["gold_answer"] = submitted.get("gold_answer")
                self._write_json({"validation": validate_unit(unit)})
                return True
            self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return True
        except FileNotFoundError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            return True
        except RuntimeError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.CONFLICT)
            return True
        except Exception as exc:
            traceback.print_exc()
            self._write_json({"error": f"{type(exc).__name__}: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return True


def register(handler_class: type) -> None:
    for method in ("GET", "POST", "PUT"):
        attribute = f"do_{method}"
        original = getattr(handler_class, attribute, None)

        def wrapped(self: Any, _original: Any = original) -> None:
            if GoldReviewHandler(self).handle(self.path):
                return
            if _original:
                _original(self)
            else:
                self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "Method Not Allowed")

        setattr(handler_class, attribute, wrapped)
