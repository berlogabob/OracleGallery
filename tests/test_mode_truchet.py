"""Contract + truchet-specific coverage for the Smith-style Truchet maze mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.truchet import (
    _radius_ladder,
    _tile_arcs,
    quality_params,
    truchet,
)
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_truchet_contract() -> None:
    report = check_mode_contract(truchet, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 32.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_arc_endpoints_land_on_the_tiles_own_border() -> None:
    """Whatever corner/radius an arc is built from, both its ends must sit on the tile edge.

    This is what makes cross-tile joining possible at all: only a point exactly on a tile
    border can coincide with a point from a neighbouring tile's own arc.
    """
    tile_mm = 4.0
    origins = [(0.0, 0.0), (8.0, 12.0), (-4.0, 16.0)]
    for x0, y0 in origins:
        radii = _radius_ladder(tile_mm, 4)
        for orientation in (0, 1):
            for arc in _tile_arcs(x0, y0, tile_mm, radii, orientation):
                for point in (arc[0], arc[-1]):
                    on_vertical_edge = math.isclose(point[0], x0, abs_tol=1e-9) or math.isclose(
                        point[0], x0 + tile_mm, abs_tol=1e-9
                    )
                    on_horizontal_edge = math.isclose(point[1], y0, abs_tol=1e-9) or math.isclose(
                        point[1], y0 + tile_mm, abs_tol=1e-9
                    )
                    assert on_vertical_edge or on_horizontal_edge, (
                        f"arc endpoint {point} is not on tile border [{x0}, {x0 + tile_mm}] x [{y0}, {y0 + tile_mm}]"
                    )
                    # And still inside the tile's own bounding square, not merely on the line.
                    assert x0 - 1e-9 <= point[0] <= x0 + tile_mm + 1e-9
                    assert y0 - 1e-9 <= point[1] <= y0 + tile_mm + 1e-9


def test_joining_collapses_strokes_on_solid_black() -> None:
    """Solid black draws every tile at max_arcs; joining should cut the raw arc count.

    Every tile with min_darkness satisfied draws exactly 2 * k arcs (k = max_arcs here,
    since darkness is 1.0 everywhere), so the un-joined count is known analytically and does
    not need a second, un-stitched code path just for this test.
    """
    tile_mm = 4.0
    max_arcs = 4
    black = _uniform_tone(1.0, size_mm=32.0)
    joined = truchet(black, tile_mm=tile_mm, max_arcs=max_arcs, seed=1)
    cols = math.ceil(black.width_mm / tile_mm)
    rows = math.ceil(black.height_mm / tile_mm)
    raw_arc_count = rows * cols * 2 * max_arcs
    assert len(joined) < raw_arc_count, (
        f"joining did not reduce stroke count: {len(joined)} joined vs {raw_arc_count} raw arcs"
    )
    assert len(joined) > 0
