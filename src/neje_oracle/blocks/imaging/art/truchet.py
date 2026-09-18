"""Smith-style Truchet tiles: a maze of quarter-circle arcs that carries tone in its density.

Each square tile holds two quarter-circle arcs, mirror images of each other, wrapped around
a pair of OPPOSITE corners and each joining the midpoints of the two tile edges that meet at
that corner. Tiled across the sheet with a random choice of which corner pair to use, the
arcs chain edge to edge into long meandering curves -- the classic "maze" look -- because an
arc that ends at an edge midpoint is exactly where the neighbouring tile's own edge-midpoint
arc (if it has one reaching that edge) picks up. Tone is not carried by moving the arcs; it is
carried by how many of them a tile draws, nested concentrically around the same two corners.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _stitch

HELP = (
    "Maze of quarter-circle arcs, Smith-style Truchet tiles randomly rotated. "
    "Darker tiles carry more concentric arcs; detail = tile size in mm."
)

MAX_TILES_DEFAULT = 100_000
_ARC_SAMPLE_SPACING_MM = 0.3
_ARC_MIN_POINTS = 6
# A stitched join needs the two arcs' shared endpoint to land on the SAME float, not merely
# nearby: both tiles compute it as (their own corner) + tile_mm/2 in the same units, so the
# only slack to allow for is float rounding, never a deliberate geometric tolerance.
_JOIN_TOLERANCE_MM = 1e-6

# (corner_u, corner_v, start_deg, end_deg) for the two corners a tile's arcs wrap, as a
# fraction of tile_mm from the tile's own top-left origin. Angles are standard math
# convention (0 deg = +x, 90 deg = +y, y growing downward like the rest of this module).
# _CORNERS_A wraps top-left + bottom-right (a "\" diagonal of arcs); _CORNERS_B wraps
# top-right + bottom-left (a "/" diagonal). Together they are the only two ways to draw two
# non-crossing quarter arcs through all four edge midpoints of a square.
_CORNERS_A = ((0.0, 0.0, 0.0, 90.0), (1.0, 1.0, 180.0, 270.0))
_CORNERS_B = ((1.0, 0.0, 90.0, 180.0), (0.0, 1.0, 270.0, 360.0))


def truchet(
    tone: ToneGrid,
    *,
    tile_mm: float = 4.0,
    max_arcs: int = 4,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_tiles: int = MAX_TILES_DEFAULT,
) -> Polylines:
    """Lay a grid of Truchet tiles, k concentric arc-pairs deep where the tile is dark.

    Orientation. Each tile independently picks _CORNERS_A or _CORNERS_B with a fresh
    `np.random.default_rng((seed, row, col))` -- keyed on the tile's own grid position, not
    on iteration order, so which way a tile leans never depends on whether a neighbour was
    dark enough to draw or on max_arcs/tile_mm changing how many tiles came before it.

    Tone. k = ceil(d * max_arcs), d the tile's MEAN darkness over its own footprint (a numpy
    slice of the tone grid, not one sampled point, for the same reason `rings` averages: a
    single sample aliases against a resampled source). k concentric arcs are drawn around
    each of the tile's two corners, from a fixed radius ladder (see `_radius_ladder`), so a
    barely-inked tile draws one thin arc pair and a solid-black one draws max_arcs nested
    pairs -- the "darker tiles carry more concentric arcs" look this mode is named for.

    Radius ladder. The FIRST radius in the ladder is always tile_mm / 2, because that is the
    one whose two endpoints land exactly on edge midpoints -- (tile_mm/2, 0) and
    (0, tile_mm/2) measured from the wrapped corner -- which is what lets it continue into a
    neighbouring tile's own tile_mm/2 arc instead of stopping dead at the border. Every tile
    that draws anything (k >= 1) therefore always draws this ring, so the connective backbone
    of the maze is present at every darkness above min_darkness; only the DECORATIVE extra
    rings depend on k. Those extra rings step alternately in and out from tile_mm / 2:

        tile_mm/2, tile_mm/2 - s, tile_mm/2 + s, tile_mm/2 - 2s, tile_mm/2 + 2s, ...

    with s = tile_mm / (2 * (max_arcs + 1)). The most extreme ring in a max_arcs-long ladder
    sits ceil((max_arcs - 1) / 2) * s away from tile_mm/2, and that offset is always strictly
    less than tile_mm/2 for any max_arcs >= 1 (s itself is already under tile_mm/(2*max_arcs)),
    so every ring's radius stays inside (0, tile_mm) -- an arc centred on a tile corner with
    radius in that range stays inside the tile by construction, whatever its k. Extra rings
    do not generally land on the neighbour's own ring at the same offset (that depends on
    both tiles choosing the same k and orientation), so they read as engraved, nested detail
    around the one ring that actually carries the maze.

    Joining. Every arc from every tile -- corner arcs and their extra rings alike -- is handed
    to `_stitch` in one pass at the end, at a near-zero tolerance: two tile_mm/2 arcs that
    share an edge midpoint compute that midpoint identically (same tile_mm, same arithmetic),
    so they always merge when they DO share an endpoint, and `_stitch` is silent everywhere
    else. This is what turns the grid into a maze rather than a field of disconnected quarter
    circles, and it is the entire saving the joining test below checks for.

    max_tiles guards the one place this mode can explode: a small tile_mm on a big sheet is a
    cols*rows blow-up that costs nothing to detect before a single arc is sampled.
    """
    if tile_mm <= 0:
        raise ValueError("tile_mm must be positive")
    if max_arcs < 1:
        raise ValueError("max_arcs must be at least 1")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_tiles < 1:
        raise ValueError("max_tiles must be at least 1")

    cols = max(1, math.ceil(tone.width_mm / tile_mm))
    rows = max(1, math.ceil(tone.height_mm / tile_mm))
    if rows * cols > max_tiles:
        raise ValueError(
            f"truchet would need {rows * cols} tiles, exceeding max_tiles={max_tiles}; "
            "increase tile_mm or reduce the drawing size"
        )

    ladder = _radius_ladder(tile_mm, max_arcs)
    arcs: Polylines = []
    for row in range(rows):
        y0 = row * tile_mm
        for col in range(cols):
            x0 = col * tile_mm
            darkness = _tile_darkness(tone, x0, y0, tile_mm)
            if darkness < min_darkness:
                continue
            k = max(1, min(max_arcs, math.ceil(darkness * max_arcs)))
            orientation = int(np.random.default_rng((seed, row, col)).integers(0, 2))
            arcs.extend(_tile_arcs(x0, y0, tile_mm, ladder[:k], orientation))

    joined = _stitch(arcs, _JOIN_TOLERANCE_MM)
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in joined]


def _clip_point(point: tuple[float, float], width_mm: float, height_mm: float) -> tuple[float, float]:
    return max(0.0, min(width_mm, point[0])), max(0.0, min(height_mm, point[1]))


def _radius_ladder(tile_mm: float, max_arcs: int) -> list[float]:
    """The concentric radii, in draw-priority order -- see the "Radius ladder" docstring above."""
    step = tile_mm / (2.0 * (max_arcs + 1))
    offsets = [0]
    magnitude = 1
    while len(offsets) < max_arcs:
        offsets.append(-magnitude)
        if len(offsets) < max_arcs:
            offsets.append(magnitude)
        magnitude += 1
    return [tile_mm / 2.0 + offset * step for offset in offsets]


def _tile_darkness(tone: ToneGrid, x0: float, y0: float, tile_mm: float) -> float:
    """Mean darkness over one tile's footprint, clipped to the grid the tone actually has."""
    rows, cols = tone.darkness.shape
    col0 = min(cols - 1, max(0, int(x0 * cols / tone.width_mm)))
    col1 = min(cols, max(col0 + 1, math.ceil((x0 + tile_mm) * cols / tone.width_mm)))
    row0 = min(rows - 1, max(0, int(y0 * rows / tone.height_mm)))
    row1 = min(rows, max(row0 + 1, math.ceil((y0 + tile_mm) * rows / tone.height_mm)))
    return float(tone.darkness[row0:row1, col0:col1].mean())


