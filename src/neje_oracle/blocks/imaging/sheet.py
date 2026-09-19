"""Lay a folder of images out as framed cells on one sheet.

Deliberately separate from gcode/layout.py: that module's SheetPlacement carries a single
diameter_mm and the plotter daemon streams against it. Wooden frames are rectangular and
come in fixed sizes, so cells need independent width and height — adding that to the shared
model would put the exhibition print path at risk for a feature only this workspace uses.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from ..text import shx
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
    frame_w = cell_width_mm - padding_mm * 2.0
    frame_h = cell_height_mm - padding_mm * 2.0
    if min(frame_w, frame_h) <= 0:
        raise ValueError("padding_mm leaves no room for art inside the cell")

    sheet: Polylines = []
    for (center_x, center_y), data in zip(centers, images, strict=False):
        sheet.extend(cell_outline(center_x, center_y, cell_width_mm, cell_height_mm, shape))
        # Per image, not per sheet: a contact sheet is usually a folder of whatever the
        # camera produced, portrait and landscape mixed.
        art_w, art_h = fit_box(image_aspect(data), frame_w, frame_h)
        art = image_to_polylines(data, mode=mode, width_mm=art_w, height_mm=art_h, cell_mm=cell_mm, **params)
        offset_x = center_x - art_w / 2.0
        offset_y = center_y - art_h / 2.0
        sheet.extend([[(x + offset_x, y + offset_y) for x, y in polyline] for polyline in art])
    return sheet, len(centers)


GRID_SIZES = tuple(range(1, 10))
GRID_GAP_MM = 4.0
GRID_LABEL_MM = 3.0
GRID_LABEL_FONT = "zzsimplex"


def grid_cells(
    n: int, *, width_mm: float, height_mm: float, gap_mm: float = GRID_GAP_MM, label_mm: float = GRID_LABEL_MM
) -> list[tuple[float, float, float]]:
    """N x N square cells as (left, top, side), row-major, the block centred in the canvas.

    build_frame_grid derives the column count from a cell size; a grid picked as "4x4" needs
    the count fixed and the size derived, which is the other way round. Each row reserves a
    label strip under its cells so the text never lands on the next row's art.
    """
    if n not in GRID_SIZES:
        raise ValueError(f"grid size must be 1..9, got {n}")
    strip = label_mm + 1.5 if label_mm > 0 else 0.0
    side = min((width_mm - gap_mm * (n - 1)) / n, (height_mm - gap_mm * (n - 1)) / n - strip)
    if side <= 0:
        raise ValueError(f"a {n}x{n} grid does not fit {width_mm:g} x {height_mm:g} mm")
    block_w = n * side + (n - 1) * gap_mm
    block_h = n * (side + strip) + (n - 1) * gap_mm
    left0 = (width_mm - block_w) / 2.0
    top0 = (height_mm - block_h) / 2.0
    return [
        (left0 + col * (side + gap_mm), top0 + row * (side + strip + gap_mm), side)
        for row in range(n)
        for col in range(n)
    ]


def _content_span(flat: np.ndarray) -> tuple[int, int]:
    """First and one-past-last index that is not a flat edge bar; the whole range if all flat."""
    content = np.where(~flat)[0]
    return (int(content[0]), int(content[-1]) + 1) if len(content) else (0, len(flat))


def photo_filter(data: bytes, *, flat_std: float = 3.0, sigma_px: float = 25.0) -> bytes:
    """Crop letterbox bars, then flatten the lighting so faces keep their features.

    Measured on a group photo (2026-09-16): the bars were 52% of the frame and every tone mode
    filled them with ink; subtracting a heavy blur is what made glasses, beards and mouths
    survive contour. A poor man's CLAHE. A bar is any edge row or column with no texture
    (std below flat_std), so black, white and transparent bars all go: the same photo came
    back a day later as RGBA with white bars, and a near-black test kept every row.
    # ponytail: fixed sigma 25 px on the source pixels; expose it if another photo needs it.
    """
    with Image.open(io.BytesIO(data)) as source:
        rgba = source.convert("RGBA")
    # Transparent pixels carry arbitrary RGB; paper is white, so that is what they become.
    image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("L")
    grey = np.asarray(image, dtype=np.float64)
    top, bottom = _content_span(grey.std(axis=1) < flat_std)
    left, right = _content_span(grey.std(axis=0) < flat_std)
    image = image.crop((left, top, right, bottom))
    grey = np.asarray(image, dtype=np.float64)
    blurred = np.asarray(image.filter(ImageFilter.GaussianBlur(sigma_px)), dtype=np.float64)
    detail = grey - blurred
    low, high = np.percentile(detail, 1), np.percentile(detail, 99)
    scaled = np.clip((detail - low) / max(high - low, 1e-6), 0.0, 1.0)
    out = io.BytesIO()
    Image.fromarray((scaled * 255).astype(np.uint8)).save(out, "PNG")
    return out.getvalue()


def _grid_label(text: str, x_mm: float, y_mm: float) -> Polylines:
    try:
        return shx.text_polylines(text, font=GRID_LABEL_FONT, cap_height_mm=GRID_LABEL_MM, origin=(x_mm, y_mm))
    except (ValueError, OSError):
        # No font means no labels, not no grid.
        return []


def image_aspect(data: bytes) -> float:
    with Image.open(io.BytesIO(data)) as source:
        return source.width / source.height


def fit_box(aspect: float, box_w_mm: float, box_h_mm: float) -> tuple[float, float]:
    """The largest box_w x box_h rectangle with this aspect ratio, in mm.

    Everything downstream renders into the mm box it is handed: load_tone resamples the
    picture to width_mm/cell_mm by height_mm/cell_mm without ever reading the source's own
    pixel dimensions, so a 2:1 photo handed a square box is stretched into it before any
    mode runs, and no mode can undo it. Shrinking the box to the picture's shape is the
    whole fix -- the caller places the result wherever it wants.

    A degenerate aspect (a zero-pixel dimension cannot happen, but a caller computing one
    can) returns the box unchanged rather than raising: refusing to draw is worse than
    drawing the old way.
    """
    if aspect <= 0 or box_w_mm <= 0 or box_h_mm <= 0:
        return box_w_mm, box_h_mm
    if box_w_mm / box_h_mm > aspect:  # the box is wider than the picture: height decides
        return box_h_mm * aspect, box_h_mm
    return box_w_mm, box_w_mm / aspect


def cell_art(data: bytes, mode: str, side_mm: float, params: dict[str, Any], *, aspect: float) -> Polylines:
    """One cell's drawing in cell-local mm, aspect kept and centred in a side x side square.

    Rendered at cell size, not rendered once and scaled: a mode's line pitch is in mm, so
    scaling afterwards would draw a 9x9 cell with lines nine times too dense. The GUI's cell
    thumbnails are this exact output, so what a tile shows is what the sheet prints.
    """
    art_w, art_h = fit_box(aspect, side_mm, side_mm)
    art = image_to_polylines(data, mode=mode, width_mm=art_w, height_mm=art_h, **params)
    dx, dy = (side_mm - art_w) / 2.0, (side_mm - art_h) / 2.0
    return [[(x + dx, y + dy) for x, y in polyline] for polyline in art]


def grid_to_polylines(
    data: bytes,
    modes: Sequence[str | None],
    *,
    n: int,
    width_mm: float,
    height_mm: float,
    params_for: Callable[[str], dict[str, Any]],
    labels: bool = True,
    art_for: Callable[[str, float], Polylines] | None = None,
) -> tuple[Polylines, list[str]]:
    """One picture, one mode per cell. Returns (polylines, failures).

    A cell whose mode refuses the picture (trace's skeleton cap, a segment cap) keeps its
    outline and says so in its label; the other cells still print. `art_for(mode, side_mm)`
    lets a caller substitute a cached cell_art; it must raise ValueError the same way.
    """
    if art_for is None:
        aspect = image_aspect(data)

        def art_for(mode: str, side_mm: float) -> Polylines:
            return cell_art(data, mode, side_mm, params_for(mode), aspect=aspect)

    cells = grid_cells(n, width_mm=width_mm, height_mm=height_mm, label_mm=GRID_LABEL_MM if labels else 0.0)
    sheet: Polylines = []
    failures: list[str] = []
    for index, (left, top, side) in enumerate(cells):
        mode = modes[index] if index < len(modes) else None
        if not mode:
            continue
        caption = mode
        try:
            art = art_for(mode, side)
        except ValueError as exc:
            art = []
            caption = f"{mode}: failed"
            failures.append(f"cell {index + 1} {mode}: {exc}")
        sheet.extend([[(x + left, y + top) for x, y in polyline] for polyline in art])
        if labels:
            sheet.extend(cell_outline(left + side / 2.0, top + side / 2.0, side, side, "rect"))
            sheet.extend(_grid_label(caption, left, top + side + 1.0))
    return sheet, failures
