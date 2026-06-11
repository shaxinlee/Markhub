#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export categorized ground-truth annotations to ms-swift SFT JSONL."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from features.layout_analysis.prompts import LAYOUT_PROMPT  # noqa: E402
from features.layout_analysis.service import build_heading_context, training_prompt_user_from_page  # noqa: E402


GROUND_TRUTH_ROOT = REPO_ROOT / "evaluation" / "datasets" / "ground_truth"
DOC_ROOT = REPO_ROOT / "backend" / "datasets" / "doc"
OUTPUT_ROOT = REPO_ROOT / "backend" / "datasets" / "swift_datasets"
BLOCK_OUTPUT_KEYS = ("id", "text", "description", "bbox", "page_id", "block_type", "level")
HEADING_LEVELS = {"H1", "H2", "H3", "H4"}


@dataclass
class ExportStats:
    categories: int = 0
    files: int = 0
    pages: int = 0
    samples: int = 0
    images: int = 0
    blocks: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ground_truth categories to ms-swift multimodal SFT datasets.")
    parser.add_argument("--ground-truth-root", type=Path, default=GROUND_TRUTH_ROOT)
    parser.add_argument("--doc-root", type=Path, default=DOC_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--category", action="append", help="Export only this category. Repeatable.")
    parser.add_argument("--clean", action="store_true", help="Remove each category output folder before exporting.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def page_size(page: dict[str, Any]) -> tuple[int, int]:
    width = int(page.get("width") or 0)
    height = int(page.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid page size: {width}x{height}")
    return width, height


def normalize_bbox_1000(raw_bbox: Any, width: int, height: int) -> list[int] | None:
    if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except Exception:
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    if x2 <= x1 or y2 <= y1:
        return None

    def clamp(value: float) -> int:
        return max(0, min(1000, int(round(value))))

    return [
        clamp(x1 / width * 1000),
        clamp(y1 / height * 1000),
        clamp(x2 / width * 1000),
        clamp(y2 / height * 1000),
    ]


def block_type_of(block: dict[str, Any]) -> str:
    value = str(block.get("block_type") or block.get("label") or "text")
    return "table_of_contents" if value == "list" else value


def normalize_block(block: dict[str, Any], page_id: int, width: int, height: int, index: int) -> dict[str, Any] | None:
    bbox = normalize_bbox_1000(block.get("bbox_1000") or block.get("bbox"), width, height)
    if bbox is None:
        return None
    block_type = block_type_of(block)
    level = block.get("level")
    description = str(block.get("description") or block.get("chart_description") or "") if block_type in {"chart", "flowchart"} else ""
    return {
        "id": str(block.get("id") or f"p{page_id:03d}_b{index:03d}"),
        "text": str(block.get("text") or ""),
        "description": description,
        "bbox": bbox,
        "page_id": page_id,
        "block_type": block_type,
        "level": level if block_type == "paragraph_title" and level in HEADING_LEVELS else None,
    }


def render_page_image(pdf_path: Path, page: dict[str, Any], target_path: Path) -> None:
    page_id = int(page.get("page_id") or 0)
    width, height = page_size(page)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf_path)) as doc:
        if page_id < 0 or page_id >= doc.page_count:
            raise ValueError(f"{pdf_path.name} has no page_id={page_id}")
        pdf_page = doc[page_id]
        matrix = fitz.Matrix(width / pdf_page.rect.width, height / pdf_page.rect.height)
        pixmap = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(str(target_path))


def sample_for_page(
    category_dir: Path,
    annotation: dict[str, Any],
    annotation_path: Path,
    page: dict[str, Any],
    prior_blocks: list[dict[str, Any]],
    doc_root: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], int]:
    filename = str(annotation.get("filename") or "")
    if not filename:
        raise ValueError(f"{annotation_path} missing filename")
    pdf_path = doc_root / filename
    if not pdf_path.is_file():
        raise FileNotFoundError(f"missing source PDF: {pdf_path}")

    page_id = int(page.get("page_id") or 0)
    width, height = page_size(page)
    raw_blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    blocks = [
        normalized
        for index, block in enumerate(raw_blocks)
        if isinstance(block, dict)
        for normalized in [normalize_block(block, page_id, width, height, index)]
        if normalized is not None
    ]
    if not blocks:
        return None, prior_blocks, 0

    image_rel = Path("images") / annotation_path.stem / f"page_{page_id:03d}.png"
    image_path = category_dir / image_rel
    render_page_image(pdf_path, page, image_path)

    prompt_page = {
        "page_id": page_id,
        "width": width,
        "height": height,
    }
    user_prompt = "<image>\n" + training_prompt_user_from_page(prompt_page, build_heading_context(prior_blocks))
    answer = {
        "image_path": image_rel.as_posix(),
        "blocks": [{key: block[key] for key in BLOCK_OUTPUT_KEYS} for block in blocks],
    }
    sample = {
        "messages": [
            {"role": "system", "content": LAYOUT_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False, separators=(",", ":"))},
        ],
        "images": [image_rel.as_posix()],
    }
    return sample, prior_blocks + blocks, len(blocks)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_category(category_path: Path, doc_root: Path, output_root: Path, clean: bool) -> dict[str, Any]:
    category_name = category_path.name
    category_output = output_root / category_name
    if clean and category_output.exists():
        shutil.rmtree(category_output)
    category_output.mkdir(parents=True, exist_ok=True)

    samples: list[dict[str, Any]] = []
    file_summaries: list[dict[str, Any]] = []
    total_blocks = 0
    total_pages = 0

    for annotation_path in sorted(category_path.glob("*.json")):
        annotation = load_json(annotation_path)
        prior_blocks: list[dict[str, Any]] = []
        file_samples = 0
        file_blocks = 0
        pages = annotation.get("pages") if isinstance(annotation.get("pages"), list) else []
        for page in sorted((item for item in pages if isinstance(item, dict)), key=lambda item: int(item.get("page_id") or 0)):
            sample, prior_blocks, block_count = sample_for_page(
                category_dir=category_output,
                annotation=annotation,
                annotation_path=annotation_path,
                page=page,
                prior_blocks=prior_blocks,
                doc_root=doc_root,
            )
            total_pages += 1
            if sample is None:
                continue
            samples.append(sample)
            file_samples += 1
            file_blocks += block_count
            total_blocks += block_count
        file_summaries.append(
            {
                "file": annotation_path.name,
                "source_pdf": annotation.get("filename"),
                "pages": len(pages),
                "samples": file_samples,
                "blocks": file_blocks,
            }
        )

    if not samples:
        raise RuntimeError(f"No usable samples found for category {category_name}")

    dataset_name = f"{category_name}.jsonl"
    dataset_path = category_output / dataset_name
    write_jsonl(dataset_path, samples)
    manifest = {
        "category": category_name,
        "dataset": dataset_name,
        "format": "ms-swift messages+images JSONL",
        "ground_truth_root": str(category_path.relative_to(REPO_ROOT)),
        "doc_root": str(doc_root.relative_to(REPO_ROOT)) if doc_root.is_relative_to(REPO_ROOT) else str(doc_root),
        "samples": len(samples),
        "pages": total_pages,
        "blocks": total_blocks,
        "files": file_summaries,
        "prompt": {
            "system": "backend/features/layout_analysis/prompt_defaults.json:layout_analysis_system",
            "user": "page_user_text + heading_context generated from previous pages' paragraph_title blocks",
            "bbox": "0-1000 relative coordinates",
        },
        "swift_usage": f"cd {category_output} && export ROOT_IMAGE_DIR=$PWD && swift sft --dataset {dataset_name}",
    }
    (category_output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = parse_args()
    ground_truth_root = args.ground_truth_root.resolve()
    doc_root = args.doc_root.resolve()
    output_root = args.output_root.resolve()

    selected = set(args.category or [])
    category_paths = [
        path
        for path in sorted(ground_truth_root.iterdir())
        if path.is_dir() and (not selected or path.name in selected)
    ]
    if not category_paths:
        raise SystemExit(f"No categories found under {ground_truth_root}")

    stats = ExportStats(categories=len(category_paths))
    manifests = []
    for category_path in category_paths:
        manifest = export_category(category_path, doc_root, output_root, clean=args.clean)
        manifests.append(manifest)
        stats.files += len(manifest["files"])
        stats.pages += int(manifest["pages"])
        stats.samples += int(manifest["samples"])
        stats.images += int(manifest["samples"])
        stats.blocks += int(manifest["blocks"])
        print(f"{manifest['category']}: {manifest['samples']} samples, {manifest['blocks']} blocks")

    index = {
        "format": "ms-swift messages+images JSONL",
        "categories": [manifest["category"] for manifest in manifests],
        "samples": stats.samples,
        "pages": stats.pages,
        "blocks": stats.blocks,
        "outputs": [
            {
                "category": manifest["category"],
                "dataset": str((output_root / manifest["category"] / manifest["dataset"]).relative_to(REPO_ROOT)),
                "manifest": str((output_root / manifest["category"] / "manifest.json").relative_to(REPO_ROOT)),
            }
            for manifest in manifests
        ],
    }
    (output_root / "ground_truth_swift_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"exported {stats.samples} samples across {stats.categories} categories to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