def _tile_arcs(x0: float, y0: float, tile_mm: float, radii: list[float], orientation: int) -> Polylines:
    """The 2 * len(radii) arcs for one tile: `radii` nested rings around each of two corners."""
    corners = _CORNERS_A if orientation == 0 else _CORNERS_B
    arcs: Polylines = []
    for corner_u, corner_v, start_deg, end_deg in corners:
        center = (x0 + corner_u * tile_mm, y0 + corner_v * tile_mm)
        for radius in radii:
            arcs.append(_quarter_arc(center, start_deg, end_deg, radius))
    return arcs


def _quarter_arc(
    center: tuple[float, float], start_deg: float, end_deg: float, radius: float
) -> list[tuple[float, float]]:
    """One quarter circle as a polyline, sampled every ~0.3 mm of arc length, 6 points minimum.

    0.3 mm matches the plotter's own pen width (PEN_WIDTH_MM_DEFAULT in modes.py): a finer
    sampling than the nib resolves is only extra vertices, not extra visible curvature.
    """
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    arc_length = radius * abs(end - start)
    samples = max(_ARC_MIN_POINTS, math.ceil(arc_length / _ARC_SAMPLE_SPACING_MM) + 1)
    return [
        (
            center[0] + radius * math.cos(start + (end - start) * index / (samples - 1)),
            center[1] + radius * math.sin(start + (end - start) * index / (samples - 1)),
        )
        for index in range(samples)
    ]


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the shared quality fader onto tile_mm: smaller tiles, finer maze.

    Scaled by 1.2x, the same move `rings` makes and for the same reason: at the fader's
    draft spacing (2.5) a bare tile_mm=2.5 on the dense 150 mm segment-cap drawing comes in
    over its 40 000-segment cap (two quarter-arc pairs per tile adds up fast at a small
    pitch); *1.2 buys enough headroom at draft while every finer step still shrinks tile_mm,
    and so still adds detail, exactly as the fader promises.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"tile_mm": spacing_mm * 1.2}
