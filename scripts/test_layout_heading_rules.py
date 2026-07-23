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
    qna_entry_from_page,
    normalize_annotation_block,
    normalize_export_block,
    normalize_heading_level,
    parse_model_json,
    reconcile_document_heading_levels,
    reconcile_heading_schema_levels,
    repair_heading_level_continuity,
    strip_think_prefix,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    assert_true(normalize_heading_level("H1", "doc_title", "年度报告") is None, "doc_title 不应保留层级")
    assert_true(normalize_heading_level("H2", "paragraph_title", "1、公司简介") == "H2", "paragraph_title 应保留合法层级")
    assert_true(normalize_heading_level("H3", "caption", "图1 架构图") is None, "非 paragraph_title 不应保留层级")

    prior_blocks = [
        {"block_type": "doc_title", "level": "H1", "text": "年度报告"},
        {"block_type": "caption", "level": "H2", "text": "图1 架构图"},
        {"block_type": "paragraph_title", "level": "H2", "text": "1、公司简介"},
        {"block_type": "paragraph_title", "level": "H3", "text": "（一）主营业务"},
    ]
    context = build_heading_context(prior_blocks)
    assert_true("年度报告" not in context, "前序上下文不应读取 doc_title 层级")
    assert_true("图1 架构图" not in context, "前序上下文不应读取 caption 层级")
    assert_true("1、公司简介" in context and "（一）主营业务" in context, "前序上下文应只包含 paragraph_title 层级")
    assert_true("当前有效标题路径" in context, "前序上下文应提供 current_heading_path")
    assert_true("最近识别的 paragraph_title 序列" in context, "前序上下文应提供 recent_paragraph_titles")
    assert_true("当前文档已出现过的标题层级" in context, "前序上下文应提供 appeared_heading_levels")
    assert_true("当前允许的下一个 paragraph_title 层级" in context, "前序上下文应提供 allowed_next_levels")
    assert_true("当前禁止的 paragraph_title 层级" in context, "前序上下文应提供 forbidden_next_levels")

    repaired, level_warnings = repair_heading_level_continuity(
        [{"id": "b1", "block_type": "paragraph_title", "level": "H3", "text": "（一）跳级标题"}],
        prior_blocks=[{"block_type": "paragraph_title", "level": "H1", "text": "第一章"}],
    )
    assert_true(repaired[0]["level"] == "H2", "前序没有 H2 时，H3 应降级为 H2")
    assert_true(level_warnings, "层级降级应产生提示")

    repaired_after_reset, reset_warnings = repair_heading_level_continuity(
        [{"id": "b2", "block_type": "paragraph_title", "level": "H3", "text": "（一）不应直接出现的三级标题"}],
        prior_blocks=[
            {"block_type": "paragraph_title", "level": "H1", "text": "第一章"},
            {"block_type": "paragraph_title", "level": "H2", "text": "1、一级小节"},
            {"block_type": "paragraph_title", "level": "H3", "text": "（一）二级小节"},
            {"block_type": "paragraph_title", "level": "H1", "text": "第二章"},
        ],
    )
    assert_true(repaired_after_reset[0]["level"] == "H2", "回到新的 H1 后，后续 H3 应按当前路径降级为 H2")
    assert_true(reset_warnings, "回到 H1 后的跳级降级应产生提示")

    reconciliation_state = {
        "pages": [
            {"page_id": 0, "blocks": [
                {"id": "h1", "block_type": "paragraph_title", "level": "H1", "text": "第三章 项目实施", "bbox": [40, 10, 400, 40]},
                {"id": "h2", "block_type": "paragraph_title", "level": "H2", "text": "3.1 系统建设", "bbox": [70, 60, 400, 90]},
                {"id": "keep_h4", "block_type": "paragraph_title", "level": "H4", "text": "3.1.1 平台性能要求", "bbox": [100, 110, 500, 140]},
                {"id": "wrong_h2", "block_type": "paragraph_title", "level": "H2", "text": "3.1.2 安全性要求", "bbox": [100, 160, 500, 190]},
                {"id": "wrong_h3", "block_type": "paragraph_title", "level": "H3", "text": "3.1.2.1 数据加密要求", "bbox": [130, 210, 500, 240]},
            ]}
        ],
        "result": {"blocks": []},
        "warnings": [],
    }
    reconciled = reconcile_document_heading_levels(
        reconciliation_state,
        "missing-job-for-unit-test",
        persist_layout_jsonl=False,
    )
    reconciled_levels = [block["level"] for block in reconciled["pages"][0]["blocks"]]
    assert_true(reconciled_levels == ["H1", "H2", "H4", "H3", "H4"], "全文校正只能将有父级证据的 H2/H3 向下提升一级，不能压浅已有 H4")
    assert_true(reconciled["heading_reconciliation"]["changed_count"] == 2, "全文校正应只记录高置信升层")

    schema_state = {
        "pages": [
            {"page_id": 0, "blocks": [
                {"id": "s_h1", "block_type": "paragraph_title", "level": "H1", "text": "第一章 总则", "bbox": [40, 10, 400, 40]},
                {"id": "s_h2", "block_type": "paragraph_title", "level": "H2", "text": "一、总体要求", "bbox": [70, 60, 400, 90]},
                {"id": "s_1", "block_type": "paragraph_title", "level": "H3", "text": "（一）适用范围", "bbox": [110, 110, 500, 140]},
                {"id": "s_2", "block_type": "paragraph_title", "level": "H2", "text": "（二）实施原则", "bbox": [110, 160, 500, 190]},
                {"id": "s_3", "block_type": "paragraph_title", "level": "H3", "text": "（三）管理职责", "bbox": [110, 210, 500, 240]},
                {"id": "s_4", "block_type": "paragraph_title", "level": "H3", "text": "（四）监督机制", "bbox": [110, 260, 500, 290]},
            ]}
        ],
        "result": {"blocks": []},
        "warnings": [],
    }
    schema_reconciled = reconcile_heading_schema_levels(
        schema_state,
        "missing-job-for-unit-test",
        persist_layout_jsonl=False,
    )
    schema_levels = [block["level"] for block in schema_reconciled["pages"][0]["blocks"]]
    assert_true(schema_levels == ["H1", "H2", "H3", "H3", "H3", "H3"], "连续的局部编号家族应将孤立 H2 修正为 H3")
    assert_true(schema_reconciled["heading_schema_reconciliation"]["changed_count"] == 1, "局部编号规则只应修正有双证据的孤立项")

    cross_chapter_schema_state = {
        "pages": [
            {"page_id": 0, "blocks": [
                {"id": "chapter_1", "block_type": "paragraph_title", "level": "H1", "text": "第一节 重要提示", "bbox": [40, 10, 400, 40]},
                {"id": "company_intro", "block_type": "paragraph_title", "level": "H2", "text": "1、公司简介", "bbox": [70, 60, 400, 90]},
                {"id": "chapter_2", "block_type": "paragraph_title", "level": "H1", "text": "第二节 主营业务", "bbox": [40, 110, 400, 140]},
                {"id": "business_1", "block_type": "paragraph_title", "level": "H3", "text": "1、火锅调料", "bbox": [110, 160, 500, 190]},
                {"id": "business_2", "block_type": "paragraph_title", "level": "H3", "text": "2、菜谱式调料", "bbox": [110, 210, 500, 240]},
                {"id": "business_3", "block_type": "paragraph_title", "level": "H3", "text": "3、香肠腊肉调料", "bbox": [110, 260, 500, 290]},
            ]}
        ],
        "result": {"blocks": []},
        "warnings": [],
    }
    cross_chapter_reconciled = reconcile_heading_schema_levels(
        cross_chapter_schema_state,
        "missing-job-for-unit-test",
        persist_layout_jsonl=False,
    )
    cross_chapter_levels = [block["level"] for block in cross_chapter_reconciled["pages"][0]["blocks"]]
    assert_true(cross_chapter_levels[1] == "H2", "编号样式相同但跨 H1 章节时，不得将正确 H2 降为 H3")
    assert_true(cross_chapter_reconciled["heading_schema_reconciliation"]["changed_count"] == 0, "跨章节编号不得产生局部结构校正")

    financial_state = {"pages": [{"page_id": 0, "blocks": [
        {"id": "root", "block_type": "paragraph_title", "level": "H1", "text": "第二节 公司基本情况", "bbox": [600, 10, 900, 40]},
        {"id": "section", "block_type": "paragraph_title", "level": "H1", "text": "2、报告期公司主要业务简介", "bbox": [220, 60, 700, 90]},
        {"id": "sub", "block_type": "paragraph_title", "level": "H2", "text": "（一）公司的主营业务", "bbox": [290, 110, 700, 140]},
        {"id": "item", "block_type": "paragraph_title", "level": "H3", "text": "1、火锅调料", "bbox": [280, 160, 500, 190]},
    ]}], "result": {"blocks": []}, "warnings": []}
    financial_reconciled = reconcile_heading_schema_levels(financial_state, "missing-job-for-unit-test", persist_layout_jsonl=False)
    assert_true([b["level"] for b in financial_reconciled["pages"][0]["blocks"]] == ["H1", "H2", "H3", "H4"], "财报第X节下的连续编号链应逐级恢复")

    reset_context = build_heading_context(
        [
            {"block_type": "paragraph_title", "level": "H1", "text": "第一章"},
            {"block_type": "paragraph_title", "level": "H2", "text": "1、一级小节"},
            {"block_type": "paragraph_title", "level": "H3", "text": "（一）二级小节"},
            {"block_type": "paragraph_title", "level": "H1", "text": "第二章"},
        ]
    )
    assert_true("H1: 第二章" in reset_context and "H2: 1、一级小节" not in reset_context, "当前路径回到 H1 后应清掉旧 H2/H3")
    assert_true("当前允许的下一个 paragraph_title 层级" in reset_context, "前序上下文应明确给出当前页允许层级")
    allowed_section = reset_context.split("当前允许的下一个 paragraph_title 层级：", 1)[1].split("当前禁止的 paragraph_title 层级：", 1)[0]
    assert_true("H1, H2" in allowed_section and "H1, H2, H3" not in allowed_section, "当前路径为 H1 时允许层级只能到 H2")
    assert_true("当前禁止的 paragraph_title 层级" in reset_context and "H3, H4" in reset_context, "当前路径为 H1 时应禁止 H3/H4")

    empty_context = build_heading_context([])
    assert_true("当前有效标题路径" in empty_context and "无" in empty_context, "无前序标题时也应提供空路径上下文")
    assert_true("当前允许的下一个 paragraph_title 层级" in empty_context and "H1" in empty_context, "无前序标题时只允许 H1")
    assert_true("当前禁止的 paragraph_title 层级" in empty_context and "H2, H3, H4" in empty_context, "无前序标题时应禁止 H2/H3/H4")

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
    thinking_response = '<think>{"source":"thinking"}</think>\n{"source":"after_think"}'
    assert_true(strip_think_prefix(thinking_response) == '{"source":"after_think"}', "应忽略 </think> 之前的模型思考内容")
    assert_true(parse_model_json(thinking_response)["source"] == "after_think", "解析模型 JSON 时应忽略 </think> 之前的内容")
    qna_entry = qna_entry_from_page(0, "model_pages/page_000_qwen.png", {"system": "s", "user": "u"}, thinking_response)
    assert_true(qna_entry["assistant"] == '{"source":"after_think"}', "保存 Q&A assistant 时应忽略 </think> 之前的内容")

    doc_block = {"label": "doc_title", "level": "H1", "bbox": [0, 0, 10, 10]}
    caption_block = {"label": "caption", "level": "H2", "bbox": [0, 0, 10, 10]}
    legacy_figure_block = {"label": "figure_title", "level": "H2", "bbox": [0, 0, 10, 10]}
    legacy_footnote_block = {"label": "footnote", "bbox": [0, 0, 10, 10]}
    legacy_other_block = {"label": "other", "bbox": [0, 0, 10, 10]}
    para_block = {"label": "paragraph_title", "level": "H3", "bbox": [0, 0, 10, 10]}
    chart_block = {"label": "chart", "description": "图表展示收入逐年上升", "bbox": [0, 0, 10, 10]}
    legacy_chart_block = {"label": "chart", "chart_description": "旧字段图表描述", "bbox": [0, 0, 10, 10]}
    flowchart_block = {"label": "flowchart", "description": "流程图展示审批流转", "bbox": [0, 0, 10, 10]}
    text_with_chart_description = {"label": "text", "chart_description": "不应保留", "bbox": [0, 0, 10, 10]}
    assert_true(normalize_annotation_block(doc_block, 0)["level"] is None, "标注保存时 doc_title 层级应清空")
    assert_true(job_block_from_annotation(caption_block)["level"] is None, "回写任务结果时非 paragraph_title 层级应清空")
    assert_true(normalize_annotation_block(legacy_figure_block, 0)["label"] == "caption", "旧 figure_title 应归一为 caption")
    assert_true(normalize_annotation_block(legacy_footnote_block, 0)["label"] == "vision_footnote", "旧 footnote 应归一为 vision_footnote")
    assert_true(normalize_annotation_block(legacy_other_block, 0)["label"] == "text", "旧 other 应归一为 text")
    assert_true(normalize_annotation_block(chart_block, 0)["description"] == "图表展示收入逐年上升", "chart 应保留 description")
    assert_true(normalize_annotation_block(legacy_chart_block, 0)["description"] == "旧字段图表描述", "旧 chart_description 应兼容迁移到 description")
    assert_true(normalize_annotation_block(flowchart_block, 0)["label"] == "flowchart", "flowchart 应作为合法 label 保留")
    assert_true(normalize_annotation_block(flowchart_block, 0)["description"] == "流程图展示审批流转", "flowchart 应保留 description")
    assert_true(job_block_from_annotation(flowchart_block)["block_type"] == "flowchart", "回写任务结果时 flowchart 应保留")
    assert_true(normalize_annotation_block(text_with_chart_description, 0)["description"] == "", "非 chart/flowchart 应清空 description")
    assert_true(job_block_from_annotation(chart_block)["description"] == "图表展示收入逐年上升", "回写任务结果时 description 应保留")
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
    assert_true("当前有效标题路径" in second_user, "训练样本 prompt 应重建 paragraph_title 层级路径")
    assert_true("年度报告" not in second_user and "H1: " in second_user, "训练样本 prompt 应使用修正后的 paragraph_title 层级上下文")

    print("layout_heading_rule_checks_ok")


if __name__ == "__main__":
    main()
