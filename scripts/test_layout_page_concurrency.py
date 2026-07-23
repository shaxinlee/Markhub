#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from features.layout_analysis import service  # noqa: E402
from features.layout_analysis.schemas import LLMConfig, PageImage, PromptTemplate, VisionResizeConfig  # noqa: E402


def main() -> int:
    old_concurrency = os.environ.get("LAYOUT_PAGE_CONCURRENCY")
    os.environ.pop("LAYOUT_PAGE_CONCURRENCY", None)
    try:
        default_concurrency = service.layout_page_concurrency(4)
    finally:
        if old_concurrency is not None:
            os.environ["LAYOUT_PAGE_CONCURRENCY"] = old_concurrency
    if default_concurrency != 1:
        raise AssertionError(f"expected default serial page inference, got {default_concurrency}")

    pages = [PageImage(page_id=index, width=100, height=200, image_path=Path(f"{index}.png"), image_url="") for index in range(4)]
    state = {
        "status": "running",
        "completed_pages": 0,
        "pages": [{"page_id": page.page_id, "status": "pending", "blocks": []} for page in pages],
        "result": {"blocks": []},
    }
    lock = threading.Lock()
    active = 0
    max_active = 0
    committed: list[int] = []

    def fake_infer(job_id, page, llm_config, resize_config, prompt_template, heading_context):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03 * (3 - min(page.page_id, 3)))
        with lock:
            active -= 1
        return page.page_id

    def fake_commit(job_id, page, future, started_at, resize_config):
        future.result()
        committed.append(page.page_id)
        state["pages"][page.page_id]["status"] = "done"
        state["completed_pages"] += 1

    old_concurrency = os.environ.get("LAYOUT_PAGE_CONCURRENCY")
    os.environ["LAYOUT_PAGE_CONCURRENCY"] = "3"
    try:
        with (
            patch.object(service, "read_job_result", return_value=state),
            patch.object(service, "write_job_result"),
            patch.object(service, "build_heading_context", return_value="context"),
            patch.object(service, "infer_page", side_effect=fake_infer),
            patch.object(service, "commit_page_inference", side_effect=fake_commit),
        ):
            service.process_job_pages(
                "test-job",
                pages,
                LLMConfig(base_url="http://localhost/v1", model="test", api_key="", timeout=30),
                VisionResizeConfig(width=100, height=200, preset="test"),
                PromptTemplate(template_id="test", name="test", prompt="test", category="layout"),
            )
    finally:
        if old_concurrency is None:
            os.environ.pop("LAYOUT_PAGE_CONCURRENCY", None)
        else:
            os.environ["LAYOUT_PAGE_CONCURRENCY"] = old_concurrency

    if max_active != 3:
        raise AssertionError(f"expected three overlapping requests, got {max_active}")
    if committed != [0, 1, 2, 3]:
        raise AssertionError(f"pages were not committed in order: {committed}")

    staggered_pages = [
        PageImage(page_id=index, width=100, height=200, image_path=Path(f"{index}.png"), image_url="")
        for index in range(8)
    ]
    staggered_state = {
        "status": "running",
        "completed_pages": 0,
        "pages": [
            {"page_id": page.page_id, "status": "pending", "blocks": []}
            for page in staggered_pages
        ],
        "result": {"blocks": []},
    }
    staggered_commits: list[int] = []
    context_calls: list[tuple[int, bool]] = []
    staggered_active = 0
    staggered_max_active = 0

    def fake_staggered_context(blocks, page_id, include_following=False):
        context_calls.append((page_id, include_following))
        return f"page={page_id};following={include_following}"

    def fake_staggered_infer(job_id, page, llm_config, resize_config, prompt_template, heading_context):
        nonlocal staggered_active, staggered_max_active
        with lock:
            staggered_active += 1
            staggered_max_active = max(staggered_max_active, staggered_active)
        time.sleep(0.03)
        with lock:
            staggered_active -= 1
        return page.page_id

    def fake_staggered_commit(job_id, page, future, started_at, resize_config):
        future.result()
        staggered_commits.append(page.page_id)
        staggered_state["pages"][page.page_id]["status"] = "done"
        staggered_state["completed_pages"] += 1

    old_schedule = os.environ.get("LAYOUT_PAGE_SCHEDULE")
    old_concurrency = os.environ.get("LAYOUT_PAGE_CONCURRENCY")
    os.environ["LAYOUT_PAGE_SCHEDULE"] = "staggered"
    os.environ["LAYOUT_PAGE_CONCURRENCY"] = "4"
    try:
        with (
            patch.object(service, "read_job_result", return_value=staggered_state),
            patch.object(service, "write_job_result"),
            patch.object(service, "build_page_heading_context", side_effect=fake_staggered_context),
            patch.object(service, "infer_page", side_effect=fake_staggered_infer),
            patch.object(service, "commit_page_inference", side_effect=fake_staggered_commit),
        ):
            service.process_job_pages(
                "staggered-job",
                staggered_pages,
                LLMConfig(base_url="http://localhost/v1", model="test", api_key="", timeout=30),
                VisionResizeConfig(width=100, height=200, preset="test"),
                PromptTemplate(template_id="test", name="test", prompt="test", category="layout"),
            )
    finally:
        if old_schedule is None:
            os.environ.pop("LAYOUT_PAGE_SCHEDULE", None)
        else:
            os.environ["LAYOUT_PAGE_SCHEDULE"] = old_schedule
        if old_concurrency is None:
            os.environ.pop("LAYOUT_PAGE_CONCURRENCY", None)
        else:
            os.environ["LAYOUT_PAGE_CONCURRENCY"] = old_concurrency

    if staggered_max_active != 4:
        raise AssertionError(f"expected four staggered requests, got {staggered_max_active}")
    if staggered_commits != [0, 2, 4, 6, 1, 3, 5, 7]:
        raise AssertionError(f"unexpected staggered commit order: {staggered_commits}")
    expected_context_calls = [
        (0, False), (2, False), (4, False), (6, False),
        (1, True), (3, True), (5, True), (7, True),
    ]
    if context_calls != expected_context_calls:
        raise AssertionError(f"unexpected staggered contexts: {context_calls}")

    anchor_pages = [
        PageImage(page_id=index, width=100, height=200, image_path=Path(f"{index}.png"), image_url="")
        for index in range(8)
    ]
    anchor_state = {
        "status": "running",
        "completed_pages": 0,
        "pages": [{"page_id": page.page_id, "status": "pending", "blocks": []} for page in anchor_pages],
        "result": {"blocks": []},
    }
    anchor_calls: list[tuple[int, list[int] | None]] = []

    def fake_anchor_infer(job_id, page, llm_config, resize_config, prompt_template, heading_context):
        time.sleep(0.01)
        return page.page_id

    def fake_anchor_commit(
        job_id,
        page,
        future,
        started_at,
        resize_config,
        prior_blocks_override=None,
    ):
        future.result()
        prior_pages = None
        if prior_blocks_override is not None:
            prior_pages = sorted({int(block["page_id"]) for block in prior_blocks_override})
        anchor_calls.append((page.page_id, prior_pages))
        block = {
            "page_id": page.page_id,
            "block_type": "paragraph_title",
            "level": "H1" if page.page_id % 4 == 0 else "H2",
            "text": f"page {page.page_id + 1}",
        }
        anchor_state["pages"][page.page_id].update({"status": "done", "blocks": [block]})
        anchor_state["result"]["blocks"] = [
            item
            for page_state in anchor_state["pages"]
            for item in page_state.get("blocks", [])
            if page_state.get("status") == "done"
        ]
        anchor_state["completed_pages"] += 1

    old_schedule = os.environ.get("LAYOUT_PAGE_SCHEDULE")
    old_concurrency = os.environ.get("LAYOUT_PAGE_CONCURRENCY")
    os.environ["LAYOUT_PAGE_SCHEDULE"] = "contiguous_anchor"
    os.environ["LAYOUT_PAGE_CONCURRENCY"] = "4"
    try:
        with (
            patch.object(service, "read_job_result", return_value=anchor_state),
            patch.object(service, "write_job_result"),
            patch.object(service, "build_page_heading_context", return_value="context"),
            patch.object(service, "infer_page", side_effect=fake_anchor_infer),
            patch.object(service, "commit_page_inference", side_effect=fake_anchor_commit),
        ):
            service.process_job_pages(
                "anchor-job",
                anchor_pages,
                LLMConfig(base_url="http://localhost/v1", model="test", api_key="", timeout=30),
                VisionResizeConfig(width=100, height=200, preset="test"),
                PromptTemplate(template_id="test", name="test", prompt="test", category="layout"),
            )
    finally:
        if old_schedule is None:
            os.environ.pop("LAYOUT_PAGE_SCHEDULE", None)
        else:
            os.environ["LAYOUT_PAGE_SCHEDULE"] = old_schedule
        if old_concurrency is None:
            os.environ.pop("LAYOUT_PAGE_CONCURRENCY", None)
        else:
            os.environ["LAYOUT_PAGE_CONCURRENCY"] = old_concurrency

    expected_anchor_calls = [
        (0, None),
        (1, [0]), (2, [0]), (3, [0]),
        (4, None),
        (5, [0, 1, 2, 3, 4]),
        (6, [0, 1, 2, 3, 4]),
        (7, [0, 1, 2, 3, 4]),
    ]
    if anchor_calls != expected_anchor_calls:
        raise AssertionError(f"unexpected contiguous-anchor inputs: {anchor_calls}")

    cascade_pages = [
        PageImage(page_id=index, width=100, height=200, image_path=Path(f"{index}.png"), image_url="")
        for index in range(4)
    ]
    cascade_state = {
        "status": "running",
        "completed_pages": 0,
        "pages": [{"page_id": page.page_id, "status": "pending", "blocks": []} for page in cascade_pages],
        "result": {"blocks": []},
    }
    cascade_context_pages: list[tuple[int, list[int]]] = []

    def fake_cascade_context(blocks, page_id, include_following=False):
        cascade_context_pages.append((page_id, sorted({int(block["page_id"]) for block in blocks})))
        return "context"

    def fake_cascade_commit(job_id, page, future, started_at, resize_config, prior_blocks_override=None):
        future.result()
        block = {"page_id": page.page_id, "block_type": "paragraph_title", "level": "H1", "text": str(page.page_id)}
        cascade_state["pages"][page.page_id].update({"status": "done", "blocks": [block]})
        cascade_state["result"]["blocks"] = [
            item for page_state in cascade_state["pages"] for item in page_state.get("blocks", []) if page_state["status"] == "done"
        ]
        cascade_state["completed_pages"] += 1

    old_schedule = os.environ.get("LAYOUT_PAGE_SCHEDULE")
    old_concurrency = os.environ.get("LAYOUT_PAGE_CONCURRENCY")
    os.environ["LAYOUT_PAGE_SCHEDULE"] = "contiguous_cascade"
    os.environ["LAYOUT_PAGE_CONCURRENCY"] = "4"
    try:
        with (
            patch.object(service, "read_job_result", return_value=cascade_state),
            patch.object(service, "write_job_result"),
            patch.object(service, "build_page_heading_context", side_effect=fake_cascade_context),
            patch.object(service, "infer_page", side_effect=fake_anchor_infer),
            patch.object(service, "commit_page_inference", side_effect=fake_cascade_commit),
        ):
            service.process_job_pages(
                "cascade-job",
                cascade_pages,
                LLMConfig(base_url="http://localhost/v1", model="test", api_key="", timeout=30),
                VisionResizeConfig(width=100, height=200, preset="test"),
                PromptTemplate(template_id="test", name="test", prompt="test", category="layout"),
            )
    finally:
        if old_schedule is None:
            os.environ.pop("LAYOUT_PAGE_SCHEDULE", None)
        else:
            os.environ["LAYOUT_PAGE_SCHEDULE"] = old_schedule
        if old_concurrency is None:
            os.environ.pop("LAYOUT_PAGE_CONCURRENCY", None)
        else:
            os.environ["LAYOUT_PAGE_CONCURRENCY"] = old_concurrency

    expected_cascade_context_pages = [(0, []), (1, [0]), (2, [0]), (3, [0])]
    if cascade_context_pages != expected_cascade_context_pages:
        raise AssertionError(f"cascade did not expose page 1 to trailing requests: {cascade_context_pages}")

    context = service.build_page_heading_context(
        [
            {"page_id": 0, "block_type": "paragraph_title", "level": "H1", "text": "第一章", "bbox": [0, 10, 10, 20]},
            {"page_id": 2, "block_type": "paragraph_title", "level": "H2", "text": "一、后页标题", "bbox": [0, 10, 10, 20]},
        ],
        page_id=1,
        include_following=True,
    )
    if "H1: 第一章" not in context:
        raise AssertionError(f"previous heading missing from active path: {context}")
    if "page 3: H2 一、后页标题" not in context:
        raise AssertionError(f"following heading missing from reference: {context}")
    active_path = context.split("【后续页面已识别", 1)[0]
    if "一、后页标题" in active_path:
        raise AssertionError(f"following heading leaked into active path: {context}")
    print("layout_page_concurrency_checks_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
