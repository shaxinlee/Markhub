#!/usr/bin/env python3
"""Regression checks for layout heading hierarchy handling."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from features.layout_analysis.service import (  # noqa: E402
    build_heading_context,
    collect_done_blocks,
    job_block_from_annotation,
    build_training_lines,
    normalize_annotation_block,
    normalize_export_block,
    normalize_heading_level,
    parse_model_json,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    assert_true(normalize_heading_level("H1", "doc_title", "年度报告") is None, "doc_title 不应保留层级")
    assert_true(normalize_heading_level("H2", "paragraph_title", "1、公司简介") == "H2", "paragraph_title 应保留合法层级")
    assert_true(normalize_heading_level("H3", "figure_title", "图1 架构图") is None, "非 paragraph_title 不应保留层级")

    prior_blocks = [
        {"block_type": "doc_title", "level": "H1", "text": "年度报告"},
        {"block_type": "figure_title", "level": "H2", "text": "图1 架构图"},
        {"block_type": "paragraph_title", "level": "H2", "text": "1、公司简介"},
        {"block_type": "paragraph_title", "level": "H3", "text": "（一）主营业务"},
    ]
    context = build_heading_context(prior_blocks)
    assert_true("年度报告" not in context, "前序上下文不应读取 doc_title 层级")
    assert_true("图1 架构图" not in context, "前序上下文不应读取 figure_title 层级")
    assert_true("1、公司简介" in context and "（一）主营业务" in context, "前序上下文应只包含 paragraph_title 层级")

    assert_true(
        parse_model_json('```json\n{"source":"old"}\n```\n```json\n{"source":"last_json_block"}\n```')["source"] == "last_json_block",
        "应优先抓取最后一个 json 代码块",
    )
    assert_true(
        parse_model_json('```\n{"source":"outer_fence"}\n```')["source"] == "outer_fence",
        "没有 json 代码块时应解析去掉代码围栏后的整段内容",
    )
    trailing = '说明 {"source":"first"} 后面才是结果 {"source":"last_object","nested":{"keep":true}} 完成'
    assert_true(parse_model_json(trailing)["source"] == "last_object", "应回退抓取文本里最后一个完整 JSON 对象")

    doc_block = {"label": "doc_title", "level": "H1", "bbox": [0, 0, 10, 10]}
    figure_block = {"label": "figure_title", "level": "H2", "bbox": [0, 0, 10, 10]}
    para_block = {"label": "paragraph_title", "level": "H3", "bbox": [0, 0, 10, 10]}
    assert_true(normalize_annotation_block(doc_block, 0)["level"] is None, "标注保存时 doc_title 层级应清空")
    assert_true(job_block_from_annotation(figure_block)["level"] is None, "回写任务结果时非 paragraph_title 层级应清空")
    assert_true(normalize_export_block(para_block)["level"] == "H3", "导出时 paragraph_title 层级应保留")
    collected = collect_done_blocks([{"blocks": [doc_block, para_block]}])
    assert_true(collected[0]["level"] is None and collected[1]["level"] == "H3", "聚合结果时只应保留 paragraph_title 层级")

    payload = {
        "prompt_template": {"id": "default_template_1"},
        "pages": [
            {"page_id": 0, "width": 100, "height": 200, "image_url": "p0.png", "model_input": {"system": "old", "user": "old p0"}},
            {"page_id": 1, "width": 100, "height": 200, "image_url": "p1.png", "model_input": {"system": "old", "user": "old p1\n年度报告"}},
        ],
    }
    repaired_lines = build_training_lines(
        payload,
        {
            0: [doc_block, para_block],
            1: [{"label": "paragraph_title", "level": "H4", "text": "（1）细分业务", "bbox": [0, 0, 10, 10]}],
        },
        repair_prompt_context=True,
        refresh_builtin_system_prompt=False,
    )
    second_user = repaired_lines[1]["input"]["user"]
    assert_true("当前所处 paragraph_title 层级路径" in second_user, "训练样本 prompt 应重建 paragraph_title 层级路径")
    assert_true("年度报告" not in second_user and "H3: " in second_user, "训练样本 prompt 不应沿用旧层级上下文")

    print("layout_heading_rule_checks_ok")


if __name__ == "__main__":
    main()
