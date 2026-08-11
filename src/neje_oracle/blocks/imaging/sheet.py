"""Lay a folder of images out as framed cells on one sheet.

Deliberately separate from gcode/layout.py: that module's SheetPlacement carries a single
diameter_mm and the plotter daemon streams against it. Wooden frames are rectangular and
come in fixed sizes, so cells need independent width and height — adding that to the shared
model would put the exhibition print path at risk for a feature only this workspace uses.
"""

from __future__ import annotations

import math
from typing import Any

from .modes import Polylines, image_to_polylines

SHAPES = ("rect", "ellipse", "none")


def build_frame_grid(
    count: int,
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    cell_width_mm: float,
    cell_height_mm: float,
    gap_mm: float = 0.0,
) -> list[tuple[float, float]]:
    """Cell centres, row-major, centred on the printable area.

    gap_mm = 0 butts the cells together (print then cut on the shared line); gap_mm > 0
    leaves a cutting alley between them.
    """
    if count <= 0:
        return []
    if min(cell_width_mm, cell_height_mm) <= 0:
        raise ValueError("cell_width_mm and cell_height_mm must be positive")
    if gap_mm < 0 or margin_mm < 0:
        raise ValueError("gap_mm and margin_mm must be non-negative")

    printable_w = sheet_width_mm - margin_mm * 2.0
    printable_h = sheet_height_mm - margin_mm * 2.0
    pitch_x = cell_width_mm + gap_mm
    pitch_y = cell_height_mm + gap_mm
    columns = int((printable_w + gap_mm) // pitch_x)
    rows = int((printable_h + gap_mm) // pitch_y)
    if columns <= 0 or rows <= 0:
        return []

    placed = min(count, columns * rows)
    used_rows = math.ceil(placed / columns)
    used_columns = min(placed, columns)
    # Centre what is actually used, not the full capacity: a half-empty last sheet should
    # still sit in the middle of the paper, not hug the top-left corner.
    span_x = used_columns * pitch_x - gap_mm
    span_y = used_rows * pitch_y - gap_mm
    left = margin_mm + (printable_w - span_x) / 2.0
    top = margin_mm + (printable_h - span_y) / 2.0

    return [
        (
            left + (index % columns) * pitch_x + cell_width_mm / 2.0,
            top + (index // columns) * pitch_y + cell_height_mm / 2.0,
        )
        for index in range(placed)
    ]


def frame_grid_capacity(
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    cell_width_mm: float,
    cell_height_mm: float,
    gap_mm: float = 0.0,
) -> int:
    return len(
        build_frame_grid(
            10_000,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            cell_width_mm=cell_width_mm,
            cell_height_mm=cell_height_mm,
            gap_mm=gap_mm,
        )
    )


def cell_outline(center_x: float, center_y: float, width_mm: float, height_mm: float, shape: str) -> Polylines:
    """The cut line for one cell. 'none' returns nothing."""
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}; valid shapes: {', '.join(SHAPES)}")
    if shape == "none":
        return []
    half_w, half_h = width_mm / 2.0, height_mm / 2.0
    if shape == "rect":
        left, right = center_x - half_w, center_x + half_w
        top, bottom = center_y - half_h, center_y + half_h
        return [[(left, top), (right, top), (right, bottom), (left, bottom), (left, top)]]
    # One segment per ~1 mm of perimeter so the cut line reads as a curve, not a polygon.
    perimeter = math.pi * (3 * (half_w + half_h) - math.sqrt((3 * half_w + half_h) * (half_w + 3 * half_h)))
    steps = max(32, min(360, int(perimeter)))
    points = [
        (center_x + half_w * math.cos(math.tau * i / steps), center_y + half_h * math.sin(math.tau * i / steps))
        for i in range(steps)
    ]
    return [points + [points[0]]]


def images_to_sheet_polylines(
    images: list[bytes],
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    cell_width_mm: float,
    cell_height_mm: float,
    gap_mm: float = 0.0,
    padding_mm: float = 2.0,
    shape: str = "rect",
    mode: str = "contour",
    cell_mm: float = 1.5,
    **params: Any,
) -> tuple[Polylines, int]:
    """Convert each image and drop it into its cell. Returns (polylines, images placed).

    Art keeps its aspect ratio and is centred, so a square render in a 10x15 frame gets
    even bands top and bottom rather than being stretched to the frame.
    """
    centers = build_frame_grid(
        len(images),
        sheet_width_mm=sheet_width_mm,
        sheet_height_mm=sheet_height_mm,
        margin_mm=margin_mm,
        cell_width_mm=cell_width_mm,
        cell_height_mm=cell_height_mm,
        gap_mm=gap_mm,
    )
    art_w = cell_width_mm - padding_mm * 2.0
    art_h = cell_height_mm - padding_mm * 2.0
    if min(art_w, art_h) <= 0:
        raise ValueError("padding_mm leaves no room for art inside the cell")

    sheet: Polylines = []
    for (center_x, center_y), data in zip(centers, images, strict=False):
        sheet.extend(cell_outline(center_x, center_y, cell_width_mm, cell_height_mm, shape))
        art = image_to_polylines(data, mode=mode, width_mm=art_w, height_mm=art_h, cell_mm=cell_mm, **params)
        offset_x = center_x - art_w / 2.0
        offset_y = center_y - art_h / 2.0
        sheet.extend([[(x + offset_x, y + offset_y) for x, y in polyline] for polyline in art])
    return sheet, len(centers)
