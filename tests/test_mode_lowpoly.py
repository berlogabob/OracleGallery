"""Contract + lowpoly-specific coverage for the faceted triangulation mode."""

from __future__ import annotations

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.lowpoly import (
    _build_facets,
    _facet_hatch,
    _lattice,
    _triangle_area,
    _triangulate,
    lowpoly,
    quality_params,
)
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_lowpoly_contract() -> None:
    report = check_mode_contract(lowpoly, quality_params, monotonic=True)
    print(report)


def _tone(darkness_fn, width_mm: float, height_mm: float, cell_mm: float = 1.0) -> ToneGrid:
    cols = round(width_mm / cell_mm)
    rows = round(height_mm / cell_mm)
    darkness = np.array([[darkness_fn(c / cols, r / rows) for c in range(cols)] for r in range(rows)])
    return ToneGrid(darkness, cell_mm, width_mm, height_mm)


def _in_triangle(point: tuple[float, float], verts: tuple, tol: float = 1e-6) -> bool:
    """Barycentric membership test, normalised so `tol` means the same thing at any scale."""
    px, py = point
    (x1, y1), (x2, y2), (x3, y3) = verts
    denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    a = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / denom
    b = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / denom
    c = 1.0 - a - b
    return -tol <= a <= 1 + tol and -tol <= b <= 1 + tol and -tol <= c <= 1 + tol


def test_hatch_points_land_inside_their_own_triangle_and_the_frame() -> None:
    """The clip in _scan_triangle must be exact: every emitted vertex belongs to its facet.

    Checked against the internal facet records rather than lowpoly()'s flat output, because
    only the records still know which triangle produced which points.
    """
    width_mm, height_mm = 48.0, 33.0
    tone = _tone(lambda x, y: 1.0, width_mm, height_mm)  # uniform black: every facet hatches
    rng = np.random.default_rng(7)
    lattice = _lattice(width_mm, height_mm, facet_mm=5.0, jitter_fraction=0.35, rng=rng)
    triangles = _triangulate(tone, lattice)
    facets = _build_facets(tone, lattice, triangles, rng, min_darkness=0.05)

    checked = 0
    for facet in facets:
        for point in _facet_hatch(facet, hatch_min_mm=0.6):
            assert _in_triangle(point, facet.triangle), f"{point} outside its own triangle {facet.triangle}"
            x, y = point
            assert -1e-6 <= x <= width_mm + 1e-6, f"{point} outside the {width_mm}mm-wide frame"
            assert -1e-6 <= y <= height_mm + 1e-6, f"{point} outside the {height_mm}mm-tall frame"
            checked += 1
    assert checked > 0, "a uniform black field must produce hatch points to check"


def test_triangles_tile_the_frame_exactly() -> None:
    """No gaps, no overlaps: every triangle's area must sum to exactly width_mm * height_mm.

    True regardless of how the diagonal was chosen -- splitting a simple quadrilateral on
    either diagonal always partitions its area exactly -- so this is really testing that the
    lattice never produces a self-crossing quad, which is what the jitter_fraction < 0.5 bound
    in lowpoly() (and the border-only jitter for edge points) exists to guarantee.
    """
    width_mm, height_mm = 51.0, 37.0
    tone = _tone(lambda x, y: 0.5, width_mm, height_mm)
    rng = np.random.default_rng(3)
    lattice = _lattice(width_mm, height_mm, facet_mm=4.5, jitter_fraction=0.35, rng=rng)
    triangles = _triangulate(tone, lattice)

    total_area = sum(
        _triangle_area((lattice[a[0]][a[1]], lattice[b[0]][b[1]], lattice[c[0]][c[1]])) for a, b, c in triangles
    )
    expected = width_mm * height_mm
    assert abs(total_area - expected) <= 1e-6 * expected, (total_area, expected)


def test_outline_is_gated_by_darkness_not_drawn_over_blank_paper() -> None:
    """outline=True must add edges near the ink, and must not wander into the blank half.

    The image is black on the left, white on the right. Facets straddle the boundary, so a
    little bleed past the exact midline into the light half is expected -- but not past one
    facet_mm, which is as far as a facet touching the boundary can reach.
    """
    width_mm, height_mm = 60.0, 30.0
    facet_mm = 6.0
    tone = _tone(lambda x, y: 1.0 if x < 0.5 else 0.0, width_mm, height_mm)
    without_outline = lowpoly(tone, facet_mm=facet_mm, outline=False, seed=2)
    with_outline = lowpoly(tone, facet_mm=facet_mm, outline=True, seed=2)

    assert len(with_outline) > len(without_outline), "outline=True must add strokes on a half-dark image"
    margin = facet_mm
    assert all(x <= width_mm * 0.5 + margin + 1e-6 for polyline in with_outline for x, _ in polyline), (
        "outline must not draw over the blank right half"
    )
