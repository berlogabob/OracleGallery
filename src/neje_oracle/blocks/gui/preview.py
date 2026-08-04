"""Sheet-preview SVG rendering for the GUI: static layout previews and
realtime/live previews driven off plotter status + spool manifests.

Split out of support.py (mechanical extraction, no behavior change) to keep
that module under the repo's file-size budget.
"""
from __future__ import annotations

import random
import json
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...shared.models import RuntimeStatus, SheetPlacement
from ...shared.origin_markers import (
    ORIGIN_FILLER_MACBOOK,
    ORIGIN_PREVIEW_COLORS,
    ORIGIN_REAL_MACMINI,
    ORIGIN_TEST_MACBOOK,
    marker_center_for_position,
    marker_position_for_origin,
    normalize_origin,
)
from ..gcode.svg_gcode import symbol_diameter_for_cell
from ..symbols.session_generator import build_variant_svg
from ..symbols.svg_normalizer import CANONICAL_BASE_DIAMETER, CANONICAL_CANVAS_SIZE, read_normalized_svg_metadata
from .support import GuiSettings, _build_layout_for_settings, effective_randomness, layout_capacity, list_base_symbols, load_symbol_scales


PREVIEW_PX_PER_MM = 2.0


@dataclass(frozen=True)
class LivePreviewItem:
    sheet_index: int
    source_kind: str
    origin: str
    state: str
    svg_path: Path | None = None
    center_x_mm: float | None = None
    center_y_mm: float | None = None
    cell_diameter_mm: float | None = None
    rotation_deg: float = 0.0
    symbol_scale: float = 1.0
    row_y_mm: float | None = None


def build_preview_svg(
    settings: GuiSettings,
    *,
    user_count: int = 2,
    idle_count: int | None = None,
    randomize_symbols: bool = False,
    highlighted_row_index: int | None = None,
    highlighted_cell_index: int | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> str:
    capacity = layout_capacity(settings)
    if capacity <= 0:
        return _empty_preview_svg(settings, "No printable cells")
    item_count = capacity
    user_count = max(0, min(user_count, item_count))
    idle_count = max(0, item_count - user_count) if idle_count is None else max(0, min(idle_count, item_count - user_count))
    placements = _build_layout_for_settings(settings, user_count + idle_count)
    scale = _preview_scale(settings)
    width = settings.sheet_width_mm * scale
    height = settings.sheet_height_mm * scale
    circles: list[str] = []
    symbol_images = _preview_symbol_images(settings, symbol_root=symbol_root, scale_path=scale_path)
    overscale = any(symbol_scale > 1.0 for _, symbol_scale in symbol_images)
    row_lookup = _placement_row_lookup(placements)
    for index, placement in enumerate(placements):
        kind = "user" if index < user_count else "idle"
        origin = ORIGIN_TEST_MACBOOK if kind == "user" else ORIGIN_FILLER_MACBOOK
        visible_origin = origin in settings.show_origins
        row_index = row_lookup.get(placement.index, 0)
        highlighted_row = highlighted_row_index is not None and row_index == highlighted_row_index
        highlighted_cell = highlighted_cell_index is not None and placement.index == highlighted_cell_index
        stroke = "#9a5b24" if kind == "user" else "#1f1a17"
        fill = "#fff0d4" if highlighted_cell else ("#f9f4ea" if kind == "user" else "#f3eadb")
        cx = placement.center_x_mm * scale
        cy = placement.center_y_mm * scale
        cell_radius = placement.diameter_mm * scale / 2.0
        mark_size = symbol_diameter_for_cell(placement.diameter_mm) * scale
        cell_stroke = "#c7472f" if highlighted_cell else ("#c78d2d" if highlighted_row else "#d8c7aa")
        cell_stroke_width = "4.0" if highlighted_cell else ("2.4" if highlighted_row else "1.0")
        circles.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{cell_radius:.2f}" fill="{fill}" '
            f'stroke="{cell_stroke}" stroke-width="{cell_stroke_width}"/>'
        )
        if settings.include_rings and visible_origin:
            circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size / 2.0:.2f}" fill="none" stroke="{stroke}" stroke-width="1.4" data-ring="outer"/>')
            if kind == "idle":
                circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.44:.2f}" fill="none" stroke="{stroke}" stroke-width="0.9" data-ring="inner"/>')
        if settings.include_markers and visible_origin:
            marker_x, marker_y = marker_center_for_position(
                placement,
                marker_position_for_origin(origin),
                marker_diameter_mm=settings.marker_diameter_mm,
            )
            marker_color = ORIGIN_PREVIEW_COLORS.get(origin, "#1f1a17")
            circles.append(
                f'<circle cx="{marker_x * scale:.2f}" cy="{marker_y * scale:.2f}" '
                f'r="{settings.marker_diameter_mm * scale / 2.0:.2f}" fill="none" '
                f'stroke="{marker_color}" stroke-width="1.6" data-origin-marker="{origin}"/>'
            )
        if symbol_images and visible_origin:
            symbol_index = _preview_symbol_index(index, symbol_images, randomize=randomize_symbols)
            href, _symbol_scale = symbol_images[symbol_index]
            image_size = _preview_image_size(mark_size, placement.symbol_scale)
            transform = _preview_rotation_transform(placement.rotation_deg, cx, cy)
            circles.append(
                f'<image href="{href}" x="{cx - image_size / 2.0:.2f}" y="{cy - image_size / 2.0:.2f}" '
                f'width="{image_size:.2f}" height="{image_size:.2f}" preserveAspectRatio="xMidYMid meet"'
                f'{transform} data-placement-rotation="{placement.rotation_deg:.3f}" '
                f'data-placement-scale="{placement.symbol_scale:.3f}"/>'
            )
        elif visible_origin:
            circles.append(
                f'<text x="{cx:.2f}" y="{cy + 4:.2f}" text-anchor="middle" font-size="12" '
                f'fill="{stroke}" font-family="monospace">{index + 1}</text>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<rect x="{settings.sheet_margin_mm * scale:.2f}" y="{settings.sheet_margin_mm * scale:.2f}" '
        f'width="{(settings.sheet_width_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        f'height="{(settings.sheet_height_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        'fill="none" stroke="#d4c3a5" stroke-width="1"/>'
        + (
            '<text x="10" y="18" font-size="11" fill="#9a5b24" font-family="monospace">'
            'overscale may overlap cells</text>'
            if overscale
            else ""
        )
        + "".join(circles)
        + "</svg>"
    )


