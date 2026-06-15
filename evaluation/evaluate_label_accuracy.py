#!/usr/bin/env python3
"""Evaluate layout-analysis predictions against ground-truth annotations.

Expected data layout::

    evaluation/datasets/ground_truth/<job_id>.json  # second annotation
    evaluation/datasets/model_pre/<job_id>.json     # first annotation / model prediction

Documents are aligned by their original filename. Blocks are then matched
one-to-one by geometry only, without looking at labels. This avoids inflating
classification accuracy by choosing a lower-quality box merely because its
label matches the answer.

The default matching rule is IoU >= 0.5. The report separates:

* detection precision/recall/F1;
* label accuracy among geometrically matched blocks;
* end-to-end precision/recall/F1, where a true positive needs both a valid
  geometric match and the correct label.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASETS = os.path.join(HERE, "datasets")
MISSING_LABEL = "__missing__"
EXTRA_LABEL = "__extra__"
FAILED_PAGE_PATTERN = re.compile(r"第\s*(\d+)\s*页")
DEFAULT_BBOX_EXEMPT_LABELS = ("footer",)
DEFAULT_LABEL_ONLY_LABELS = ("header",)


def normalize_label(block: Dict[str, Any]) -> str:
    return str(block.get("label") or block.get("block_type") or "unknown")


def normalize_level(block: Dict[str, Any]) -> str:
    return str(block.get("level") or "none")


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return "".join(character for character in text if character.isalnum())


def text_group_coverage(
    blocks: List[Dict[str, Any]],
    other_blocks: List[Dict[str, Any]],
) -> Tuple[float, float]:
    def joined_text(items: List[Dict[str, Any]]) -> str:
        ordered = sorted(
            items,
            key=lambda block: (
                block["page_id"],
                block["bbox"][1],
                block["bbox"][0],
                block["bbox"][3],
                block["bbox"][2],
            ),
        )
        return "".join(normalize_text(block.get("text")) for block in ordered)

    text = joined_text(blocks)
    other_text = joined_text(other_blocks)
    if not text or not other_text:
        return 0.0, 0.0
    matcher = difflib.SequenceMatcher(None, text, other_text, autojunk=False)
    sequence_common = sum(block.size for block in matcher.get_matching_blocks())
    unordered_common = sum((Counter(text) & Counter(other_text)).values())
    common = max(sequence_common, unordered_common)
    return common / len(text), common / len(other_text)


def normalize_bbox(value: Any) -> Optional[List[float]]:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(item) for item in value]
    except Exception:
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def bbox_area(bbox: List[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def bbox_intersection(a: List[float], b: List[float]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def bbox_intersection_box(a: List[float], b: List[float]) -> Optional[List[float]]:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def bbox_union_area(bboxes: List[List[float]]) -> float:
    if not bboxes:
        return 0.0
    xs = sorted({bbox[0] for bbox in bboxes} | {bbox[2] for bbox in bboxes})
    total = 0.0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted(
            (bbox[1], bbox[3])
            for bbox in bboxes
            if bbox[0] < right and bbox[2] > left
        )
        if not intervals:
            continue
        covered = 0.0
        top, bottom = intervals[0]
        for next_top, next_bottom in intervals[1:]:
            if next_top <= bottom:
                bottom = max(bottom, next_bottom)
            else:
                covered += bottom - top
                top, bottom = next_top, next_bottom
        covered += bottom - top
        total += (right - left) * covered
    return total


def bbox_coverage_by_group(bbox: List[float], other_bboxes: List[List[float]]) -> float:
    intersections = []
    for other_bbox in other_bboxes:
        intersection = bbox_intersection_box(bbox, other_bbox)
        if intersection is not None:
            intersections.append(intersection)
    area = bbox_area(bbox)
    return bbox_union_area(intersections) / area if area else 0.0


def max_pairwise_overlap_ratio(bboxes: List[List[float]]) -> float:
    maximum = 0.0
    for index, bbox in enumerate(bboxes):
        for other_bbox in bboxes[index + 1 :]:
            smaller_area = min(bbox_area(bbox), bbox_area(other_bbox))
            if not smaller_area:
                continue
            maximum = max(maximum, bbox_intersection(bbox, other_bbox) / smaller_area)
    return maximum


def bbox_metrics(gt_bbox: List[float], pred_bbox: List[float]) -> Tuple[float, float]:
    inter = bbox_intersection(gt_bbox, pred_bbox)
    gt_area = bbox_area(gt_bbox)
    pred_area = bbox_area(pred_bbox)
    union = gt_area + pred_area - inter
    gt_coverage = inter / gt_area if gt_area else 0.0
    iou = inter / union if union else 0.0
    return gt_coverage, iou


def load_blocks(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    blocks: List[Dict[str, Any]] = []
    for page in data.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = int(page.get("page_id") or 0)
        for index, block in enumerate(page.get("blocks", [])):
            if not isinstance(block, dict):
                continue
            bbox = normalize_bbox(block.get("bbox"))
            if bbox is None:
                continue
            blocks.append(
                {
                    "id": str(block.get("id") or f"p{page_id:03d}_b{index:03d}"),
                    "page_id": page_id,
                    "label": normalize_label(block),
                    "level": normalize_level(block),
                    "bbox": bbox,
                    "text": str(block.get("text") or ""),
                }
            )
    return blocks


def annotation_key(path: str, data: Optional[Dict[str, Any]] = None) -> str:
    if data is None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    file_name = (
        data.get("file_name")
        or data.get("filename")
        or data.get("document_name")
        or data.get("name")
    )
    if isinstance(file_name, str) and file_name.strip():
        return os.path.splitext(os.path.basename(file_name.strip()))[0]

    stem = os.path.splitext(os.path.basename(path))[0]
    if stem == "result" or stem.startswith("annotation_v2_"):
        return os.path.basename(os.path.dirname(path))
    return stem


def add_annotation_file(files: Dict[str, str], key: str, path: str) -> None:
    existing = files.get(key)
    if existing and os.path.abspath(existing) != os.path.abspath(path):
        raise ValueError(f"发现重复文档名 {key!r}: {existing} 与 {path}")
    files[key] = path


def json_files_by_job(root: str) -> Dict[str, str]:
    if not os.path.isdir(root):
        return {}
    all_json = []
    result_json = []
    for current_root, _dirs, names in os.walk(root):
        for name in sorted(names):
            if not name.endswith(".json") or name == "dataset_state.json":
                continue
            path = os.path.join(current_root, name)
            all_json.append(path)
            if name == "result.json":
                result_json.append(path)

    files: Dict[str, str] = {}
    for path in result_json or all_json:
        add_annotation_file(files, annotation_key(path), path)
    return files


def job_id_from_annotation_file(path: str) -> str:
    """Backward-compatible alias for callers that used the old helper name."""
    return annotation_key(path)


def discover_first_annotation_files(root: str) -> Dict[str, str]:
    """Find first-pass Markhub annotations under backend/datasets/first_annotations."""
    if not os.path.isdir(root):
        return {}
    files: Dict[str, str] = {}
    for current_root, _dirs, names in os.walk(root):
        if "result.json" not in names:
            continue
        path = os.path.join(current_root, "result.json")
        add_annotation_file(files, annotation_key(path), path)
    return dict(sorted(files.items()))


def discover_second_annotation_files(root: str) -> Dict[str, str]:
    """Find latest submitted second-pass Markhub annotation for each job."""
    if not os.path.isdir(root):
        return {}
    files: Dict[str, str] = {}
    for job_id in sorted(os.listdir(root)):
        job_dir = os.path.join(root, job_id)
        if not os.path.isdir(job_dir):
            continue
        candidates = sorted(
            os.path.join(job_dir, name)
            for name in os.listdir(job_dir)
            if name.startswith("annotation_v2_") and name.endswith(".json")
        )
        if candidates:
            path = candidates[-1]
            add_annotation_file(files, annotation_key(path), path)
    return files


def discover_failed_pages(root: str) -> Dict[str, set]:
    """Return zero-based failed page ids keyed by original document name."""
    failed_pages: Dict[str, set] = defaultdict(set)
    for path in discover_first_annotation_files(root).values():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        job_id = annotation_key(path, data)
        for error in data.get("errors") or []:
            match = FAILED_PAGE_PATTERN.search(str(error))
            if match:
                failed_pages[job_id].add(int(match.group(1)) - 1)
    return dict(failed_pages)


def merge_failed_pages(*page_maps: Dict[str, set]) -> Dict[str, set]:
    merged: Dict[str, set] = defaultdict(set)
    for page_map in page_maps:
        for job_id, page_ids in page_map.items():
            merged[job_id].update(page_ids)
    return dict(merged)


def filter_excluded_pages(blocks: List[Dict[str, Any]], excluded_pages: set) -> List[Dict[str, Any]]:
    if not excluded_pages:
        return blocks
    return [block for block in blocks if block["page_id"] not in excluded_pages]


def region_correct_indices(
    gt_blocks: List[Dict[str, Any]],
    pred_blocks: List[Dict[str, Any]],
    min_region_coverage: float = 0.8,
    min_iou: float = 0.5,
    key_fields: Tuple[str, ...] = ("label",),
    excluded_labels: Tuple[str, ...] = (),
) -> Tuple[set, set]:
    """Match equivalent same-class content while allowing shifted/split/merge layouts.

    Geometry remains the first link between blocks, but complete text content
    can validate a component even when its boxes are shifted, split, merged, or
    contain layout whitespace.
    """
    validate_threshold("min_region_coverage", min_region_coverage)
    validate_threshold("min_iou", min_iou)

    gt_groups: Dict[Tuple[Any, ...], List[int]] = defaultdict(list)
    pred_groups: Dict[Tuple[Any, ...], List[int]] = defaultdict(list)
    for index, block in enumerate(gt_blocks):
        if block["label"] in excluded_labels:
            continue
        key = (block["page_id"], *(block[field] for field in key_fields))
        gt_groups[key].append(index)
    for index, block in enumerate(pred_blocks):
        if block["label"] in excluded_labels:
            continue
        key = (block["page_id"], *(block[field] for field in key_fields))
        pred_groups[key].append(index)

    correct_gt = set()
    correct_pred = set()
    for key in sorted(set(gt_groups) & set(pred_groups), key=str):
        gt_indices = gt_groups[key]
        pred_indices = pred_groups[key]
        adjacency: Dict[Tuple[str, int], List[Tuple[str, int]]] = defaultdict(list)
        for gt_index in gt_indices:
            for pred_index in pred_indices:
                if bbox_intersection(gt_blocks[gt_index]["bbox"], pred_blocks[pred_index]["bbox"]) <= 0:
                    continue
                adjacency[("gt", gt_index)].append(("pred", pred_index))
                adjacency[("pred", pred_index)].append(("gt", gt_index))

        visited = set()
        for node in list(adjacency):
            if node in visited:
                continue
            stack = [node]
            visited.add(node)
            component_gt = []
            component_pred = []
            while stack:
                side, index = stack.pop()
                if side == "gt":
                    component_gt.append(index)
                else:
                    component_pred.append(index)
                for neighbor in adjacency[(side, index)]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)

            gt_bboxes = [gt_blocks[index]["bbox"] for index in component_gt]
            pred_bboxes = [pred_blocks[index]["bbox"] for index in component_pred]
            gt_component = [gt_blocks[index] for index in component_gt]
            pred_component = [pred_blocks[index] for index in component_pred]
            gt_text_coverage, pred_text_coverage = text_group_coverage(
                gt_component,
                pred_component,
            )
            if min(gt_text_coverage, pred_text_coverage) >= min_region_coverage:
                correct_gt.update(component_gt)
                correct_pred.update(component_pred)
                continue
            if (
                len(component_gt) == 1
                and len(component_pred) == 1
                and gt_text_coverage >= 0.9
            ):
                correct_gt.update(component_gt)
                correct_pred.update(component_pred)
                continue
            if len(component_gt) == 1 and len(component_pred) == 1:
                continue
            if max_pairwise_overlap_ratio(gt_bboxes) > 0.5:
                continue
            if max_pairwise_overlap_ratio(pred_bboxes) > 0.5:
                continue
            gt_coverages = [
                bbox_coverage_by_group(gt_blocks[index]["bbox"], pred_bboxes)
                for index in component_gt
            ]
            pred_coverages = [
                bbox_coverage_by_group(pred_blocks[index]["bbox"], gt_bboxes)
                for index in component_pred
            ]
            if min(gt_coverages + pred_coverages) >= min_region_coverage:
                correct_gt.update(component_gt)
                correct_pred.update(component_pred)

    return correct_gt, correct_pred


def label_only_matches(
    gt_blocks: List[Dict[str, Any]],
    pred_blocks: List[Dict[str, Any]],
    labels: Tuple[str, ...],
) -> Tuple[Dict[int, Tuple[int, float, float]], set, set]:
    """Pair selected labels by page and label without applying bbox thresholds."""
    gt_groups: Dict[Tuple[int, str], List[int]] = defaultdict(list)
    pred_groups: Dict[Tuple[int, str], List[int]] = defaultdict(list)
    label_set = set(labels)
    for index, block in enumerate(gt_blocks):
        if block["label"] in label_set:
            gt_groups[(block["page_id"], block["label"])].append(index)
    for index, block in enumerate(pred_blocks):
        if block["label"] in label_set:
            pred_groups[(block["page_id"], block["label"])].append(index)

    matched: Dict[int, Tuple[int, float, float]] = {}
    used_gt = set()
    used_pred = set()
    for key in sorted(set(gt_groups) & set(pred_groups)):
        gt_indices = sorted(gt_groups[key], key=lambda index: tuple(gt_blocks[index]["bbox"]))
        pred_indices = sorted(pred_groups[key], key=lambda index: tuple(pred_blocks[index]["bbox"]))
        for gt_index, pred_index in zip(gt_indices, pred_indices):
            coverage, iou = bbox_metrics(gt_blocks[gt_index]["bbox"], pred_blocks[pred_index]["bbox"])
            matched[gt_index] = (pred_index, coverage, iou)
            used_gt.add(gt_index)
            used_pred.add(pred_index)
    return matched, used_gt, used_pred


def evaluate_file_maps(
    gt_files: Dict[str, str],
    pred_files: Dict[str, str],
    min_gt_coverage: Optional[float] = None,
    min_iou: float = 0.5,
    min_region_coverage: float = 0.8,
    excluded_pages: Optional[Dict[str, set]] = None,
    bbox_exempt_labels: Tuple[str, ...] = DEFAULT_BBOX_EXEMPT_LABELS,
    label_only_labels: Tuple[str, ...] = DEFAULT_LABEL_ONLY_LABELS,
) -> Dict[str, Any]:
    validate_threshold("min_iou", min_iou)
    validate_threshold("min_region_coverage", min_region_coverage)
    if min_gt_coverage is not None:
        validate_threshold("min_gt_coverage", min_gt_coverage)
    excluded_pages = excluded_pages or {}

    support = defaultdict(int)
    correct = defaultdict(int)
    predicted = defaultdict(int)
    pred_correct = defaultdict(int)
    confusion = defaultdict(int)

    lvl_support = defaultdict(int)
    lvl_correct = defaultdict(int)
    lvl_predicted = defaultdict(int)
    lvl_pred_correct = defaultdict(int)
    lvl_confusion = defaultdict(int)
    para_lvl_support = defaultdict(int)
    para_lvl_correct = defaultdict(int)
    para_lvl_predicted = defaultdict(int)
    para_lvl_pred_correct = defaultdict(int)
    para_lvl_confusion = defaultdict(int)

    total_gt = 0
    total_matched = 0
    total_correct = 0
    total_pred_correct = 0
    total_strict_label_correct = 0
    missing = 0
    extra = 0
    excluded_page_count = 0
    job_rows = []
    skipped = []

    for job_id in sorted(gt_files):
        gt_path = gt_files[job_id]
        pred_path = pred_files.get(job_id)

        job_excluded_pages = excluded_pages.get(job_id, set())
        gt_blocks = filter_excluded_pages(load_blocks(gt_path), job_excluded_pages)
        pred_blocks = (
            filter_excluded_pages(load_blocks(pred_path), job_excluded_pages)
            if pred_path
            else []
        )
        excluded_page_count += len(job_excluded_pages)
        if not pred_path:
            skipped.append((job_id, "找不到对应预测，整份文档按漏检计入"))
        label_matches, _label_used_gt, label_used_pred = label_only_matches(
            gt_blocks,
            pred_blocks,
            tuple(dict.fromkeys((*bbox_exempt_labels, *label_only_labels))),
        )
        bbox_exempt_label_set = set(bbox_exempt_labels)
        geometry_exempt_label_set = bbox_exempt_label_set | set(label_only_labels)
        bbox_exempt_gt = {
            index for index, block in enumerate(gt_blocks)
            if block["label"] in bbox_exempt_label_set
        }
        bbox_exempt_pred = {
            index for index, block in enumerate(pred_blocks)
            if block["label"] in bbox_exempt_label_set
        }
        geometry_exempt_gt = {
            index for index, block in enumerate(gt_blocks)
            if block["label"] in geometry_exempt_label_set
        }
        geometry_exempt_pred = {
            index for index, block in enumerate(pred_blocks)
            if block["label"] in geometry_exempt_label_set
        }
        matched, _used_gt, used_pred = match_blocks(
            gt_blocks,
            pred_blocks,
            min_iou=min_iou,
            min_gt_coverage=min_gt_coverage,
            excluded_gt_indices=geometry_exempt_gt,
            excluded_pred_indices=geometry_exempt_pred,
        )
        matched.update(label_matches)
        used_pred.update(label_used_pred)
        grouped_correct_gt, grouped_correct_pred = region_correct_indices(
            gt_blocks,
            pred_blocks,
            min_region_coverage=min_region_coverage,
            min_iou=min_iou,
            key_fields=("label",),
            excluded_labels=tuple(geometry_exempt_label_set),
        )
        grouped_level_gt, grouped_level_pred = region_correct_indices(
            gt_blocks,
            pred_blocks,
            min_region_coverage=min_region_coverage,
            min_iou=min_iou,
            key_fields=("label", "level"),
            excluded_labels=tuple(geometry_exempt_label_set),
        )
        strict_label_correct = sum(
            gt_blocks[gt_index]["label"] == pred_blocks[pred_index]["label"]
            for gt_index, (pred_index, _coverage, _iou) in matched.items()
        )
        strict_correct_gt = {
            gt_index
            for gt_index, (pred_index, _coverage, _iou) in matched.items()
            if gt_blocks[gt_index]["label"] == pred_blocks[pred_index]["label"]
        }
        strict_correct_pred = {
            pred_index
            for gt_index, (pred_index, _coverage, _iou) in matched.items()
            if gt_blocks[gt_index]["label"] == pred_blocks[pred_index]["label"]
        }
        strict_level_gt = {
            gt_index
            for gt_index, (pred_index, _coverage, _iou) in matched.items()
            if gt_blocks[gt_index]["label"] == pred_blocks[pred_index]["label"]
            and gt_blocks[gt_index]["level"] == pred_blocks[pred_index]["level"]
        }
        strict_level_pred = {
            pred_index
            for gt_index, (pred_index, _coverage, _iou) in matched.items()
            if gt_blocks[gt_index]["label"] == pred_blocks[pred_index]["label"]
            and gt_blocks[gt_index]["level"] == pred_blocks[pred_index]["level"]
        }
        correct_gt = strict_correct_gt | grouped_correct_gt | bbox_exempt_gt
        correct_pred = strict_correct_pred | grouped_correct_pred | bbox_exempt_pred
        correct_level_gt = strict_level_gt | grouped_level_gt | bbox_exempt_gt
        correct_level_pred = strict_level_pred | grouped_level_pred | bbox_exempt_pred

        for pred_index, pred in enumerate(pred_blocks):
            pred_label = pred["label"]
            pred_level = pred["level"]
            predicted[pred_label] += 1
            lvl_predicted[pred_level] += 1
            if pred_label == "paragraph_title":
                para_lvl_predicted[pred_level] += 1
            if pred_index in correct_pred:
                pred_correct[pred_label] += 1
            if pred_index in correct_level_pred:
                lvl_pred_correct[pred_level] += 1
                if pred_label == "paragraph_title":
                    para_lvl_pred_correct[pred_level] += 1

        job_correct = 0
        job_pred_correct = len(correct_pred)
        job_missing = 0
        for gt_index, gt in enumerate(gt_blocks):
            gt_label = gt["label"]
            gt_level = gt["level"]
            support[gt_label] += 1
            lvl_support[gt_level] += 1
            if gt_label == "paragraph_title":
                para_lvl_support[gt_level] += 1
            if gt_index in correct_gt:
                correct[gt_label] += 1
                total_correct += 1
                job_correct += 1
            elif gt_index not in matched:
                missing += 1
                job_missing += 1
                confusion[(gt_label, MISSING_LABEL)] += 1
            else:
                pred_index, _coverage, _iou = matched[gt_index]
                pred = pred_blocks[pred_index]
                confusion[(gt_label, pred["label"])] += 1

            if gt_index in correct_level_gt:
                lvl_correct[gt_level] += 1
            else:
                if gt_index in matched:
                    pred_index, _coverage, _iou = matched[gt_index]
                    pred = pred_blocks[pred_index]
                    level_value = pred["level"] if pred["label"] == gt_label else pred["label"]
                else:
                    level_value = MISSING_LABEL
                lvl_confusion[(gt_level, level_value)] += 1
            if gt_label == "paragraph_title":
                if gt_index in correct_level_gt:
                    para_lvl_correct[gt_level] += 1
                else:
                    if gt_index in matched:
                        pred_index, _coverage, _iou = matched[gt_index]
                        pred = pred_blocks[pred_index]
                        level_value = pred["level"] if pred["label"] == "paragraph_title" else pred["label"]
                    else:
                        level_value = MISSING_LABEL
                    para_lvl_confusion[(gt_level, level_value)] += 1
        unmatched_pred = set(range(len(pred_blocks))) - used_pred - correct_pred
        for pred_index in unmatched_pred:
            pred = pred_blocks[pred_index]
            confusion[(EXTRA_LABEL, pred["label"])] += 1
            lvl_confusion[(EXTRA_LABEL, pred["level"])] += 1
            if pred["label"] == "paragraph_title":
                para_lvl_confusion[(EXTRA_LABEL, pred["level"])] += 1

        total_gt += len(gt_blocks)
        total_matched += len(matched)
        total_pred_correct += len(correct_pred)
        total_strict_label_correct += strict_label_correct
        extra += len(unmatched_pred)
        job_rows.append(
            {
                "job_id": job_id,
                "gt": len(gt_blocks),
                "predicted": len(pred_blocks),
                "matched": len(matched),
                "correct": job_correct,
                "pred_correct": job_pred_correct,
                "detection_recall": len(matched) / len(gt_blocks) if gt_blocks else 0.0,
                "classification_accuracy": strict_label_correct / len(matched) if matched else 0.0,
                "end_to_end_recall": job_correct / len(gt_blocks) if gt_blocks else 0.0,
                "recall": job_correct / len(gt_blocks) if gt_blocks else 0.0,
                "missing": job_missing,
                "extra": len(unmatched_pred),
            }
        )

    for job_id in sorted(set(pred_files) - set(gt_files)):
        pred_blocks = filter_excluded_pages(
            load_blocks(pred_files[job_id]),
            excluded_pages.get(job_id, set()),
        )
        for pred in pred_blocks:
            predicted[pred["label"]] += 1
            lvl_predicted[pred["level"]] += 1
            if pred["label"] == "paragraph_title":
                para_lvl_predicted[pred["level"]] += 1
            confusion[(EXTRA_LABEL, pred["label"])] += 1
        extra += len(pred_blocks)
        skipped.append((job_id, "预测没有对应 ground_truth，整份文档按误检计入"))

    return {
        "support": support,
        "correct": correct,
        "predicted": predicted,
        "pred_correct": pred_correct,
        "confusion": confusion,
        "lvl_support": lvl_support,
        "lvl_correct": lvl_correct,
        "lvl_predicted": lvl_predicted,
        "lvl_pred_correct": lvl_pred_correct,
        "lvl_confusion": lvl_confusion,
        "para_lvl_support": para_lvl_support,
        "para_lvl_correct": para_lvl_correct,
        "para_lvl_predicted": para_lvl_predicted,
        "para_lvl_pred_correct": para_lvl_pred_correct,
        "para_lvl_confusion": para_lvl_confusion,
        "total_gt": total_gt,
        "total_matched": total_matched,
        "total_correct": total_correct,
        "total_pred_correct": total_pred_correct,
        "total_strict_label_correct": total_strict_label_correct,
        "missing": missing,
        "extra": extra,
        "excluded_page_count": excluded_page_count,
        "job_rows": job_rows,
        "skipped": skipped,
        "min_gt_coverage": min_gt_coverage,
        "min_iou": min_iou,
        "min_region_coverage": min_region_coverage,
        "bbox_exempt_labels": bbox_exempt_labels,
        "label_only_labels": label_only_labels,
    }


def evaluate_annotation_roots(
    ground_truth_root: str,
    model_pre_root: str,
    min_gt_coverage: Optional[float] = None,
    min_iou: float = 0.5,
    min_region_coverage: float = 0.8,
    excluded_pages: Optional[Dict[str, set]] = None,
    bbox_exempt_labels: Tuple[str, ...] = DEFAULT_BBOX_EXEMPT_LABELS,
    label_only_labels: Tuple[str, ...] = DEFAULT_LABEL_ONLY_LABELS,
) -> Dict[str, Any]:
    gt_files = discover_second_annotation_files(ground_truth_root) or json_files_by_job(ground_truth_root)
    pred_files = discover_first_annotation_files(model_pre_root) or json_files_by_job(model_pre_root)
    result = evaluate_file_maps(
        gt_files,
        pred_files,
        min_gt_coverage=min_gt_coverage,
        min_iou=min_iou,
        min_region_coverage=min_region_coverage,
        excluded_pages=excluded_pages,
        bbox_exempt_labels=bbox_exempt_labels,
        label_only_labels=label_only_labels,
    )

    category_jobs: Dict[str, List[str]] = defaultdict(list)
    for job_id, path in gt_files.items():
        relative_parts = os.path.relpath(path, ground_truth_root).split(os.sep)
        filename = os.path.basename(path)
        if len(relative_parts) >= 2 and not filename.startswith("annotation_v2_"):
            category_jobs[relative_parts[0]].append(job_id)
        else:
            category_jobs["all"].append(job_id)

    if set(category_jobs) != {"all"}:
        result["by_category"] = {}
        for category, job_ids in sorted(category_jobs.items()):
            result["by_category"][category] = evaluate_file_maps(
                {job_id: gt_files[job_id] for job_id in job_ids},
                {job_id: pred_files[job_id] for job_id in job_ids if job_id in pred_files},
                min_gt_coverage=min_gt_coverage,
                min_iou=min_iou,
                min_region_coverage=min_region_coverage,
                excluded_pages=excluded_pages,
                bbox_exempt_labels=bbox_exempt_labels,
                label_only_labels=label_only_labels,
            )
    return result


def match_blocks(
    gt_blocks: List[Dict[str, Any]],
    pred_blocks: List[Dict[str, Any]],
    min_gt_coverage: Optional[float] = None,
    min_iou: float = 0.5,
    excluded_gt_indices: Optional[set] = None,
    excluded_pred_indices: Optional[set] = None,
) -> Tuple[Dict[int, Tuple[int, float, float]], set, set]:
    """Greedily match highest-IoU boxes one-to-one, independent of label."""
    excluded_gt_indices = excluded_gt_indices or set()
    excluded_pred_indices = excluded_pred_indices or set()
    preds_by_page: Dict[int, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for pred_index, pred in enumerate(pred_blocks):
        if pred_index in excluded_pred_indices:
            continue
        preds_by_page[pred["page_id"]].append((pred_index, pred))

    candidates: List[Tuple[float, float, int, int]] = []
    for gt_index, gt in enumerate(gt_blocks):
        if gt_index in excluded_gt_indices:
            continue
        for pred_index, pred in preds_by_page.get(gt["page_id"], []):
            coverage, iou = bbox_metrics(gt["bbox"], pred["bbox"])
            if iou < min_iou:
                continue
            if min_gt_coverage is not None and coverage < min_gt_coverage:
                continue
            candidates.append((iou, coverage, gt_index, pred_index))

    matched: Dict[int, Tuple[int, float, float]] = {}
    used_gt: set = set()
    used_pred: set = set()

    candidates.sort(reverse=True)
    for iou, coverage, gt_index, pred_index in candidates:
        if gt_index in used_gt or pred_index in used_pred:
            continue
        matched[gt_index] = (pred_index, coverage, iou)
        used_gt.add(gt_index)
        used_pred.add(pred_index)
    return matched, used_gt, used_pred


def evaluate(
    datasets_dir: str,
    prediction_dir: str = "qwen3.6-27b",
    min_gt_coverage: Optional[float] = None,
    min_iou: float = 0.5,
    min_region_coverage: float = 0.8,
    excluded_pages: Optional[Dict[str, set]] = None,
    bbox_exempt_labels: Tuple[str, ...] = DEFAULT_BBOX_EXEMPT_LABELS,
    label_only_labels: Tuple[str, ...] = DEFAULT_LABEL_ONLY_LABELS,
) -> Dict[str, Any]:
    gt_root = os.path.join(datasets_dir, "ground_truth")
    pred_root = prediction_dir if os.path.isabs(prediction_dir) else os.path.join(datasets_dir, prediction_dir)
    if not os.path.isdir(gt_root):
        raise SystemExit(f"找不到 ground_truth 目录: {gt_root}")
    if not os.path.isdir(pred_root):
        raise SystemExit(f"找不到预测目录: {pred_root}")

    return evaluate_annotation_roots(
        gt_root,
        pred_root,
        min_gt_coverage=min_gt_coverage,
        min_iou=min_iou,
        min_region_coverage=min_region_coverage,
        excluded_pages=excluded_pages,
        bbox_exempt_labels=bbox_exempt_labels,
        label_only_labels=label_only_labels,
    )


def f1_score(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def validate_threshold(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} 必须在 0 到 1 之间，当前值: {value}")


def level_sort_key(level: str) -> Tuple[int, int, str]:
    if level.startswith("H") and level[1:].isdigit():
        return (0, int(level[1:]), level)
    if level == "none":
        return (2, 0, level)
    return (1, 0, level)


def print_report(r: Dict[str, Any]) -> None:
    print("=" * 92)
    print("版面分析评估 (几何匹配与标签评估解耦)")
    print("=" * 92)
    threshold = f"IoU >= {r['min_iou']:.2f}"
    if r["min_gt_coverage"] is not None:
        threshold += f", GT bbox 覆盖率 >= {r['min_gt_coverage']:.0%}"
    print(
        f"检测阈值: {threshold}；label 指标允许同标签区域拆分/合并，"
        f"双向覆盖率 >= {r['min_region_coverage']:.0%}"
    )
    if r["bbox_exempt_labels"]:
        print(f"完全免除 bbox/漏检/误检惩罚的标签: {', '.join(r['bbox_exempt_labels'])}")
    if r["label_only_labels"]:
        print(f"只按同页标签配对、不检测 bbox 的标签: {', '.join(r['label_only_labels'])}")
    if r["excluded_page_count"]:
        print(f"公平比较: 两个模型统一排除 {r['excluded_page_count']} 个失败页面")

    print("\n【各任务概况】")
    print(f"  {'文档':<24}{'GT':>7}{'预测':>7}{'匹配':>7}{'标签正确':>10}{'端到端召回':>12}{'漏检':>7}{'误检':>7}")
    for row in r["job_rows"]:
        print(
            f"  {row['job_id'][:24]:<24}{row['gt']:>7}{row['predicted']:>7}{row['matched']:>7}"
            f"{row['correct']:>10}{row['end_to_end_recall']:>11.1%}{row['missing']:>7}{row['extra']:>7}"
        )

    print("\n【各 label 指标】(以 ground_truth bbox 为基准)")
    header = f"  {'label':<20}{'support':>9}{'correct':>9}{'recall':>9}{'precision':>11}{'f1':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    labels = sorted(set(r["support"]) | set(r["predicted"]))
    for label in labels:
        sup = r["support"][label]
        cor = r["correct"][label]
        pre = r["predicted"][label]
        pred_cor = r["pred_correct"][label]
        recall = cor / sup if sup else 0.0
        precision = pred_cor / pre if pre else 0.0
        print(f"  {label:<20}{sup:>9}{cor:>9}{recall:>8.1%}{precision:>10.1%}{f1_score(precision, recall):>8.3f}")

    print("\n【label + level 联合指标】(全部 block)")
    header = f"  {'level':<20}{'support':>9}{'correct':>9}{'recall':>9}{'precision':>11}{'f1':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    levels = sorted(set(r["lvl_support"]) | set(r["lvl_predicted"]), key=level_sort_key)
    for level in levels:
        sup = r["lvl_support"][level]
        cor = r["lvl_correct"][level]
        pre = r["lvl_predicted"][level]
        pred_cor = r["lvl_pred_correct"][level]
        recall = cor / sup if sup else 0.0
        precision = pred_cor / pre if pre else 0.0
        print(f"  {level:<20}{sup:>9}{cor:>9}{recall:>8.1%}{precision:>10.1%}{f1_score(precision, recall):>8.3f}")

    print("\n【paragraph_title 按层级指标】(label 和 level 都正确才算 correct)")
    header = f"  {'level':<20}{'support':>9}{'correct':>9}{'recall':>9}{'precision':>11}{'f1':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    para_levels = sorted(set(r["para_lvl_support"]) | set(r["para_lvl_predicted"]), key=level_sort_key)
    for level in para_levels:
        sup = r["para_lvl_support"][level]
        cor = r["para_lvl_correct"][level]
        pre = r["para_lvl_predicted"][level]
        pred_cor = r["para_lvl_pred_correct"][level]
        recall = cor / sup if sup else 0.0
        precision = pred_cor / pre if pre else 0.0
        print(f"  {level:<20}{sup:>9}{cor:>9}{recall:>8.1%}{precision:>10.1%}{f1_score(precision, recall):>8.3f}")

    total_pred = sum(r["predicted"].values())
    detection_precision = r["total_matched"] / total_pred if total_pred else 0.0
    detection_recall = r["total_matched"] / r["total_gt"] if r["total_gt"] else 0.0
    classification_accuracy = (
        r["total_strict_label_correct"] / r["total_matched"]
        if r["total_matched"]
        else 0.0
    )
    end_to_end_precision = r["total_pred_correct"] / total_pred if total_pred else 0.0
    end_to_end_recall = r["total_correct"] / r["total_gt"] if r["total_gt"] else 0.0
    print("\n【整体】")
    print(
        f"  block 数: GT={r['total_gt']}, 预测={total_pred}, 几何匹配={r['total_matched']}, "
        f"区域等价正确 GT/预测={r['total_correct']}/{r['total_pred_correct']}"
    )
    print(
        "  检测       : "
        f"Precision={detection_precision:.2%}, Recall={detection_recall:.2%}, "
        f"F1={f1_score(detection_precision, detection_recall):.2%}"
    )
    print(f"  严格一对一匹配后的标签准确率: {classification_accuracy:.2%}")
    print(
        "  端到端     : "
        f"Precision={end_to_end_precision:.2%}, Recall={end_to_end_recall:.2%}, "
        f"F1={f1_score(end_to_end_precision, end_to_end_recall):.2%}"
    )
    print(f"  漏检={r['missing']}, 误检={r['extra']}")

    if r.get("by_category"):
        for category, category_result in r["by_category"].items():
            print(f"\n【{category}：各 label】")
            print(f"  {'label':<20}{'support':>9}{'recall':>10}{'precision':>11}{'f1':>9}")
            labels = sorted(set(category_result["support"]) | set(category_result["predicted"]))
            for label in labels:
                support = category_result["support"][label]
                predicted = category_result["predicted"][label]
                gt_correct = category_result["correct"][label]
                pred_correct = category_result["pred_correct"][label]
                recall = gt_correct / support if support else 0.0
                precision = pred_correct / predicted if predicted else 0.0
                print(
                    f"  {label:<20}{support:>9}{recall:>9.1%}"
                    f"{precision:>10.1%}{f1_score(precision, recall):>9.3f}"
                )

            print(f"\n【{category}：paragraph_title 层级】")
            print(f"  {'level':<20}{'support':>9}{'recall':>10}{'precision':>11}{'f1':>9}")
            levels = sorted(
                set(category_result["para_lvl_support"]) | set(category_result["para_lvl_predicted"]),
                key=level_sort_key,
            )
            for level in levels:
                support = category_result["para_lvl_support"][level]
                predicted = category_result["para_lvl_predicted"][level]
                gt_correct = category_result["para_lvl_correct"][level]
                pred_correct = category_result["para_lvl_pred_correct"][level]
                recall = gt_correct / support if support else 0.0
                precision = pred_correct / predicted if predicted else 0.0
                print(
                    f"  {level:<20}{support:>9}{recall:>9.1%}"
                    f"{precision:>10.1%}{f1_score(precision, recall):>9.3f}"
                )

    if r["confusion"]:
        print("\n【主要错误  GT -> 预测 (Top 20)】")
        for (gt_label, pred_label), count in sorted(r["confusion"].items(), key=lambda item: -item[1])[:20]:
            print(f"  {gt_label:<20} -> {pred_label:<20} {count}")

    if r["para_lvl_confusion"]:
        print("\n【paragraph_title 层级错误 GT level -> 预测 (Top 10)】")
        for (gt_level, pred_level), count in sorted(r["para_lvl_confusion"].items(), key=lambda item: -item[1])[:10]:
            print(f"  {gt_level:<10} -> {pred_level:<16} {count}")

    if r["skipped"]:
        print("\n【数据对齐提示】")
        for job_id, reason in r["skipped"]:
            print(f"  {job_id}: {reason}")


def result_to_jsonable(r: Dict[str, Any]) -> Dict[str, Any]:
    labels = sorted(set(r["support"]) | set(r["predicted"]))
    per_label = {}
    for label in labels:
        sup = r["support"][label]
        cor = r["correct"][label]
        pre = r["predicted"][label]
        pred_cor = r["pred_correct"][label]
        recall = cor / sup if sup else 0.0
        precision = pred_cor / pre if pre else 0.0
        per_label[label] = {
            "support": sup,
            "correct": cor,
            "pred_correct": pred_cor,
            "predicted": pre,
            "recall": recall,
            "precision": precision,
            "f1": f1_score(precision, recall),
        }
    paragraph_title_by_level = {}
    para_levels = sorted(set(r["para_lvl_support"]) | set(r["para_lvl_predicted"]), key=level_sort_key)
    for level in para_levels:
        sup = r["para_lvl_support"][level]
        cor = r["para_lvl_correct"][level]
        pre = r["para_lvl_predicted"][level]
        pred_cor = r["para_lvl_pred_correct"][level]
        recall = cor / sup if sup else 0.0
        precision = pred_cor / pre if pre else 0.0
        paragraph_title_by_level[level] = {
            "support": sup,
            "correct": cor,
            "pred_correct": pred_cor,
            "predicted": pre,
            "recall": recall,
            "precision": precision,
            "f1": f1_score(precision, recall),
        }
    total_predicted = sum(r["predicted"].values())
    detection_precision = r["total_matched"] / total_predicted if total_predicted else 0.0
    detection_recall = r["total_matched"] / r["total_gt"] if r["total_gt"] else 0.0
    end_to_end_precision = r["total_pred_correct"] / total_predicted if total_predicted else 0.0
    end_to_end_recall = r["total_correct"] / r["total_gt"] if r["total_gt"] else 0.0
    jsonable = {
        "min_gt_coverage": r["min_gt_coverage"],
        "min_iou": r["min_iou"],
        "min_region_coverage": r["min_region_coverage"],
        "bbox_exempt_labels": list(r["bbox_exempt_labels"]),
        "label_only_labels": list(r["label_only_labels"]),
        "matching": {
            "detection_method": "greedy_one_to_one_highest_iou",
            "label_method": "same_label_content_or_bidirectional_region_coverage",
            "min_iou": r["min_iou"],
            "min_gt_coverage": r["min_gt_coverage"],
            "min_region_coverage": r["min_region_coverage"],
            "bbox_exempt_labels": list(r["bbox_exempt_labels"]),
            "label_only_labels": list(r["label_only_labels"]),
        },
        "detection": {
            "precision": detection_precision,
            "recall": detection_recall,
            "f1": f1_score(detection_precision, detection_recall),
        },
        "classification_accuracy_on_matched": (
            r["total_strict_label_correct"] / r["total_matched"]
            if r["total_matched"]
            else 0.0
        ),
        "end_to_end": {
            "precision": end_to_end_precision,
            "recall": end_to_end_recall,
            "f1": f1_score(end_to_end_precision, end_to_end_recall),
        },
        "overall_accuracy": end_to_end_recall,
        "total_gt": r["total_gt"],
        "total_predicted": total_predicted,
        "total_matched": r["total_matched"],
        "total_correct": r["total_correct"],
        "total_pred_correct": r["total_pred_correct"],
        "missing": r["missing"],
        "extra": r["extra"],
        "excluded_page_count": r["excluded_page_count"],
        "per_label": per_label,
        "paragraph_title_by_level": paragraph_title_by_level,
        "job_rows": r["job_rows"],
        "skipped": r["skipped"],
    }
    if r.get("by_category"):
        jsonable["by_category"] = {
            category: result_to_jsonable(category_result)
            for category, category_result in r["by_category"].items()
        }
    return jsonable


def main() -> None:
    parser = argparse.ArgumentParser(description="按 IoU 几何匹配评估版面分析预测")
    parser.add_argument("--datasets", default=DEFAULT_DATASETS, help=f"datasets 目录 (默认: {DEFAULT_DATASETS})")
    parser.add_argument(
        "--prediction",
        default="qwen3.6-27b",
        help="datasets 下的预测目录名或绝对路径 (默认: qwen3.6-27b)",
    )
    parser.add_argument("--first-annotations", help="一次标注目录，例如 backend/datasets/first_annotations")
    parser.add_argument("--second-annotations", help="二次标注目录，例如 backend/datasets/second_annotations；作为标准答案")
    parser.add_argument(
        "--min-gt-coverage",
        type=float,
        default=None,
        help="可选附加条件：预测 bbox 至少覆盖 GT bbox 的比例；标准评估通常不设置",
    )
    parser.add_argument("--min-iou", type=float, default=0.5, help="IoU 下限 (默认: 0.5)")
    parser.add_argument(
        "--min-region-coverage",
        type=float,
        default=0.8,
        help="拆分/合并区域的双向覆盖率下限 (默认: 0.8)",
    )
    parser.add_argument(
        "--exclude-failed-pages-from",
        action="append",
        default=[],
        metavar="PREDICTION_DIR",
        help="读取该预测目录的失败页，并从所有模型的 GT/预测中统一排除；可重复指定",
    )
    parser.add_argument("--json", metavar="PATH", help="可选: 将结果以 JSON 写入该文件")
    args = parser.parse_args()

    failed_page_maps = []
    for failed_root in args.exclude_failed_pages_from:
        resolved_root = (
            failed_root
            if os.path.isabs(failed_root)
            else os.path.join(args.datasets, failed_root)
        )
        failed_page_maps.append(discover_failed_pages(resolved_root))
    excluded_pages = merge_failed_pages(*failed_page_maps)

    if args.first_annotations or args.second_annotations:
        if not args.first_annotations or not args.second_annotations:
            raise SystemExit("--first-annotations 与 --second-annotations 需要同时提供")
        result = evaluate_annotation_roots(
            args.second_annotations,
            args.first_annotations,
            min_gt_coverage=args.min_gt_coverage,
            min_iou=args.min_iou,
            min_region_coverage=args.min_region_coverage,
            excluded_pages=excluded_pages,
        )
    else:
        result = evaluate(
            args.datasets,
            args.prediction,
            min_gt_coverage=args.min_gt_coverage,
            min_iou=args.min_iou,
            min_region_coverage=args.min_region_coverage,
            excluded_pages=excluded_pages,
        )
    print_report(result)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result_to_jsonable(result), f, ensure_ascii=False, indent=2)
        print(f"\n已写入 JSON: {args.json}")


if __name__ == "__main__":
    main()
