#!/usr/bin/env python3
"""Regression checks for layout Q&A/layout JSONL file flow."""

from pathlib import Path
import sys
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from features.layout_analysis.service import (  # noqa: E402
    build_qna_answer_from_layout_page,
    samples_from_qna,
    update_qna_entries_from_layout_pages,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="layout_qa_flow_") as tmp:
        root = Path(tmp)
        job_dir = root / "job"
        (job_dir / "model_pages").mkdir(parents=True)
        Image.new("RGB", (100, 200), "white").save(job_dir / "model_pages" / "page_000_qwen.png")

        qna_entries = [
            {
                "page_id": 0,
                "image": "model_pages/page_000_qwen.png",
                "system": "system prompt",
                "user": "user prompt",
                "assistant": "{\"image_path\":\"model_pages/page_000_qwen.png\",\"blocks\":[]}",
            },
            {
                "page_id": 1,
                "image": "model_pages/page_000_qwen.png",
                "system": "system prompt",
                "user": "stale user prompt",
                "assistant": "{\"image_path\":\"model_pages/page_000_qwen.png\",\"blocks\":[]}",
            }
        ]
        layout_pages = [
            {
                "page_id": 0,
                "image_path": "pages/page_000.png",
                "width": 100,
                "height": 200,
                "model_image_path": "model_pages/page_000_qwen.png",
                "model_width": 100,
                "model_height": 200,
                "model_content_bbox": [0, 0, 100, 200],
                "blocks": [
                    {
                        "id": "p000_b000",
                        "text": "修正标题",
                        "bbox": [10, 20, 50, 100],
                        "page_id": 0,
                        "block_type": "paragraph_title",
                        "level": "H1",
                    }
                ],
            },
            {
                "page_id": 1,
                "image_path": "pages/page_001.png",
                "width": 100,
                "height": 200,
                "model_image_path": "model_pages/page_000_qwen.png",
                "model_width": 100,
                "model_height": 200,
                "blocks": [
                    {
                        "id": "p001_b000",
                        "text": "章内条目",
                        "bbox": [10, 20, 50, 100],
                        "page_id": 1,
                        "block_type": "paragraph_title",
                        "level": "H2",
                    }
                ],
            }
        ]

        answer = build_qna_answer_from_layout_page(layout_pages[0], qna_entries[0])
        assert_true(answer["blocks"][0]["bbox"] == [100, 100, 500, 500], "Q&A assistant 应使用与模型图一致的 0-1000 bbox")
        assert_true(answer["blocks"][0]["text"] == "修正标题", "Q&A assistant 应使用二标后的文本")

        updated_qna = update_qna_entries_from_layout_pages(qna_entries, layout_pages)
        assert_true("修正标题" in updated_qna[0]["assistant"], "二标完成后应把 layout 结果回写到 Q&A assistant")
        assert_true("H1: 修正标题" in updated_qna[1]["user"], "二标完成后应按修正后的标题层级重建后续 Q&A user prompt")

        output_dir = root / "swift"
        samples, skipped = samples_from_qna(
            qna_entries=updated_qna,
            dataset_id="job",
            job_dir=job_dir,
            target_format="swift",
            output_dir=output_dir,
        )
        assert_true(skipped == 0 and len(samples) == 2, "应从 Q&A 生成训练样本")
        assert_true(samples[0]["messages"][0]["content"] == "system prompt", "训练样本 system 应来自 Q&A")
        assert_true(samples[0]["messages"][1]["content"].startswith("<image>\n当前页面 page_id=0"), "训练样本 user 应来自重建后的 Q&A 并带 image token")
        assert_true("H1: 修正标题" in samples[1]["messages"][1]["content"], "训练样本 user 应包含二标后的前序标题层级")
        assert_true("修正标题" in samples[0]["messages"][2]["content"], "训练样本 assistant 应来自更新后的 Q&A")
        assert_true((output_dir / samples[0]["images"][0]).is_file(), "训练图片应从 Q&A 相对路径复制")

    print("layout_qa_file_checks_ok")


if __name__ == "__main__":
    main()
