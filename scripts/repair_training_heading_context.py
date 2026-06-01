#!/usr/bin/env python3
"""Repair training_samples.jsonl prompt hierarchy context from annotations."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from features.layout_analysis.service import normalize_annotation_block, repair_training_samples_from_annotations, training_jsonl_path  # noqa: E402
from features.layout_analysis.storage import annotation_file_for, iter_result_files, read_job_result, read_json_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild training_samples.jsonl so each page prompt uses the corrected paragraph_title hierarchy from annotations."
    )
    parser.add_argument("--job-id", action="append", help="Repair only the given dataset/job id. Can be passed multiple times.")
    parser.add_argument(
        "--include-missing",
        action="store_true",
        help="Generate training_samples.jsonl for datasets that do not already have one.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be repaired without writing files.")
    return parser.parse_args()


def active_annotation_path(job_id: str) -> Optional[Path]:
    return annotation_file_for(job_id, "draft") or annotation_file_for(job_id, "second") or annotation_file_for(job_id, "first")


def blocks_by_page_from_annotation(annotation: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    blocks_by_page: Dict[int, List[Dict[str, Any]]] = {}
    pages = annotation.get("pages")
    if not isinstance(pages, list):
        return blocks_by_page
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = int(page.get("page_id") or 0)
        raw_blocks = page.get("blocks")
        blocks_by_page[page_id] = [
            normalize_annotation_block(block, page_id)
            for block in (raw_blocks or [])
            if isinstance(block, dict)
        ]
    return blocks_by_page


def selected_job_ids(args: argparse.Namespace) -> List[str]:
    if args.job_id:
        return [str(job_id).strip() for job_id in args.job_id if str(job_id).strip()]
    return [path.parent.name for path in iter_result_files()]


def repair_job(job_id: str, include_missing: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    payload = read_job_result(job_id)
    training_path = training_jsonl_path(job_id)
    if not include_missing and not training_path.is_file():
        return {"job_id": job_id, "status": "skipped", "reason": "training_samples.jsonl not found"}

    annotation_path = active_annotation_path(job_id)
    if not annotation_path:
        return {"job_id": job_id, "status": "skipped", "reason": "annotation not found"}

    annotation = read_json_file(annotation_path, {})
    if not isinstance(annotation, dict):
        return {"job_id": job_id, "status": "skipped", "reason": "annotation is not an object"}

    blocks_by_page = blocks_by_page_from_annotation(annotation)
    if dry_run:
        return {
            "job_id": job_id,
            "status": "would_repair",
            "training_samples": str(training_path),
            "annotation": str(annotation_path),
            "pages": len(blocks_by_page),
        }

    output_path = repair_training_samples_from_annotations(job_id, payload, blocks_by_page)
    return {
        "job_id": job_id,
        "status": "repaired",
        "training_samples": str(output_path),
        "annotation": str(annotation_path),
        "pages": len(blocks_by_page),
    }


def main() -> None:
    args = parse_args()
    results = [repair_job(job_id, include_missing=args.include_missing, dry_run=args.dry_run) for job_id in selected_job_ids(args)]
    repaired = sum(1 for item in results if item["status"] == "repaired")
    would_repair = sum(1 for item in results if item["status"] == "would_repair")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    for item in results:
        detail = item.get("training_samples") or item.get("reason") or ""
        print(f"{item['status']}: {item['job_id']} {detail}".rstrip())
    print(f"summary: repaired={repaired} would_repair={would_repair} skipped={skipped}")


if __name__ == "__main__":
    main()
