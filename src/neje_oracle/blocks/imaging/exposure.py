"""Choose how fine a mode should render, by solving for the ink it actually lays.

Every mode's `quality_params(spacing_mm)` speaks in absolute millimetres, and every one of
them is tuned against a ~150 mm sheet. A GRID cell's art box is about 25 x 34 mm, so the
same numbers put a 7.7 mm brick or a 3.8 mm voronoi site into a picture a few centimetres
across: the geometry is bigger than the features of the subject, and the cell comes back as
abstraction. Measured on one drawing at a 34 mm cell, the mode's own detail fader turned up
is worth 3-13x the ink (engraving 221 -> 752 mm, dotdot 56 -> 947, crosshatch 498 -> 1848).

Rather than guess a multiplier per mode, solve it: ink per unit area rises monotonically as
the spacing tightens, for every mode measured, so a handful of renders bisect onto a target
coverage. A mode that cannot reach the target (stitch saturates, ripple and sunburst top out
near a third of it) lands on its finest setting, which is the honest answer rather than a
number invented for it.

The cost is a few renders per cell; a whole 36-cell sheet renders in well under a second.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from .modes import Polylines

# Where the cells that already read sit: halftone measures 1.05 mm of ink per mm2 on a grid
# cell, scales 0.93. Below about 0.3 a cell reads as a few marks on paper rather than as a
# picture.
DEFAULT_TARGET_INK_PER_MM2 = 1.0
# How far past the target a candidate may land and still be preferred. Without a little room
# the solve rejects the setting just over the line and keeps one far under it.
_OVERSHOOT = 1.35


@dataclass(frozen=True)
class Exposure:
    """What a solve settled on, so a caller can report or cache it."""

    polylines: Polylines
    detail: float
    ink_per_mm2: float
    saturated: bool  # the mode could not reach the target even at its finest


def ink_mm(polylines: Polylines) -> float:
    return sum(
        math.dist(start, end)
        for polyline in polylines
        if len(polyline) >= 2
        for start, end in zip(polyline, polyline[1:], strict=False)
    )


def expose(
    render: Callable[[float], Polylines],
    *,
    area_mm2: float,
    target_ink_per_mm2: float = DEFAULT_TARGET_INK_PER_MM2,
    detail_bounds: tuple[float, float] = (1.0, 6.0),
    steps: int = 4,
) -> Exposure:
    """Render at the detail that lays `target_ink_per_mm2`, by bisection.

    `render(detail)` is the caller's own render at that detail -- the GRID pane hands over a
    closure round `cell_art`, so this function never has to know what a mode is.

    A mode that raises at a fine setting is treated as "too fine" and the solve steps back:
    several of them refuse a spacing their own geometry cannot hold (rings raises once its
    fixed pen gap exceeds the half-pitch), and a refusal is information, not an error.
    """
    low, high = detail_bounds
    if area_mm2 <= 0:
        raise ValueError("area_mm2 must be positive")
    if low <= 0 or high < low:
        raise ValueError("detail_bounds must be positive and ordered")

    def attempt(detail: float) -> tuple[Polylines, float] | None:
        try:
            polylines = render(detail)
        except ValueError:
            return None
        return polylines, ink_mm(polylines) / area_mm2

    baseline = attempt(low)
    if baseline is None:
        raise ValueError("mode refused even the coarsest detail")
    if baseline[1] >= target_ink_per_mm2:
        return Exposure(baseline[0], low, baseline[1], saturated=False)

    # Not every mode is monotonic all the way down. rings shrinks its circles as the lattice
    # tightens and drops the ones the nib cannot resolve; halftone's marks go under the
    # minimum stroke. Both can draw LESS at a finer setting, and once drew nothing at all --
    # so the shipped spacing is a floor the solve may never go below.
    best, best_detail = baseline, low

    def consider(result: tuple[Polylines, float] | None, detail: float) -> None:
        nonlocal best, best_detail
        if result is not None and result[1] > best[1] and result[1] <= target_ink_per_mm2 * _OVERSHOOT:
            best, best_detail = result, detail

    finest = attempt(high)
    consider(finest, high)
    if finest is not None and finest[1] < target_ink_per_mm2:
        # Even wide open it cannot reach the target: take the best seen, and say so.
        return Exposure(best[0], best_detail, best[1], saturated=True)

    lo, hi = low, high
    for _ in range(steps):
        mid = math.sqrt(lo * hi)  # geometric: detail is a scale factor, not an offset
        result = attempt(mid)
        consider(result, mid)
        if result is None or result[1] > target_ink_per_mm2:
            hi = mid
        else:
            lo = mid
    return Exposure(best[0], best_detail, best[1], saturated=best[1] < target_ink_per_mm2)
