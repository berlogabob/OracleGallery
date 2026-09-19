"""Contract + moire-specific coverage for the two-grating interference mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.moire import _field_polylines, _stretch_fn, moire, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_moire_contract() -> None:
    report = check_mode_contract(moire, quality_params, monotonic=True)
    print(report)
    print("dense_150mm_strokes:", report["dense_segments"][-1])


def _photo_tone(*, width_mm: float = 60.0, height_mm: float = 40.0, cell_mm: float = 0.5) -> ToneGrid:
    """A dark disc (a stand-in sphere) on a light field -- enough tone spread to wobble on."""
    cols = round(width_mm / cell_mm)
    rows = round(height_mm / cell_mm)
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    center_x, center_y, radius = cols * 0.5, rows * 0.5, min(rows, cols) * 0.3
    disc = ((x - center_x) ** 2 + (y - center_y) ** 2) < radius**2
    darkness = np.where(disc, 0.85, 0.1)
    return ToneGrid(darkness, cell_mm, width_mm, height_mm)


def _mean_heading_deg(polylines: list[list[tuple[float, float]]]) -> float:
    """Mean chord heading (start->end, folded into 0..180) across a field's own polylines."""
    headings = []
    for polyline in polylines:
        (x0, y0), (x1, y1) = polyline[0], polyline[-1]
        if math.dist((x0, y0), (x1, y1)) < 1e-6:
            continue
        headings.append(math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180)
    return sum(headings) / len(headings)


def test_two_fields_are_distinguishable_by_heading() -> None:
    """Field A stays at field_angle_deg; field B's own average heading drifts toward
    field_angle_deg + beat_deg because its wobble is perpendicular to its own straight line,
    not to A's -- a wobbling line and a straight line a few degrees apart must read as two
    different headings, or there is only one field here, not a moire of two.
    """
    tone = _photo_tone()
    stretch = _stretch_fn(tone, 1.2, 0.05)
    field_a = _field_polylines(
        tone, angle_deg=0.0, line_spacing_mm=1.2, gate_darkness=0.05, stretch=stretch, wobble_amplitude_mm=0.0
    )
    field_b = _field_polylines(
        tone, angle_deg=5.0, line_spacing_mm=1.2, gate_darkness=0.05, stretch=stretch, wobble_amplitude_mm=1.2
    )
    assert field_a and field_b, "both fields must draw something on a partly-dark image"
    heading_a = _mean_heading_deg(field_a)
    heading_b = _mean_heading_deg(field_b)
    assert abs(heading_b - heading_a) > 1.0, (heading_a, heading_b)


def test_beat_deg_changes_the_render_deterministically() -> None:
    tone = _photo_tone()
    default_render = moire(tone, beat_deg=5.0)
    wider_beat_render = moire(tone, beat_deg=12.0)
    assert default_render != wider_beat_render

    repeat_render = moire(tone, beat_deg=5.0)
    assert default_render == repeat_render, "same input must give the same output"
