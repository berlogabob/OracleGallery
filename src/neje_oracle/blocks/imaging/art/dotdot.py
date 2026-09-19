"""dotdot: a dot-to-dot puzzle rendered from the picture's own tone.

Points are the same darkness-weighted blue-noise cloud tsp.py builds (denser where the image
is dark, spaced point_spacing_mm / sqrt(darkness) apart -- see tsp.py's own docstring), walked
into a tour with tsp's own nearest-neighbour + bounded 2-opt + stray-relocation machinery
(`tsp._place_points` / `_nearest_neighbour_tour` / `_two_opt` / `_relocate_strays`). That
machinery is reused wholesale rather than reimplemented: a second point sampler would drift
from tsp's placement law and the puzzle would stop looking like the same picture as tsp's own
render of it. The tour order becomes the puzzle's numbering -- point 1 is where tracing starts,
point N is where it ends, exactly as a paper dot-to-dot numbers its dots.

Unlike tsp(), the plot never draws the connecting lines: that is the whole point of a
dot-to-dot, left for the operator or a child to fill in with a pencil. What the plotter draws
per point is a small ring marking the dot and its index in the zzsimplex single-stroke font
(ascii.py's own cached glyph lookup, `_glyph_polylines` / `_pick_font`, reused so a multi-digit
number costs one font-parse per unique DIGIT across the whole puzzle, not per point), offset
away from the point along the PERPENDICULAR of the local tour direction so the label sits to
the side of the path the child will trace rather than on top of the dot or straddling the next
one.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _sample_darkness
from .ascii import _glyph_polylines, _pick_font
from .tsp import IMPROVEMENT_ROUNDS, _nearest_neighbour_tour, _place_points, _relocate_strays, _two_opt

HELP = (
    "Dot-to-dot puzzle: darkness-weighted points numbered along a short tour. "
    "No connecting lines are drawn -- join the dots yourself."
)

# A puzzle, not a stipple: past a few hundred dots the numbers stop being something a person
# would actually trace by hand, and every dot's number is at least one extra pen lift on top of
# the dot's own ring (see the module docstring on why lifts are the real cost here).
MAX_POINTS_DEFAULT = 300
_QUALITY_MAX_POINTS_CEILING = 900
# The fader's own draft step (mode_contract.SPACING_MM[0]) -- quality_params pins the defaults
# above to this value so draft quality reproduces them exactly (see quality_params).
_DRAFT_SPACING_MM = 2.5

# tsp's own required-spacing law (point_spacing_mm / sqrt(darkness)) is gentle: even at the
# gate floor it only asks for ~4.5x the fully-dark spacing, so a typical midtone background
# still reads as "sparse but present" rather than "paper". A dot-to-dot has to read as the
# subject before a single line is drawn, so _stretch_tone raises the gated range to this power
# before feeding it to tsp -- see _stretch_tone for the measured effect.
_DENSITY_CONTRAST_GAMMA = 3.0

# Dot ring: an octagon reads as "a dot" at plot scale for a fraction of a circle's vertex count.
_DOT_SIDES = 8
_DOT_RADIUS_FACTOR = 0.2  # dot radius as a fraction of cap_height_mm, so bigger numbers get bigger dots
_DIGIT_GAP_FACTOR = 0.15  # gap between adjacent digit glyphs, as a fraction of cap_height_mm
_LABEL_GAP_MM = 0.3  # clearance between the dot ring and the nearest corner of its own label


def dotdot(
    tone: ToneGrid,
    *,
    point_spacing_mm: float = 6.0,
    cap_height_mm: float = 2.5,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_points: int = MAX_POINTS_DEFAULT,
    font: str | None = None,
) -> Polylines:
    """A dot ring plus a numbered label at every point of a darkness-weighted, toured cloud.

    Placement and touring are entirely tsp's (see module docstring); this function only turns
    that tour into ring-plus-number geometry. `max_points` silently caps the cloud the same way
    tsp's own accept/reject pass already does (`_place_points` stops once it has enough) --
    there is no separate "too many points" error to catch here, because a puzzle that is asked
    for more dots than it can afford should just draw the darkest/first-accepted subset rather
    than refuse to draw at all.
    """
    if point_spacing_mm <= 0:
        raise ValueError("point_spacing_mm must be positive")
    if cap_height_mm <= 0:
        raise ValueError("cap_height_mm must be positive")
    if not 0.0 <= min_darkness < 1.0:
        raise ValueError("min_darkness must be in [0, 1)")
    if max_points <= 0:
        raise ValueError("max_points must be positive")

    plan = _plan(tone, point_spacing_mm, min_darkness, seed, max_points)
    if not plan:
        return []

    resolved_font = _pick_font(font)
    dot_radius = cap_height_mm * _DOT_RADIUS_FACTOR
    polylines: Polylines = []
    for index, point, direction in plan:
        polylines.append(_dot_ring(point, dot_radius))
        strokes, width, height = _number_glyphs(index, resolved_font, cap_height_mm)
        if not strokes:
            continue
        placed, _offset = _place_label(point, direction, strokes, width, height, dot_radius)
        polylines.extend(placed)

    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in polylines]


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Denser points, and down to a floor, smaller numbers, as quality rises.

    point_spacing_mm scales with the fader's own spacing directly: *2.4 lines the fader's
    draft step (2.5 mm) up with this mode's default point_spacing_mm (6.0 mm) exactly, so
    draft quality reproduces the default render rather than a different one.

    cap_height_mm tracks spacing_mm 1:1 but never drops below 2.0 mm -- the same shape of
    floor ascii.quality_params holds at 1.2 mm, for the same reason: below it a glyph stops
    resolving into a legible shape at the plotter's 0.3 mm nib and just prints as a blob of
    overlapping strokes. A number is worse off than ascii's letters here, because a 2-3 digit
    number packs 2-3 glyphs into roughly the same width a single ascii cell gives one
    character, so the floor for dotdot sits noticeably higher than ascii's.

    max_points scales with the SQUARE of how much closer together the fader has asked the
    points to be (area coverage, not linear count), since that is what the denser point cloud
    actually needs room for -- capped at _QUALITY_MAX_POINTS_CEILING so quality's benefit is
    "a denser cloud" and never "a puzzle nobody would trace by hand" (see MAX_POINTS_DEFAULT).
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    scale = (_DRAFT_SPACING_MM / spacing_mm) ** 2
    return {
        "point_spacing_mm": round(spacing_mm * 2.4, 3),
        "cap_height_mm": max(2.0, round(spacing_mm, 3)),
        "max_points": min(_QUALITY_MAX_POINTS_CEILING, round(MAX_POINTS_DEFAULT * scale)),
    }


def _stretch_tone(tone: ToneGrid, min_darkness: float) -> ToneGrid:
    """Rescale the GATED cells' own min..max onto [min_darkness, 1], then raise that to
    _DENSITY_CONTRAST_GAMMA, before handing the grid to tsp's point placement.

    The plain 0..1 stretch alone (what ascii._char_grid does at cell granularity) is not
    enough here. tsp spaces an accepted point at point_spacing_mm / sqrt(darkness): measured
    on this mode's own preview image (a lit sphere, a shaded cylinder, a solid bar, on a grey
    background spanning nearly the FULL raw 0..1 range already), a linear stretch alone still
    left ordinary midtone background asking for only ~9-13 mm of spacing against ~6-7 mm for
    the genuinely dark regions -- both "present", nowhere near "paper". A dot-to-dot has to
    read as its subject before a single line is drawn, so the gated range is raised to a power
    first: unit**gamma pushes every midtone value hard toward 0 while leaving 0 and 1 fixed,
    so light gated areas now land close to the min_darkness floor (required spacing ~19-26 mm,
    close to bare paper) while the truly dark regions still reach the full ~6 mm floor tsp's
    own law gives fully-dark cells. Cells below min_darkness are left untouched, so they still
    fail _place_points' own gate exactly as before.
    """
    darkness = tone.darkness
    gated = darkness[darkness >= min_darkness]
    if gated.size == 0:
        return tone
    low, high = float(gated.min()), float(gated.max())
    spread = high - low
    if spread <= 1e-9:
        return tone
    unit = np.clip((darkness - low) / spread, 0.0, 1.0) ** _DENSITY_CONTRAST_GAMMA
    stretched = np.where(darkness >= min_darkness, min_darkness + unit * (1.0 - min_darkness), darkness)
    return replace(tone, darkness=stretched)


def _ordered_points(
    tone: ToneGrid, point_spacing_mm: float, min_darkness: float, seed: int, max_points: int
) -> list[tuple[float, float]]:
    """tsp's own placement + tour, reused wholesale (see module docstring), fed a
    tone-stretched grid so the resulting cloud actually carries the picture's contrast
    (see _stretch_tone).

    tsp's own accept/reject pass already gates on the STRETCHED array's min_darkness, but the
    stretch only ever pushes gated values UP (toward min_darkness or above), never down past
    it, so this filter is normally a no-op; it is here as a hard guarantee, checked against
    the ORIGINAL unstretched tone, that a point below the gate can never survive into the
    tour -- "let the background go" should hold even if a future change to the density curve
    stops being monotonic at the floor.
    """
    stretched = _stretch_tone(tone, min_darkness)
    points = _place_points(stretched, point_spacing_mm, min_darkness, seed, max_points)
    points = [point for point in points if _sample_darkness(tone, *point) >= min_darkness]
    if len(points) < 2:
        return points
    tour = _nearest_neighbour_tour(points, point_spacing_mm)
    for _ in range(IMPROVEMENT_ROUNDS):
        tour = _two_opt(points, tour, point_spacing_mm)
        tour = _relocate_strays(points, tour, point_spacing_mm)
    return [points[i] for i in tour]


def _plan(
    tone: ToneGrid, point_spacing_mm: float, min_darkness: float, seed: int, max_points: int
) -> list[tuple[int, tuple[float, float], tuple[float, float]]]:
    """One entry per dot: (1-based puzzle index in tour order, the dot's point, the unit
    direction the tour runs through it). Geometry-free -- like ascii._char_grid -- so the
    tour's own correctness (every index 1..N present exactly once, in tour order) is cheap to
    test without rendering a single glyph (see tests/test_mode_dotdot.py).
    """
    ordered = _ordered_points(tone, point_spacing_mm, min_darkness, seed, max_points)
    count = len(ordered)
    plan: list[tuple[int, tuple[float, float], tuple[float, float]]] = []
    for i, point in enumerate(ordered):
        prev_point = ordered[i - 1] if i > 0 else None
        next_point = ordered[i + 1] if i < count - 1 else None
        plan.append((i + 1, point, _local_direction(prev_point, point, next_point)))
    return plan


def _local_direction(
    prev_point: tuple[float, float] | None,
    point: tuple[float, float],
    next_point: tuple[float, float] | None,
) -> tuple[float, float]:
    """Unit vector along the tour through this point: prev-to-next when both neighbours exist,
    else whichever single edge is available, else a fixed rightward default for an isolated
    point. A label is offset by the PERPENDICULAR of this (see _place_label), so it lands to
    the side of the path the child will trace rather than in front of or behind the dot, where
    the previous or next dot already sits.
    """
    if prev_point is not None and next_point is not None:
        dx, dy = next_point[0] - prev_point[0], next_point[1] - prev_point[1]
    elif next_point is not None:
        dx, dy = next_point[0] - point[0], next_point[1] - point[1]
    elif prev_point is not None:
        dx, dy = point[0] - prev_point[0], point[1] - prev_point[1]
    else:
        dx, dy = 1.0, 0.0
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 1.0, 0.0
    return dx / length, dy / length


def _dot_ring(center: tuple[float, float], radius: float) -> list[tuple[float, float]]:
    """A small closed octagon marking the point -- one pen lift, _DOT_SIDES segments."""
    cx, cy = center
    return [
        (
            cx + radius * math.cos(2 * math.pi * i / _DOT_SIDES),
            cy + radius * math.sin(2 * math.pi * i / _DOT_SIDES),
        )
        for i in range(_DOT_SIDES + 1)
    ]


def _number_glyphs(index: int, font: str, cap_height_mm: float) -> tuple[Polylines, float, float]:
    """The digits of `index` laid out left-to-right at their own measured widths.

    Returns strokes in LOCAL number space (origin at the number's own bottom-left corner) plus
    its total (width, height), so the caller can center that box wherever it likes without
    this function knowing anything about dots, tours, or offsets. Digit width comes from each
    cached glyph's own bounding box (ascii.py measures a font-wide average instead, for a
    whole alphabet's worth of characters; digits alone are cheap enough to measure exactly).
    """
    digit_gap = cap_height_mm * _DIGIT_GAP_FACTOR
    cursor_x = 0.0
    strokes: Polylines = []
    max_height = 0.0
    for character in str(index):
        glyph = _glyph_polylines(character, font, cap_height_mm)
        if not glyph:
            continue
        xs = [x for polyline in glyph for x, _ in polyline]
        ys = [y for polyline in glyph for _, y in polyline]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        shift_x, shift_y = cursor_x - min_x, -min_y
        strokes.extend([(x + shift_x, y + shift_y) for x, y in polyline] for polyline in glyph)
        cursor_x += (max_x - min_x) + digit_gap
        max_height = max(max_height, max_y - min_y)
    total_width = max(0.0, cursor_x - digit_gap)
    return strokes, total_width, max_height


def _place_label(
    point: tuple[float, float],
    direction: tuple[float, float],
    strokes: Polylines,
    width: float,
    height: float,
    dot_radius: float,
) -> tuple[Polylines, float]:
    """Translate a number's local-space strokes so its bounding box sits beside `point`.

    The box is centred at point + perpendicular(direction) * offset, with
    offset = dot_radius + _LABEL_GAP_MM + corner_radius (corner_radius = half the box's own
    diagonal). That specific offset is what guarantees no overlap regardless of which way the
    box happens to face: by the triangle inequality, every point inside the box is at least
    offset - corner_radius = dot_radius + _LABEL_GAP_MM away from `point`, i.e. clear of the
    dot ring with room to spare, however the number's digits actually stack up.
    """
    corner_radius = math.hypot(width / 2.0, height / 2.0)
    offset = dot_radius + _LABEL_GAP_MM + corner_radius
    perp = (-direction[1], direction[0])
    center = (point[0] + perp[0] * offset, point[1] + perp[1] * offset)
    shift = (center[0] - width / 2.0, center[1] - height / 2.0)
    placed = [[(x + shift[0], y + shift[1]) for x, y in stroke] for stroke in strokes]
    return placed, offset
