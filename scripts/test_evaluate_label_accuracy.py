#!/usr/bin/env python3
"""Regression checks for Markhub first/second annotation evaluation."""

from __future__ import annotations

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
    evaluate_file_maps,
    match_blocks,
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


def block(block_id: str, label: str, bbox: list[int]) -> dict:
    return {
        "id": block_id,
        "page_id": 0,
        "label": label,
        "level": "none",
        "bbox": bbox,
    }


def main() -> None:
    gt_one_text = [block("gt-big", "text", [0, 0, 100, 100])]
    pred_split_text = [
        block("pred-top", "text", [0, 0, 100, 50]),
        block("pred-bottom", "text", [0, 50, 100, 100]),
    ]
    matched, _used_gt, used_pred = match_blocks(gt_one_text, pred_split_text, 0.8, 0.0)
    assert_true(0 in matched, "GT 大 text 被预测拆成多个 text 时应算匹配")
    assert_true(used_pred == {0, 1}, "拆分 text 的多个预测块都应被视为已使用")

    gt_split_text = [
        block("gt-top", "text", [0, 0, 100, 50]),
        block("gt-bottom", "text", [0, 50, 100, 100]),
    ]
    pred_one_text = [block("pred-big", "text", [0, 0, 100, 100])]
    matched, _used_gt, used_pred = match_blocks(gt_split_text, pred_one_text, 0.8, 0.0)
    assert_true(set(matched) == {0, 1}, "多个 GT text 被预测合成一个 text 时都应算匹配")
    assert_true(used_pred == {0}, "合并 text 的单个预测块应只计为已使用一次")

    gt_footer = [block("gt-footer", "footer", [497, 892, 508, 904])]
    pred_shifted_footer = [block("pred-footer", "footer", [494, 893, 505, 905])]
    matched, _used_gt, used_pred = match_blocks(gt_footer, pred_shifted_footer, 0.8, 0.0)
    assert_true(0 in matched, "footer 小框轻微偏移时应使用更宽松的覆盖阈值")
    assert_true(used_pred == {0}, "轻微偏移的 footer 预测块应被视为已使用")

    gt_seal_and_signature = [
        block("gt-seal", "seal", [0, 0, 100, 100]),
        block("gt-signature", "handwriting", [40, 40, 60, 60]),
    ]
    pred_seal_and_signature = [
        block("pred-seal", "seal", [0, 0, 98, 98]),
        block("pred-signature", "handwriting", [40, 40, 62, 59]),
    ]
    matched, _used_gt, used_pred = match_blocks(gt_seal_and_signature, pred_seal_and_signature, 0.8, 0.0)
    assert_true(matched[0][0] == 0, "印章应优先匹配预测印章，而不是被内部手写字干扰")
    assert_true(matched[1][0] == 1, "手写字应优先匹配预测手写字，而不是被大印章框抢走")
    assert_true(used_pred == {0, 1}, "印章和手写字预测都应被正确使用")

    gt_seal = [block("gt-seal", "seal", [0, 0, 100, 100])]
    pred_small_seal = [block("pred-seal", "seal", [0, 0, 80, 80])]
    matched, _used_gt, used_pred = match_blocks(gt_seal, pred_small_seal, 0.8, 0.0)
    assert_true(0 in matched, "seal 同 label 框略小但覆盖超过 60% 时应算匹配")
    assert_true(used_pred == {0}, "略小的 seal 预测框应被视为已使用")

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

        gt_merge = root / "gt_merge.json"
        pred_merge = root / "pred_merge.json"
        write_json(
            gt_merge,
            {
                "pages": [
                    {
                        "page_id": 0,
                        "blocks": [
                            {"id": "gt-1", "bbox": [0, 0, 100, 50], "label": "text", "level": None},
                            {"id": "gt-2", "bbox": [0, 50, 100, 100], "label": "text", "level": None},
                        ],
                    }
                ]
            },
        )
        write_json(
            pred_merge,
            {
                "pages": [
                    {
                        "page_id": 0,
                        "blocks": [
                            {"id": "pred-1", "bbox": [0, 0, 100, 100], "label": "text", "level": None},
                        ],
                    }
                ]
            },
        )
        merged_result = result_to_jsonable(evaluate_file_maps({"job": str(gt_merge)}, {"job": str(pred_merge)}))
        assert_true(merged_result["per_label"]["text"]["recall"] == 1.0, "合并 text 时 GT 召回应为 100%")
        assert_true(merged_result["per_label"]["text"]["precision"] == 1.0, "合并 text 时 precision 不应超过 100%")

    print("evaluate_label_accuracy_checks_ok")


if __name__ == "__main__":
    main()
