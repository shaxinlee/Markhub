"""Dataclasses and label/category constants for bounding-box annotation feature.

Anything that is "pure data" — label sets, annotation data structures,
storage constants — lives here so the main ``server.py`` can stay focused
on HTTP handling and orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DATASET_LABEL_TYPES = {
    "person",
    "car",
    "truck",
    "bus",
    "bicycle",
    "motorcycle",
    "animal",
    "dog",
    "cat",
    "bird",
    "traffic_light",
    "stop_sign",
    "fire_hydrant",
    "bench",
    "chair",
    "table",
    "plant",
    "building",
    "street_sign",
    "other",
}

DEFAULT_BOUNDING_BOX_LABELS = [
    {"id": "person", "name": "person", "color": "#FF6B6B"},
    {"id": "car", "name": "car", "color": "#4ECDC4"},
    {"id": "truck", "name": "truck", "color": "#45B7D1"},
    {"id": "bus", "name": "bus", "color": "#96CEB4"},
    {"id": "bicycle", "name": "bicycle", "color": "#FFEAA7"},
    {"id": "motorcycle", "name": "motorcycle", "color": "#DDA0DD"},
    {"id": "animal", "name": "animal", "color": "#98D8C8"},
    {"id": "traffic_light", "name": "traffic_light", "color": "#F7DC6F"},
    {"id": "stop_sign", "name": "stop_sign", "color": "#BB8FCE"},
    {"id": "fire_hydrant", "name": "fire_hydrant", "color": "#85C1E9"},
    {"id": "bench", "name": "bench", "color": "#F8B500"},
    {"id": "chair", "name": "chair", "color": "#00CED1"},
    {"id": "table", "name": "table", "color": "#FF7F50"},
    {"id": "plant", "name": "plant", "color": "#32CD32"},
    {"id": "building", "name": "building", "color": "#9370DB"},
    {"id": "street_sign", "name": "street_sign", "color": "#20B2AA"},
    {"id": "other", "name": "other", "color": "#A9A9A9"},
]


@dataclass
class BoundingBoxLabel:
    id: str
    name: str
    color: str
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BoundingBoxLabel:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            color=str(data.get("color", "#A9A9A9")),
            description=data.get("description"),
        )


@dataclass
class BoundingBoxAnnotation:
    id: str
    image_id: str
    label_id: str
    label_name: str
    bbox: tuple[float, float, float, float]
    confidence: Optional[float] = None
    notes: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "image_id": self.image_id,
            "label_id": self.label_id,
            "label_name": self.label_name,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BoundingBoxAnnotation:
        bbox = data.get("bbox", [0, 0, 0, 0])
        if len(bbox) != 4:
            bbox = [0, 0, 0, 0]
        return cls(
            id=str(data.get("id", "")),
            image_id=str(data.get("image_id", "")),
            label_id=str(data.get("label_id", "")),
            label_name=str(data.get("label_name", "")),
            bbox=tuple(bbox),
            confidence=data.get("confidence"),
            notes=data.get("notes"),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass
class BoundingBoxImage:
    id: str
    dataset_id: str
    filename: str
    image_url: str
    width: int
    height: int
    annotation_count: int = 0
    status: str = "pending"
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "filename": self.filename,
            "image_url": self.image_url,
            "width": self.width,
            "height": self.height,
            "annotation_count": self.annotation_count,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BoundingBoxImage:
        return cls(
            id=str(data.get("id", "")),
            dataset_id=str(data.get("dataset_id", "")),
            filename=str(data.get("filename", "")),
            image_url=str(data.get("image_url", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            annotation_count=int(data.get("annotation_count", 0)),
            status=str(data.get("status", "pending")),
            created_at=str(data.get("created_at", "")),
        )


@dataclass
class BoundingBoxDataset:
    id: str
    name: str
    description: str = ""
    image_count: int = 0
    annotated_count: int = 0
    label_count: int = 0
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    labels: List[BoundingBoxLabel] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "image_count": self.image_count,
            "annotated_count": self.annotated_count,
            "label_count": self.label_count,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "labels": [label.to_dict() for label in self.labels],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BoundingBoxDataset:
        labels = [BoundingBoxLabel.from_dict(l) for l in data.get("labels", [])]
        if not labels:
            labels = [BoundingBoxLabel.from_dict(l) for l in DEFAULT_BOUNDING_BOX_LABELS]
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            image_count=int(data.get("image_count", 0)),
            annotated_count=int(data.get("annotated_count", 0)),
            label_count=int(data.get("label_count", len(labels))),
            status=str(data.get("status", "active")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            labels=labels,
        )


@dataclass
class BoundingBoxJob:
    dataset_id: str
    dataset_name: str
    status: str = "draft"
    image_count: int = 0
    annotated_count: int = 0
    labels: List[BoundingBoxLabel] = field(default_factory=list)
    images: List[BoundingBoxImage] = field(default_factory=list)
    annotations: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "image_count": self.image_count,
            "annotated_count": self.annotated_count,
            "labels": [label.to_dict() for label in self.labels],
            "images": [img.to_dict() for img in self.images],
            "annotations": self.annotations,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BoundingBoxJob:
        labels = [BoundingBoxLabel.from_dict(l) for l in data.get("labels", [])]
        if not labels:
            labels = [BoundingBoxLabel.from_dict(l) for l in DEFAULT_BOUNDING_BOX_LABELS]
        images = [BoundingBoxImage.from_dict(img) for img in data.get("images", [])]
        return cls(
            dataset_id=str(data.get("dataset_id", "")),
            dataset_name=str(data.get("dataset_name", "")),
            status=str(data.get("status", "draft")),
            image_count=int(data.get("image_count", len(images))),
            annotated_count=int(data.get("annotated_count", 0)),
            labels=labels,
            images=images,
            annotations=data.get("annotations", {}),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )
