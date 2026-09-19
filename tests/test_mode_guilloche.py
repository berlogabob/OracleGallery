"""Contract + guilloche-specific coverage for the spirograph rosette mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.guilloche import (
    _epicycle_ring,
    guilloche,
    quality_params,
)
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_guilloche_contract() -> None:
    report = check_mode_contract(guilloche, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 40.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_epicycle_ring_closes_on_itself() -> None:
    """The hypotrochoid must be exactly periodic over t = 0..2*pi: lobes - 1 is an integer
    ratio by construction, so the first and last sampled points should coincide to float
    precision, not merely within a generous tolerance.
    """
    for lobes in (2, 3, 5, 8):
        ring = _epicycle_ring((10.0, 10.0), R=5.0, r=1.0, d=1.5, lobes=lobes, points=200)
        start, end = ring[0], ring[-1]
        assert math.dist(start, end) < 1e-9, (lobes, start, end)
        # And the ring is not degenerate -- it actually leaves its own start point.
        midpoint = ring[len(ring) // 2]
        assert math.dist(start, midpoint) > 0.1


def test_points_stay_in_frame() -> None:
    tone = _uniform_tone(0.9, size_mm=37.0)
    polylines = guilloche(tone, rosette_mm=9.0)
    assert polylines
    for polyline in polylines:
        for x, y in polyline:
            assert -1e-6 <= x <= 37.0 + 1e-6
            assert -1e-6 <= y <= 37.0 + 1e-6


def test_dark_region_carries_more_ink_per_area_than_light() -> None:
    """Same footprint, different darkness -- more ink where it is darker, on a per-mm^2 basis
    (both tones use the same grid, so a raw ink-length comparison is already area-normalised).
    """

    def ink_mm(polylines: list[list[tuple[float, float]]]) -> float:
        return sum(math.dist(polyline[i], polyline[i + 1]) for polyline in polylines for i in range(len(polyline) - 1))

    light = ink_mm(guilloche(_uniform_tone(0.2), rosette_mm=9.0))
    dark = ink_mm(guilloche(_uniform_tone(0.95), rosette_mm=9.0))
    assert dark > light * 1.5, (dark, light)


def test_dense_150mm_stroke_count_is_low() -> None:
    """Pen lifts dominate plot time; a solid-dark 150mm rosette field should be one pen-down
    per rosette, in the tens, not thousands.
    """
    tone = _uniform_tone(0.9, size_mm=150.0, cell_mm=1.0)
    polylines = guilloche(tone)
    assert 0 < len(polylines) < 300, len(polylines)