def _preview_symbol_index(cell_index: int, symbol_images: list[tuple[str, float]], *, randomize: bool) -> int:
    if not randomize:
        return cell_index % len(symbol_images)
    return random.Random(10_007 + cell_index * 101).randrange(len(symbol_images))


def build_realtime_preview_svg(
    settings: GuiSettings,
    status: dict[str, Any],
    queue: dict[str, Any],
    *,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> str:
    items = _live_preview_items(settings, status, queue)
    if not items:
        pending_users = _pending_user_queue_count(queue)
        return build_preview_svg(
            settings,
            user_count=min(pending_users, layout_capacity(settings)),
            symbol_root=symbol_root,
            scale_path=scale_path,
        )
    return _build_live_preview_svg(settings, items)


def build_symbol_preview_svg(
    symbol_path: Path,
    *,
    marker_kind: str,
    scale: float,
    include_rings: bool,
    randomness: float,
) -> str:
    # Preview SVGs are displayed much smaller than the 800px source canvas, so the
    # UI uses amplified jitter to make the Randomness slider visually legible.
    jitter_px = max(0.0, min(randomness, 100.0)) / 100.0 * 80.0
    return build_variant_svg(
        symbol_path,
        marker_kind=marker_kind,
        scale=scale,
        rng=random.Random(1),
        jitter_px=jitter_px,
        include_rings=include_rings,
    )


def _preview_symbol_images(
    settings: GuiSettings,
    *,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[tuple[str, float]]:
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        return []
    scales = load_symbol_scales(scale_path, symbol_root)
    images: list[tuple[str, float]] = []
    for symbol in symbols:
        symbol_scale = scales.get(symbol.name, 1.0) * settings.global_scale
        svg = build_symbol_preview_svg(
            symbol,
            marker_kind="user",
            scale=symbol_scale,
            include_rings=False,
            randomness=effective_randomness(settings),
        )
        encoded = b64encode(svg.encode("utf-8")).decode("ascii")
        images.append((f"data:image/svg+xml;base64,{encoded}", symbol_scale))
    return images


def _build_live_preview_svg(settings: GuiSettings, items: list[LivePreviewItem]) -> str:
    capacity = layout_capacity(settings)
    if capacity <= 0:
        return _empty_preview_svg(settings, "No printable cells")
    placements = _build_layout_for_settings(settings, capacity)
    scale = _preview_scale(settings)
    # A stale manifest may have been laid out for a bigger sheet than the
    # current settings; grow the frame so its cells stay visible instead of
    # spilling out of the viewBox.
    content_x_mm = max(
        (item.center_x_mm + (item.cell_diameter_mm or 0.0) / 2.0 for item in items if item.center_x_mm is not None),
        default=0.0,
    )
    content_y_mm = max(
        (item.center_y_mm + (item.cell_diameter_mm or 0.0) / 2.0 for item in items if item.center_y_mm is not None),
        default=0.0,
    )
    width = max(settings.sheet_width_mm, content_x_mm) * scale
    height = max(settings.sheet_height_mm, content_y_mm) * scale
    # Only draw cells the manifest actually materialized: inventing the missing
    # cells from the current-settings layout mixes two geometries (frozen
    # manifest positions vs. a fresh organic layout) into overlapping nonsense.
    placement_by_index = {placement.index: placement for placement in placements}
    elements: list[str] = []
    for item in sorted(items, key=lambda entry: entry.sheet_index):
        base_placement = placement_by_index.get(
            item.sheet_index, placements[min(item.sheet_index, len(placements) - 1)]
        )
        placement = _preview_item_placement(item, base_placement)
        cx = placement.center_x_mm * scale
        cy = placement.center_y_mm * scale
        cell_radius = placement.diameter_mm * scale / 2.0
        mark_size = symbol_diameter_for_cell(placement.diameter_mm) * scale
        state = item.state
        fill = {
            "drawn": "#fffdf8",
            "drawing": "#fff0d4",
            "next": "#e1ded8",
            "empty": "#f3eadb",
        }.get(state, "#f3eadb")
        stroke = {
            "drawn": "#1f1a17",
            "drawing": "#c7472f",
            "next": "#8f8980",
            "empty": "#d8c7aa",
        }.get(state, "#d8c7aa")
        stroke_width = {"drawing": "3.2", "next": "2.2"}.get(state, "1.0")
        dash = ' stroke-dasharray="5 4"' if state == "next" else ""
        elements.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{cell_radius:.2f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" data-preview-state="{state}"{dash}/>'
        )
        if item.origin not in settings.show_origins:
            continue
        if settings.include_rings:
            ring_opacity = "0.35" if state == "next" else "0.9"
            elements.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size / 2.0:.2f}" fill="none" '
                f'stroke="{stroke}" stroke-width="1.2" opacity="{ring_opacity}" data-ring="outer"/>'
            )
            if item.source_kind != "user":
                elements.append(
                    f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.44:.2f}" fill="none" '
                    f'stroke="{stroke}" stroke-width="0.8" opacity="{ring_opacity}" data-ring="inner"/>'
                )
        if settings.include_markers:
            marker_x, marker_y = marker_center_for_position(
                placement,
                marker_position_for_origin(item.origin),
                marker_diameter_mm=settings.marker_diameter_mm,
            )
            marker_color = ORIGIN_PREVIEW_COLORS.get(item.origin, "#1f1a17")
            marker_opacity = "0.35" if state == "next" else "1.0"
            elements.append(
                f'<circle cx="{marker_x * scale:.2f}" cy="{marker_y * scale:.2f}" '
                f'r="{settings.marker_diameter_mm * scale / 2.0:.2f}" fill="none" '
                f'stroke="{marker_color}" stroke-width="1.6" opacity="{marker_opacity}" '
                f'data-origin-marker="{item.origin}"/>'
            )
        href = _svg_file_data_uri(item.svg_path)
        if href:
            opacity = "0.35" if state == "next" else "1.0"
            grayscale = ' filter="grayscale(1)"' if state == "next" else ""
            image_size = _preview_image_size(mark_size, placement.symbol_scale, svg_path=item.svg_path)
            transform = _preview_rotation_transform(placement.rotation_deg, cx, cy)
            elements.append(
                f'<image href="{href}" x="{cx - image_size / 2.0:.2f}" y="{cy - image_size / 2.0:.2f}" '
                f'width="{image_size:.2f}" height="{image_size:.2f}" opacity="{opacity}"{grayscale} '
                f'preserveAspectRatio="xMidYMid meet"{transform} data-preview-state="{state}" '
                f'data-placement-rotation="{placement.rotation_deg:.3f}" '
                f'data-placement-scale="{placement.symbol_scale:.3f}"/>'
            )
        elif state == "next":
            elements.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.22:.2f}" '
                f'fill="none" stroke="{stroke}" stroke-width="1.4" opacity="0.45" data-preview-state="next-placeholder"/>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<rect x="{settings.sheet_margin_mm * scale:.2f}" y="{settings.sheet_margin_mm * scale:.2f}" '
        f'width="{(settings.sheet_width_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        f'height="{(settings.sheet_height_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        'fill="none" stroke="#d4c3a5" stroke-width="1"/>'
        + "".join(elements)
        + "</svg>"
    )


