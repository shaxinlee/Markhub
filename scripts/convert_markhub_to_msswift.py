#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert Markhub layout-analysis jobs to the ms-swift multimodal SFT format."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOBS_DIR = REPO_ROOT / "backend" / "datasets" / "first_annotations"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "backend" / "datasets" / "swift_datasets" / "markhub_layout_msswift_export"
DEFAULT_DATASET_NAME = "markhub_layout_msswift"

DEFAULT_SYSTEM = "你是一个专业的文档版面分析模型。"
DEFAULT_USER_PROMPT = """<image>
请识别图片中的所有主要版面块，并按照阅读顺序输出严格合法的 JSON。

要求：
- 只输出 JSON，不要输出 Markdown 或解释文字。
- 输出对象必须包含 image_path、blocks、context_before、context_after。
- blocks 中每个对象必须包含 id、text、bbox、page_id、block_type、weak_heading、level。
- bbox 使用 0-1000 相对坐标，格式为 [左上角x, 左上角y, 右下角x, 右下角y]。
- block_type 只能使用 doc_title、paragraph_title、text、list、table、formula、chart、figure_title、image、vision_footnote、header、footer、caption、handwriting、seal。
- doc_title / paragraph_title 需要判断 level，可为 H1、H2、H3；其他类型 level 必须为 null。
- 必须逐类扫描页面：标题、正文、列表、表格、公式、图表、图片/流程图、caption、单位/资料来源、页眉页脚、手写字、印章。
- list 表示项目符号/编号条款/目录式条目；table 表示行列结构；formula 表示数学/化学公式；chart 表示数据图表；header/footer 表示页眉页脚；caption 表示图表公式说明。
- 不要把公式、图表、手写字、印章误标为 image 或 text；不要把 caption、单位说明、资料来源并入主体块。
- formula 表示数学/化学公式；chart 表示柱状图、折线图、饼图等数据图表；header/footer 表示页眉页脚；caption 表示图表公式说明。
- handwriting 表示手写字、手写签名、手写日期、手写批注等；seal 表示印章、签章、骑缝章等。
"""

BLOCK_OUTPUT_KEYS = (
    "id",
    "text",
    "bbox",
    "page_id",
    "block_type",
    "weak_heading",
    "level",
)


