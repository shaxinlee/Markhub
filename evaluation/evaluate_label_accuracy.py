#!/usr/bin/env python3
"""Evaluate model_pre annotations against ground_truth annotations.

Expected data layout::

    evaluation/datasets/ground_truth/<job_id>.json  # second annotation
    evaluation/datasets/model_pre/<job_id>.json     # first annotation / model prediction

For each ground-truth block, the evaluator finds the best model_pre bbox on the
same page. A prediction is usable only when it covers enough of the GT bbox.
Then the predicted label is compared with the GT label. Missing GT blocks count
as errors for that GT label; unmatched predictions count as false positives.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASETS = os.path.join(HERE, "datasets")
MISSING_LABEL = "__missing__"
EXTRA_LABEL = "__extra__"
MERGEABLE_LABELS = {"text"}
RELAXED_COVERAGE_LABELS = {
    "footer": 0.5,
    "header": 0.5,
    "seal": 0.6,
    "vision_footnote": 0.5,
}


def normalize_label(block: Dict[str, Any]) -> str:
    return str(block.get("label") or block.get("block_type") or "unknown")


def normalize_level(block: Dict[str, Any]) -> str:
    return str(block.get("level") or "none")


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
        if right <= left:
            continue
        intervals = []
        for bbox in bboxes:
            if bbox[0] < right and bbox[2] > left:
                intervals.append((bbox[1], bbox[3]))
        if not intervals:
            continue
        intervals.sort()
        covered = 0.0
        cur_top, cur_bottom = intervals[0]
        for top, bottom in intervals[1:]:
            if top <= cur_bottom:
                cur_bottom = max(cur_bottom, bottom)
            else:
                covered += cur_bottom - cur_top
                cur_top, cur_bottom = top, bottom
        covered += cur_bottom - cur_top
        total += (right - left) * covered
    return total


def bbox_group_gt_coverage(gt_bbox: List[float], pred_bboxes: List[List[float]]) -> float:
    intersections = []
    for pred_bbox in pred_bboxes:
        intersection = bbox_intersection_box(gt_bbox, pred_bbox)
        if intersection is not None:
            intersections.append(intersection)
    gt_area = bbox_area(gt_bbox)
    return bbox_union_area(intersections) / gt_area if gt_area else 0.0


def bbox_metrics(gt_bbox: List[float], pred_bbox: List[float]) -> Tuple[float, float]:
    inter = bbox_intersection(gt_bbox, pred_bbox)
    gt_area = bbox_area(gt_bbox)
    pred_area = bbox_area(pred_bbox)
    union = gt_area + pred_area - inter
    gt_coverage = inter / gt_area if gt_area else 0.0
    iou = inter / union if union else 0.0
    return gt_coverage, iou


def min_coverage_for_label(label: str, default_min_gt_coverage: float) -> float:
    return min(default_min_gt_coverage, RELAXED_COVERAGE_LABELS.get(label, default_min_gt_coverage))


def correct_prediction_indices(
    gt_blocks: List[Dict[str, Any]],
    pred_blocks: List[Dict[str, Any]],
    matched: Dict[int, Tuple[int, float, float]],
    used_pred: set,
) -> set:
    correct_pred = set()
    correctly_matched_mergeable_gt = []
    for gt_index, (pred_index, _coverage, _iou) in matched.items():
        gt = gt_blocks[gt_index]
        pred = pred_blocks[pred_index]
        if pred["label"] != gt["label"]:
            continue
        correct_pred.add(pred_index)
        if gt["label"] in MERGEABLE_LABELS:
            correctly_matched_mergeable_gt.append(gt)

    for pred_index in used_pred:
        pred = pred_blocks[pred_index]
        if pred["label"] not in MERGEABLE_LABELS:
            continue
        for gt in correctly_matched_mergeable_gt:
            if pred["page_id"] == gt["page_id"] and bbox_intersection(gt["bbox"], pred["bbox"]) > 0:
                correct_pred.add(pred_index)
                break
    return correct_pred


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
                }
            )
    return blocks


def json_files_by_job(root: str) -> Dict[str, str]:
    if not os.path.isdir(root):
        return {}
    files: Dict[str, str] = {}
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isfile(path) and name.endswith(".json"):
            files[os.path.splitext(name)[0]] = path
            continue
        if os.path.isdir(path):
            candidates = sorted(item for item in os.listdir(path) if item.endswith(".json"))
            if candidates:
                files[name] = os.path.join(path, candidates[-1])
    return files


def discover_first_annotation_files(root: str) -> Dict[str, str]:
    """Find first-pass Markhub annotations under backend/datasets/first_annotations."""
    if not os.path.isdir(root):
        return {}
    files: Dict[str, str] = {}
    for current_root, _dirs, names in os.walk(root):
        if "result.json" not in names:
            continue
        path = os.path.join(current_root, "result.json")
        job_id = os.path.basename(current_root)
        files[job_id] = path
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
            files[job_id] = candidates[-1]
    return files


def evaluate_file_maps(
    gt_files: Dict[str, str],
    pred_files: Dict[str, str],
    min_gt_coverage: float = 0.8,
    min_iou: float = 0.0,
) -> Dict[str, Any]:
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
    missing = 0
    extra = 0
    bbox_too_small = 0
    job_rows = []
    skipped = []

    for job_id in sorted(gt_files):
        gt_path = gt_files[job_id]
        pred_path = pred_files.get(job_id)
        if not pred_path:
            skipped.append((job_id, "找不到对应 model_pre/一次标注"))
            continue

        gt_blocks = load_blocks(gt_path)
        pred_blocks = load_blocks(pred_path)
        matched, used_gt, used_pred = match_blocks(gt_blocks, pred_blocks, min_gt_coverage, min_iou)
        correct_pred = correct_prediction_indices(gt_blocks, pred_blocks, matched, used_pred)

        for pred_index, pred in enumerate(pred_blocks):
            pred_label = pred["label"]
            pred_level = pred["level"]
            predicted[pred_label] += 1
            lvl_predicted[pred_level] += 1
            if pred_label == "paragraph_title":
                para_lvl_predicted[pred_level] += 1
            if pred_index in correct_pred:
                pred_correct[pred_label] += 1
                lvl_pred_correct[pred_level] += 1
                if pred_label == "paragraph_title":
                    para_lvl_pred_correct[pred_level] += 1

        job_correct = 0
        job_missing = 0
        for gt_index, gt in enumerate(gt_blocks):
            gt_label = gt["label"]
            gt_level = gt["level"]
            support[gt_label] += 1
            lvl_support[gt_level] += 1
            if gt_label == "paragraph_title":
                para_lvl_support[gt_level] += 1
            if gt_index not in matched:
                missing += 1
                job_missing += 1
                confusion[(gt_label, MISSING_LABEL)] += 1
                lvl_confusion[(gt_level, MISSING_LABEL)] += 1
                if gt_label == "paragraph_title":
                    para_lvl_confusion[(gt_level, MISSING_LABEL)] += 1
                continue

            pred_index, coverage, _iou = matched[gt_index]
            pred = pred_blocks[pred_index]
            pred_label = pred["label"]
            pred_level = pred["level"]
            if pred_label == gt_label:
                correct[gt_label] += 1
                total_correct += 1
                job_correct += 1
            else:
                confusion[(gt_label, pred_label)] += 1
            if pred_level == gt_level:
                lvl_correct[gt_level] += 1
            else:
                lvl_confusion[(gt_level, pred_level)] += 1
            if gt_label == "paragraph_title":
                if pred_label == "paragraph_title" and pred_level == gt_level:
                    para_lvl_correct[gt_level] += 1
                else:
                    para_lvl_confusion[(gt_level, pred_level if pred_label == "paragraph_title" else pred_label)] += 1
            if coverage < 1.0:
                bbox_too_small += 1

        unmatched_pred = set(range(len(pred_blocks))) - used_pred
        for pred_index in unmatched_pred:
            pred = pred_blocks[pred_index]
            confusion[(EXTRA_LABEL, pred["label"])] += 1
            lvl_confusion[(EXTRA_LABEL, pred["level"])] += 1
            if pred["label"] == "paragraph_title":
                para_lvl_confusion[(EXTRA_LABEL, pred["level"])] += 1

        total_gt += len(gt_blocks)
        total_matched += len(matched)
        extra += len(unmatched_pred)
        job_rows.append(
            {
                "job_id": job_id,
                "gt": len(gt_blocks),
                "matched": len(matched),
                "correct": job_correct,
                "recall": job_correct / len(gt_blocks) if gt_blocks else 0.0,
                "missing": job_missing,
                "extra": len(unmatched_pred),
            }
        )

    for job_id in sorted(set(pred_files) - set(gt_files)):
        skipped.append((job_id, "model_pre/一次标注没有对应 ground_truth/二次标注"))

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
        "missing": missing,
        "extra": extra,
        "bbox_too_small": bbox_too_small,
        "job_rows": job_rows,
        "skipped": skipped,
        "min_gt_coverage": min_gt_coverage,
        "min_iou": min_iou,
    }


def evaluate_annotation_roots(
    ground_truth_root: str,
    model_pre_root: str,
    min_gt_coverage: float = 0.8,
    min_iou: float = 0.0,
) -> Dict[str, Any]:
    gt_files = discover_second_annotation_files(ground_truth_root) or json_files_by_job(ground_truth_root)
    pred_files = discover_first_annotation_files(model_pre_root) or json_files_by_job(model_pre_root)
    return evaluate_file_maps(gt_files, pred_files, min_gt_coverage=min_gt_coverage, min_iou=min_iou)


def match_blocks(
    gt_blocks: List[Dict[str, Any]],
    pred_blocks: List[Dict[str, Any]],
    min_gt_coverage: float,
    min_iou: float,
) -> Tuple[Dict[int, Tuple[int, float, float]], set, set]:
    preds_by_page: Dict[int, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for pred_index, pred in enumerate(pred_blocks):
        preds_by_page[pred["page_id"]].append((pred_index, pred))

    same_label_candidates: List[Tuple[float, float, int, int]] = []
    cross_label_candidates: List[Tuple[float, float, int, int]] = []
    for gt_index, gt in enumerate(gt_blocks):
        if gt["label"] in MERGEABLE_LABELS:
            continue
        gt_min_coverage = min_coverage_for_label(gt["label"], min_gt_coverage)
        for pred_index, pred in preds_by_page.get(gt["page_id"], []):
            coverage, iou = bbox_metrics(gt["bbox"], pred["bbox"])
            if coverage >= gt_min_coverage and iou >= min_iou:
                if pred["label"] == gt["label"]:
                    same_label_candidates.append((coverage, iou, gt_index, pred_index))
                else:
                    cross_label_candidates.append((coverage, iou, gt_index, pred_index))

    matched: Dict[int, Tuple[int, float, float]] = {}
    used_gt: set = set()
    used_pred: set = set()

    same_label_candidates.sort(reverse=True)
    for coverage, iou, gt_index, pred_index in same_label_candidates:
        if gt_index in used_gt or pred_index in used_pred:
            continue
        matched[gt_index] = (pred_index, coverage, iou)
        used_gt.add(gt_index)
        used_pred.add(pred_index)

    cross_label_candidates.sort(reverse=True)
    for coverage, iou, gt_index, pred_index in cross_label_candidates:
        if gt_index in used_gt or pred_index in used_pred:
            continue
        matched[gt_index] = (pred_index, coverage, iou)
        used_gt.add(gt_index)
        used_pred.add(pred_index)

    used_pred_by_fixed_label = {
        pred_index
        for pred_index in used_pred
        if pred_blocks[pred_index]["label"] not in MERGEABLE_LABELS
    }

    for gt_index, gt in enumerate(gt_blocks):
        if gt_index in used_gt or gt["label"] not in MERGEABLE_LABELS:
            continue

        gt_min_coverage = min_coverage_for_label(gt["label"], min_gt_coverage)
        same_label_preds = [
            (pred_index, pred)
            for pred_index, pred in preds_by_page.get(gt["page_id"], [])
            if pred["label"] == gt["label"]
            and pred_index not in used_pred_by_fixed_label
            and bbox_intersection(gt["bbox"], pred["bbox"]) > 0
        ]
        if not same_label_preds:
            continue

        coverage = bbox_group_gt_coverage(
            gt["bbox"],
            [pred["bbox"] for _pred_index, pred in same_label_preds],
        )
        if coverage < gt_min_coverage:
            continue

        primary_pred_index, primary_pred = max(
            same_label_preds,
            key=lambda item: bbox_metrics(gt["bbox"], item[1]["bbox"]),
        )
        _single_coverage, iou = bbox_metrics(gt["bbox"], primary_pred["bbox"])
        matched[gt_index] = (primary_pred_index, coverage, iou)
        used_gt.add(gt_index)
        for pred_index, _pred in same_label_preds:
            used_pred.add(pred_index)

    mergeable_fallback_candidates: List[Tuple[float, float, int, int]] = []
    for gt_index, gt in enumerate(gt_blocks):
        if gt_index in used_gt or gt["label"] not in MERGEABLE_LABELS:
            continue
        gt_min_coverage = min_coverage_for_label(gt["label"], min_gt_coverage)
        for pred_index, pred in preds_by_page.get(gt["page_id"], []):
            if pred_index in used_pred or pred["label"] in MERGEABLE_LABELS:
                continue
            coverage, iou = bbox_metrics(gt["bbox"], pred["bbox"])
            if coverage >= gt_min_coverage and iou >= min_iou:
                mergeable_fallback_candidates.append((coverage, iou, gt_index, pred_index))

    mergeable_fallback_candidates.sort(reverse=True)
    for coverage, iou, gt_index, pred_index in mergeable_fallback_candidates:
        if gt_index in used_gt or pred_index in used_pred:
            continue
        matched[gt_index] = (pred_index, coverage, iou)
        used_gt.add(gt_index)
        used_pred.add(pred_index)
    return matched, used_gt, used_pred


def evaluate(datasets_dir: str, min_gt_coverage: float = 0.8, min_iou: float = 0.0) -> Dict[str, Any]:
    gt_root = os.path.join(datasets_dir, "ground_truth")
    pred_root = os.path.join(datasets_dir, "model_pre")
    if not os.path.isdir(gt_root):
        raise SystemExit(f"找不到 ground_truth 目录: {gt_root}")
    if not os.path.isdir(pred_root):
        raise SystemExit(f"找不到 model_pre 目录: {pred_root}")

    return evaluate_annotation_roots(gt_root, pred_root, min_gt_coverage=min_gt_coverage, min_iou=min_iou)


def f1_score(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def level_sort_key(level: str) -> Tuple[int, int, str]:
    if level.startswith("H") and level[1:].isdigit():
        return (0, int(level[1:]), level)
    if level == "none":
        return (2, 0, level)
    return (1, 0, level)


def print_report(r: Dict[str, Any]) -> None:
    print("=" * 92)
    print("按 bbox + label 的准确率评估 (model_pre=预测, ground_truth=标准答案)")
    print("=" * 92)
    print(f"匹配阈值: GT bbox 覆盖率 >= {r['min_gt_coverage']:.0%}, IoU >= {r['min_iou']:.2f}")

    print("\n【各任务概况】")
    print(f"  {'job_id':<16}{'GT数':>8}{'匹配':>8}{'正确':>8}{'召回':>10}{'漏检':>8}{'多检':>8}")
    for row in r["job_rows"]:
        print(
            f"  {row['job_id']:<16}{row['gt']:>8}{row['matched']:>8}{row['correct']:>8}"
            f"{row['recall']:>9.1%}{row['missing']:>8}{row['extra']:>8}"
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

    print("\n【各标题层级 level 指标】")
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

    overall = r["total_correct"] / r["total_gt"] if r["total_gt"] else 0.0
    print("\n【整体】")
    print(f"  ground_truth block 数 : {r['total_gt']}")
    print(f"  bbox 可匹配 block 数  : {r['total_matched']}")
    print(f"  label 正确 block 数   : {r['total_correct']}")
    print(f"  整体 GT 召回准确率    : {overall:.2%}")
    print(f"  ground_truth 有但 model_pre 无/覆盖不足: {r['missing']}")
    print(f"  model_pre 多出的预测 block: {r['extra']}")

    if r["confusion"]:
        print("\n【主要错误  GT -> 预测 (Top 20)】")
        for (gt_label, pred_label), count in sorted(r["confusion"].items(), key=lambda item: -item[1])[:20]:
            print(f"  {gt_label:<20} -> {pred_label:<20} {count}")

    if r["para_lvl_confusion"]:
        print("\n【paragraph_title 层级错误 GT level -> 预测 (Top 10)】")
        for (gt_level, pred_level), count in sorted(r["para_lvl_confusion"].items(), key=lambda item: -item[1])[:10]:
            print(f"  {gt_level:<10} -> {pred_level:<16} {count}")

    if r["skipped"]:
        print("\n【跳过的任务】")
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
    return {
        "min_gt_coverage": r["min_gt_coverage"],
        "min_iou": r["min_iou"],
        "overall_accuracy": r["total_correct"] / r["total_gt"] if r["total_gt"] else 0.0,
        "total_gt": r["total_gt"],
        "total_matched": r["total_matched"],
        "total_correct": r["total_correct"],
        "missing": r["missing"],
        "extra": r["extra"],
        "per_label": per_label,
        "paragraph_title_by_level": paragraph_title_by_level,
        "job_rows": r["job_rows"],
        "skipped": r["skipped"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="按 bbox + label 评估 model_pre 相对 ground_truth 的准确率")
    parser.add_argument("--datasets", default=DEFAULT_DATASETS, help=f"datasets 目录 (默认: {DEFAULT_DATASETS})")
    parser.add_argument("--first-annotations", help="一次标注目录，例如 backend/datasets/first_annotations")
    parser.add_argument("--second-annotations", help="二次标注目录，例如 backend/datasets/second_annotations；作为标准答案")
    parser.add_argument("--min-gt-coverage", type=float, default=0.8, help="预测 bbox 至少覆盖 GT bbox 的比例")
    parser.add_argument("--min-iou", type=float, default=0.0, help="可选 IoU 下限")
    parser.add_argument("--json", metavar="PATH", help="可选: 将结果以 JSON 写入该文件")
    args = parser.parse_args()

    if args.first_annotations or args.second_annotations:
        if not args.first_annotations or not args.second_annotations:
            raise SystemExit("--first-annotations 与 --second-annotations 需要同时提供")
        result = evaluate_annotation_roots(
            args.second_annotations,
            args.first_annotations,
            min_gt_coverage=args.min_gt_coverage,
            min_iou=args.min_iou,
        )
    else:
        result = evaluate(args.datasets, min_gt_coverage=args.min_gt_coverage, min_iou=args.min_iou)
    print_report(result)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result_to_jsonable(result), f, ensure_ascii=False, indent=2)
        print(f"\n已写入 JSON: {args.json}")


if __name__ == "__main__":
    main()
