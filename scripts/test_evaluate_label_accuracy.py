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
    discover_failed_pages,
    discover_second_annotation_files,
    evaluate_annotation_roots,
    evaluate_file_maps,
    json_files_by_job,
    match_blocks,
    region_correct_indices,
    result_to_jsonable,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def annotation(label: str, level: str | None, filename: str | None = None) -> dict:
    return {
        **({"filename": filename} if filename else {}),
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


def block(block_id: str, label: str, bbox: list[int], text: str = "") -> dict:
    return {
        "id": block_id,
        "page_id": 0,
        "label": label,
        "level": "none",
        "bbox": bbox,
        "text": text,
    }


def main() -> None:
    gt_text = [block("gt", "text", [0, 0, 100, 100])]
    pred_candidates = [
        block("same-label-worse-box", "text", [0, 0, 70, 100]),
        block("wrong-label-exact-box", "paragraph_title", [0, 0, 100, 100]),
    ]
    matched, _used_gt, used_pred = match_blocks(gt_text, pred_candidates, min_iou=0.5)
    assert_true(matched[0][0] == 1, "bbox 匹配不能偷看 label，应选择 IoU 更高的预测")
    assert_true(used_pred == {1}, "一个 GT 只能使用一个预测框")

    huge_prediction = [block("huge", "text", [0, 0, 1000, 1000])]
    matched, _used_gt, used_pred = match_blocks(gt_text, huge_prediction, min_iou=0.5)
    assert_true(not matched, "仅覆盖 GT 但 IoU 很低的大框不应算标准匹配")
    assert_true(not used_pred, "低 IoU 预测应计为误检")

    gt_merged_text = [
        block("gt-top", "text", [0, 0, 100, 45]),
        block("gt-bottom", "text", [0, 55, 100, 100]),
    ]
    pred_merged_text = [block("pred-merged", "text", [0, 0, 100, 100])]
    correct_gt, correct_pred = region_correct_indices(
        gt_merged_text,
        pred_merged_text,
        min_region_coverage=0.8,
    )
    assert_true(correct_gt == {0, 1}, "连续 text 合成整洁大框时，两个 GT 都应算正确")
    assert_true(correct_pred == {0}, "合并后的单个 text 预测应算正确")

    gt_split_image = [block("gt-image", "image", [0, 0, 100, 100])]
    pred_split_image = [
        block("pred-left", "image", [0, 0, 50, 100]),
        block("pred-right", "image", [50, 0, 100, 100]),
    ]
    correct_gt, correct_pred = region_correct_indices(
        gt_split_image,
        pred_split_image,
        min_region_coverage=0.8,
    )
    assert_true(correct_gt == {0}, "同一 image 被拆成多个完整区域时应算正确")
    assert_true(correct_pred == {0, 1}, "组成完整 image 的多个预测框都应算正确")

    duplicate_image_predictions = [
        block("pred-a", "image", [0, 0, 100, 100]),
        block("pred-b", "image", [0, 0, 100, 100]),
    ]
    correct_gt, correct_pred = region_correct_indices(
        gt_split_image,
        duplicate_image_predictions,
        min_region_coverage=0.8,
    )
    assert_true(not correct_gt and not correct_pred, "重复预测框不能伪装成合理拆分")

    gt_sparse_text = [
        block("gt-top", "text", [0, 0, 100, 20]),
        block("gt-bottom", "text", [0, 80, 100, 100]),
    ]
    pred_page_box = [block("pred-page", "text", [0, 0, 100, 100])]
    correct_gt, correct_pred = region_correct_indices(
        gt_sparse_text,
        pred_page_box,
        min_region_coverage=0.8,
    )
    assert_true(not correct_gt and not correct_pred, "跨越大量空白的大框不能因覆盖多个 text 而算正确")

    gt_content_blocks = [
        block("gt-project", "text", [0, 0, 100, 20], "项目名称：迁移上线项目"),
        block("gt-client", "text", [0, 40, 100, 60], "委托方：某公司"),
        block("gt-vendor", "text", [0, 80, 100, 100], "受托方：某软件公司"),
    ]
    pred_content_merge = [
        block(
            "pred-content-merge",
            "text",
            [0, 0, 100, 100],
            "项目名称：迁移上线项目 委托方：某公司 受托方：某软件公司",
        )
    ]
    correct_gt, correct_pred = region_correct_indices(gt_content_blocks, pred_content_merge)
    assert_true(correct_gt == {0, 1, 2}, "同标签文字完整合并时不应因 bbox 内空白较多而判错")
    assert_true(correct_pred == {0}, "完整包含多个 GT 文本的合并预测应算正确")

    gt_content_merge = [
        block("gt-content-merge", "text", [0, 0, 100, 100], "第一段正文 第二段正文 第三段正文")
    ]
    pred_content_split = [
        block("pred-first", "text", [0, 0, 100, 20], "第一段正文"),
        block("pred-second", "text", [0, 40, 100, 60], "第二段正文"),
        block("pred-third", "text", [0, 80, 100, 100], "第三段正文"),
    ]
    correct_gt, correct_pred = region_correct_indices(gt_content_merge, pred_content_split)
    assert_true(correct_gt == {0}, "完整正文被拆成多个准确预测时 GT 应算正确")
    assert_true(correct_pred == {0, 1, 2}, "组成完整正文的拆分预测都应算正确")

    partial_content_split = [
        block("pred-only-middle", "text", [0, 40, 100, 60], "第二段正文"),
    ]
    correct_gt, correct_pred = region_correct_indices(gt_content_merge, partial_content_split)
    assert_true(not correct_gt and not correct_pred, "只识别部分文字时不能利用内容规则算正确")

    shifted_exact_title = [
        block("pred-shifted-title", "paragraph_title", [60, 60, 160, 160], "治理升级，筑牢风险防控底线")
    ]
    exact_title_gt = [
        block("gt-title", "paragraph_title", [0, 0, 100, 100], "治理升级，筑牢风险防控底线")
    ]
    correct_gt, correct_pred = region_correct_indices(exact_title_gt, shifted_exact_title)
    assert_true(correct_gt == {0} and correct_pred == {0}, "同标签文字完全一致时不应再要求单框 IoU")

    answer_with_prompt = [
        block(
            "pred-answer-with-prompt",
            "text",
            [0, 0, 100, 100],
            "1、技术咨询的目标：某软件股份有限公司提供技术支持，确保系统正常运行。",
        )
    ]
    answer_only_gt = [
        block(
            "gt-answer-only",
            "text",
            [10, 40, 90, 80],
            "某软件股份有限公司提供技术支持，确保系统正常运行。",
        )
    ]
    correct_gt, correct_pred = region_correct_indices(answer_only_gt, answer_with_prompt)
    assert_true(correct_gt == {0} and correct_pred == {0}, "完整正文附带少量提示文字时应算正确")

    short_gt = [block("gt-none", "text", [10, 40, 90, 80], "无")]
    short_pred = [block("pred-none", "text", [0, 0, 100, 100], "4、本合同履行完毕后：无")]
    correct_gt, correct_pred = region_correct_indices(short_gt, short_pred)
    assert_true(correct_gt == {0} and correct_pred == {0}, "局部相交且完整包含的短文字也应算正确")

    with tempfile.TemporaryDirectory(prefix="markhub_eval_") as tmp:
        root = Path(tmp)
        first_root = root / "first_annotations"
        second_root = root / "second_annotations"

        write_json(
            first_root / "model-a" / "job-1" / "result.json",
            annotation("paragraph_title", "H2", "document-a.pdf"),
        )
        write_json(second_root / "job-1" / "annotation_v2_20260608_100000.json", annotation("text", None))
        latest_second = second_root / "job-1" / "annotation_v2_20260608_110000.json"
        write_json(latest_second, annotation("paragraph_title", "H3", "document-a.pdf"))

        first_files = discover_first_annotation_files(str(first_root))
        second_files = discover_second_annotation_files(str(second_root))
        assert_true(first_files["document-a"].endswith("result.json"), "应按原始文档名发现一次标注")
        assert_true(second_files["document-a"] == str(latest_second), "应按原始文档名选择最新二次标注")

        result = result_to_jsonable(evaluate_annotation_roots(str(second_root), str(first_root)))
        assert_true(result["total_gt"] == 1, "应读取二次标注作为 ground truth")
        assert_true(result["per_label"]["paragraph_title"]["correct"] == 1, "label 相同应算正确")
        assert_true(result["paragraph_title_by_level"]["H3"]["correct"] == 0, "标题层级不同应算层级错误")

        gt_merge = root / "gt" / "document-b.json"
        pred_merge = root / "pred" / "document-b" / "result.json"
        write_json(
            gt_merge,
            {
                "filename": "document-b.pdf",
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
                "filename": "document-b.pdf",
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
        assert_true(merged_result["per_label"]["text"]["recall"] == 1.0, "合并 text 后 GT recall 应为 100%")
        assert_true(merged_result["per_label"]["text"]["precision"] == 1.0, "合并 text 后预测 precision 应为 100%")

        discovered_gt = json_files_by_job(str(root / "gt"))
        discovered_pred = json_files_by_job(str(root / "pred"))
        assert_true(set(discovered_gt) == {"document-b"}, "GT 应按 filename 对齐")
        assert_true(set(discovered_pred) == {"document-b"}, "result.json 应按 filename 对齐")

        label_leak_gt = root / "label_leak_gt.json"
        label_leak_pred = root / "label_leak_pred.json"
        write_json(label_leak_gt, annotation("text", None))
        write_json(
            label_leak_pred,
            {
                "pages": [
                    {
                        "page_id": 0,
                        "blocks": [
                            {"id": "same-label", "bbox": [0, 0, 70, 100], "label": "text"},
                            {"id": "exact-box", "bbox": [0, 0, 100, 100], "label": "paragraph_title"},
                        ],
                    }
                ]
            },
        )
        leak_result = result_to_jsonable(
            evaluate_file_maps({"job": str(label_leak_gt)}, {"job": str(label_leak_pred)}, min_iou=0.5)
        )
        assert_true(leak_result["total_matched"] == 1, "应找到一个几何匹配")
        assert_true(leak_result["total_correct"] == 0, "几何最优框标签错误时不能改配给同标签低质量框")
        assert_true(leak_result["classification_accuracy_on_matched"] == 0.0, "匹配后的标签准确率应为 0")
        assert_true(leak_result["end_to_end"]["f1"] == 0.0, "错标签时端到端 F1 应为 0")

        footer_gt = root / "footer_gt.json"
        footer_pred = root / "footer_pred.json"
        write_json(footer_gt, annotation("footer", None))
        write_json(
            footer_pred,
            {
                "pages": [
                    {
                        "page_id": 0,
                        "blocks": [
                            {"id": "shifted-footer", "bbox": [300, 300, 320, 320], "label": "footer"},
                        ],
                    }
                ]
            },
        )
        footer_result = result_to_jsonable(
            evaluate_file_maps({"job": str(footer_gt)}, {"job": str(footer_pred)})
        )
        assert_true(footer_result["total_matched"] == 1, "同页 footer 应忽略 bbox 直接匹配")
        assert_true(footer_result["per_label"]["footer"]["recall"] == 1.0, "偏移 footer 的 recall 应为 100%")
        assert_true(footer_result["per_label"]["footer"]["precision"] == 1.0, "偏移 footer 的 precision 应为 100%")

        missing_footer_result = result_to_jsonable(
            evaluate_file_maps({"job": str(footer_gt)}, {})
        )
        assert_true(
            missing_footer_result["per_label"]["footer"]["recall"] == 1.0,
            "footer 完全缺失时也应按用户指定口径计为正确",
        )

        header_gt = root / "header_gt.json"
        header_pred = root / "header_pred.json"
        write_json(header_gt, annotation("header", None))
        write_json(
            header_pred,
            {
                "pages": [
                    {
                        "page_id": 0,
                        "blocks": [
                            {"id": "shifted-header", "bbox": [300, 300, 320, 320], "label": "header"},
                        ],
                    }
                ]
            },
        )
        header_result = result_to_jsonable(
            evaluate_file_maps({"job": str(header_gt)}, {"job": str(header_pred)})
        )
        assert_true(header_result["per_label"]["header"]["recall"] == 1.0, "同页 header 应忽略 bbox")
        missing_header_result = result_to_jsonable(
            evaluate_file_maps({"job": str(header_gt)}, {})
        )
        assert_true(
            missing_header_result["per_label"]["header"]["recall"] == 0.0,
            "真正漏检的 header 仍应算错",
        )

        gt_two_pages = root / "categories" / "Contract" / "document-c.json"
        pred_two_pages = root / "pred-two-pages" / "document-c" / "result.json"
        write_json(
            gt_two_pages,
            {
                "filename": "document-c.pdf",
                "pages": [
                    {"page_id": 0, "blocks": [{"id": "gt-0", "bbox": [0, 0, 100, 100], "label": "text"}]},
                    {"page_id": 1, "blocks": [{"id": "gt-1", "bbox": [0, 0, 100, 100], "label": "text"}]},
                ],
            },
        )
        write_json(
            pred_two_pages,
            {
                "filename": "document-c.pdf",
                "errors": ["第 2 页分析失败: timeout"],
                "pages": [
                    {"page_id": 0, "blocks": [{"id": "pred-0", "bbox": [0, 0, 100, 100], "label": "text"}]},
                    {"page_id": 1, "blocks": []},
                ],
            },
        )
        failed_pages = discover_failed_pages(str(root / "pred-two-pages"))
        assert_true(failed_pages == {"document-c": {1}}, "应从运行错误中识别零基失败页")
        filtered = result_to_jsonable(
            evaluate_file_maps(
                {"document-c": str(gt_two_pages)},
                {"document-c": str(pred_two_pages)},
                excluded_pages=failed_pages,
            )
        )
        assert_true(filtered["total_gt"] == 1, "失败页应同时从 GT 分母中移除")
        assert_true(filtered["total_predicted"] == 1, "失败页应同时从预测分母中移除")

    print("evaluate_label_accuracy_checks_ok")


if __name__ == "__main__":
    main()
