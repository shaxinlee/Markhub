"""Loader for Markhub layout-analysis prompt text.

All prompt strings live in the committed, editable resource file
``prompt_defaults.json`` beside this module — never inlined here. Keeping the
text in data (not code) means prompt edits don't require touching Python, and
the long Chinese prompt no longer clutters the source tree.

The dynamic runtime store at ``backend/datasets/prompt_templates/prompts.json``
(which is gitignored / regenerated per deployment) is seeded from these defaults
on startup; see ``prompts_store.bootstrap_prompt_store``. To change the shipped
default system prompt, edit ``layout_analysis_system`` here and bump
``BUILTIN_LAYOUT_PROMPT_REVISION`` in ``schemas.py`` so existing stores re-sync
once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_DEFAULTS_PATH = Path(__file__).with_name("prompt_defaults.json")


def _load_defaults() -> Dict[str, Any]:
    with _DEFAULTS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


PROMPT_DEFAULTS: Dict[str, Any] = _load_defaults()

# The built-in layout-analysis system prompt, assembled from its line array.
LAYOUT_PROMPT = "\n".join(PROMPT_DEFAULTS["layout_analysis_system"])
COMPACT_LAYOUT_PROMPT = "\n".join(PROMPT_DEFAULTS["compact_layout_analysis_system"])


def prompt_fragment(*path: str, default: str = "") -> str:
    """Fetch a nested string fragment from ``prompt_defaults.json``.

    Example: ``prompt_fragment("heading_context", "header")``. Returns
    ``default`` if the path is missing or does not resolve to a string.
    """
    node: Any = PROMPT_DEFAULTS
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node if isinstance(node, str) else default


PROMPT_TEMPLATES = {
    "default_template_1": {
        "id": "default_template_1",
        "name": "默认模板 1",
        "category": "layout",
        "prompt": LAYOUT_PROMPT,
    },
    "compact_layout_prompt": {
        "id": "compact_layout_prompt",
        "name": "精简提示词",
        "category": "layout",
        "prompt": COMPACT_LAYOUT_PROMPT,
    },
}
