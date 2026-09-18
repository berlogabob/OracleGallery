"""Matrix-film-style pseudo-katakana: pictograms generated from a stroke vocabulary, not a font.

Real Matrix-style "digital rain" glyphs are stylised half-width katakana; this mode does not
load a font or approximate any real script -- it builds its own alphabet in code from strokes
on a 3x3 lattice (the corners, edge midpoints and centre of a unit cell): three horizontals,
three verticals, two full diagonals, and four half-diagonals from the centre to each corner.
A glyph is 1-4 of those strokes, filtered by four rules (`_reads_as_character`) so it reads as
a character rather than confetti or "missing glyph" tofu:

1. Connected. Every stroke after the first must share a lattice point (an actual endpoint, not
   merely a crossing) with a stroke already in the glyph, so a glyph is always one shape. The
   two full diagonals cross at the centre without sharing an endpoint there, so they never
   connect a glyph on their own -- only once a third stroke bridges their corners.
2. No closed box. A glyph may not use all four of the cell's own border edges: a rectangle is
   the one shape that reads as an error glyph, not a character.
3. At most one diagonal. Two full diagonals together is the "X in a box" look rule 2 is really
   guarding against; capping diagonals at one keeps every glyph reading as a single stroke
   crossing at most once, the way katakana strokes do.
4. Spine required. Every glyph of two or more strokes needs at least one full-length horizontal
   or vertical; short strokes then read as ticks hanging off that spine rather than a
   disconnected cloud of marks.

Tone is carried the way `ascii` carries it: every glyph the alphabet can produce is drawn once
and its ink (total stroke length) measured, the alphabet is sorted ascending by that measured
ink, and each cell's mean darkness (`cell_darkness`, area-averaged like every other tone mode
here) is mapped onto that ramp. The mapping is never assumed from generation order -- a 3-stroke
glyph built from short half-strokes can measure less ink than a 2-stroke glyph built from two
full diagonals -- so sorting by measurement is what keeps the render monotonic. Where two or
more glyphs land in the same measured-ink bucket, `np.random.default_rng((seed, row, col))`
picks between them: varied across the sheet, but pinned to the cell's own position so the same
tone always renders the same pixels.
"""

from __future__ import annotations

import bisect
import itertools
import math
from functools import lru_cache

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

HELP = "Matrix-style pseudo-katakana: darker cells get inkier code-generated glyphs, not a font."

# A 150 mm sheet at a 1.5 mm cell is already 100x100 = 10 000 cells; this backstops a caller
# combining a small char_mm with a large sheet, the same guard shape `ascii` uses for its own
# per-cell loop.
MAX_MATRIX_GLYPHS = 20_000

# Fraction of the cell a glyph's own bounding strokes may fill -- the rest is gutter so two
# adjacent solid glyphs never touch pen to pen.
_FIT = 0.8

# The 3x3 lattice, as fractions of a unit cell. Every stroke's endpoints are two of these nine
# points, which is what makes "shares a lattice point" a well-defined, checkable relation.
_TL, _TM, _TR = (0.0, 0.0), (0.5, 0.0), (1.0, 0.0)
_ML, _C, _MR = (0.0, 0.5), (0.5, 0.5), (1.0, 0.5)
_BL, _BM, _BR = (0.0, 1.0), (0.5, 1.0), (1.0, 1.0)

Point = tuple[float, float]
Stroke = tuple[Point, Point]
Glyph = tuple[Stroke, ...]

# Three horizontals, three verticals, two full diagonals, four half-strokes (centre to each
# corner) -- the whole vocabulary a glyph is ever built from.
_STROKES: tuple[Stroke, ...] = (
    (_TL, _TR),
    (_ML, _MR),
    (_BL, _BR),
    (_TL, _BL),
    (_TM, _BM),
    (_TR, _BR),
    (_TL, _BR),
    (_TR, _BL),
    (_C, _TL),
    (_C, _TR),
    (_C, _BL),
    (_C, _BR),
)

_MAX_GLYPH_STROKES = 4
_INK_ROUND = 6

# The four strokes that trace the cell's own border. A glyph using all four draws a closed
# rectangle -- the one shape that reads as tofu (a missing-character box) rather than a
# character, so it is rejected outright regardless of how well it would otherwise measure.
_OUTER_EDGES = frozenset({(_TL, _TR), (_BL, _BR), (_TL, _BL), (_TR, _BR)})

