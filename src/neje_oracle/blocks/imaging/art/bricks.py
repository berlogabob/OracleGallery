"""Running-bond brick wall: the picture as a mosaic of hatched bricks.

Rows ("courses") of rectangular bricks, each course offset half a brick from the one above
-- the standard running-bond stagger, chosen over a plain grid because a grid of aligned
bricks reads as graph paper, while the half-offset stagger reads as masonry at a glance. Tone
is carried the way `lowpoly` carries it: each brick is hatched with parallel lines whose
spacing falls with the brick's own darkness, stitched into one serpentine stroke per brick
(see `_rect_hatch`, the axis-aligned cousin of `lowpoly._facet_hatch`). Mortar is drawn only
around bricks that pass `min_darkness` -- see `bricks()` for why that reads as "a picture made
of bricks" rather than "a wall with a picture on it", and why the two would fight for ink if
combined.
"""

from __future__ import annotations

import math

from ..modes import Polylines, ToneGrid, _clip_point, _stitch, cell_darkness

Point = tuple[float, float]

HELP = (
    "Running-bond brick wall: half-offset courses hatched to tone like a mosaic. "
    "Darker bricks carry denser hatch; detail = brick size in mm."
)

MAX_BRICKS_DEFAULT = 20_000
# Endpoints from two neighbouring gated bricks land on the SAME float when they share an edge
# -- both compute it as (row/col index) * brick size in the same arithmetic -- so this only
# needs to swallow float rounding, never a deliberate geometric tolerance (same reasoning as
# truchet's _JOIN_TOLERANCE_MM).
_JOIN_TOLERANCE_MM = 1e-6


def _row_shift(row: int, brick_width_mm: float) -> float:
    """Half-brick offset every other course -- the running-bond stagger."""
    return brick_width_mm / 2.0 if row % 2 else 0.0


def _row_columns(row: int, width_mm: float, brick_width_mm: float) -> list[tuple[float, float]]:
    """(x0, x1) of every brick in one course, clipped to the sheet.

    A shifted course starts half a brick to the LEFT of x=0, so the stagger is real at the
    left edge too: a running-bond wall's even courses run full bricks from the edge and its
    odd courses run a half-brick first, not a half-brick only where it happens to land at the
    right edge. That leading half-brick is simply clipped to [0, width_mm] like any other
    brick that runs off the sheet, not sized specially.
    """
    start = -_row_shift(row, brick_width_mm)
    cols = max(1, math.ceil((width_mm - start) / brick_width_mm))
    spans: list[tuple[float, float]] = []
    for col in range(cols):
        x0 = start + col * brick_width_mm
        x1 = x0 + brick_width_mm
        if x1 <= 0 or x0 >= width_mm:
            continue
        spans.append((max(0.0, x0), min(width_mm, x1)))
    return spans


def _rect_hatch(x0: float, y0: float, x1: float, y1: float, darkness: float, hatch_min_mm: float) -> list[Point]:
    """One serpentine of horizontal hatch lines filling a brick -- one stroke, however dark.

    spacing = hatch_min_mm / darkness is the same density law `lowpoly._facet_hatch` uses,
    capped at the brick's own height so a spacing wider than the brick still draws its one
    line rather than none. Because a brick is an axis-aligned rectangle (unlike a triangle
    facet) every hatch line already spans the full width with no clipping needed, so
    alternating the line direction is enough on its own to turn the implicit segment from one
    line's end to the next line's start into the connector that makes the whole fill one
    polyline instead of one stroke per line.
    """
    extent = y1 - y0
    if extent < 1e-9:
        return []
    spacing = min(hatch_min_mm / max(darkness, 1e-6), extent)
    if spacing <= 1e-9:
        return []
    points: list[Point] = []
    forward = True
    offset = y0 + spacing / 2.0
    while offset < y1:
        left, right = (x0, x1) if forward else (x1, x0)
        points.append((left, offset))
        points.append((right, offset))
        forward = not forward
        offset += spacing
    return points


def _edge_key(a: Point, b: Point) -> frozenset[Point]:
    """Order-independent identity for a mortar edge, rounded to swallow float noise only."""
    return frozenset({(round(a[0], 6), round(a[1], 6)), (round(b[0], 6), round(b[1], 6))})


