from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.edges import edges, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_edges_contract() -> None:
    # monotonic=False for the same reason trace() opts out: a constant-slope gradient has no
    # tone-proportional ink to speak of, only a constant edge response, so "darker side carries
    # more ink" is not a property this mode has.
    report = check_mode_contract(edges, quality_params, monotonic=False, solid_ink=False)
    print(report)


def _distance_to_rect_border(x: float, y: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """0 exactly on the rectangle's outline; positive whether the point sits inside or outside."""
    outside_x = max(x0 - x, x - x1, 0.0)
    outside_y = max(y0 - y, y - y1, 0.0)
    if outside_x > 0 or outside_y > 0:
        return math.hypot(outside_x, outside_y)
    return min(x - x0, x1 - x, y - y0, y1 - y)


def test_edges_black_rectangle_on_white_hugs_the_border() -> None:
    """Every drawn point sits within ~2 cells of the rectangle's outline, none deep inside it.

    That is the whole point of an edge mode versus contour or a tone mode: it marks where
    brightness CHANGES, not the flat interior where it does not.
    """
    cell_mm = 1.0
    width_mm = height_mm = 40.0
    size = int(width_mm / cell_mm)
    darkness = np.zeros((size, size))
    row0, row1, col0, col1 = 10, 30, 10, 30
    darkness[row0:row1, col0:col1] = 1.0
    tone = ToneGrid(darkness=darkness, cell_mm=cell_mm, width_mm=width_mm, height_mm=height_mm)

    polylines = edges(tone, blur_px=0.5, min_length_mm=0.5)
    assert polylines, "a black square on white must draw its border"

    x0, y0, x1, y1 = col0 * cell_mm, row0 * cell_mm, col1 * cell_mm, row1 * cell_mm
    tolerance = 2 * cell_mm
    for polyline in polylines:
        for x, y in polyline:
            distance = _distance_to_rect_border(x, y, x0, y0, x1, y1)
            assert distance <= tolerance, (x, y, distance)


def test_edges_uniform_grey_field_draws_nothing() -> None:
    """A flat field below the ink floor has no gradient and is not the flat-dark special case.

    Distinct from the contract's white-paper check: this grey is not zero, only uniform and
    faint, so it exercises the min_darkness gate rather than the "nothing to sample" path.
    """
    tone = ToneGrid(darkness=np.full((48, 48), 0.02), cell_mm=1.0, width_mm=48.0, height_mm=48.0)
    assert edges(tone) == []


def test_edges_bold_threshold_adds_an_offset_pass() -> None:
    """A hard black/white edge clears any reasonable bold_threshold and gets a second stroke."""
    cell_mm = 1.0
    width_mm = height_mm = 30.0
    size = int(width_mm / cell_mm)
    darkness = np.zeros((size, size))
    darkness[:, 15:] = 1.0
    tone = ToneGrid(darkness=darkness, cell_mm=cell_mm, width_mm=width_mm, height_mm=height_mm)

    plain = edges(tone, bold_threshold=0.0)
    bold = edges(tone, bold_threshold=0.3)
    assert sum(len(p) for p in bold) > sum(len(p) for p in plain)
