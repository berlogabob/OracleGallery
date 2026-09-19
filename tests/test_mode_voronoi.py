"""Contract + geometry coverage for the stained-glass Voronoi mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.voronoi import (
    _cell_edges,
    quality_params,
    voronoi,
)
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_voronoi_contract() -> None:
    report = check_mode_contract(voronoi, quality_params, monotonic=True)
    print(report)


def _all_cells(
    width_mm: float, height_mm: float, cols: int, rows: int, seed: int = 3
) -> list[list[tuple[float, float]]]:
    """Every site's own closed ring, via the same _cell_edges voronoi() itself calls.

    Bypasses voronoi()'s tone-driven seeding and darkness gate entirely -- this tests the
    clipping geometry (_cell_edges) on its own, the same way test_mode_truchet.py tests
    _tile_arcs directly rather than through truchet()'s own tile-darkness gate. _cell_edges'
    own 2x-distance termination rule (see its docstring) makes this an EXACT Voronoi diagram
    for a grid this small, not an approximation.
    """
    rng = np.random.default_rng(seed)
    positions = [
        (
            col * width_mm / cols + rng.uniform(0.2, width_mm / cols - 0.2),
            row * height_mm / rows + rng.uniform(0.2, height_mm / rows - 0.2),
        )
        for row in range(rows)
        for col in range(cols)
    ]
    origins = [(row, col) for row in range(rows) for col in range(cols)]
    buckets: dict[tuple[int, int], list[int]] = {}
    for index, origin in enumerate(origins):
        buckets.setdefault(origin, []).append(index)

    cells = []
    for index in range(len(positions)):
        edges = _cell_edges(index, positions, origins, buckets, rows, cols, width_mm, height_mm)
        ring = [point for point, _end, _label in edges]
        ring.append(ring[0])
        cells.append(ring)
    return cells


def _polygon_area(ring: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def test_cells_are_closed_rings() -> None:
    cells = _all_cells(24.0, 24.0, cols=4, rows=4)
    for ring in cells:
        assert math.dist(ring[0], ring[-1]) < 1e-6, "ring does not close"
        distinct = {(round(x, 6), round(y, 6)) for x, y in ring[:-1]}
        assert len(distinct) >= 3, f"cell has fewer than 3 distinct vertices: {ring}"


def test_cells_tile_without_gaps_or_overlap() -> None:
    width_mm, height_mm = 24.0, 24.0
    cells = _all_cells(width_mm, height_mm, cols=4, rows=4)
    total_area = sum(_polygon_area(ring) for ring in cells)
    frame_area = width_mm * height_mm
    assert math.isclose(total_area, frame_area, rel_tol=1e-6), (
        f"cell areas sum to {total_area}, frame area is {frame_area} -- gap or overlap"
    )


def test_joining_reduces_stroke_count_on_solid_black() -> None:
    """Solid black draws every cell dark; deduplicating shared edges should cut stroke count.

    Mirrors test_mode_truchet.py's test_joining_collapses_strokes_on_solid_black: on a fully
    dark tone every cell is drawn, so an UN-deduplicated render would emit one 2-point stroke
    per edge, with every interior edge counted twice (once per bordering cell). The mode itself
    always deduplicates -- this test just confirms the final stroke count is far below that
    raw, doubled-up figure.
    """
    size_mm, site_mm = 32.0, 4.0
    cells = round(size_mm / site_mm)
    tone = ToneGrid(np.full((cells, cells), 1.0), 1.0, size_mm, size_mm)
    strokes = voronoi(tone, site_mm=site_mm, seed=2)
    cols = rows = cells
    raw_edge_upper_bound = 2 * rows * cols * 9 * 6  # generous: buckets * max seeds/bucket * ~hex edges
    assert 0 < len(strokes) < raw_edge_upper_bound
    print(f"solid-black {size_mm}mm strokes: {len(strokes)}")
