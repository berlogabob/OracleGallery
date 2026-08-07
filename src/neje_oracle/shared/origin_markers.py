from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import SheetPlacement

ORIGIN_REAL_MACMINI = "real_macmini"
ORIGIN_TEST_MACBOOK = "test_macbook"
ORIGIN_TEST_MACMINI = "test_macmini"
ORIGIN_FILLER_MACBOOK = "filler_macbook"
ORIGIN_UNKNOWN = "unknown"

ALL_ORIGINS = (
    ORIGIN_REAL_MACMINI,
    ORIGIN_TEST_MACBOOK,
    ORIGIN_TEST_MACMINI,
    ORIGIN_FILLER_MACBOOK,
    ORIGIN_UNKNOWN,
)

ORIGIN_LABELS = {
    ORIGIN_REAL_MACMINI: "Real Mac mini",
    ORIGIN_TEST_MACBOOK: "Test MacBook",
    ORIGIN_TEST_MACMINI: "Test Mac mini",
    ORIGIN_FILLER_MACBOOK: "Filler MacBook",
    ORIGIN_UNKNOWN: "Unknown",
}

ORIGIN_PREVIEW_COLORS = {
    ORIGIN_REAL_MACMINI: "#1f1a17",
    ORIGIN_TEST_MACBOOK: "#c7472f",
    ORIGIN_TEST_MACMINI: "#2f6f73",
    ORIGIN_FILLER_MACBOOK: "#c7a45a",
    ORIGIN_UNKNOWN: "#77706a",
}

ORIGIN_MARKER_POSITIONS = {
    ORIGIN_REAL_MACMINI: "bottom-right",
    ORIGIN_TEST_MACBOOK: "top-right",
    ORIGIN_TEST_MACMINI: "top-left",
    ORIGIN_FILLER_MACBOOK: "bottom-left",
    ORIGIN_UNKNOWN: "right",
}

DEFAULT_MARKER_DIAMETER_MM = 1.5


@dataclass(frozen=True)
class OriginClassification:
    origin: str
    tags: list[str]
    visible_in_library: bool


def normalize_origin(value: Any) -> str:
    origin = str(value or "").strip().lower()
    return origin if origin in ALL_ORIGINS else ORIGIN_UNKNOWN


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    tags: list[str] = []
    for item in raw:
        tag = str(item).strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def classify_session_origin(metadata: dict[str, Any] | None) -> OriginClassification:
    metadata = metadata or {}
    explicit = normalize_origin(metadata.get("origin"))
    if explicit != ORIGIN_UNKNOWN:
        return _classification_for_origin(explicit, metadata.get("tags"))

    kind = str(metadata.get("kind") or "").strip().lower()
    generated_by = str(metadata.get("generatedBy") or metadata.get("generated_by") or "").strip().lower()
    source_machine = (
        str(
            metadata.get("sourceMachine")
            or metadata.get("source_machine")
            or metadata.get("machine")
            or metadata.get("host")
            or ""
        )
        .strip()
        .lower()
    )

    if kind.startswith("test") or "generate" in generated_by:
        if "mini" in source_machine or "macmini" in source_machine or "mac-mini" in source_machine:
            return _classification_for_origin(ORIGIN_TEST_MACMINI, metadata.get("tags"))
        return _classification_for_origin(ORIGIN_TEST_MACBOOK, metadata.get("tags"))

    if kind in {"filler", "placeholder", "idle"}:
        return _classification_for_origin(ORIGIN_FILLER_MACBOOK, metadata.get("tags"))

    return _classification_for_origin(ORIGIN_REAL_MACMINI, metadata.get("tags"))


def tags_for_origin(origin: str, extra_tags: Any = None) -> list[str]:
    origin = normalize_origin(origin)
    base = {
        ORIGIN_REAL_MACMINI: ["real", "oracle", "macmini"],
        ORIGIN_TEST_MACBOOK: ["test", "generated", "macbook"],
        ORIGIN_TEST_MACMINI: ["test", "generated", "macmini"],
        ORIGIN_FILLER_MACBOOK: ["filler", "local", "macbook"],
        ORIGIN_UNKNOWN: ["unknown"],
    }[origin]
    tags = list(base)
    for tag in normalize_tags(extra_tags):
        if tag not in tags:
            tags.append(tag)
    return tags


def visible_in_library_for_origin(origin: str) -> bool:
    return normalize_origin(origin) == ORIGIN_REAL_MACMINI


def origin_allowed(origin: str, allowed_origins: set[str] | list[str] | tuple[str, ...] | None) -> bool:
    if not allowed_origins:
        return True
    normalized = {normalize_origin(item) for item in allowed_origins}
    return normalize_origin(origin) in normalized


def marker_position_for_origin(origin: str) -> str:
    return ORIGIN_MARKER_POSITIONS.get(normalize_origin(origin), ORIGIN_MARKER_POSITIONS[ORIGIN_UNKNOWN])


def marker_center_for_position(
    placement: SheetPlacement,
    position: str,
    *,
    marker_diameter_mm: float = DEFAULT_MARKER_DIAMETER_MM,
) -> tuple[float, float]:
    marker_radius = max(marker_diameter_mm, 0.1) / 2.0
    radius = max((placement.diameter_mm / 2.0) - marker_radius * 2.0 - 1.0, 0.0)
    angle = {
        "top-right": -math.pi / 4.0,
        "bottom-right": math.pi / 4.0,
        "bottom-left": math.pi * 3.0 / 4.0,
        "top-left": -math.pi * 3.0 / 4.0,
        "right": 0.0,
    }.get(position, 0.0)
    return (
        placement.center_x_mm + math.cos(angle) * radius,
        placement.center_y_mm + math.sin(angle) * radius,
    )


def _classification_for_origin(origin: str, extra_tags: Any = None) -> OriginClassification:
    origin = normalize_origin(origin)
    return OriginClassification(
        origin=origin,
        tags=tags_for_origin(origin, extra_tags),
        visible_in_library=visible_in_library_for_origin(origin),
    )