@dataclass(frozen=True)
class ConvertStats:
    result_files: int
    samples: int
    skipped_pages: int
    copied_images: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Markhub layout-analysis results into ms-swift messages+images SFT data."
    )
    parser.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS_DIR, help="Markhub jobs directory.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for converted files.")
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME, help="Output dataset file stem.")
    parser.add_argument(
        "--format",
        choices=("jsonl", "json"),
        default="jsonl",
        help="ms-swift supports JSONL and JSON. JSONL is the default.",
    )
    parser.add_argument(
        "--image-source",
        choices=("model", "page"),
        default="model",
        help="Use model_pages images for 0-1000 bbox training, or original rendered page images.",
    )
    parser.add_argument(
        "--no-copy-images",
        action="store_true",
        help="Reference existing image files instead of copying them into output-dir/images.",
    )
    parser.add_argument(
        "--system",
        default=DEFAULT_SYSTEM,
        help="Optional system message. Pass an empty string to omit it.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Optional UTF-8 prompt file used as the user message. It must contain exactly one <image> tag.",
    )
    parser.add_argument(
        "--append-no-think",
        action="store_true",
        help="Append /no_think to the user message for Qwen3-style no-thinking SFT.",
    )
    parser.add_argument(
        "--min-blocks",
        type=int,
        default=1,
        help="Skip pages with fewer than this many labeled blocks.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def iter_result_files(jobs_dir: Path) -> Iterable[Path]:
    if not jobs_dir.exists():
        return []
    return sorted(path for path in jobs_dir.rglob("result.json") if path.is_file())


def is_bbox(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    return all(isinstance(item, (int, float)) for item in value)


def make_output_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    output_blocks: list[dict[str, Any]] = []
    for index, raw_block in enumerate(blocks):
        if not isinstance(raw_block, dict):
            continue

        bbox = raw_block.get("bbox_1000") or raw_block.get("bbox")
        if not is_bbox(bbox):
            continue

        block: dict[str, Any] = {}
        for key in BLOCK_OUTPUT_KEYS:
            if key == "bbox":
                block[key] = [int(value) for value in bbox]
            elif key == "id":
                block[key] = str(raw_block.get("id") or f"b{index:03d}")
            elif key == "text":
                block[key] = str(raw_block.get("text") or "")
            elif key == "page_id":
                block[key] = int(raw_block.get("page_id") or 0)
            elif key == "weak_heading":
                block[key] = bool(raw_block.get("weak_heading"))
            elif key == "level":
                level = raw_block.get("level")
                block[key] = level if level in {"H1", "H2", "H3"} else None
            else:
                block[key] = str(raw_block.get(key) or "text")
        output_blocks.append(block)
    return output_blocks


def image_path_from_url(job_dir: Path, image_url: str) -> Path | None:
    marker = job_dir.name
    parts = image_url.strip("/").split("/")
    if marker not in parts:
        return None
    relative_parts = parts[parts.index(marker) + 1 :]
    if not relative_parts:
        return None
    return job_dir.joinpath(*relative_parts)


def resolve_page_image(job_dir: Path, page: dict[str, Any], image_source: str) -> Path | None:
    url_key = "model_image_url" if image_source == "model" else "image_url"
    image_url = page.get(url_key)
    if isinstance(image_url, str):
        image_path = image_path_from_url(job_dir, image_url)
        if image_path and image_path.is_file():
            return image_path

    page_id = int(page.get("page_id") or 0)
    candidates = (
        [job_dir / "model_pages" / f"page_{page_id:03d}_qwen.png", job_dir / "pages" / f"page_{page_id:03d}.png"]
        if image_source == "model"
        else [job_dir / "pages" / f"page_{page_id:03d}.png"]
    )
    return next((path for path in candidates if path.is_file()), None)


def export_image_path(
    source: Path,
    output_dir: Path,
    dataset_name: str,
    job_id: str,
    page_id: int,
    copy_images: bool,
) -> tuple[str, bool]:
    if not copy_images:
        return str(source.resolve()), False

    suffix = source.suffix or ".png"
    target = output_dir / "images" / dataset_name / job_id / f"page_{page_id:03d}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or source.stat().st_mtime_ns != target.stat().st_mtime_ns or source.stat().st_size != target.stat().st_size:
        shutil.copy2(source, target)
        copied = True
    else:
        copied = False
    return str(target.resolve()), copied


def make_user_prompt(args: argparse.Namespace) -> str:
    prompt = DEFAULT_USER_PROMPT
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    if prompt.count("<image>") != 1:
        raise ValueError("user prompt must contain exactly one <image> tag")
    if args.append_no_think and "/no_think" not in prompt:
        prompt = f"{prompt.rstrip()} /no_think"
    return prompt


def build_sample(
    result_path: Path,
    result: dict[str, Any],
    page: dict[str, Any],
    user_prompt: str,
    system_prompt: str,
    output_dir: Path,
    dataset_name: str,
    image_source: str,
    copy_images: bool,
) -> tuple[dict[str, Any] | None, bool]:
    blocks = make_output_blocks(page.get("blocks") if isinstance(page.get("blocks"), list) else [])
    if not blocks:
        return None, False

    job_dir = result_path.parent
    page_id = int(page.get("page_id") or 0)
    image_path = resolve_page_image(job_dir, page, image_source)
    if image_path is None:
        return None, False

    job_id = str(result.get("job_id") or job_dir.name)
    image_ref, copied = export_image_path(
        image_path,
        output_dir=output_dir,
        dataset_name=dataset_name,
        job_id=job_id,
        page_id=page_id,
        copy_images=copy_images,
    )
    answer = {
        "image_path": image_ref,
        "blocks": blocks,
        "context_before": "",
        "context_after": "",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(
        [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False, separators=(",", ":"))},
        ]
    )
    return {"messages": messages, "images": [image_ref]}, copied


def write_dataset(samples: list[dict[str, Any]], output_dir: Path, dataset_name: str, output_format: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / f"{dataset_name}.{output_format}"
    if output_format == "jsonl":
        with dataset_path.open("w", encoding="utf-8") as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    else:
        dataset_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dataset_path


def convert(args: argparse.Namespace) -> tuple[ConvertStats, Path]:
    jobs_dir = args.jobs_dir.resolve()
    output_dir = args.output_dir.resolve()
    user_prompt = make_user_prompt(args)

    samples: list[dict[str, Any]] = []
    result_count = 0
    skipped_pages = 0
    copied_images = 0

    for result_path in iter_result_files(jobs_dir):
        result_count += 1
        result = load_json(result_path)
        pages = result.get("pages")
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict) or page.get("status") != "done":
                skipped_pages += 1
                continue
            if len(page.get("blocks") or []) < args.min_blocks:
                skipped_pages += 1
                continue
            sample, copied = build_sample(
                result_path=result_path,
                result=result,
                page=page,
                user_prompt=user_prompt,
                system_prompt=args.system,
                output_dir=output_dir,
                dataset_name=args.dataset_name,
                image_source=args.image_source,
                copy_images=not args.no_copy_images,
            )
            if sample is None:
                skipped_pages += 1
                continue
            samples.append(sample)
            copied_images += int(copied)

    if not samples:
        raise RuntimeError(f"No usable samples found under {jobs_dir}")

    dataset_path = write_dataset(samples, output_dir, args.dataset_name, args.format)
    return (
        ConvertStats(
            result_files=result_count,
            samples=len(samples),
            skipped_pages=skipped_pages,
            copied_images=copied_images,
        ),
        dataset_path,
    )


def main() -> int:
    args = parse_args()
    try:
        stats, dataset_path = convert(args)
    except Exception as exc:
        print(f"conversion failed: {exc}", file=sys.stderr)
        return 1

    print(
        "converted "
        f"{stats.samples} samples from {stats.result_files} result files; "
        f"skipped {stats.skipped_pages} pages; copied {stats.copied_images} images"
    )
    print(f"dataset: {dataset_path.resolve()}")
    print(f"swift usage: swift sft --dataset {dataset_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
