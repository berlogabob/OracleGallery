"""Faceted triangle mesh: the picture as flat planes, each plane hatched to its own tone.

No scipy in this repo (only transitively installed), so there is no Delaunay library to reach
for. A jittered lattice stands in for it: start from a regular grid of points, nudge each
interior point by a small seeded random offset, and split every resulting quad on its diagonal.
That is not a Delaunay triangulation, but it does not need to be one — the effect being chased
is "a low-poly render", i.e. locally-flat facets with plausible-looking triangle edges, not a
mesh with any particular optimality property. What it must do is tile the frame exactly
(nothing else here promises that), which is why border points are only allowed to slide along
their own edge and corners never move at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _sample_darkness

HELP = "Low-poly facets, each hatched to its own tone at its own angle — a stained-glass read."

# Cheap safety rails, not tuned to any one image: max_facets guards the lattice itself
# (a tiny facet_mm on a big sheet is a quadratic blowup before a single hatch line is drawn),
# max_lines guards the hatch pass that follows it (a tiny hatch_min_mm on a dark image is a
# blowup of a different shape, in scanlines rather than facets). Sized generously above what
# the quality ladder needs on a full plotter bed -- see lowpoly's docstring for the ladder math.
MAX_LOWPOLY_FACETS = 120_000
MAX_LOWPOLY_LINES = 400_000

# A small fixed set rather than a free angle: three angles 60 degrees apart is the classic
# isometric-facet look (three families of parallel lines, like the three visible faces of a
# cube), and it is what makes neighbouring facets read as different planes at a glance instead
# of as one hatch pattern that happens to have gaps in it.
_ANGLE_CHOICES_DEG = (0.0, 60.0, 120.0)

# Sampling the centroid alone lets a facet that straddles a hard edge (half the triangle in a
# dark region, half in a highlight) come out at the AVERAGE of the two, which is a tone neither
# side actually has. Three more samples pulled two-thirds of the way toward each vertex mix in
# what the corners see, without paying for a full per-pixel scan of the triangle's interior.
_BARY_SAMPLES: tuple[tuple[float, float, float], ...] = (
    (1 / 3, 1 / 3, 1 / 3),
    (2 / 3, 1 / 6, 1 / 6),
    (1 / 6, 2 / 3, 1 / 6),
    (1 / 6, 1 / 6, 2 / 3),
)

LatticeIndex = tuple[int, int]
Triangle = tuple[LatticeIndex, LatticeIndex, LatticeIndex]
Point = tuple[float, float]


@dataclass(frozen=True)
class _Facet:
    triangle: tuple[Point, Point, Point]
    indices: Triangle
    darkness: float
    angle_deg: float
    is_dark: bool


def _clip(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lattice(
    width_mm: float, height_mm: float, facet_mm: float, jitter_fraction: float, rng: np.random.Generator
) -> list[list[Point]]:
    """A (rows+1) x (cols+1) grid of points, border-locked and interior-jittered.

    Corners never move, so the four corners of the sheet are always exactly the four corners of
    the mesh. A border point (not a corner) only jitters ALONG its edge -- an x-only wiggle on
    the top and bottom rows, a y-only wiggle on the left and right columns -- so it stays glued
    to x=0/width or y=0/height rather than drifting into the margin or off the sheet. That is
    what makes the mesh tile the frame exactly: nothing here can pull a boundary vertex, and
    hence a boundary edge, off the rectangle it has to close.
    """
    cols = max(1, round(width_mm / facet_mm))
    rows = max(1, round(height_mm / facet_mm))
    # Half a cell at jitter_fraction=1 -- any more and a point could cross a neighbouring
    # lattice line and fold the quad it sits in over on itself. The validated range
    # [0, 0.5) in lowpoly() keeps a healthy margin below that at the documented default 0.35.
    amplitude = jitter_fraction * facet_mm * 0.5
    points: list[list[Point]] = [[(0.0, 0.0)] * (cols + 1) for _ in range(rows + 1)]
    for row in range(rows + 1):
        base_y = height_mm * row / rows
        on_h_border = row in (0, rows)
        for col in range(cols + 1):
            base_x = width_mm * col / cols
            on_v_border = col in (0, cols)
            x, y = base_x, base_y
            if on_h_border and on_v_border:
                pass  # corner: fixed
            elif on_h_border:
                x = _clip(base_x + rng.uniform(-amplitude, amplitude), 0.0, width_mm)
            elif on_v_border:
                y = _clip(base_y + rng.uniform(-amplitude, amplitude), 0.0, height_mm)
            else:
                x = base_x + rng.uniform(-amplitude, amplitude)
                y = base_y + rng.uniform(-amplitude, amplitude)
            points[row][col] = (x, y)
    return points


def _triangulate(tone: ToneGrid, lattice: list[list[Point]]) -> list[Triangle]:
    """Split every quad on the diagonal that connects its more-similar pair of corners.

    Either diagonal tiles the quad correctly; the choice only affects which pair of triangles
    the quad's tone is divided between. Cutting along the corners that already agree keeps that
    cut edge itself inside a roughly flat region and pushes any real tone boundary in the quad
    onto the triangles' OTHER edges, which is where the hatch spacing (driven by each facet's
    own darkness) can actually render it as a facet-to-facet jump. Cutting the other way does
    the opposite: the diagonal itself would cross the boundary, splitting one hard edge into two
    triangles that each get a blurred, in-between tone instead of one clean step. This is the
    same "cut along the flatter diagonal" heuristic used to triangulate terrain height grids;
    alternating the diagonal by parity was the simpler alternative but ignores the image.
    """
    rows = len(lattice) - 1
    cols = len(lattice[0]) - 1
    triangles: list[Triangle] = []
    for row in range(rows):
        for col in range(cols):
            tl, tr, br, bl = (row, col), (row, col + 1), (row + 1, col + 1), (row + 1, col)
            d_tl = _sample_darkness(tone, *lattice[tl[0]][tl[1]])
            d_tr = _sample_darkness(tone, *lattice[tr[0]][tr[1]])
            d_br = _sample_darkness(tone, *lattice[br[0]][br[1]])
            d_bl = _sample_darkness(tone, *lattice[bl[0]][bl[1]])
            if abs(d_tl - d_br) <= abs(d_tr - d_bl):
                triangles.append((tl, tr, br))
                triangles.append((tl, br, bl))
            else:
                triangles.append((tl, tr, bl))
                triangles.append((tr, br, bl))
    return triangles


def _facet_darkness(tone: ToneGrid, verts: tuple[Point, Point, Point]) -> float:
    total = 0.0
    for wa, wb, wc in _BARY_SAMPLES:
        x = wa * verts[0][0] + wb * verts[1][0] + wc * verts[2][0]
        y = wa * verts[0][1] + wb * verts[1][1] + wc * verts[2][1]
        total += _sample_darkness(tone, x, y)
    return total / len(_BARY_SAMPLES)


def _build_facets(
    tone: ToneGrid,
    lattice: list[list[Point]],
    triangles: list[Triangle],
    rng: np.random.Generator,
    min_darkness: float,
) -> list[_Facet]:
    # Drawn in one batch rather than per-triangle so the angle sequence depends only on the
    # triangle count and the seed -- not on anything about how a caller later iterates them.
    angle_picks = rng.integers(0, len(_ANGLE_CHOICES_DEG), size=len(triangles))
    facets: list[_Facet] = []
    for indices, pick in zip(triangles, angle_picks, strict=True):
        verts = (
            lattice[indices[0][0]][indices[0][1]],
            lattice[indices[1][0]][indices[1][1]],
            lattice[indices[2][0]][indices[2][1]],
        )
        darkness = _facet_darkness(tone, verts)
        facets.append(_Facet(verts, indices, darkness, _ANGLE_CHOICES_DEG[int(pick)], darkness >= min_darkness))
    return facets


def _scan_triangle(uv: tuple[Point, Point, Point], v: float) -> tuple[float, float] | None:
    """Where the horizontal line at height v (in the hatch's rotated frame) crosses the triangle.

    Walks the three edges and keeps whichever give a u at this v; a convex triangle crossed by
    one line yields exactly two (or, on the rare edge that runs flat along v, its own endpoints
    stand in for the crossing). That pair is the hatch line's clipped interval -- exact, not an
    approximation, because it comes from the same line-segment intersection algebra hatch() uses
    against the whole frame, just run against three edges instead of four.
    """
    hits: list[float] = []
    for index in range(3):
        (u0, v0), (u1, v1) = uv[index], uv[(index + 1) % 3]
        if v0 == v1:
            if v0 == v:
                hits.append(u0)
                hits.append(u1)
            continue
        lo, hi = (v0, v1) if v0 <= v1 else (v1, v0)
        if lo <= v <= hi:
            hits.append(u0 + (v - v0) / (v1 - v0) * (u1 - u0))
    if len(hits) < 2:
        return None
    return min(hits), max(hits)


def _facet_hatch(facet: _Facet, hatch_min_mm: float) -> list[Point]:
    """One serpentine polyline of parallel hatch lines clipped exactly to this facet.

    spacing = hatch_min_mm / darkness is hatch()'s own density law, reused per facet instead of
    per frame. Capping it at the facet's own extent along the hatch normal is what "at least one
    line if d >= min_darkness" means in practice: a spacing wider than the facet is short for
    zero lines, and light-but-not-white facets are exactly where that would otherwise happen.
    Consecutive lines are stitched end-to-start (serpentine, like wave's rows) so a facet with
    several lines costs one pen lift instead of one per line -- with thousands of facets on a
    sheet, that is most of the plot-time difference between "textured" and "unplottable".
    """
    if not facet.is_dark:
        return []
    angle = math.radians(facet.angle_deg)
    direction = (math.cos(angle), math.sin(angle))
    perpendicular = (-direction[1], direction[0])
    projected = [
        (x * direction[0] + y * direction[1], x * perpendicular[0] + y * perpendicular[1]) for x, y in facet.triangle
    ]
    uv: tuple[Point, Point, Point] = (projected[0], projected[1], projected[2])
    v_values = [v for _, v in uv]
    v_min, v_max = min(v_values), max(v_values)
    extent = v_max - v_min
    if extent < 1e-9:
        return []
    spacing = min(hatch_min_mm / facet.darkness, extent)
    if spacing <= 1e-9:
        return []

    points_uv: list[Point] = []
    forward = True
    offset = v_min + spacing / 2.0
    while offset < v_max:
        interval = _scan_triangle(uv, offset)
        if interval is not None:
            u0, u1 = interval if forward else interval[::-1]
            points_uv.append((u0, offset))
            points_uv.append((u1, offset))
            forward = not forward
        offset += spacing
    return [(direction[0] * u + perpendicular[0] * v, direction[1] * u + perpendicular[1] * v) for u, v in points_uv]


def _triangle_area(verts: tuple[Point, Point, Point]) -> float:
    (x0, y0), (x1, y1), (x2, y2) = verts
    return abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) / 2.0


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the quality fader's spacing onto facet size and hatch density together.

    Both move with spacing, and the constants are chosen so quality_params(2.5) reproduces
    lowpoly's own defaults exactly (facet_mm=8.0, hatch_min_mm=1.2) -- draft quality is not a
    special case, it is just the top of the same ladder as every other rung. At the fader's
    finest rung (spacing 1.0) that gives facet_mm=3.2, hatch_min_mm=0.48: a mesh 2.5x denser
    with hatch lines 2.5x tighter, which is what "more detail" has to mean for a mode whose two
    knobs are plane size and plane shading.
    """
    return {
        "facet_mm": round(spacing_mm * 3.2, 4),
        "hatch_min_mm": round(spacing_mm * 0.48, 4),
    }


def lowpoly(
    tone: ToneGrid,
    *,
    facet_mm: float = 8.0,
    jitter_fraction: float = 0.35,
    hatch_min_mm: float = 1.2,
    min_darkness: float = 0.05,
    outline: bool = False,
    seed: int = 0,
    max_facets: int = MAX_LOWPOLY_FACETS,
    max_lines: int = MAX_LOWPOLY_LINES,
) -> Polylines:
    """The picture as a faceted mesh of triangles, each one hatched to its own flat tone.

    Three passes over one jittered lattice (see module docstring for why a lattice and not a
    real Delaunay triangulation):

    1. Build the lattice and split each quad into two triangles, picking the diagonal that
       keeps a real tone edge inside a facet rather than straddling the cut (_triangulate).
    2. Score every facet: darkness from several barycentric samples (not just the centroid, so
       a facet that straddles a hard edge does not get smeared to the average of both sides),
       and a hatch angle drawn from a small fixed set so neighbouring facets read as distinct
       planes rather than one continuous hatch.
    3. Hatch each dark-enough facet with parallel lines whose spacing falls with darkness,
       clipped exactly to the triangle and stitched into one serpentine stroke per facet.

    outline=True adds the facet edges themselves, but only where drawing them earns their keep:
    an edge is emitted if EITHER triangle touching it is at or above min_darkness, so the mesh
    stays legible over the dark two-thirds of an image without also outlining blank margins in
    ink. Edges are deduplicated by their shared lattice indices (exact, not a coordinate
    tolerance) before being drawn, so an interior edge costs one stroke, not two.

    facet_mm=8 / hatch_min_mm=1.2 sit above the geometric mean you would guess from hatch()'s
    own defaults (spacing ~1mm on a much finer grid). Tried at that finer scale on a real group
    photo (mean darkness 0.51 -- an ordinary midtone-heavy source, not an outlier), almost every
    facet fell in the 3-6 lines range and the frame printed as one undifferentiated crosshatch
    texture: correct per-facet, illegible as a mesh. Coarser facets plus sparser hatch is what
    lets a lightly-toned facet stay near-empty next to a heavily-hatched dark one, which is the
    entire visual point of "faceted" -- the mesh has to disappear into flat white in the
    highlights for the dark facets to read as planes rather than as generic shading.
    """
    if facet_mm <= 0:
        raise ValueError("facet_mm must be positive")
    if not 0.0 <= jitter_fraction < 0.5:
        raise ValueError("jitter_fraction must be in [0, 0.5) or the lattice can fold over itself")
    if hatch_min_mm <= 0:
        raise ValueError("hatch_min_mm must be positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if max_facets <= 0 or max_lines <= 0:
        raise ValueError("max_facets and max_lines must be positive")

    cols = max(1, round(tone.width_mm / facet_mm))
    rows = max(1, round(tone.height_mm / facet_mm))
    facet_count = 2 * rows * cols
    if facet_count > max_facets:
        raise ValueError(
            f"lowpoly would build {facet_count} facets, exceeding max_facets={max_facets}; "
            "increase facet_mm or raise max_facets"
        )

    rng = np.random.default_rng(seed)
    lattice = _lattice(tone.width_mm, tone.height_mm, facet_mm, jitter_fraction, rng)
    triangles = _triangulate(tone, lattice)
    facets = _build_facets(tone, lattice, triangles, rng, min_darkness)

    total_lines = 0
    polylines: Polylines = []
    for facet in facets:
        points = _facet_hatch(facet, hatch_min_mm)
        if not points:
            continue
        total_lines += len(points) // 2
        if total_lines > max_lines:
            raise ValueError(
                f"lowpoly would draw more than max_lines={max_lines} hatch strokes; "
                "raise hatch_min_mm, facet_mm, or max_lines"
            )
        polylines.append(points)

    if outline:
        edge_dark: dict[frozenset[LatticeIndex], bool] = {}
        edge_points: dict[frozenset[LatticeIndex], tuple[Point, Point]] = {}
        for facet in facets:
            a, b, c = facet.indices
            for start, end in ((a, b), (b, c), (c, a)):
                key = frozenset((start, end))
                edge_dark[key] = edge_dark.get(key, False) or facet.is_dark
                edge_points.setdefault(key, (lattice[start[0]][start[1]], lattice[end[0]][end[1]]))
        polylines.extend([point_a, point_b] for key, (point_a, point_b) in edge_points.items() if edge_dark[key])

    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in polylines]
