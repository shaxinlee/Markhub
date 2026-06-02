#!/usr/bin/env python3
"""Regression checks for Swift export image/bbox coordinate consistency."""

from pathlib import Path
import tempfile
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from features.layout_analysis.service import normalize_export_bbox_1000, prepare_portable_image_ref  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected}, got {actual}")


def main() -> None:
    assert_equal(
        normalize_export_bbox_1000(
            {"bbox": [10, 20, 50, 100]},
            {"width": 100, "height": 200},
            {"model_width": 1000, "model_height": 2000, "model_content_bbox": [0, 0, 1000, 2000]},
            uses_model_page=True,
        ),
        [100, 100, 500, 500],
        "无 padding 的 model_pages 应按内容区换算到 0-1000",
    )
    assert_equal(
        normalize_export_bbox_1000(
            {"bbox": [0, 0, 100, 100]},
            {"width": 100, "height": 100},
            {"model_width": 200, "model_height": 300, "model_content_bbox": [0, 50, 200, 250]},
            uses_model_page=True,
        ),
        [0, 167, 1000, 833],
        "有 padding 的 model_pages 应先映射到内容区再换算 0-1000",
    )
    assert_equal(
        normalize_export_bbox_1000(
            {"bbox": [0, 0, 100, 100]},
            {"width": 100, "height": 100},
            {"model_width": 200, "model_height": 300, "model_content_bbox": [0, 50, 200, 250]},
            uses_model_page=False,
        ),
        [0, 0, 1000, 1000],
        "缺少 model_pages 而拉伸原图时不应套用 padding",
    )
    assert_equal(
        normalize_export_bbox_1000(
            {"bbox": [10, 20, 50, 100], "bbox_1000": [101, 102, 501, 502]},
            {"width": 100, "height": 200},
            {"model_width": 1000, "model_height": 2000, "model_content_bbox": [0, 0, 1000, 2000]},
            uses_model_page=True,
        ),
        [101, 102, 501, 502],
        "已有 bbox_1000 时应优先使用原始标准化坐标",
    )

    with tempfile.TemporaryDirectory(prefix="swift_export_resize_") as tmp:
        tmp_dir = Path(tmp)
        source = tmp_dir / "source.png"
        target = tmp_dir / "out" / "page.png"
        Image.new("RGB", (10, 20), "white").save(source)
        prepare_portable_image_ref(source, target, tmp_dir, target_size=(100, 200))
        with Image.open(target) as image:
            assert_equal(image.size, (100, 200), "缺少 model_pages 时应按目标尺寸拉伸图片")

    print("swift_export_coordinate_checks_ok")


if __name__ == "__main__":
    main()