# The two full corner-to-corner diagonals. Real (and Matrix pseudo-) katakana strokes cross at
# most once; two full diagonals together is the "X in a box" look this mode is meant to avoid.
_DIAGONALS = frozenset({(_TL, _BR), (_TR, _BL)})

# A full-length horizontal or vertical -- border or mid-line, but never a half-stroke or a
# diagonal. A multi-stroke glyph needs one of these as its spine so the rest read as ticks
# hanging off a character rather than a loose cloud of short marks.
_SPINE_STROKES = frozenset({(_TL, _TR), (_ML, _MR), (_BL, _BR), (_TL, _BL), (_TM, _BM), (_TR, _BR)})


def _stroke_length(stroke: Stroke) -> float:
    (x0, y0), (x1, y1) = stroke
    return math.hypot(x1 - x0, y1 - y0)


def _connected(glyph: Glyph) -> bool:
    """One stroke is trivially connected; more strokes must form a single component.

    Union-find over the lattice points the glyph's strokes actually touch: two strokes are in
    the same component once some chain of shared endpoints links them, which is the same
    "shares a lattice point" test applied transitively across the whole glyph, not just to
    consecutive strokes.
    """
    if len(glyph) <= 1:
        return True
    parent: dict[Point, Point] = {}

    def find(point: Point) -> Point:
        parent.setdefault(point, point)
        while parent[point] != point:
            parent[point] = parent[parent[point]]
            point = parent[point]
        return point

    def union(a: Point, b: Point) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in glyph:
        union(a, b)
    roots = {find(a) for a, _ in glyph} | {find(b) for _, b in glyph}
    return len(roots) == 1


def _is_closed_box(glyph: Glyph) -> bool:
    """True once a glyph's strokes cover all four of the cell's own border edges."""
    return set(glyph) >= _OUTER_EDGES


def _diagonal_count(glyph: Glyph) -> int:
    return sum(1 for stroke in glyph if stroke in _DIAGONALS)


def _has_spine(glyph: Glyph) -> bool:
    return any(stroke in _SPINE_STROKES for stroke in glyph)


def _reads_as_character(glyph: Glyph) -> bool:
    """The full katakana-shape gate: connected, no closed box, <=1 diagonal, spine if >1 stroke.

    Connectivity alone was not enough: it happily accepted a 4-stroke box (all four border
    edges) or a box with both diagonals through it, which measured as the alphabet's inkiest
    glyphs and so were exactly what dark cells rendered -- but a closed box with an X through
    it reads as "missing character" tofu, not as a character. The three extra rules -- no
    closed border, never two full diagonals together, and every multi-stroke glyph anchored by
    at least one full-length horizontal or vertical -- are what katakana-like strokes actually
    obey: they never close into a frame, they cross at most once, and short strokes always hang
    off a longer spine rather than floating as a disconnected cloud of ticks.
    """
    if not _connected(glyph):
        return False
    if _is_closed_box(glyph):
        return False
    if _diagonal_count(glyph) > 1:
        return False
    return len(glyph) < 2 or _has_spine(glyph)


@lru_cache(maxsize=1)
def _alphabet() -> tuple[Glyph, ...]:
    """Every 1-`_MAX_GLYPH_STROKES` stroke combination that reads as a character, generated once.

    itertools.combinations over 12 strokes already rules out duplicate stroke sets; filtering by
    `_reads_as_character` is what turns "every subset of size <= _MAX_GLYPH_STROKES" into "every
    subset that reads as one character, not confetti and not tofu" -- see that function's own
    docstring for what each rule guards against.
    """
    glyphs: list[Glyph] = []
    for count in range(1, _MAX_GLYPH_STROKES + 1):
        for combo in itertools.combinations(_STROKES, count):
            if _reads_as_character(combo):
                glyphs.append(combo)
    return tuple(glyphs)


@lru_cache(maxsize=1)
def _build_ramp() -> tuple[tuple[float, tuple[Glyph, ...]], ...]:
    """Measure every alphabet glyph's ink and bucket by that measurement, ascending.

    Ink is rounded to 1e-6 mm-equivalent units before bucketing: different stroke combinations
    can sum to the exact same total length (e.g. two 1.0-length strokes vs. one 1.0 plus two
    0.5s), and those are meant to collide into one bucket, picked between at render time --
    not to land a hair apart from float summation order and silently never tie.
    """
    buckets: dict[float, list[Glyph]] = {}
    for glyph in _alphabet():
        ink = round(sum(_stroke_length(stroke) for stroke in glyph), _INK_ROUND)
        buckets.setdefault(ink, []).append(glyph)
    return tuple(sorted(buckets.items()))


