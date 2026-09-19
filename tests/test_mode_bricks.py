"""Contract + bricks-specific coverage for the running-bond brick-wall mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.bricks import _rect_hatch, _row_columns, _row_shift, bricks, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_bricks_contract() -> None:
    report = check_mode_contract(bricks, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, width_mm: float = 40.0, height_mm: float = 5.0, cell_mm: float = 1.0) -> ToneGrid:
    cols = round(width_mm / cell_mm)
    rows = round(height_mm / cell_mm)
    return ToneGrid(np.full((rows, cols), darkness), cell_mm, width_mm, height_mm)


def test_rows_are_offset_by_half_a_brick() -> None:
    """Course 1 must start a half-brick to the left of course 0 -- the running-bond stagger.

    Checked two ways: directly from `_row_shift` (the formula), and from `_row_columns`'
    second span in each course (the first span is deliberately clipped at the sheet edge and
    would not show the offset on its own).
    """
    brick_width_mm = 10.0
    assert _row_shift(0, brick_width_mm) == 0.0
    assert _row_shift(1, brick_width_mm) == brick_width_mm / 2.0
    assert _row_shift(2, brick_width_mm) == 0.0

    row0 = _row_columns(0, 100.0, brick_width_mm)
    row1 = _row_columns(1, 100.0, brick_width_mm)
    assert math.isclose(row1[1][0] - row0[1][0], -brick_width_mm / 2.0)


def test_dark_brick_carries_more_hatch_than_light_brick() -> None:
    """Same brick footprint, higher stretched darkness must mean more drawn ink."""
    dark_points = _rect_hatch(0.0, 0.0, 12.0, 5.0, darkness=1.0, hatch_min_mm=1.0)
    light_points = _rect_hatch(0.0, 0.0, 12.0, 5.0, darkness=0.2, hatch_min_mm=1.0)

    def _length(points: list[tuple[float, float]]) -> float:
        return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))

    assert _length(dark_points) > _length(light_points) > 0


def test_mortar_only_frames_gated_bricks() -> None:
    """A below-gate wall draws nothing: mortar must not appear on its own over blank paper."""
    faint = _uniform_tone(0.05)
    assert bricks(faint, min_darkness=0.12) == []


def test_mortar_dedupes_shared_edges() -> None:
    """A solid dark strip with several bricks in a row must not double-draw the shared edges.

    Raw (undeduplicated) mortar would be 4 edges per brick; a shared internal edge between
    neighbours is drawn once, so the joined stroke count must come in under that raw count.
    """
    black = _uniform_tone(1.0, width_mm=40.0, height_mm=5.0)
    drawn = bricks(black, brick_width_mm=10.0, brick_height_mm=5.0, min_darkness=0.12)
    raw_edge_upper_bound = 4 * 4  # at most 4 bricks in a 40mm-wide, 10mm-brick single course
    assert 0 < len(drawn) < raw_edge_upper_bound
