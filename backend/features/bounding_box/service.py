"""Business logic for the bounding-box annotation feature.

This module handles the core business workflows: dataset management,
image handling, annotation CRUD. It imports from storage, schemas, utils,
and paths but not from server.
"""

from __future__ import annotations

import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from PIL import Image

from .paths import IMAGES_DIR
from .schemas import DEFAULT_BOUNDING_BOX_LABELS, BoundingBoxAnnotation, BoundingBoxLabel
from .storage import (
    annotations_dir_for_dataset,
    create_bounding_box_dataset,
    delete_bounding_box_dataset,
    ensure_dataset_storage,
    get_annotation_for_image,
    get_bounding_box_dataset,
    get_bounding_box_job,
    images_dir_for_dataset,
    list_bounding_box_datasets,
    save_bounding_box_draft,
    save_bounding_box_version,
    update_bounding_box_dataset,
)
from .utils import generate_id, iso_now, normalize_bbox, parse_image_id


def list_datasets() -> List[Dict[str, Any]]:
    return list_bounding_box_datasets()


def get_dataset(dataset_id: str) -> Dict[str, Any]:
    dataset = get_bounding_box_dataset(dataset_id)
    if not dataset:
        raise FileNotFoundError(f"dataset not found: {dataset_id}")
    return dataset


def create_dataset(name: str, description: str = "", labels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return create_bounding_box_dataset(name, description, labels)


def update_dataset(dataset_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    updated = update_bounding_box_dataset(dataset_id, updates)
    if not updated:
        raise FileNotFoundError(f"dataset not found: {dataset_id}")
    return updated


def remove_dataset(dataset_id: str) -> Dict[str, Any]:
    if not delete_bounding_box_dataset(dataset_id):
        raise FileNotFoundError(f"dataset not found: {dataset_id}")
    return {"success": True, "dataset_id": dataset_id}


def get_job(dataset_id: str) -> Dict[str, Any]:
    return get_bounding_box_job(dataset_id)


def add_images(dataset_id: str, files: List[Dict[str, Any]]) -> Dict[str, Any]:
    ensure_dataset_storage()
    img_dir = images_dir_for_dataset(dataset_id)
    img_dir.mkdir(parents=True, exist_ok=True)

    added_images = []
    for file_info in files:
        filename = file_info.get("filename", "unknown")
        content = file_info.get("content", b"")
        image_id = file_info.get("id") or generate_id("img")

        safe_filename = f"{image_id}_{Path(filename).name}"
        image_path = img_dir / safe_filename

        if isinstance(content, str):
            content = content.encode("utf-8")
        with open(image_path, "wb") as f:
            f.write(content)

        width, height = 800, 600
        try:
            with Image.open(BytesIO(content)) as img:
                width, height = img.size
        except Exception:
            pass

        added_images.append({
            "id": image_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "image_url": f"/api/bounding-box/datasets/{dataset_id}/images/{quote(safe_filename)}",
            "width": width,
            "height": height,
            "annotation_count": 0,
            "status": "pending",
            "created_at": iso_now(),
        })

    update_bounding_box_dataset(dataset_id, {"status": "active"})
    return {"added": added_images, "total": len(added_images)}


def remove_image(dataset_id: str, image_id: str) -> Dict[str, Any]:
    img_dir = images_dir_for_dataset(dataset_id)
    if not img_dir.exists():
        raise FileNotFoundError(f"images not found for dataset: {dataset_id}")

    removed = False
    for img_path in img_dir.glob("*"):
        if img_path.is_file() and parse_image_id(img_path.name) == image_id:
            img_path.unlink()
            removed = True
            break

    if not removed:
        raise FileNotFoundError(f"image not found: {image_id}")

    return {"success": True, "image_id": image_id}


def get_annotations(dataset_id: str, image_id: Optional[str] = None) -> Any:
    if image_id:
        return get_annotation_for_image(dataset_id, image_id)
    job = get_bounding_box_job(dataset_id)
    return job.get("annotations", {})


def save_annotation(dataset_id: str, image_id: str, annotation_data: Dict[str, Any]) -> Dict[str, Any]:
    job = get_bounding_box_job(dataset_id)
    annotations = job.get("annotations", {})
    image_annotations = annotations.get(image_id, [])

    annotation_id = annotation_data.get("id") or generate_id("ann")
    bbox = normalize_bbox(annotation_data.get("bbox", [0, 0, 0, 0]))
    label_id = str(annotation_data.get("label_id", "other"))
    label_name = str(annotation_data.get("label_name", "other"))

    new_annotation = {
        "id": annotation_id,
        "image_id": image_id,
        "label_id": label_id,
        "label_name": label_name,
        "bbox": list(bbox),
        "confidence": annotation_data.get("confidence"),
        "notes": annotation_data.get("notes", ""),
        "created_at": annotation_data.get("created_at") or iso_now(),
        "updated_at": iso_now(),
    }

    existing_idx = None
    for i, ann in enumerate(image_annotations):
        if ann.get("id") == annotation_id:
            existing_idx = i
            break

    if existing_idx is not None:
        image_annotations[existing_idx] = new_annotation
    else:
        image_annotations.append(new_annotation)

    annotations[image_id] = image_annotations
    save_bounding_box_draft(dataset_id, annotations)

    return new_annotation


def delete_annotation(dataset_id: str, image_id: str, annotation_id: str) -> Dict[str, Any]:
    job = get_bounding_box_job(dataset_id)
    annotations = job.get("annotations", {})
    image_annotations = annotations.get(image_id, [])

    original_len = len(image_annotations)
    image_annotations = [ann for ann in image_annotations if ann.get("id") != annotation_id]

    if len(image_annotations) == original_len:
        raise FileNotFoundError(f"annotation not found: {annotation_id}")

    annotations[image_id] = image_annotations
    save_bounding_box_draft(dataset_id, annotations)

    return {"success": True, "annotation_id": annotation_id}


def save_draft(dataset_id: str, annotations: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return save_bounding_box_draft(dataset_id, annotations)


def submit_version(dataset_id: str, annotations: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(annotations, dict):
        # Persist the submitted annotations as the working draft. The workspace
        # always reloads from the draft, so without this a submit made before
        # "save draft" would store an empty version and lose the boxes on reopen.
        save_bounding_box_draft(dataset_id, annotations)
    else:
        job = get_bounding_box_job(dataset_id)
        annotations = job.get("annotations", {})
    version_path = save_bounding_box_version(dataset_id, annotations)
    return {
        "success": True,
        "dataset_id": dataset_id,
        "version_path": str(version_path),
        "annotated_count": sum(1 for anns in annotations.values() if anns),
    }


def get_default_labels() -> List[Dict[str, Any]]:
    return DEFAULT_BOUNDING_BOX_LABELS.copy()


def list_labels(dataset_id: str) -> List[Dict[str, Any]]:
    from .storage import get_dataset_labels
    return get_dataset_labels(dataset_id)


def create_label(dataset_id: str, label_data: Dict[str, Any]) -> Dict[str, Any]:
    from .storage import add_dataset_label
    return add_dataset_label(dataset_id, label_data)


def update_label(dataset_id: str, label_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    from .storage import update_dataset_label
    return update_dataset_label(dataset_id, label_id, updates)


def remove_label(dataset_id: str, label_id: str) -> Dict[str, Any]:
    from .storage import delete_dataset_label
    return delete_dataset_label(dataset_id, label_id)