def _pick_glyph(
    ramp: tuple[tuple[float, tuple[Glyph, ...]], ...],
    darkness: float,
    seed: int,
    row: int,
    col: int,
) -> Glyph:
    """Nearest-ink bucket for this darkness; a seeded draw breaks ties within that bucket."""
    target = min(1.0, max(0.0, darkness)) * ramp[-1][0]
    inks = [ink for ink, _ in ramp]
    index = bisect.bisect_left(inks, target)
    if index == 0:
        bucket = ramp[0][1]
    elif index == len(ramp):
        bucket = ramp[-1][1]
    else:
        before, after = ramp[index - 1], ramp[index]
        bucket = before[1] if abs(before[0] - target) <= abs(after[0] - target) else after[1]
    if len(bucket) == 1:
        return bucket[0]
    choice = int(np.random.default_rng((seed, row, col)).integers(0, len(bucket)))
    return bucket[choice]


def _place_glyph(glyph: Glyph, x0: float, y0: float, char_mm: float) -> Polylines:
    """Scale a unit-square glyph into its cell, `_FIT` of the cell with the rest as gutter."""
    scale = char_mm * _FIT
    margin = (char_mm - scale) / 2.0
    return [[(x0 + margin + px * scale, y0 + margin + py * scale) for px, py in stroke] for stroke in glyph]


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto char_mm, `ascii`'s own move and for the same reason.

    The floor is 1.5 mm rather than `ascii`'s 1.2: a single letterform stays legible carved
    from one stroke at 1.2 mm with a 0.3 mm nib, but a matrix glyph can be four strokes meeting
    at shared corners, and those joins need more room to stay distinguishable at the nib's
    resolution than a single stroke does.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"char_mm": max(1.5, spacing_mm * 1.6)}


def matrix(
    tone: ToneGrid,
    *,
    char_mm: float = 3.0,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_glyphs: int = MAX_MATRIX_GLYPHS,
) -> Polylines:
    """Fill a grid of char_mm cells with a code-generated glyph closest to each cell's tone.

    Cells are square and column-aligned -- a plain grid, no rotation, no per-row offset, no
    falling trails: those belong to an actual digital-rain animation, not a static plotted
    tone image. Darkness is stretched from the gated cells' own min..max onto the ramp's full
    range before picking a glyph, the same contrast fix `ascii` applies for the same reason:
    an area-averaged cell rarely reaches the true 0 or 1 extremes of the source image, so an
    unstretched mapping would use only the ramp's middle glyphs across most of a real photo.
    """
    if char_mm <= 0:
        raise ValueError("char_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_glyphs <= 0:
        raise ValueError("max_glyphs must be positive")

    cols = max(1, int(tone.width_mm / char_mm))
    rows = max(1, int(tone.height_mm / char_mm))
    if cols * rows > max_glyphs:
        raise ValueError(
            f"matrix would place {cols * rows} glyph cells, exceeding max_glyphs={max_glyphs}; "
            "increase char_mm or reduce the drawing size"
        )

    ramp = _build_ramp()
    if not ramp:
        return []

    raw = [
        [
            cell_darkness(
                tone.darkness,
                col * char_mm,
                row * char_mm,
                col * char_mm + char_mm,
                row * char_mm + char_mm,
                tone.width_mm,
                tone.height_mm,
            )
            for col in range(cols)
        ]
        for row in range(rows)
    ]
    passing = [value for line in raw for value in line if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    def normalized(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    polylines: Polylines = []
    for row in range(rows):
        y0 = row * char_mm
        for col in range(cols):
            darkness = raw[row][col]
            if darkness < min_darkness:
                continue
            glyph = _pick_glyph(ramp, normalized(darkness), seed, row, col)
            x0 = col * char_mm
            for stroke in _place_glyph(glyph, x0, y0, char_mm):
                polylines.append([_clip_point(point, tone.width_mm, tone.height_mm) for point in stroke])
    return polylines
