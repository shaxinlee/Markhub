#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from features.layout_analysis.service import suppress_duplicate_seal_text  # noqa: E402


def main() -> int:
    blocks = [
        {"block_type": "seal", "text": "某公司合同专用章", "bbox_1000": [100, 100, 400, 400]},
        {"block_type": "text", "text": "合同专用章", "bbox_1000": [180, 300, 320, 420]},
        {"block_type": "text", "text": "乙方：某公司（盖章）", "bbox_1000": [150, 250, 500, 280]},
        {"block_type": "text", "text": "合同专用章", "bbox_1000": [600, 600, 750, 650]},
    ]
    filtered = suppress_duplicate_seal_text(blocks)
    texts = [block["text"] for block in filtered]
    if texts != ["某公司合同专用章", "乙方：某公司（盖章）", "合同专用章"]:
        raise AssertionError(f"unexpected seal text cleanup result: {texts}")
    print("layout_block_cleanup_checks_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