def bricks(
    tone: ToneGrid,
    *,
    brick_width_mm: float = 12.0,
    brick_height_mm: float = 5.0,
    hatch_min_mm: float = 1.0,
    min_darkness: float = 0.12,
    max_bricks: int = MAX_BRICKS_DEFAULT,
) -> Polylines:
    """Lay a running-bond wall, hatch each brick to tone, frame gated bricks with mortar.

    Tone. Darkness is sampled once per brick as the MEAN over its own footprint (`cell_darkness`,
    the same area-average `ascii` uses), never a single point -- a brick spans several tone
    cells and a point sample would let one bright or dark pixel in the source decide the whole
    brick's hatch. Cheap gate first (min_darkness, default 0.12: light areas stay bare paper,
    the same default rationale as every other mode's floor), then the GATED bricks' own
    min..max darkness is stretched onto [0, 1] before it drives hatch spacing -- exactly what
    `ascii._char_grid` documents and for the same reason: area-averaging compresses a real
    photo's variance long before this function sees it, and without the stretch every brick
    would come out at the same middling density instead of carrying the picture.

    Mortar: gated bricks only, not the whole wall. The two readings are "a picture made of
    bricks" (mortar only where the picture is gated) and "a wall with a picture on it" (mortar
    everywhere, tone laid on top). The second was rejected: a mortar grid over the whole sheet
    draws exactly as much ink in the whitest highlight as in the darkest shadow, which is the
    same kind of cancellation that flattens a gradient into a "flat" bucket profile if the two
    signals are not chosen to cooperate. Gating the mortar to the same bricks that gate the
    hatch keeps mortar and hatch pulling the same direction -- both zero in the light, both
    present in the dark -- so light areas genuinely stay paper.

    Pen lifts. Each brick's hatch is already one serpentine (`_rect_hatch`). Mortar edges are
    deduplicated by exact shared endpoint (`_edge_key`) before drawing, so an edge sitting
    between two gated neighbours costs one stroke, not two, and the deduplicated edges are
    then handed to `_stitch` in one pass so a whole run of collinear course/course-boundary or
    brick/brick-boundary edges becomes one long stroke instead of many short ones -- the same
    join that turns truchet's per-tile arcs into a continuous maze.

    max_bricks guards the one place this mode can explode: a small brick on a big sheet is a
    rows*cols blow-up before a single hatch line or mortar edge is built.
    """
    if brick_width_mm <= 0 or brick_height_mm <= 0:
        raise ValueError("brick_width_mm and brick_height_mm must be positive")
    if hatch_min_mm <= 0:
        raise ValueError("hatch_min_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_bricks < 1:
        raise ValueError("max_bricks must be at least 1")

    rows = max(1, math.ceil(tone.height_mm / brick_height_mm))
    row_spans = [_row_columns(row, tone.width_mm, brick_width_mm) for row in range(rows)]
    total = sum(len(spans) for spans in row_spans)
    if total > max_bricks:
        raise ValueError(
            f"bricks would need {total} bricks, exceeding max_bricks={max_bricks}; "
            "increase brick_width_mm/brick_height_mm or raise max_bricks"
        )

    candidates: list[tuple[float, float, float, float, float]] = []
    for row, spans in enumerate(row_spans):
        y0 = row * brick_height_mm
        y1 = min(y0 + brick_height_mm, tone.height_mm)
        for x0, x1 in spans:
            darkness = cell_darkness(tone.darkness, x0, y0, x1, y1, tone.width_mm, tone.height_mm)
            candidates.append((x0, y0, x1, y1, darkness))

    passing = [c[4] for c in candidates if c[4] >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    hatches: Polylines = []
    mortar_edges: dict[frozenset[Point], tuple[Point, Point]] = {}
    for x0, y0, x1, y1, raw in candidates:
        if raw < min_darkness:
            continue
        stretched = (raw - low) / spread if spread > 1e-9 else raw
        points = _rect_hatch(x0, y0, x1, y1, stretched, hatch_min_mm)
        if points:
            hatches.append(points)
        corners: tuple[Point, Point, Point, Point] = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        for start, end in zip(corners, corners[1:] + corners[:1], strict=True):
            mortar_edges[_edge_key(start, end)] = (start, end)

    mortar = _stitch([[a, b] for a, b in mortar_edges.values()], _JOIN_TOLERANCE_MM)
    polylines = hatches + mortar
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in polylines]


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the quality fader onto hatch density and, secondarily, brick size.

    hatch_min_mm tracks spacing_mm directly (*0.4) and reproduces the default 1.0 mm exactly
    at the fader's draft rung (spacing 2.5), same convention as lowpoly's own quality_params.
    Brick size also shrinks with spacing (*4.8 width, *2.0 height -- again exactly the
    defaults 12.0/5.0 at spacing 2.5) so finer quality means smaller bricks as well as denser
    hatch, but both are floored (6.0 mm / 2.5 mm) at the fader's finest rung. Below that floor
    a brick stops reading as a brick at all -- its mortar frame and one hatch line would be
    nearly the same size, so the wall dissolves into plain hatching -- and un-floored it would
    also multiply the mortar-edge count on the dense 150 mm drawing faster than hatch density
    needs to grow for "more detail".
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {
        "brick_width_mm": max(6.0, round(spacing_mm * 4.8, 4)),
        "brick_height_mm": max(2.5, round(spacing_mm * 2.0, 4)),
        "hatch_min_mm": max(0.4, round(spacing_mm * 0.4, 4)),
    }
