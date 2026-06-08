#!/usr/bin/env python3
"""Regression checks for Markhub first/second annotation evaluation."""

from pathlib import Path
import json
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.evaluate_label_accuracy import (  # noqa: E402
    discover_first_annotation_files,
    discover_second_annotation_files,
    evaluate_annotation_roots,
    result_to_jsonable,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def annotation(label: str, level: str | None) -> dict:
    return {
        "pages": [
            {
                "page_id": 0,
                "blocks": [
                    {
                        "id": "b1",
                        "bbox": [0, 0, 100, 100],
                        "label": label,
                        "block_type": label,
                        "level": level,
                    }
                ],
            }
        ]
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="markhub_eval_") as tmp:
        root = Path(tmp)
        first_root = root / "first_annotations"
        second_root = root / "second_annotations"

        write_json(first_root / "model-a" / "job-1" / "result.json", annotation("paragraph_title", "H2"))
        write_json(second_root / "job-1" / "annotation_v2_20260608_100000.json", annotation("text", None))
        latest_second = second_root / "job-1" / "annotation_v2_20260608_110000.json"
        write_json(latest_second, annotation("paragraph_title", "H3"))

        first_files = discover_first_annotation_files(str(first_root))
        second_files = discover_second_annotation_files(str(second_root))
        assert_true(first_files["job-1"].endswith("result.json"), "应从模型嵌套目录发现一次标注 result.json")
        assert_true(second_files["job-1"] == str(latest_second), "应选择最新二次标注版本作为标准答案")

        result = result_to_jsonable(evaluate_annotation_roots(str(second_root), str(first_root)))
        assert_true(result["total_gt"] == 1, "应读取二次标注作为 ground truth")
        assert_true(result["per_label"]["paragraph_title"]["correct"] == 1, "label 相同应算正确")
        assert_true(result["paragraph_title_by_level"]["H3"]["correct"] == 0, "标题层级不同应算层级错误")

    print("evaluate_label_accuracy_checks_ok")


if __name__ == "__main__":
    main()
