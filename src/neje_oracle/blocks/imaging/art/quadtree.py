"""Recursive squares: the picture as a quadtree, small cells where it is dark.

A square splits into four when its own mean darkness clears the threshold for its depth, so
the subdivision follows tone and the result reads as a mosaic that tightens into shadow --
large open squares across paper, a dense checkerboard through a face. The alternative rule,
splitting on variance (detail), is the one image-compression quadtrees use, and it is wrong
here for a reason worth stating: a pen draws outlines, so ink per square millimetre comes from
how MANY squares there are, and a variance rule puts them wherever the picture is busy, which
on a smooth gradient is nowhere. Tone-driven splitting is what makes ink follow darkness.

Each leaf is drawn as its outline plus nested squares inside it, one more ring per step of
darkness. The nesting is not decoration: splitting is a step function, so between two split
thresholds a leaf's ink would not change at all and the picture would come out as flat plateaus
with cliffs between them. The rings fill in the ramp, the same job the nested arcs do in
`scales`, and they are also what stops the darkest region reading as an empty grid once every
square there has shrunk to the floor.
"""

from __future__ import annotations

from ..modes import Polylines, ToneGrid, cell_darkness

HELP = (
    "Recursive squares: dark areas split into smaller cells, light ones stay whole. "
    "Darker cells carry nested squares inside them; detail = smallest cell in mm."
)

MAX_CELLS_DEFAULT = 20_000
# Splitting gets harder with depth, so a mid-grey stops before a black does. Without the ramp
# one threshold either splits the whole sheet to the floor or never splits at all: the mean
# darkness of a cell does not fall as it shrinks, it converges on the local tone.
_DEPTH_PENALTY = 0.20


def quadtree(
    tone: ToneGrid,
    *,
    min_cell_mm: float = 4.0,
    max_cell_mm: float = 32.0,
    split_darkness: float = 0.30,
    max_rings: int = 2,
    min_darkness: float = 0.10,
    max_cells: int = MAX_CELLS_DEFAULT,
) -> Polylines:
    """Subdivide from `max_cell_mm` down to `min_cell_mm`, following tone.

    The root grid is whole cells of `max_cell_mm` covering the sheet, not one square over the
    whole picture: a single root on a non-square sheet either overhangs the paper or leaves a
    strip undrawn, and clipping it back re-introduces the ragged edge at every depth.

    A cell under `min_darkness` draws nothing at all -- that is the white-paper gate every mode
    needs -- and it is checked before the split test, so paper costs no recursion.
    """
    if min_cell_mm <= 0 or max_cell_mm < min_cell_mm:
        raise ValueError("cell sizes must be positive and max_cell_mm >= min_cell_mm")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")

    darkness = tone.darkness
    if darkness.size == 0:
        return []

    polylines: Polylines = []

    def emit(x0: float, y0: float, size: float, value: float) -> None:
        x1, y1 = min(tone.width_mm, x0 + size), min(tone.height_mm, y0 + size)
        polylines.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
        # Rings are inset by even fractions of the half-size, so the innermost one of a
        # 3-ring cell is still a square with ink around it rather than a dot in the middle.
        rings = int(value * (max_rings + 1))
        half_w, half_h = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        for ring in range(1, min(rings, max_rings) + 1):
            fx, fy = half_w * ring / (max_rings + 1), half_h * ring / (max_rings + 1)
            polylines.append(
                [(x0 + fx, y0 + fy), (x1 - fx, y0 + fy), (x1 - fx, y1 - fy), (x0 + fx, y1 - fy), (x0 + fx, y0 + fy)]
            )

    def visit(x0: float, y0: float, size: float, depth: int) -> None:
        if len(polylines) >= max_cells or x0 >= tone.width_mm or y0 >= tone.height_mm:
            return
        x1, y1 = min(tone.width_mm, x0 + size), min(tone.height_mm, y0 + size)
        value = cell_darkness(darkness, x0, y0, x1, y1, tone.width_mm, tone.height_mm)
        if value < min_darkness:
            return
        half = size / 2.0
        if half >= min_cell_mm and value >= split_darkness + depth * _DEPTH_PENALTY:
            for dx, dy in ((0.0, 0.0), (half, 0.0), (0.0, half), (half, half)):
                visit(x0 + dx, y0 + dy, half, depth + 1)
            return
        emit(x0, y0, size, value)

    step = max_cell_mm
    y = 0.0
    while y < tone.height_mm:
        x = 0.0
        while x < tone.width_mm:
            visit(x, y, step, 0)
            x += step
        y += step
    return polylines


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Smallest and largest cell from the quality fader.

    Both track spacing_mm and reproduce the defaults (4.0 / 32.0) at the draft rung
    (spacing 2.5). The floor is 2.5 mm, measured rather than guessed: at 1.5 mm a 120 mm
    photograph split to the floor almost everywhere and printed as a black field with a few
    white squares in it -- the picture was in the SIZES and there were no sizes left. A square
    also stops reading as a square somewhere under five pen widths.
    """
    return {"min_cell_mm": max(2.5, spacing_mm * 2.4), "max_cell_mm": max(12.0, spacing_mm * 12.8)}