def _live_preview_items(settings: GuiSettings, status: dict[str, Any], queue: dict[str, Any]) -> list[LivePreviewItem]:
    manifest_path = Path(str(status.get("latest_manifest") or ""))
    manifest_items = _manifest_preview_items(manifest_path)
    if not manifest_items:
        return []
    status_name = str(status.get("status") or "")
    cells_completed = max(0, int(status.get("cells_completed", 0) or 0))
    current_cell_in_row = int(status.get("current_cell_in_row", 0) or 0)
    is_drawing = status_name == RuntimeStatus.PRINTING.value and current_cell_in_row > 0
    current_ordinal = cells_completed if is_drawing else None
    next_ordinal = (current_ordinal + 1) if current_ordinal is not None else cells_completed
    if status_name == RuntimeStatus.OPERATOR_PAUSED.value and float(status.get("sheet_progress_percent", 0.0) or 0.0) >= 100.0:
        current_ordinal = None
        next_ordinal = len(manifest_items)

    live_items: list[LivePreviewItem] = []
    for ordinal, item in enumerate(manifest_items):
        if ordinal < cells_completed or current_ordinal is None and ordinal < next_ordinal:
            state = "drawn"
        elif current_ordinal is not None and ordinal == current_ordinal:
            state = "drawing"
        elif ordinal == next_ordinal:
            state = "next"
        else:
            continue
        live_items.append(_manifest_live_preview_item(item, state=state))

    if not any(item.state == "next" for item in live_items):
        ghost = _next_preview_ghost(settings, len(manifest_items), queue)
        if ghost is not None:
            live_items.append(ghost)
    return live_items


