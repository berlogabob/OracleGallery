"""Contract + stitch-specific coverage for the cross-stitch embroidery mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.stitch import _BOLD_INSET_FRACTION, quality_params, stitch
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_stitch_contract() -> None:
    report = check_mode_contract(stitch, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 32.0, stitch_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / stitch_mm)
    return ToneGrid(np.full((cells, cells), darkness), stitch_mm, size_mm, size_mm)


def test_every_stitch_lands_on_a_grid_corner() -> None:
    """Every drawn point must be near a stitch_mm grid corner -- the "counted" in counted needlework.

    The base X of every stitched cell lands exactly on a corner; only a bold tier's extra
    nested X is deliberately inset (see _BOLD_INSET_FRACTION), so the tolerance here is that
    inset's own worst case for max_weight=2, not mere float slop. A point clipped to the frame
    would also satisfy this trivially since the frame here is a whole number of cells
    (32 / 4 = 8), so any escape from the grid shows up as a genuine bug, not clipping noise.
    """
    stitch_mm = 4.0
    max_inset_mm = _BOLD_INSET_FRACTION * stitch_mm  # tier=1 (max_weight=2 below) inset, worst case
    tone = _uniform_tone(0.9, size_mm=32.0)
    polylines = stitch(tone, stitch_mm=stitch_mm, min_darkness=0.1, max_weight=2)
    assert polylines, "expected some stitches on a dark uniform tone"
    for polyline in polylines:
        for x, y in polyline:
            x_remainder = min(x % stitch_mm, stitch_mm - x % stitch_mm)
            y_remainder = min(y % stitch_mm, stitch_mm - y % stitch_mm)
            assert x_remainder <= max_inset_mm + 1e-9, f"x={x} is not near a stitch_mm={stitch_mm} grid line"
            assert y_remainder <= max_inset_mm + 1e-9, f"y={y} is not near a stitch_mm={stitch_mm} grid line"


def test_dark_region_carries_more_stitch_length_per_area() -> None:
    """A dark cell gets a bold, nested second X (weight 2); a mid cell gets one -- more ink per mm^2."""
    stitch_mm = 4.0
    dark = stitch(_uniform_tone(0.95, size_mm=32.0), stitch_mm=stitch_mm, min_darkness=0.1, max_weight=2)
    mid = stitch(_uniform_tone(0.3, size_mm=32.0), stitch_mm=stitch_mm, min_darkness=0.1, max_weight=2)

    def ink_density(polylines: list[list[tuple[float, float]]]) -> float:
        length = sum(math.dist(p[i], p[i + 1]) for p in polylines if len(p) >= 2 for i in range(len(p) - 1))
        return length / (32.0 * 32.0)

    assert ink_density(dark) > ink_density(mid) > 0
