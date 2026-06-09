"""Dataclasses and label/category constants shared across the feature.

Anything that is "pure data" — bounding-box label sets, the layout prompt
text, prompt category enums, render dataclasses — lives here so the main
``server.py`` can stay focused on HTTP handling and orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BLOCK_TYPES = {
    "doc_title",
    "paragraph_title",
    "text",
    "table_of_contents",
    "table",
    "formula",
    "chart",
    "image",
    "vision_footnote",
    "header",
    "footer",
    "caption",
    "handwriting",
    "seal",
}
BLOCK_TYPE_ALIASES = {
    "list": "table_of_contents",
    "title": "paragraph_title",
    "figure_title": "caption",
    "figure": "image",
    "footnote": "vision_footnote",
    "reference": "vision_footnote",
    "other": "text",
}
LEVELS = {"H1", "H2", "H3", "H4"}

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = ""
ENV_CONFIG_KEYS = [
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT",
    "LAYOUT_RENDER_DPI",
    "LAYOUT_MAX_PAGES",
    "LAYOUT_MAX_PDF_BYTES",
    "QWEN_RESIZE_PRESET",
    "QWEN_IMAGE_PROFILE",
    "QWEN_RESIZED_WIDTH",
    "QWEN_RESIZED_HEIGHT",
]
DEFAULT_MAX_PDF_BYTES = 200 * 1024 * 1024
RESIZE_PRESETS = {
    "speed": (1216, 1728),
    "default": (1536, 2176),
    "high": (2048, 2912),
}

DEFAULT_PROMPT_TEMPLATE_ID = "default_template_1"
BUILTIN_LAYOUT_PROMPT_REVISION = "layout_prompt_v20260606_chart_description"
PROMPT_TEMPLATE_CATEGORIES = {"bounding_box", "polygon", "layout", "keypoints", "text_transcription"}
PROMPT_TYPES = {
    "data_annotation",
    "second_review",
    "data_cleaning",
    "data_conversion",
    "model_inference",
    "system_role",
    "custom",
}
PROMPT_TASK_TYPES = {
    "layout_analysis",
    "table_recognition",
    "image_captioning",
    "data_quality_check",
    "llamafactory_conversion",
    "swift_conversion",
    "second_manual_review",
    "auto_annotation",
    "custom",
}
PROMPT_STATUS = {"enabled", "disabled"}
DATASET_LABEL_TYPES = {
    "doc_title",
    "paragraph_title",
    "text",
    "table",
    "chart",
    "formula",
    "seal",
    "header",
    "footer",
    "caption",
    "table_of_contents",
    "image",
    "vision_footnote",
    "handwriting",
}


@dataclass
class PageImage:
    page_id: int
    width: int
    height: int
    image_path: Path
    image_url: str


@dataclass
class ModelPageImage:
    page_id: int
    width: int
    height: int
    image_path: Path
    image_url: str
    content_x: int
    content_y: int
    content_width: int
    content_height: int
    original_width: int
    original_height: int


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int


@dataclass
class VisionResizeConfig:
    width: int = 1536
    height: int = 2176
    preset: str = "default"
    factor: int = 32
    image_profile: str = "qwen3_6"

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def min_pixels(self) -> int:
        return self.pixels

    @property
    def max_pixels(self) -> int:
        return self.pixels


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    name: str
    prompt: str
    category: str
