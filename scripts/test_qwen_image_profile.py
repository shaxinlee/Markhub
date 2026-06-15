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
from features.layout_analysis.server import parse_resize_config  # noqa: E402
from features.layout_analysis.service import normalize_blocks, prompt_for_image_profile, qwen_bbox_to_model_pixels, resize_page_for_model, scale_bbox  # noqa: E402


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

        qwen3 = resize_page_for_model(page, root / "qwen3", VisionResizeConfig(width=1536, height=2176, preset="default", image_profile="qwen3"))
        assert_equal((qwen3.width % 32, qwen3.height % 32), (0, 0), "qwen3 输出尺寸应是 32 的倍数")
        assert_equal((qwen3.content_x, qwen3.content_y), (0, 0), "qwen3 应等比缩放而不加白边")
        assert qwen3.width * qwen3.height <= 1536 * 2176, "qwen3 不应超过所选像素预算"
        assert 0.45 < (qwen3.width / qwen3.height) < 0.55, "qwen3 应尽量保持原始纵横比"
        model_bbox = qwen_bbox_to_model_pixels([100, 100, 500, 500], qwen3)
        assert_equal(scale_bbox(model_bbox, qwen3, page), [100, 200, 500, 1000], "qwen3 的 0-1000 bbox 应映射回原页面坐标")

        parsed = parse_resize_config({"qwen_preset": "default", "qwen_image_profile": "qwen3"})
        assert_equal(parsed.image_profile, "qwen3", "后端应保留 qwen3 图像规格")

        qwen25_config = parse_resize_config({"qwen_preset": "default", "qwen_image_profile": "qwen2_5"})
        assert_equal(qwen25_config.image_profile, "qwen2_5", "后端应保留 qwen2.5 图像规格")
        assert_equal(qwen25_config.factor, 28, "qwen2.5 动态分辨率应使用 28 倍数")
        qwen25 = resize_page_for_model(page, root / "qwen25", qwen25_config)
        assert_equal((qwen25.width % 28, qwen25.height % 28), (0, 0), "qwen2.5 输出尺寸应是 28 的倍数")
        assert_equal((qwen25.content_x, qwen25.content_y), (0, 0), "qwen2.5 应等比缩放而不加白边")
        qwen25_pixel_bbox = [
            round(qwen25.width * 0.1),
            round(qwen25.height * 0.1),
            round(qwen25.width * 0.5),
            round(qwen25.height * 0.5),
        ]
        blocks, warnings = normalize_blocks(
            {"blocks": [{"block_type": "text", "text": "像素坐标", "bbox": qwen25_pixel_bbox}]},
            model_page=qwen25,
            original_page=page,
            image_profile="qwen2_5",
        )
        assert_equal(warnings, [], "qwen2.5 像素 bbox 不应产生警告")
        assert_equal(blocks[0]["bbox"], [100, 200, 500, 1000], "qwen2.5 像素 bbox 应映射回原页面")
        assert_equal(blocks[0]["bbox_1000"], [100, 100, 500, 500], "qwen2.5 像素 bbox 应统一保存为 0-1000")
        qwen25_prompt = prompt_for_image_profile(
            "bbox 必须使用 Qwen3-VL grounding 的 0–1000 相对坐标系，不要输出原始像素坐标。\n"
            "bbox 格式为 [左上角x, 左上角y, 右下角x, 右下角y]，每个值都必须在 0 到 1000 之间。",
            qwen25,
            "qwen2_5",
        )
        assert "绝对像素坐标" in qwen25_prompt, "qwen2.5 提示词应要求绝对像素坐标"
        assert "必须使用 Qwen3-VL grounding" not in qwen25_prompt, "qwen2.5 提示词不应残留 Qwen3 坐标要求"

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
