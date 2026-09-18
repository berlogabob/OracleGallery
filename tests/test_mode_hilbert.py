"""Contract + hilbert-specific coverage for the adaptive space-filling-curve mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.hilbert import hilbert, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_hilbert_contract() -> None:
    report = check_mode_contract(hilbert, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 8.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_solid_black_is_one_polyline_of_min_cell_neighbours() -> None:
    # 8 mm is power-of-two friendly against the default min_cell_mm=1.0: a full-depth curve
    # lands on exact 1.0 mm grid centres with no rounding slop.
    tone = _uniform_tone(1.0, size_mm=8.0)
    polylines = hilbert(tone, min_cell_mm=1.0, max_cell_mm=8.0)
    assert len(polylines) == 1, "solid black must draw as a single continuous stroke"
    polyline = polylines[0]
    assert len(polyline) == 64, "an 8mm frame at 1mm cells fully split is a 64-point order-3 curve"
    for (x0, y0), (x1, y1) in zip(polyline, polyline[1:], strict=False):
        distance = math.hypot(x1 - x0, y1 - y0)
        assert abs(distance - 1.0) < 1e-6, f"step {distance} is not exactly one min cell"
        assert (abs(x1 - x0) < 1e-9) != (abs(y1 - y0) < 1e-9), "each step must be axis-aligned, not diagonal"


def test_darker_field_yields_more_points_than_lighter_field() -> None:
    light = _uniform_tone(0.2, size_mm=32.0)
    dark = _uniform_tone(0.95, size_mm=32.0)
    light_points = sum(len(p) for p in hilbert(light, min_cell_mm=1.0, max_cell_mm=8.0))
    dark_points = sum(len(p) for p in hilbert(dark, min_cell_mm=1.0, max_cell_mm=8.0))
    assert dark_points > light_points, "a darker field must recurse deeper and draw more points"


def test_bad_params_raise() -> None:
    tone = _uniform_tone(0.5)
    for kwargs in (
        {"min_cell_mm": 0.0},
        {"min_cell_mm": 2.0, "max_cell_mm": 1.0},
        {"gamma": 0.0},
        {"min_darkness": -0.1},
        {"max_points": 0},
    ):
        try:
            hilbert(tone, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")