def _manifest_preview_items(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists() or not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("items", [])
    if not items and isinstance(payload.get("rows"), list):
        items = [
            item
            for row in payload["rows"]
            if isinstance(row, dict)
            for item in row.get("items", [])
            if isinstance(item, dict)
        ]
    return [item for item in items if isinstance(item, dict)]


def _manifest_live_preview_item(item: dict[str, Any], *, state: str) -> LivePreviewItem:
    raw_svg_path = str(item.get("svg_path") or "")
    return LivePreviewItem(
        sheet_index=int(item.get("sheet_index", 0) or 0),
        source_kind=str(item.get("source_kind") or "placeholder"),
        origin=normalize_origin(item.get("origin") or ORIGIN_FILLER_MACBOOK),
        state=state,
        svg_path=Path(raw_svg_path) if raw_svg_path else None,
        center_x_mm=_optional_float(item.get("center_x_mm")),
        center_y_mm=_optional_float(item.get("center_y_mm")),
        cell_diameter_mm=_optional_float(item.get("cell_diameter_mm")),
        rotation_deg=float(item.get("rotation_deg", 0.0) or 0.0),
        symbol_scale=float(item.get("symbol_scale", 1.0) or 1.0),
        row_y_mm=_optional_float(item.get("row_y_mm")),
    )


def _next_preview_ghost(settings: GuiSettings, next_sheet_index: int, queue: dict[str, Any]) -> LivePreviewItem | None:
    capacity = layout_capacity(settings)
    if next_sheet_index < 0 or next_sheet_index >= capacity:
        return None
    pending_users = _pending_user_queue_count(queue)
    if pending_users > 0:
        return LivePreviewItem(
            sheet_index=next_sheet_index,
            source_kind="user",
            origin=ORIGIN_REAL_MACMINI,
            state="next",
        )
    return LivePreviewItem(
        sheet_index=next_sheet_index,
        source_kind="placeholder",
        origin=ORIGIN_FILLER_MACBOOK,
        state="next",
    )


def _svg_file_data_uri(path: Path | None) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    try:
        encoded = b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/svg+xml;base64,{encoded}"


def _preview_item_placement(item: LivePreviewItem | None, fallback: SheetPlacement) -> SheetPlacement:
    if item is None or item.center_x_mm is None or item.center_y_mm is None:
        return fallback
    return SheetPlacement(
        index=fallback.index,
        center_x_mm=item.center_x_mm,
        center_y_mm=item.center_y_mm,
        diameter_mm=item.cell_diameter_mm if item.cell_diameter_mm is not None else fallback.diameter_mm,
        rotation_deg=item.rotation_deg,
        symbol_scale=item.symbol_scale,
        row_y_mm=item.row_y_mm,
    )


def _preview_rotation_transform(rotation_deg: float, cx: float, cy: float) -> str:
    if abs(rotation_deg) < 0.001:
        return ""
    return f' transform="rotate({rotation_deg:.2f} {cx:.2f} {cy:.2f})"'


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pending_user_queue_count(queue: dict[str, Any]) -> int:
    if "pendingUserAfterBaseline" in queue:
        return int(queue.get("pendingUserAfterBaseline", 0) or 0)
    return int(queue.get("pendingAfterBaseline", 0) or 0)


def _placement_row_lookup(placements) -> dict[int, int]:
    rows: dict[float, int] = {}
    lookup: dict[int, int] = {}
    for placement in sorted(placements, key=lambda item: (item.row_y_mm if item.row_y_mm is not None else item.center_y_mm, item.center_x_mm)):
        placement_row_y = placement.row_y_mm if placement.row_y_mm is not None else placement.center_y_mm
        row_key = next((key for key in rows if abs(key - placement_row_y) < 0.001), None)
        if row_key is None:
            row_key = placement_row_y
            rows[row_key] = len(rows) + 1
        lookup[placement.index] = rows[row_key]
    return lookup


def _preview_scale(settings: GuiSettings) -> float:
    return PREVIEW_PX_PER_MM


def _preview_image_size(mark_size: float, placement_symbol_scale: float, *, svg_path: Path | None = None) -> float:
    canvas_to_base_ratio = CANONICAL_CANVAS_SIZE / CANONICAL_BASE_DIAMETER
    if svg_path is not None:
        try:
            metadata = read_normalized_svg_metadata(svg_path)
        except Exception:  # noqa: BLE001
            canvas_to_base_ratio = 1.0
        else:
            if metadata.normalized and metadata.base_diameter > 0:
                canvas_to_base_ratio = metadata.canvas_size / metadata.base_diameter
            else:
                canvas_to_base_ratio = 1.0
    return mark_size * canvas_to_base_ratio * max(0.0, placement_symbol_scale)


def _empty_preview_svg(settings: GuiSettings, message: str) -> str:
    scale = _preview_scale(settings)
    width = max(settings.sheet_width_mm * scale, 300)
    height = max(settings.sheet_height_mm * scale, 200)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<text x="{width / 2:.2f}" y="{height / 2:.2f}" text-anchor="middle" '
        f'font-size="18" fill="#8f4f2b">{message}</text></svg>'
    )
