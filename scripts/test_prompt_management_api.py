#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Basic prompt-management API behavior checks without starting the HTTP server."""

from __future__ import annotations

import tempfile
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from features.layout_analysis import server as s  # noqa: E402
from features.layout_analysis import prompts_store as ps  # noqa: E402


def assert_true(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "prompts.json"
        s.PROMPTS_STORE_FILE = store_path
        ps.PROMPTS_STORE_FILE = store_path

        created = s.create_prompt(
            {
                "id": "test_layout_prompt",
                "name": "测试版面分析提示词",
                "description": "用于测试 CRUD",
                "type": "data_annotation",
                "task_type": "layout_analysis",
                "model_name": "qwen-test",
                "content": "请处理 {{input_text}} 并输出 JSON。",
                "variables": "{{input_text}}",
                "default_values": {"input_text": "默认文本"},
                "status": "enabled",
                "is_default": False,
            }
        )
        assert_true(created["id"] == "test_layout_prompt", "新增提示词失败")

        detail = s.get_prompt("test_layout_prompt")
        assert_true(detail and detail["name"] == "测试版面分析提示词", "查看提示词失败")

        edited = s.update_prompt(
            "test_layout_prompt",
            {"content": "请重新处理 {{input_text}} 和 {{ocr_result}}。", "change_log": "加入 OCR 变量"},
        )
        assert_true(edited["version"] == "v1.1", "编辑提示词没有生成新版本")

        queried = s.list_prompts({"search": "OCR", "type": "data_annotation", "task_type": "layout_analysis", "model_name": "qwen-test"})
        assert_true(any(item["id"] == "test_layout_prompt" for item in queried), "查询或筛选提示词失败")

        copied = s.copy_prompt("test_layout_prompt")
        assert_true(copied["name"].endswith("_副本") and not copied["is_default"], "复制提示词失败")

        disabled_copy = s.set_prompt_status(copied["id"], "disabled")
        assert_true(disabled_copy["status"] == "disabled", "停用提示词失败")
        enabled_copy = s.set_prompt_status(copied["id"], "enabled")
        assert_true(enabled_copy["status"] == "enabled", "启用提示词失败")

        default_prompt = s.set_default_prompt("test_layout_prompt")
        assert_true(default_prompt["is_default"], "设置默认提示词失败")
        assert_true(s.default_prompt_for_task("layout_analysis")["id"] == "test_layout_prompt", "业务模块未读取默认提示词")

        versions = s.get_prompt("test_layout_prompt")["versions"]
        assert_true(len(versions) >= 2, "查看历史版本失败")
        rolled_back = s.rollback_prompt("test_layout_prompt", {"version": "v1.0"})
        assert_true(rolled_back["version"] == "v1.2", "回滚没有生成新版本")

        rendered = s.test_prompt("test_layout_prompt", {"inputs": {"input_text": "测试输入"}, "call_model": False})
        assert_true(rendered["success"] and "测试输入" in rendered["rendered_prompt"], "Prompt 测试运行失败")

        manual = s.resolve_prompt_template("test_layout_prompt")
        assert_true(manual.template_id == "test_layout_prompt", "业务模块手动选择提示词失败")

        deleted = s.soft_delete_prompt(copied["id"])
        assert_true(deleted["deleted_at"] and deleted["status"] == "disabled", "删除提示词失败")

    print("prompt_management_checks_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
