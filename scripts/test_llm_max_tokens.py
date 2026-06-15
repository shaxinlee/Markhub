#!/usr/bin/env python3
"""Regression checks for the configurable model output-token limit."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from features.layout_analysis.schemas import LLMConfig, ModelPageImage, PromptTemplate  # noqa: E402
from features.layout_analysis import service  # noqa: E402


def main() -> int:
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content='{"image_path":"","blocks":[]}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    original_openai = service.OpenAI
    service.OpenAI = FakeOpenAI
    try:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "page.png"
            Image.new("RGB", (32, 32), "white").save(image_path)
            model_page = ModelPageImage(
                page_id=0,
                width=32,
                height=32,
                image_path=image_path,
                image_url="/page.png",
                content_x=0,
                content_y=0,
                content_width=32,
                content_height=32,
                original_width=32,
                original_height=32,
            )
            config = LLMConfig(
                base_url="http://localhost/v1",
                model="qwen-test",
                api_key="",
                timeout=180,
                max_tokens=12345,
            )
            prompt = PromptTemplate(
                template_id="test",
                name="test",
                prompt="只输出 JSON。",
                category="layout",
            )
            service.call_layout_llm(model_page, model_page, config, prompt)
    finally:
        service.OpenAI = original_openai

    if captured.get("max_tokens") != 12345:
        raise AssertionError(f"expected max_tokens=12345, got {captured.get('max_tokens')!r}")
    print("llm_max_tokens_checks_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
