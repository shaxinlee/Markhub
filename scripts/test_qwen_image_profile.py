#!/usr/bin/env python3
"""Regression checks for Qwen image profile resizing."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from features.layout_analysis.paths import JOBS_DIR  # noqa: E402
from features.layout_analysis.schemas import PageImage, VisionResizeConfig  # noqa: E402
from features.layout_analysis.service import resize_page_for_model  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def main() -> int:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=JOBS_DIR) as tmp:
        root = Path(tmp)
        source = root / "page.png"
        Image.new("RGB", (1000, 2000), "white").save(source)
        page = PageImage(page_id=0, width=1000, height=2000, image_path=source, image_url="/page.png")

        qwen36 = resize_page_for_model(page, root / "qwen36", VisionResizeConfig(width=1536, height=2176, preset="default", image_profile="qwen3_6"))
        assert_equal((qwen36.width, qwen36.height), (1536, 2176), "qwen3.6 应保持当前固定画布")
        assert qwen36.content_x > 0, "qwen3.6 竖版页面在固定画布中应保留横向 padding"

        qwen35 = resize_page_for_model(page, root / "qwen35", VisionResizeConfig(width=1536, height=2176, preset="default", image_profile="qwen3_5"))
        assert_equal((qwen35.width % 32, qwen35.height % 32), (0, 0), "qwen3.5 输出尺寸应是 32 的倍数")
        assert_equal((qwen35.content_x, qwen35.content_y), (0, 0), "qwen3.5 应等比缩放而不加白边")
        assert qwen35.width * qwen35.height <= 1536 * 2176, "qwen3.5 不应超过所选像素预算"
        assert 0.45 < (qwen35.width / qwen35.height) < 0.55, "qwen3.5 应尽量保持原始纵横比"

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
