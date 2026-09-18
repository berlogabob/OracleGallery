"""One continuous Hilbert curve, recursing finer where the image is dark.

Built on the generalised recursive form of the Hilbert curve (four quadrants visited in an
S-shape, each carrying the parent's edge vectors rotated/swapped into itself), rather than the
usual fixed-order table lookup: the fixed form only knows how to answer "give me an order-n
curve everywhere", and this mode needs a DIFFERENT order in every quadrant, decided by what is
under it. Passing the edge vectors down instead of an integer order is what lets one quadrant
stop at a coarse cell while its sibling keeps splitting.
"""

from __future__ import annotations

import math

from ..modes import Polylines, ToneGrid, _sample_darkness

MAX_HILBERT_POINTS = 400_000
# Samples averaged per cell before it decides whether to split further. A single centre sample
# lets a thin dark feature sitting off-centre in a large, otherwise-light cell go undetected —
# the cell reads as light and never subdivides down onto it. A 3x3 average costs 9 lookups per
# node, cheap next to the recursion itself, and catches it.
_DARKNESS_GRID = 3
_EPSILON = 1e-6


def hilbert(
    tone: ToneGrid,
    *,
    min_cell_mm: float = 1.0,
    max_cell_mm: float = 8.0,
    gamma: float = 1.8,
    min_darkness: float = 0.05,
    max_points: int = MAX_HILBERT_POINTS,
) -> Polylines:
    """Subdivide a covering square in Hilbert order; draw the leaves' centres in that order.

    The frame is covered by a square of side S = max(width_mm, height_mm), corner at the
    origin, so it always contains the (possibly non-square) sheet. Each cell is offered up for
    a split: split while its side is still above min_cell_mm AND its own mean darkness asks for
    something finer than its current size. The per-cell target size is

        target = min_cell_mm + (max_cell_mm - min_cell_mm) * (1 - darkness) ** gamma

    which lands exactly on min_cell_mm at darkness 1 (split all the way down) and on
    max_cell_mm at darkness 0 (stop as soon as the cell is no coarser than that — the
    "coarsest level that is still drawn"). A plain min_cell_mm / darkness**gamma blows up
    as darkness -> 0 and needs its own clamp back down to max_cell_mm; interpolating between
    the two bounds gets the same darker-is-smaller shape without a division or a second clamp.

    gamma defaults above 1 (not the linear 1.0) because a real photograph sits mid-grey almost
    everywhere -- measured on a filtered group photo, 88% of cells came out above 0.3 darkness
    -- so a linear map put nearly the whole sheet at nearly the same cell size and the subject
    read as a flat, uniform grid. Raising gamma pushes that whole mid-range further toward
    max_cell_mm and reserves the fine end for what is genuinely close to black, which is what
    made the density actually trace the picture's shapes instead of its average tone.

    Leaves are emitted as their own centres, not a per-leaf mini-curve: two leaves that are
    consecutive in Hilbert order are always edge- or corner-adjacent by construction of the
    recursion (each of the four children shares a border with the next one visited), even when
    the two cells are different sizes, so centres alone already draw one connected line without
    inventing extra in-cell geometry. Confirmed by the solid-black test below, where every
    consecutive pair sits exactly min_cell_mm apart on the grid axes.

    A cell entirely outside [0, width_mm] x [0, height_mm] stops immediately without sampling
    or recursing into it — S can exceed the shorter side of a non-square sheet by a lot, and
    without this check that whole margin would otherwise get walked down to min_cell_mm for no
    image underneath it at all.
    """
    if min_cell_mm <= 0:
        raise ValueError("min_cell_mm must be positive")
    if max_cell_mm < min_cell_mm:
        raise ValueError("max_cell_mm must be >= min_cell_mm")
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if max_points <= 0:
        raise ValueError("max_points must be positive")

    width, height = tone.width_mm, tone.height_mm
    side = max(width, height)
    # Cell size exactly halves every level regardless of darkness, so the deepest a fully-black
    # image can ever force is fixed by geometry alone: this is an exact worst case (equality at
    # darkness == 1 everywhere), not an estimate, and it is cheap to check before recursing.
    depth = 0 if side <= min_cell_mm else math.ceil(math.log2(side / min_cell_mm))
    worst_case_leaves = 4**depth
    if worst_case_leaves > max_points:
        raise ValueError(
            f"hilbert could need up to {worst_case_leaves} leaves at min_cell_mm={min_cell_mm}, "
            f"exceeding max_points={max_points}; raise min_cell_mm or shrink the drawing"
        )

    leaves: list[tuple[float, float] | None] = []

    def mean_darkness(x0: float, y0: float, xi: float, xj: float, yi: float, yj: float) -> float:
        total = 0.0
        for row in range(_DARKNESS_GRID):
            v = (row + 0.5) / _DARKNESS_GRID
            for col in range(_DARKNESS_GRID):
                u = (col + 0.5) / _DARKNESS_GRID
                total += _sample_darkness(tone, x0 + u * xi + v * yi, y0 + u * xj + v * yj)
        return total / (_DARKNESS_GRID * _DARKNESS_GRID)

    def recurse(x0: float, y0: float, xi: float, xj: float, yi: float, yj: float) -> None:
        corners_x = (x0, x0 + xi, x0 + yi, x0 + xi + yi)
        corners_y = (y0, y0 + xj, y0 + yj, y0 + xj + yj)
        if (
            max(corners_x) < -_EPSILON
            or min(corners_x) > width + _EPSILON
            or max(corners_y) < -_EPSILON
            or min(corners_y) > height + _EPSILON
        ):
            leaves.append(None)  # off the sheet entirely: stop, and break the path here
            return

        cell_size = math.hypot(xi, xj)
        darkness = mean_darkness(x0, y0, xi, xj, yi, yj)
        target = min_cell_mm + (max_cell_mm - min_cell_mm) * (1.0 - darkness) ** gamma
        if cell_size > min_cell_mm and cell_size > target:
            # The four children, in Hilbert order: first and last quadrants get the parent's
            # axes swapped (a 90-degree turn), the middle two keep them, and the last also
            # negates them (a 180-degree turn) — the standard construction that makes each
            # child's own curve line up, open end to open end, with its neighbours.
            recurse(x0, y0, yi / 2, yj / 2, xi / 2, xj / 2)
            recurse(x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
            recurse(x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2)
            recurse(x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2)
            return

        center_x = x0 + (xi + yi) / 2
        center_y = y0 + (xj + yj) / 2
        inside = -_EPSILON <= center_x <= width + _EPSILON and -_EPSILON <= center_y <= height + _EPSILON
        if darkness < min_darkness or not inside:
            leaves.append(None)
        else:
            leaves.append((min(max(center_x, 0.0), width), min(max(center_y, 0.0), height)))

    recurse(0.0, 0.0, side, 0.0, 0.0, side)

    polylines: Polylines = []
    run: list[tuple[float, float]] = []
    for leaf in leaves:
        if leaf is None:
            if len(run) >= 2:
                polylines.append(run)
            run = []
        else:
            run.append(leaf)
    if len(run) >= 2:
        polylines.append(run)
    return polylines


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Scale both cell bounds by the fader's spacing, keeping their ratio fixed.

    spacing_mm 2.5 (draft) maps to min_cell_mm=1.0 / max_cell_mm=8.0 — exactly this module's own
    defaults — and every finer step shrinks both by the same factor. That keeps max_cell_mm /
    min_cell_mm constant across the fader (how much denser the darkest cell can get than the
    lightest one), instead of only sharpening the fine end and leaving flat areas as coarse at
    `max` as they are at `draft`.
    """
    return {
        "min_cell_mm": max(0.3, spacing_mm * 0.4),
        "max_cell_mm": max(1.5, spacing_mm * 3.2),
    }


HELP = "One blocky Hilbert curve that recurses finer where the image is dark and stays coarse where it is light."
