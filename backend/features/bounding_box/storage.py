"""Persistence and path helpers for the bounding-box annotation feature.

This module owns every disk-touching operation: dataset state files,
image storage, annotation files, atomic JSON I/O. Nothing here imports from
``service.py`` or ``server.py`` — those are downstream consumers.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from urllib.parse import quote

from .paths import ANNOTATIONS_DIR, BOUNDING_BOX_DIR, DATASETS_INDEX_FILE, IMAGES_DIR
from .schemas import BoundingBoxDataset, BoundingBoxImage, BoundingBoxJob, BoundingBoxLabel
from .utils import generate_id, iso_now, normalize_bbox, parse_image_id, sanitize_path_name


def ensure_dataset_storage() -> None:
    for path in (BOUNDING_BOX_DIR, IMAGES_DIR, ANNOTATIONS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def dataset_dir(dataset_id: str) -> Path:
    safe_id = sanitize_path_name(dataset_id)
    return BOUNDING_BOX_DIR / safe_id


def images_dir_for_dataset(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "images"


def annotations_dir_for_dataset(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "annotations"


def draft_annotation_path(dataset_id: str) -> Path:
    return annotations_dir_for_dataset(dataset_id) / "draft.json"


def versioned_annotation_path(dataset_id: str, version: str) -> Path:
    return annotations_dir_for_dataset(dataset_id) / f"annotation_v{version}.json"


def read_json_file(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return default


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def save_image(dataset_id: str, filename: str, content: bytes) -> Dict[str, Any]:
    ensure_dataset_storage()
    img_dir = images_dir_for_dataset(dataset_id)
    img_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = sanitize_path_name(filename)
    image_id = generate_id("img")
    stored_filename = f"{image_id}_{safe_filename}"
    image_path = img_dir / stored_filename

    with open(image_path, "wb") as f:
        f.write(content)

    return {
        "id": image_id,
        "dataset_id": dataset_id,
        "filename": safe_filename,
        "stored_filename": stored_filename,
        "path": str(image_path),
    }


def read_datasets_index() -> List[Dict[str, Any]]:
    return read_json_file(DATASETS_INDEX_FILE, [])


def write_datasets_index(datasets: List[Dict[str, Any]]) -> None:
    ensure_dataset_storage()
    write_json_file(DATASETS_INDEX_FILE, datasets)


def list_bounding_box_datasets() -> List[Dict[str, Any]]:
    datasets = read_datasets_index()
    results = []
    for ds in datasets:
        if not isinstance(ds, dict):
            continue
        dataset_id = ds.get("id", "")
        if not dataset_id:
            continue
        dataset_path = dataset_dir(dataset_id)
        if not dataset_path.exists():
            continue
        img_dir = images_dir_for_dataset(dataset_id)
        image_count = len(list(img_dir.glob("*"))) if img_dir.exists() else 0

        draft = read_json_file(draft_annotation_path(dataset_id), {})
        annotations = draft.get("annotations", {})
        annotated_count = sum(1 for anns in annotations.values() if anns)

        results.append({
            "id": dataset_id,
            "name": ds.get("name", dataset_id),
            "description": ds.get("description", ""),
            "image_count": image_count,
            "annotated_count": annotated_count,
            "label_count": len(ds.get("labels", [])),
            "status": ds.get("status", "active"),
            "created_at": ds.get("created_at", ""),
            "updated_at": ds.get("updated_at", ""),
        })
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results


def create_bounding_box_dataset(name: str, description: str = "", labels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    ensure_dataset_storage()
    dataset_id = generate_id("bbox_ds")
    created_at = iso_now()

    if labels is None:
        from .schemas import DEFAULT_BOUNDING_BOX_LABELS
        labels = DEFAULT_BOUNDING_BOX_LABELS.copy()

    dataset_info = {
        "id": dataset_id,
        "name": name,
        "description": description,
        "labels": labels,
        "status": "active",
        "created_at": created_at,
        "updated_at": created_at,
    }

    datasets = read_datasets_index()
    datasets.append(dataset_info)
    write_datasets_index(datasets)

    dataset_dir(dataset_id).mkdir(parents=True, exist_ok=True)
    images_dir_for_dataset(dataset_id).mkdir(parents=True, exist_ok=True)
    annotations_dir_for_dataset(dataset_id).mkdir(parents=True, exist_ok=True)

    return dataset_info


def get_bounding_box_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    datasets = read_datasets_index()
    for ds in datasets:
        if isinstance(ds, dict) and ds.get("id") == dataset_id:
            return ds
    return None


def update_bounding_box_dataset(dataset_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    datasets = read_datasets_index()
    for i, ds in enumerate(datasets):
        if isinstance(ds, dict) and ds.get("id") == dataset_id:
            ds.update(updates)
            ds["updated_at"] = iso_now()
            datasets[i] = ds
            write_datasets_index(datasets)
            return ds
    return None


def delete_bounding_box_dataset(dataset_id: str) -> bool:
    datasets = read_datasets_index()
    original_len = len(datasets)
    datasets = [ds for ds in datasets if not (isinstance(ds, dict) and ds.get("id") == dataset_id)]
    if len(datasets) < original_len:
        write_datasets_index(datasets)
        ds_dir = dataset_dir(dataset_id)
        if ds_dir.exists():
            shutil.rmtree(ds_dir)
        return True
    return False


def get_bounding_box_job(dataset_id: str) -> Dict[str, Any]:
    dataset_info = get_bounding_box_dataset(dataset_id)
    if not dataset_info:
        raise FileNotFoundError(f"dataset not found: {dataset_id}")

    img_dir = images_dir_for_dataset(dataset_id)
    images = []
    if img_dir.exists():
        for img_path in sorted(img_dir.glob("*")):
            if img_path.is_file() and not img_path.name.startswith("."):
                image_id = parse_image_id(img_path.name)
                width, height = 800, 600
                try:
                    from PIL import Image
                    with Image.open(img_path) as img:
                        width, height = img.size
                except Exception:
                    pass
                images.append({
                    "id": image_id,
                    "dataset_id": dataset_id,
                    "filename": img_path.name,
                    "image_url": f"/api/bounding-box/datasets/{dataset_id}/images/{quote(img_path.name)}",
                    "width": width,
                    "height": height,
                    "annotation_count": 0,
                    "status": "pending",
                    "created_at": iso_now(),
                })

    draft = read_json_file(draft_annotation_path(dataset_id), {})

    return {
        "dataset_id": dataset_id,
        "dataset_name": dataset_info.get("name", dataset_id),
        "status": "annotating" if images else "draft",
        "image_count": len(images),
        "annotated_count": sum(1 for anns in draft.get("annotations", {}).values() if anns),
        "labels": dataset_info.get("labels", []),
        "images": images,
        "annotations": draft.get("annotations", {}),
        "created_at": dataset_info.get("created_at", ""),
        "updated_at": iso_now(),
    }


def save_bounding_box_draft(dataset_id: str, annotations: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    ensure_dataset_storage()
    draft_path = draft_annotation_path(dataset_id)
    draft = {
        "dataset_id": dataset_id,
        "annotations": annotations,
        "updated_at": iso_now(),
    }
    write_json_file(draft_path, draft)
    return draft


def save_bounding_box_version(dataset_id: str, annotations: Dict[str, List[Dict[str, Any]]]) -> Path:
    ensure_dataset_storage()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    version = f"v1_{timestamp}"
    version_path = versioned_annotation_path(dataset_id, version)
    version_data = {
        "dataset_id": dataset_id,
        "version": version,
        "annotations": annotations,
        "created_at": iso_now(),
    }
    write_json_file(version_path, version_data)
    update_bounding_box_dataset(dataset_id, {"status": "completed"})
    return version_path


def get_annotation_for_image(dataset_id: str, image_id: str) -> List[Dict[str, Any]]:
    draft = read_json_file(draft_annotation_path(dataset_id), {})
    return draft.get("annotations", {}).get(image_id, [])


def get_dataset_labels(dataset_id: str) -> List[Dict[str, Any]]:
    dataset_info = get_bounding_box_dataset(dataset_id)
    if not dataset_info:
        raise FileNotFoundError(f"dataset not found: {dataset_id}")
    return dataset_info.get("labels", [])


def add_dataset_label(dataset_id: str, label: Dict[str, Any]) -> Dict[str, Any]:
    datasets = read_datasets_index()
    for i, ds in enumerate(datasets):
        if isinstance(ds, dict) and ds.get("id") == dataset_id:
            labels = ds.get("labels", [])
            new_label = {
                "id": label.get("id") or generate_id("label"),
                "name": label.get("name", "New Label"),
                "color": label.get("color", "#A9A9A9"),
                "description": label.get("description", ""),
            }
            labels.append(new_label)
            ds["labels"] = labels
            ds["label_count"] = len(labels)
            ds["updated_at"] = iso_now()
            datasets[i] = ds
            write_datasets_index(datasets)
            return new_label
    raise FileNotFoundError(f"dataset not found: {dataset_id}")


def update_dataset_label(dataset_id: str, label_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    datasets = read_datasets_index()
    for i, ds in enumerate(datasets):
        if isinstance(ds, dict) and ds.get("id") == dataset_id:
            labels = ds.get("labels", [])
            for j, label in enumerate(labels):
                if label.get("id") == label_id:
                    label.update({
                        "name": updates.get("name", label.get("name", "New Label")),
                        "color": updates.get("color", label.get("color", "#A9A9A9")),
                        "description": updates.get("description", label.get("description", "")),
                    })
                    labels[j] = label
                    ds["labels"] = labels
                    ds["updated_at"] = iso_now()
                    datasets[i] = ds
                    write_datasets_index(datasets)
                    return label
            raise FileNotFoundError(f"label not found: {label_id}")
    raise FileNotFoundError(f"dataset not found: {dataset_id}")


def delete_dataset_label(dataset_id: str, label_id: str) -> Dict[str, Any]:
    datasets = read_datasets_index()
    for i, ds in enumerate(datasets):
        if isinstance(ds, dict) and ds.get("id") == dataset_id:
            labels = ds.get("labels", [])
            original_len = len(labels)
            labels = [l for l in labels if l.get("id") != label_id]
            if len(labels) == original_len:
                raise FileNotFoundError(f"label not found: {label_id}")
            ds["labels"] = labels
            ds["label_count"] = len(labels)
            ds["updated_at"] = iso_now()
            datasets[i] = ds
            write_datasets_index(datasets)
            return {"success": True, "label_id": label_id}
    raise FileNotFoundError(f"dataset not found: {dataset_id}")
