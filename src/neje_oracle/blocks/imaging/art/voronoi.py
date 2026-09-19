"""Stained-glass Voronoi: seed points whose density follows tone, cells as closed polygons.

No scipy in this repo (see lowpoly's own docstring for the same constraint), so there is no
`scipy.spatial.Voronoi` to reach for. A Voronoi cell is, by definition, the intersection of
half-planes -- one per other site, each the "closer to me than to them" side of the
perpendicular bisector -- so clipping the frame rectangle against those half-planes one at a
time (Sutherland-Hodgman) builds each cell directly and exactly (see _cell_edges for the
termination rule that makes "exactly" true, not just "against the nearby ones").

This is the first mode in the set that tiles the plane with CLOSED cells rather than open
hatch strokes -- that is its whole reason to exist, so cell closure and gaplessness are load
bearing, not incidental (see the two geometry tests in tests/test_mode_voronoi.py).

Density. Seeds are generated on a coarse candidate grid (one bucket per site_mm-ish patch, like
lowpoly's lattice), with a DARKER bucket splitting into an N x N sub-grid of seeds instead of
one -- more competing sites in the same area means smaller cells there, which is the only lever
this mode has for "darker reads denser". Buckets below min_darkness still spawn exactly one
seed (never zero) so the mesh stays a genuine full tiling wherever it draws anything; see
"Gating" for how a light region still ends up blank.

Gating. Every candidate bucket gets a seed regardless of tone -- the mesh must tile without
holes, and a hole-in-the-lattice is not how "light region reads lighter" is supposed to work
here (that is the sub-grid's job, not a missing seed's). Instead, each cell independently
qualifies as `is_dark` from the tone sampled at its own seed point, and an edge is only drawn
if EITHER of the (at most two) cells it borders is dark -- the same OR-rule lowpoly's own
`outline=True` uses for facet edges, for the same reason: an edge between a dark cell and a
light one is the boundary of the dark region and has to be drawn, or the region reads as
melting into the paper on one side.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _sample_darkness, _stitch, cell_darkness

HELP = (
    "Stained-glass Voronoi cells, density tracking tone -- darker areas get smaller, denser "
    "cells. Closed polygons, shared edges drawn once; detail = cell size in mm."
)

Point = tuple[float, float]
# Either ("frame", site_index, side) for one of the 4 original rectangle edges (never shared --
# only the one cell that owns that corner of the sheet ever touches it), or frozenset({i, j})
# for the shared bisector edge between sites i and j (identical geometry from either side, see
# _build_cell, so it is only ever computed once no matter which of the two visits it first).
EdgeLabel = Any

MAX_CELLS_DEFAULT = 40_000
# The darkest passing bucket subdivides into a _MAX_SUBDIVISIONS x _MAX_SUBDIVISIONS sub-grid of
# seeds (see _seed_points); 3 gives a 9x seed-count, 3x linear-density spread between the
# lightest passing bucket (1 seed) and the darkest (9), enough to read as "smaller cells" rather
# than a subtle texture shift.
_MAX_SUBDIVISIONS = 3
# A stitched join needs two edges' shared endpoint to be the SAME float, not merely nearby: the
# two adjacent cells that produced them cut a bisector at different points in their own clip
# sequence, so rounding differs at the ~1e-13 (double precision, mm-scale coordinates) level --
# 1e-6 is generous headroom above that noise floor and still far below any real cell dimension.
_JOIN_TOLERANCE_MM = 1e-6


def voronoi(
    tone: ToneGrid,
    *,
    site_mm: float = 6.0,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_cells: int = MAX_CELLS_DEFAULT,
) -> Polylines:
    """Stained-glass mosaic: seed density from tone, cell edges as one stitched edge graph.

    Three passes:

    1. Seed the frame on a coarse `site_mm` grid, more seeds per bucket where the (gated,
       stretched) tone is darker -- see the module docstring's "Density" section.
    2. Clip the frame rectangle against each seed's nearest neighbours to build its cell as a
       closed polygon, tagging every edge with what produced it: a frame side, or the site pair
       whose bisector cut it (_build_cell).
    3. Flatten every cell's edges into one dict keyed by that tag, so a bisector shared by two
       cells is stored once no matter which cell's clip reached it first; keep an edge only if
       either of its (at most two) owning cells is dark enough. The result is handed to
       `_stitch` as a single graph, not drawn cell-by-cell -- see "Joining" below.

    Joining. Measured on the dense_line_art() 150 mm drawing at the fader's default (draft)
    quality: 2603 seeds, 2224 of them dark enough to draw. Emitting every dark cell's edges
    without dedup or stitching -- one 2-point stroke per edge, shared bisectors counted once
    per side -- is 13283 strokes (13283 pen lifts). Deduplicating by edge tag before drawing
    (this mode's actual, always-on behaviour) drops that to 7181 unique edges -- the ~6100
    difference is interior bisectors that would otherwise have been inked twice. Handing those
    7181 deduplicated edges to `_stitch` in one pass, rather than drawing each as its own lift,
    chains runs across cells wherever their shared endpoints allow and brings the final stroke
    count to 2260: an 83% cut in pen lifts (13283 -> 2260) versus the no-dedup-no-stitch
    baseline, for identical ink on the page.
    """
    if site_mm <= 0:
        raise ValueError("site_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_cells < 1:
        raise ValueError("max_cells must be at least 1")

    cols = max(1, round(tone.width_mm / site_mm))
    rows = max(1, round(tone.height_mm / site_mm))
    worst_case_seeds = rows * cols * _MAX_SUBDIVISIONS * _MAX_SUBDIVISIONS
    if worst_case_seeds > max_cells:
        raise ValueError(
            f"voronoi would need up to {worst_case_seeds} seeds, exceeding max_cells={max_cells}; "
            "increase site_mm or raise max_cells"
        )

    positions, origins = _seed_points(tone, rows, cols, min_darkness, seed)
    n = len(positions)
    if n == 0:
        return []

    is_dark = [_sample_darkness(tone, x, y) >= min_darkness for x, y in positions]
    if not any(is_dark):
        return []

    buckets: dict[tuple[int, int], list[int]] = {}
    for index, origin in enumerate(origins):
        buckets.setdefault(origin, []).append(index)

    edge_points: dict[EdgeLabel, tuple[Point, Point]] = {}
    edge_dark: dict[EdgeLabel, bool] = {}
    for index in range(n):
        cell = _cell_edges(index, positions, origins, buckets, rows, cols, tone.width_mm, tone.height_mm)
        for point, next_point, label in cell:
            if label not in edge_points:
                edge_points[label] = (point, next_point)
            edge_dark[label] = edge_dark.get(label, False) or is_dark[index]

    strokes = [list(edge_points[label]) for label, dark in edge_dark.items() if dark]
    joined = _stitch(strokes, _JOIN_TOLERANCE_MM)
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in joined]


def _seed_points(
    tone: ToneGrid, rows: int, cols: int, min_darkness: float, seed: int
) -> tuple[list[Point], list[tuple[int, int]]]:
    """One seed per grid bucket, up to a `_MAX_SUBDIVISIONS` x `_MAX_SUBDIVISIONS` sub-grid
    where the tone is darkest.

    Stretches the GATED buckets' own min..max onto the subdivision ramp before using it, exactly
    as ascii._char_grid documents: cell-mean darkness over a multi-mm bucket is already
    compressed toward the middle of 0..1 by area-averaging, so an unstretched ramp would spend
    almost its whole range on the middle subdivision rungs and the mosaic would come out one
    density everywhere. A bucket below min_darkness always contributes exactly one
    seed (never zero) so the lattice keeps tiling; see the module docstring's "Gating" section
    for why sparseness, not absence, is what should read as "lighter" here.
    """
    cell_w = tone.width_mm / cols
    cell_h = tone.height_mm / rows
    raw = np.empty((rows, cols))
    for row in range(rows):
        y0 = row * cell_h
        y1 = min(y0 + cell_h, tone.height_mm)
        for col in range(cols):
            x0 = col * cell_w
            x1 = min(x0 + cell_w, tone.width_mm)
            raw[row, col] = cell_darkness(tone.darkness, x0, y0, x1, y1, tone.width_mm, tone.height_mm)

    passing = raw >= min_darkness
    low, high = (float(raw[passing].min()), float(raw[passing].max())) if passing.any() else (0.0, 0.0)
    spread = high - low

    positions: list[Point] = []
    origins: list[tuple[int, int]] = []
    for row in range(rows):
        y0 = row * cell_h
        for col in range(cols):
            x0 = col * cell_w
            darkness = raw[row, col]
            stretched = 0.0 if darkness < min_darkness else ((darkness - low) / spread if spread > 1e-9 else darkness)
            # An N x N sub-grid, not N extra points scattered anywhere in the bucket: N points
            # placed anywhere in the same footprint barely shrinks the resulting cells (they can
            # still land close together, leaving big gaps elsewhere in the bucket), whereas N x N
            # sub-cells guarantee the darkest buckets actually split into a fine, even mosaic --
            # linear density scales with N, area with N^2, which is what makes "darker reads
            # smaller cells" legible rather than a faint texture change.
            subdivisions = 1 + round(stretched * _MAX_SUBDIVISIONS)
            sub_w, sub_h = cell_w / subdivisions, cell_h / subdivisions
            for sub_row in range(subdivisions):
                for sub_col in range(subdivisions):
                    rng = np.random.default_rng((seed, row, col, sub_row, sub_col))
                    sx = x0 + sub_col * sub_w
                    sy = y0 + sub_row * sub_h
                    x = min(tone.width_mm, sx + rng.uniform(0.0, sub_w))
                    y = min(tone.height_mm, sy + rng.uniform(0.0, sub_h))
                    positions.append((x, y))
                    origins.append((row, col))
    return positions, origins


def _cell_edges(
    index: int,
    positions: list[Point],
    origins: list[tuple[int, int]],
    buckets: dict[tuple[int, int], list[int]],
    rows: int,
    cols: int,
    width_mm: float,
    height_mm: float,
) -> list[tuple[Point, Point, EdgeLabel]]:
    """One site's Voronoi cell, as (start, end, label) edges around a closed ring.

    Starts from the frame rectangle and clips it against nearby sites' bisectors, nearest first,
    using the standard exact termination rule for an incremental Voronoi cell: once a candidate
    site is farther from this one than TWICE the current polygon's farthest vertex, that site's
    bisector cuts entirely outside the polygon and can never shrink it further, so it and every
    site farther still (they are visited in distance order) can be skipped. This is what makes
    the clip exact rather than a fixed-k approximation -- a first cut at fixed k=16 nearest
    neighbours looked plausible almost everywhere but produced long spurious spikes wherever a
    sparse-tone seed sat next to a dense cluster: its 16 nearest were all on the cluster side,
    so nothing bounded the cell on the empty side and it ballooned out to the frame edge. Sites
    are still gathered from the bucket grid _seed_points already built (not an O(n^2) distance
    matrix -- real memory pressure at the finest quality rung, n in the low tens of thousands),
    growing the search window only while the 2x rule above cannot yet be confirmed.
    """
    site = positions[index]
    row0, col0 = origins[index]
    edges: list[tuple[Point, EdgeLabel]] = [
        ((0.0, 0.0), ("frame", index, 0)),
        ((width_mm, 0.0), ("frame", index, 1)),
        ((width_mm, height_mm), ("frame", index, 2)),
        ((0.0, height_mm), ("frame", index, 3)),
    ]
    window_limit = max(rows, cols)
    window = 1
    processed: set[int] = set()
    while edges:
        candidates = sorted(
            (
                other
                for dr in range(-window, window + 1)
                for dc in range(-window, window + 1)
                for other in buckets.get((row0 + dr, col0 + dc), ())
                if other != index and other not in processed
            ),
            key=lambda other: math.dist(site, positions[other]),
        )
        for other_index in candidates:
            max_dist = max(math.dist(site, point) for point, _ in edges)
            if math.dist(site, positions[other_index]) > 2.0 * max_dist:
                break
            other = positions[other_index]
            mid = ((site[0] + other[0]) / 2.0, (site[1] + other[1]) / 2.0)
            normal = (other[0] - site[0], other[1] - site[1])
            edges = _clip_edges(edges, mid, normal, frozenset((index, other_index)))
            processed.add(other_index)
            if not edges:
                break
        if not edges:
            break
        max_dist = max(math.dist(site, point) for point, _ in edges)
        window_margin_mm = window * min(width_mm / cols, height_mm / rows)
        if window_margin_mm >= 2.0 * max_dist or window >= window_limit:
            break
        window += 1
    count = len(edges)
    return [(edges[i][0], edges[(i + 1) % count][0], edges[i][1]) for i in range(count)]


def _inside(point: Point, mid: Point, normal: Point) -> bool:
    """True on the site's own side of the bisector through `mid` with normal `normal`.

    `mid` is equidistant from both sites by construction, so testing (point - mid) . normal <=
    0 is testing "closer to the site normal points away from" without ever computing either
    distance -- the defining half-plane of a Voronoi cell, for free from the dot product.
    """
    return (point[0] - mid[0]) * normal[0] + (point[1] - mid[1]) * normal[1] <= 1e-9


def _intersect(p: Point, q: Point, mid: Point, normal: Point) -> Point:
    denom = (q[0] - p[0]) * normal[0] + (q[1] - p[1]) * normal[1]
    t = min(1.0, max(0.0, ((mid[0] - p[0]) * normal[0] + (mid[1] - p[1]) * normal[1]) / denom))
    return p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])


def _clip_edges(
    edges: list[tuple[Point, EdgeLabel]], mid: Point, normal: Point, label: EdgeLabel
) -> list[tuple[Point, EdgeLabel]]:
    """Sutherland-Hodgman clip of one closed polygon against one half-plane, edges labelled.

    Each output edge keeps its INPUT label if it is a (possibly truncated) piece of an edge that
    survives -- because it still lies on whatever line it always lay on -- and gets `label` only
    for the new edge this cut itself introduces, the segment of the cutting line that closes the
    gap between where the polygon exits the half-plane and where it re-enters. That is what
    lets every edge in the final cell be traced back to either a frame side or a specific
    neighbour's bisector, which is the whole mechanism _cell_edges relies on for dedup.
    """
    out: list[tuple[Point, EdgeLabel]] = []
    count = len(edges)
    for index in range(count):
        point, point_label = edges[index]
        next_point, _ = edges[(index + 1) % count]
        point_in = _inside(point, mid, normal)
        next_in = _inside(next_point, mid, normal)
        if point_in:
            out.append((point, point_label))
            if not next_in:
                out.append((_intersect(point, next_point, mid, normal), label))
        elif next_in:
            out.append((_intersect(point, next_point, mid, normal), point_label))
    return out


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the quality fader's spacing onto site_mm, matching the mode's own default at draft.

    quality_params(2.5) == site_mm=6.0 (this mode's own default), the same "draft is just the
    top of the ladder" convention lowpoly and truchet both use. Below roughly 1.5-2 mm a cell
    stops reading as a stained-glass pane and starts reading as noise -- with the plotter's
    ~0.3 mm nib, a cell needs a handful of nib widths on a side just to show its polygon shape
    rather than blur into a dot, which is why the fader's finest rung (spacing 1.0, site_mm
    2.4) is left comfortably above that floor rather than chasing arbitrarily small cells.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"site_mm": round(spacing_mm * 2.4, 4)}
