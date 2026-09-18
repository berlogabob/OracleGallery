from __future__ import annotations

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.ridgeline import quality_params, ridgeline
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_ridgeline_contract() -> None:
    # Not a tone mode: a uniform field draws the same flat rows at any darkness, because tone
    # becomes displacement, and displacement needs a CHANGE in darkness. Like trace and edges.
    report = check_mode_contract(ridgeline, quality_params, monotonic=False)
    print(report)


def _y_values_at(polylines: list[list[tuple[float, float]]], x: float) -> list[float]:
    """Linearly interpolate every polyline's y at x, for polylines whose x-range covers it."""
    values: list[float] = []
    for polyline in polylines:
        for (x0, y0), (x1, y1) in zip(polyline, polyline[1:], strict=False):
            lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
            if lo <= x <= hi:
                values.append(y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return values


def test_ridgeline_occludes_the_rows_behind_a_single_bump() -> None:
    """A near ridge hides the far ridges it rises above; a taller far ridge still pokes through.

    Ten rows at a 3 mm pitch, lift 9 mm (the 3x default). A 3 mm-wide dark band sits under
    exactly one row (base_y=19.5) and lifts it 9 mm -- enough to bury the two rows immediately
    behind it (base_y 16.5 and 13.5, each only 1.35 mm off their own baseline). The row behind
    those, base_y=10.5, is close enough to its OWN baseline that it is naturally higher up the
    page than the bump's peak, so it should still show through -- exactly the "far spike pokes
    over a near ridge" case real Joy Division plots exhibit, not a case this mode should hide.
    """
    cell_mm = 0.5
    width_mm, height_mm = 40.0, 30.0
    cols, rows = int(width_mm / cell_mm), int(height_mm / cell_mm)
    col_x = (np.arange(cols) + 0.5) * cell_mm
    row_y = (np.arange(rows) + 0.5) * cell_mm
    in_band_x = (col_x >= 10.0) & (col_x <= 30.0)
    in_peak_y = (row_y >= 18.0) & (row_y <= 21.0)

    darkness = np.zeros((rows, cols))
    darkness[:, in_band_x] = 0.15
    darkness[np.ix_(in_peak_y, in_band_x)] = 1.0
    tone = ToneGrid(darkness=darkness, cell_mm=cell_mm, width_mm=width_mm, height_mm=height_mm)

    polylines = ridgeline(
        tone,
        row_pitch_mm=3.0,
        lift_mm=9.0,
        step_mm=0.5,
        blur_px=0.0,
        min_darkness=0.05,
        simplify_mm=0.0,
    )

    probe_x = 20.0
    found = _y_values_at(polylines, probe_x)

    def near(target: float, tolerance: float = 0.4) -> bool:
        return any(abs(value - target) < tolerance for value in found)

    # Peak row (base_y=19.5, darkness=1.0) -> y = 19.5 - 9*1.0 = 10.5. Always visible: it is
    # the first thing in the whole field to push this far up.
    assert near(10.5), found
    # The two rows immediately behind the peak (base_y=16.5 and 13.5, each lifted only
    # 9*0.15=1.35mm) land at y=15.15 and y=12.15 -- both BELOW (numerically greater than) the
    # peak's envelope of 10.5, so both must be entirely absent from the drawn output here.
    assert not near(15.15), found
    assert not near(12.15), found
    # base_y=10.5 lifted the same 1.35mm lands at y=9.15, which is ABOVE the peak's 10.5 --
    # its own baseline already carries it past the peak, so it must still be visible.
    assert near(9.15), found
    # Everything further back again is progressively higher up the page and stays visible.
    for expected in (6.15, 3.15, 0.15, 21.15, 24.15, 27.15):
        assert near(expected), (expected, found)


def test_ridgeline_uniform_field_is_one_parallel_line_per_row() -> None:
    """A flat mid-grey field lifts every row by the same amount: no ridge can occlude another.

    Every row samples the identical constant darkness at every x, so every row's displaced y
    is its own base_y minus the same fixed lift -- rows stay in their original front-to-back
    order and never cross, which the spec calls out as the second mode-specific behaviour to
    check. The result should be exactly one polyline per row, each a flat, full-width line,
    evenly spaced by row_pitch_mm.
    """
    cell_mm = 0.5
    width_mm, height_mm = 40.0, 20.0
    rows, cols = int(height_mm / cell_mm), int(width_mm / cell_mm)
    tone = ToneGrid(darkness=np.full((rows, cols), 0.5), cell_mm=cell_mm, width_mm=width_mm, height_mm=height_mm)

    polylines = ridgeline(
        tone,
        row_pitch_mm=2.0,
        lift_mm=1.0,
        step_mm=0.5,
        blur_px=0.0,
        min_darkness=0.05,
        simplify_mm=0.0,
    )

    assert len(polylines) == 10, [len(p) for p in polylines]

    row_ys: list[float] = []
    for polyline in polylines:
        ys = [point[1] for point in polyline]
        assert max(ys) - min(ys) < 1e-9, ys  # flat: darkness never varies along the row
        row_ys.append(ys[0])
        xs = sorted(point[0] for point in polyline)
        assert xs[0] < 1e-6, xs  # spans the full width: nothing gated, nothing occluded
        assert xs[-1] > width_mm - 1e-6, xs

    row_ys.sort(reverse=True)  # front (bottom, largest base_y) first
    gaps = [a - b for a, b in zip(row_ys, row_ys[1:], strict=False)]
    for gap in gaps:
        assert abs(gap - 2.0) < 1e-9, gaps  # parallel and evenly spaced by row_pitch_mm
