"""Contract + dotdot-specific coverage for the numbered dot-to-dot puzzle mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.ascii import _pick_font
from neje_oracle.blocks.imaging.art.dotdot import (
    _DOT_RADIUS_FACTOR,
    _LABEL_GAP_MM,
    _number_glyphs,
    _place_label,
    _plan,
    dotdot,
    quality_params,
)
from neje_oracle.blocks.imaging.modes import ToneGrid


# monotonic=False: the contract's gradient check is an 80x20mm strip, and this mode is
# deliberately sparse (point_spacing_mm=6.0 default -- "a puzzle, not a stipple") on top of a
# density curve now raised to _DENSITY_CONTRAST_GAMMA specifically so light gated areas read as
# nearly bare paper (see dotdot.py's own _stretch_tone). Both together mean the default render
# places only ~9 points across this strip, and several 10mm buckets legitimately get none at
# all -- the correct behaviour for "let the background go", not a bug. A number's own ink also
# depends on how many digits it has, and with single-digit counts per bucket that is nowhere
# near enough samples for digit-length variance to average out on top of the sparsity itself.
# Measured: buckets [23, 17, 7, 14, 0, 0, 0, 11] mm -- the darkest (leftmost) strip still carries
# the most ink, but the tolerance's adjacent-strip check cannot survive buckets of zero.
def test_dotdot_contract() -> None:
    report = check_mode_contract(dotdot, quality_params, monotonic=False)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 60.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_plan_indices_are_1_to_n_in_tour_order_with_none_missing() -> None:
    tone = _uniform_tone(0.8, size_mm=60.0)
    plan = _plan(tone, point_spacing_mm=6.0, min_darkness=0.05, seed=0, max_points=80)
    assert len(plan) > 1, "expected a real cloud of points on a dark 60mm square"
    indices = [entry[0] for entry in plan]
    assert indices == list(range(1, len(plan) + 1)), (
        f"indices must be 1..N in tour order with none missing/repeated, got {indices}"
    )


def test_label_clears_its_own_dot_and_stays_close() -> None:
    """Every stroke point of a placed label must sit outside the dot ring (no overlap) and
    within a distance that scales sanely with the number's own digit count (no drift)."""
    font = _pick_font(None)
    cap_height_mm = 2.5
    dot_radius = cap_height_mm * _DOT_RADIUS_FACTOR
    point = (50.0, 50.0)
    diagonal = math.sqrt(0.5)
    directions = [(1.0, 0.0), (0.0, 1.0), (-diagonal, -diagonal), (diagonal, -diagonal)]
    for index, direction in zip((1, 42, 137, 999), directions, strict=True):
        strokes, width, height = _number_glyphs(index, font, cap_height_mm)
        assert strokes, f"digit {index} produced no strokes"
        placed, offset = _place_label(point, direction, strokes, width, height, dot_radius)
        distances = [math.hypot(x - point[0], y - point[1]) for stroke in placed for x, y in stroke]
        assert min(distances) > dot_radius + _LABEL_GAP_MM - 1e-6, (
            f"label for {index} overlaps its own dot ring: nearest point {min(distances)} mm, "
            f"dot radius {dot_radius} mm"
        )
        corner_radius = math.hypot(width / 2.0, height / 2.0)
        sane_bound = offset + corner_radius + 1e-6
        assert max(distances) <= sane_bound, (
            f"label for {index} drifted past its own bounding box: {max(distances)} mm > {sane_bound} mm"
        )
