"""Contract + scales-specific coverage for the seigaiha-style fish-scale mode."""

from __future__ import annotations

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.scales import _lattice, quality_params, scales
from neje_oracle.blocks.imaging.modes import ToneGrid, _stitch


def test_scales_contract() -> None:
    report = check_mode_contract(scales, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 32.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_rows_are_offset_by_half_a_scale() -> None:
    """Alternate rows must be shifted by scale_mm / 2 so the scales interlock.

    Reads `_lattice`, the geometry the arcs are built from, the same way truchet's own test
    (`test_arc_endpoints_land_on_the_tiles_own_border`) reads `_tile_arcs` rather than the
    full `truchet()` output: going through the public `scales()` call would run every centre
    through `_stitch`, which -- correctly, that is its job -- merges same-row touching arcs
    into single multi-scale polylines and destroys the one-centre-per-arc structure this
    check needs.
    """
    scale_mm = 6.0
    tone = _uniform_tone(1.0, size_mm=36.0)
    positions = _lattice(tone, scale_mm, scale_mm * 0.42)

    centres_by_row: dict[float, set[float]] = {}
    for cx, cy, _darkness in positions:
        centres_by_row.setdefault(round(cy, 6), set()).add(round(cx, 3))

    rows = sorted(centres_by_row)
    assert len(rows) >= 2, "need at least two rows to compare an offset"
    for top_row, next_row in zip(rows, rows[1:], strict=False):
        top_xs = centres_by_row[top_row]
        next_xs = centres_by_row[next_row]
        # Every x in one row must land half a scale away from some x in the other row.
        for x in next_xs:
            shifted = {round(x + scale_mm / 2.0, 3), round(x - scale_mm / 2.0, 3)}
            assert shifted & top_xs, f"row at y={next_row} centre x={x} has no half-scale match in row y={top_row}"


def test_every_arc_stays_inside_the_frame() -> None:
    """A photo-sized, non-square tone must never draw a point outside its own sheet."""
    width_mm, height_mm = 50.0, 30.0
    tone = ToneGrid(np.random.default_rng(0).uniform(0.0, 1.0, size=(30, 50)), 1.0, width_mm, height_mm)
    polylines = scales(tone, scale_mm=4.0, min_darkness=0.1)
    assert polylines, "expected some ink on a random mid-grey field"
    for polyline in polylines:
        for x, y in polyline:
            assert -1e-6 <= x <= width_mm + 1e-6, f"x {x} outside [0, {width_mm}]"
            assert -1e-6 <= y <= height_mm + 1e-6, f"y {y} outside [0, {height_mm}]"


def test_stitching_collapses_touching_arcs_into_long_runs() -> None:
    """_stitch must cut the stroke count when neighbouring scales' arcs actually touch.

    A flat tone stretches to nothing (ascii._char_grid's own fallback: raw darkness used
    as-is when the passing cells have no spread), so darkness=0.06 with max_scales=8 lands
    every cell on level = round(0.06 * 7) = 0, i.e. radius == scale_mm/2 everywhere -- the
    one level where a scale's arc endpoints land exactly on its row neighbour's, by
    construction (see `scales`'s "Why level, not radius alone" note). That is the case
    `_stitch` exists for, and this asserts it actually fires: one whole row collapses to a
    single polyline instead of one per scale.
    """
    tone = _uniform_tone(0.06, size_mm=32.0)
    unjoined_arc_count = sum(level + 1 for *_rest, level in _levels(tone, scale_mm=4.0, min_darkness=0.05))
    joined = scales(tone, scale_mm=4.0, min_darkness=0.05)
    print(f"stitching: {unjoined_arc_count} raw arcs -> {len(joined)} strokes")
    assert len(joined) < unjoined_arc_count, (
        f"stitching did not reduce stroke count: {len(joined)} vs {unjoined_arc_count}"
    )
    assert len(joined) > 0


def _levels(tone: ToneGrid, *, scale_mm: float, min_darkness: float, max_scales: int = 8):
    """(cx, cy, level) for every drawn cell -- the same quantising `scales` itself does."""
    positions = _lattice(tone, scale_mm, scale_mm * 0.42)
    passing = [d for _cx, _cy, d in positions if d >= min_darkness]
    if not passing:
        return
    low, high = min(passing), max(passing)
    spread = high - low
    for cx, cy, darkness in positions:
        if darkness < min_darkness:
            continue
        normalized = (darkness - low) / spread if spread > 1e-9 else darkness
        level = round(min(1.0, max(0.0, normalized)) * (max_scales - 1))
        yield cx, cy, level


def test_stitch_is_a_noop_when_nothing_shares_an_endpoint() -> None:
    """Sanity check on the helper itself: independent arcs never merge below tolerance."""
    a = [(0.0, 0.0), (1.0, 1.0)]
    b = [(5.0, 5.0), (6.0, 6.0)]
    assert _stitch([a, b], 1e-6) == [a, b]
