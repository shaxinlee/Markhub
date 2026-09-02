#!/usr/bin/env python3
"""Gold-review service checks using an isolated copy of the dataset."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from features.gold_review import service  # noqa: E402


def main() -> int:
    original = Path("/home/sdnu_lsx/compliance_review/gold_standard")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "output_schema.json").write_bytes((original / "output_schema.json").read_bytes())
        rows = [json.loads(line) for line in (original / "gold_standard.jsonl").read_text(encoding="utf-8").splitlines()[:2]]
        (root / "gold_standard.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        os.environ["MARKHUB_GOLD_STANDARD_DIR"] = str(root)
        os.environ["MARKHUB_GOLD_SOURCE_ROOT"] = str(Path("/home/sdnu_lsx/compliance_review/layout/data/公司制度"))

        summary = service.get_summary()
        assert summary["unit_count"] == 2
        listing = service.list_units(document_id="D01")
        assert listing["total"] == 2
        detail = service.get_unit("G01-U001")
        assert detail["validation"]["valid"]

        detail["unit"]["gold_answer"]["制度规则"][0]["行为动作"][0]["动作名称"] = "原文不存在的动作"
        failed = service.validate_unit(detail["unit"])
        assert not failed["valid"] and any(issue["code"] == "evidence_span" for issue in failed["issues"])

        detail = service.get_unit("G01-U001")
        saved = service.update_unit("G01-U001", {
            "expected_revision": detail["revision"],
            "gold_answer": detail["unit"]["gold_answer"],
            "adjudication_notes": ["人工检查无误"],
            "review_status": "human_reviewed",
            "review_note": "测试审查",
            "reviewer": "test_reviewer",
        })
        assert saved["unit"]["review_status"] == "human_reviewed"
        assert saved["validation"]["valid"]
        assert Path(saved["backup"]).is_file()
        assert service.get_summary()["status_counts"]["human_reviewed"] == 1

        try:
            service.update_unit("G01-U001", {
                "expected_revision": detail["revision"],
                "gold_answer": detail["unit"]["gold_answer"],
                "review_status": "in_progress",
            })
        except RuntimeError:
            pass
        else:
            raise AssertionError("stale revision was not rejected")

    os.environ.pop("MARKHUB_GOLD_STANDARD_DIR", None)
    os.environ.pop("MARKHUB_GOLD_SOURCE_ROOT", None)
    print("gold_review_checks_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
