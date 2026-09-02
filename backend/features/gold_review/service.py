"""Safe persistence and validation for the nested gold-standard dataset."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DATA_LOCK = threading.RLock()
REVIEW_STATUSES = {
    "requires_independent_human_review",
    "in_progress",
    "human_reviewed",
}
ALLOWED = {
    "规则类型": ["义务", "禁止", "许可", "责任", "审批", "后果", "处罚", "定义", "适用范围", "其他"],
    "主体角色": ["适用主体", "责任主体", "执行主体", "审批主体", "处理对象", "权利主体", "其他"],
    "动作类型": ["制定", "审批", "执行", "监督", "报告", "披露", "备案", "申报", "培训", "考核", "其他"],
    "对象类型": ["事项", "文件", "资金", "岗位", "人员", "其他"],
    "约束类型": ["时间", "金额", "数量", "审批", "前提", "顺序", "例外", "其他"],
    "来源类别": ["时间约束", "数量约束", "审批要求", "适用条件", "例外情形"],
    "后果类型": ["处罚", "整改", "责任", "追责", "其他"],
    "参照目标类型": ["法律法规", "监管规则", "内部制度", "公司章程", "其他"],
}
STRICT_FIELDS = {
    "主体名称", "主体别名", "动作名称", "对象名称", "约束内容", "关联事项",
    "触发条件", "处理措施", "处理对象", "执行主体", "参照目标", "文号",
}


def gold_root() -> Path:
    configured = os.getenv("MARKHUB_GOLD_STANDARD_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[4] / "gold_standard"


def data_path() -> Path:
    return gold_root() / "gold_standard.jsonl"


def schema_path() -> Path:
    return gold_root() / "output_schema.json"


def _normalized(value: str) -> str:
    value = value.replace("責任", "责任").replace("行為", "行为")
    return re.sub(r"\s+|---|#{1,6}", "", value)


def _normalized_document(value: str) -> str:
    value = re.sub(r"(?m)^\s*---\s*$", "", value)
    value = re.sub(r"(?m)^\s*\d+\s*$", "", value)
    return _normalized(value)


def _revision(path: Path | None = None) -> str:
    target = path or data_path()
    return hashlib.sha256(target.read_bytes()).hexdigest()[:16]


def _read_rows() -> list[dict[str, Any]]:
    target = data_path()
    if not target.is_file():
        raise FileNotFoundError(f"gold standard not found: {target}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"line {number} must be a JSON object")
        rows.append(value)
    return rows


def _schema() -> dict[str, Any]:
    value = json.loads(schema_path().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("output_schema.json must be an object")
    return value


def _exact_shape(value: Any, template: Any, path: str = "gold_answer") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if isinstance(template, dict):
        if not isinstance(value, dict):
            return [{"severity": "error", "code": "schema_type", "path": path, "message": "应为对象"}]
        missing = set(template) - set(value)
        extra = set(value) - set(template)
        for key in sorted(missing):
            issues.append({"severity": "error", "code": "schema_missing", "path": f"{path}.{key}", "message": "缺少必需字段"})
        for key in sorted(extra):
            issues.append({"severity": "error", "code": "schema_extra", "path": f"{path}.{key}", "message": "存在 schema 未定义字段"})
        for key in template.keys() & value.keys():
            issues.extend(_exact_shape(value[key], template[key], f"{path}.{key}"))
        return issues
    if isinstance(template, list):
        if not isinstance(value, list):
            return [{"severity": "error", "code": "schema_type", "path": path, "message": "应为数组"}]
        if not template:
            for index, item in enumerate(value):
                if not isinstance(item, str):
                    issues.append({"severity": "error", "code": "schema_type", "path": f"{path}[{index}]", "message": "应为字符串"})
        else:
            for index, item in enumerate(value):
                issues.extend(_exact_shape(item, template[0], f"{path}[{index}]"))
        return issues
    if value is not None and not isinstance(value, str):
        issues.append({"severity": "error", "code": "schema_type", "path": path, "message": "应为字符串或 null"})
    return issues


def _leaves(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, path + (str(index),))
    else:
        yield path, value


def validate_unit(unit: dict[str, Any]) -> dict[str, Any]:
    answer = unit.get("gold_answer")
    issues = _exact_shape(answer, _schema())
    if not isinstance(answer, dict) or issues:
        return _validation_payload(issues)

    input_text = str(unit.get("input_text") or "")
    evidence = _normalized(input_text)
    source_root_value = os.getenv("MARKHUB_GOLD_SOURCE_ROOT", "").strip()
    source_root = Path(source_root_value).expanduser().resolve() if source_root_value else gold_root().parent / "layout" / "data" / "公司制度"
    source_value = str(unit.get("source_markdown") or "")
    try:
        source_path = Path(source_value).expanduser().resolve()
        if source_root.resolve() not in source_path.parents or not source_path.is_file():
            issues.append({"severity": "error", "code": "source_path", "path": "source_markdown", "message": "来源文件不存在或不在允许的公司制度目录中"})
        else:
            source_bytes = source_path.read_bytes()
            actual_hash = hashlib.sha256(source_bytes).hexdigest()
            if actual_hash != unit.get("source_sha256"):
                issues.append({"severity": "error", "code": "source_hash", "path": "source_sha256", "message": "来源文件 SHA-256 已变化"})
            source_document = _normalized_document(source_bytes.decode("utf-8"))
            if _normalized(str(unit.get("source_text") or "")) not in source_document:
                issues.append({"severity": "error", "code": "source_text_grounding", "path": "source_text", "message": "source_text 无法在来源 Markdown 中回溯"})
            if _normalized(str(unit.get("document_name") or "")) not in source_document:
                issues.append({"severity": "error", "code": "document_name_grounding", "path": "document_name", "message": "制度名称无法在来源 Markdown 中回溯"})
    except (OSError, UnicodeError) as exc:
        issues.append({"severity": "error", "code": "source_read", "path": "source_markdown", "message": f"读取来源文件失败：{exc}"})

    document = answer["制度文件"]
    if document["制度名称"] != unit.get("document_name"):
        issues.append({"severity": "error", "code": "document_name", "path": "gold_answer.制度文件.制度名称", "message": "制度名称必须与单元元数据一致"})
    if document["制度条款"]["条款原文"] != input_text:
        issues.append({"severity": "error", "code": "clause_text", "path": "gold_answer.制度文件.制度条款.条款原文", "message": "条款原文必须与 input_text 完全一致"})

    for path_parts, value in _leaves(answer):
        field = next((part for part in reversed(path_parts) if not part.isdigit()), "")
        path = "gold_answer." + ".".join(path_parts)
        if field in ALLOWED and value is not None and value not in ALLOWED[field]:
            issues.append({"severity": "error", "code": "controlled_value", "path": path, "message": f"“{value}”不在受控词表中"})
        if field in STRICT_FIELDS and isinstance(value, str) and value and _normalized(value) not in evidence:
            issues.append({"severity": "error", "code": "evidence_span", "path": path, "message": f"“{value}”无法在本条原文中回溯"})

    for rule_index, rule in enumerate(answer["制度规则"]):
        base = f"gold_answer.制度规则.{rule_index}"
        if not rule["行为动作"]:
            issues.append({"severity": "error", "code": "missing_action", "path": f"{base}.行为动作", "message": "每条规则至少需要一个行为动作"})
        requirements = {
            "审批": ("审批主体", "审批规则需要标注审批主体"),
            "责任": ("责任主体", "责任规则需要标注责任主体"),
            "许可": ("权利主体", "有主体的许可规则需要标注权利主体"),
        }
        requirement = requirements.get(rule["规则类型"])
        if requirement and (rule["规则类型"] != "许可" or rule["主体"]):
            if not any(item["主体角色"] == requirement[0] for item in rule["主体"]):
                issues.append({"severity": "error", "code": "subject_role", "path": f"{base}.主体", "message": requirement[1]})
        if rule["规则类型"] == "处罚" and not rule["违规后果"]:
            issues.append({"severity": "error", "code": "missing_consequence", "path": f"{base}.违规后果", "message": "处罚规则需要标注违规后果"})

        for family, key in (("主体", "主体名称"), ("行为动作", "动作名称"), ("行为对象", "对象名称"), ("约束条件", "约束内容"), ("参照制度", "参照目标")):
            values = [_normalized(str(item.get(key) or "")) for item in rule[family] if item.get(key)]
            if len(values) != len(set(values)):
                issues.append({"severity": "error", "code": "duplicate_entity", "path": f"{base}.{family}", "message": f"{family}中存在重复值"})

    return _validation_payload(issues)


def _validation_payload(issues: list[dict[str, str]]) -> dict[str, Any]:
    counts = Counter(item["severity"] for item in issues)
    return {
        "valid": not counts["error"],
        "error_count": counts["error"],
        "warning_count": counts["warning"],
        "issues": issues,
    }


def get_summary() -> dict[str, Any]:
    with DATA_LOCK:
        rows = _read_rows()
        documents: dict[str, dict[str, Any]] = {}
        statuses = Counter(str(row.get("review_status") or "requires_independent_human_review") for row in rows)
        total_rules = 0
        invalid = 0
        for row in rows:
            rules = row.get("gold_answer", {}).get("制度规则", [])
            total_rules += len(rules) if isinstance(rules, list) else 0
            if not validate_unit(row)["valid"]:
                invalid += 1
            doc_id = str(row.get("document_id") or "")
            item = documents.setdefault(doc_id, {
                "document_id": doc_id,
                "document_name": row.get("document_name") or "未命名制度",
                "unit_count": 0,
                "reviewed_count": 0,
            })
            item["unit_count"] += 1
            if row.get("review_status") == "human_reviewed":
                item["reviewed_count"] += 1
        return {
            "dataset": "公司制度嵌套信息抽取金标准",
            "revision": _revision(),
            "documents": sorted(documents.values(), key=lambda item: item["document_id"]),
            "document_count": len(documents),
            "unit_count": len(rows),
            "rule_count": total_rules,
            "invalid_unit_count": invalid,
            "status_counts": dict(statuses),
            "vocabularies": ALLOWED,
        }


def list_units(document_id: str = "", review_status: str = "", query: str = "") -> dict[str, Any]:
    with DATA_LOCK:
        rows = _read_rows()
        needle = query.strip().casefold()
        items: list[dict[str, Any]] = []
        for row in rows:
            status = str(row.get("review_status") or "requires_independent_human_review")
            if document_id and row.get("document_id") != document_id:
                continue
            if review_status and status != review_status:
                continue
            haystack = " ".join(str(row.get(key) or "") for key in ("unit_id", "unit_number", "document_name", "input_text")).casefold()
            if needle and needle not in haystack:
                continue
            rules = row.get("gold_answer", {}).get("制度规则", [])
            validation = validate_unit(row)
            items.append({
                "unit_id": row.get("unit_id"),
                "document_id": row.get("document_id"),
                "document_name": row.get("document_name"),
                "unit_index": row.get("unit_index"),
                "unit_number": row.get("unit_number"),
                "input_preview": str(row.get("input_text") or "")[:140],
                "rule_count": len(rules) if isinstance(rules, list) else 0,
                "review_status": status,
                "valid": validation["valid"],
                "error_count": validation["error_count"],
            })
        return {"revision": _revision(), "total": len(items), "units": items}


def get_unit(unit_id: str) -> dict[str, Any]:
    with DATA_LOCK:
        rows = _read_rows()
        unit = next((row for row in rows if row.get("unit_id") == unit_id), None)
        if unit is None:
            raise FileNotFoundError(f"unit not found: {unit_id}")
        return {
            "revision": _revision(),
            "unit": unit,
            "validation": validate_unit(unit),
            "vocabularies": ALLOWED,
        }


def _atomic_write(rows: list[dict[str, Any]]) -> Path:
    target = data_path()
    backup_dir = gold_root() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    backup = backup_dir / f"gold_standard.{stamp}.{uuid.uuid4().hex[:6]}.jsonl"
    shutil.copy2(target, backup)
    temp = target.with_name(f"{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)
    try:
        temp.write_text(payload, encoding="utf-8")
        with temp.open("rb") as stream:
            os.fsync(stream.fileno())
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return backup


def update_unit(unit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with DATA_LOCK:
        rows = _read_rows()
        current_revision = _revision()
        expected_revision = str(payload.get("expected_revision") or "")
        if expected_revision and expected_revision != current_revision:
            raise RuntimeError("数据集已被其他保存操作更新，请刷新该单元后再保存")
        index = next((i for i, row in enumerate(rows) if row.get("unit_id") == unit_id), None)
        if index is None:
            raise FileNotFoundError(f"unit not found: {unit_id}")

        current = rows[index]
        candidate = dict(current)
        if "gold_answer" not in payload:
            raise ValueError("missing gold_answer")
        candidate["gold_answer"] = payload["gold_answer"]
        candidate["adjudication_notes"] = payload.get("adjudication_notes", current.get("adjudication_notes", []))
        requested_status = str(payload.get("review_status") or current.get("review_status") or "in_progress")
        if requested_status not in REVIEW_STATUSES:
            raise ValueError("invalid review_status")
        validation = validate_unit(candidate)
        if requested_status == "human_reviewed" and not validation["valid"]:
            raise ValueError("当前单元存在严格校验错误，不能标记为审查通过")

        now = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
        reviewer = str(payload.get("reviewer") or "independent_human").strip() or "independent_human"
        history = list(current.get("review_history") or [])
        history.append({
            "reviewer": reviewer,
            "reviewed_at": now,
            "status": requested_status,
            "note": str(payload.get("review_note") or "").strip(),
            "previous_revision": current_revision,
        })
        candidate["review_status"] = requested_status
        candidate["reviewed_by"] = reviewer
        candidate["reviewed_at"] = now
        candidate["review_history"] = history
        rows[index] = candidate
        backup = _atomic_write(rows)
        return {
            "revision": _revision(),
            "unit": candidate,
            "validation": validation,
            "backup": str(backup),
        }
