"""Contract + rings-specific coverage for the concentric-circle halftone mode."""

from __future__ import annotations

import math

from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.rings import quality_params, rings
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_rings_contract() -> None:
    report = check_mode_contract(rings, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 30.0, cell_mm: float = 1.0) -> ToneGrid:
    import numpy as np

    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_rings_are_closed_and_fit_their_cell() -> None:
    tone = _uniform_tone(0.9)
    polylines = rings(tone, pitch_mm=3.0)
    assert polylines, "a dark uniform field must draw rings"
    for polyline in polylines:
        assert polyline[0] == polyline[-1], "every ring must be a closed polyline"
        center_x = sum(x for x, _ in polyline[:-1]) / (len(polyline) - 1)
        center_y = sum(y for _, y in polyline[:-1]) / (len(polyline) - 1)
        radius = max(math.hypot(x - center_x, y - center_y) for x, y in polyline[:-1])
        assert radius <= 1.5 + 1e-6, f"ring radius {radius} exceeds half the 3.0 mm pitch"


def test_darker_field_draws_more_rings_and_more_ink() -> None:
    light = _uniform_tone(0.15)
    dark = _uniform_tone(0.9)
    light_lines = rings(light, pitch_mm=3.0)
    dark_lines = rings(dark, pitch_mm=3.0)
    assert len(dark_lines) > len(light_lines), "darker field must draw more rings"
    light_ink = sum(math.dist(p[i], p[i + 1]) for p in light_lines for i in range(len(p) - 1))
    dark_ink = sum(math.dist(p[i], p[i + 1]) for p in dark_lines for i in range(len(p) - 1))
    assert dark_ink > light_ink, "darker field must carry more ink"
