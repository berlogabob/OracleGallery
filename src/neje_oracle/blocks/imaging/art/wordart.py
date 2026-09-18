"""Word art: a typed sentence, flowed left to right across scanlines, drawn as the picture.

`ascii` picks a character by ink weight -- what it says is incidental. This mode inverts the
priority: the operator's text is the payload and must stay readable and in order, so tone
cannot be allowed to reorder or drop characters. Instead tone modulates SIZE. The sheet is
covered by a fixed grid of cells, exactly the way `ascii` lays out its char grid (same
`cell_darkness` over each cell's own footprint, same SHX single-stroke fonts, same
lru_cache'd glyph-polyline pattern); the difference is that a cell's darkness never changes
WHICH glyph is chosen -- the next character of `text` is always next, cycling with wraparound
so the sentence keeps flowing across row boundaries instead of restarting each row -- it only
chooses how big that glyph is drawn and, through the fixed cell pitch, how much of the cell's
own gap that size eats into.

Sizing is quantized to a handful of discrete scale levels (`_SCALE_LEVELS`) rather than a
continuous function of darkness, for the same reason `ascii`'s ramp is a fixed set of glyphs
rather than a continuous stroke-width: it keeps `_glyph_polylines` cache-friendly (bounded by
distinct characters times levels, not by every darkness value a photo can produce) and it is
what makes "same input twice" trivially exact -- no float accumulation, no sub-pixel drift.

Tight spacing at high darkness is not a second parameter: the cell pitch (`cell_w`, `cell_h`)
is fixed per render at the *unscaled* cap height, and a dark cell's glyph is simply allowed to
grow past `cap_height_mm` toward the cell's own edges -- `_GAP_FACTOR` is chosen so the
darkest scale level exactly fills the pitch (no inter-glyph gap, no overlap either) and the
lightest level fills well under half of it, which is what reads as "sparse" without a second
knob to keep in sync with the first.
"""

from __future__ import annotations

import math
from functools import lru_cache

from ...text import shx
from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

HELP = "A typed sentence, flowed across scanlines; darker cells get bigger, tighter-set type."

# A 150 mm sheet at a 1.2 mm cell pitch is already 125x125 cells; this is the same backstop
# ascii uses for MAX_ASCII_GLYPHS -- catch a small cap_height_mm on a big sheet before a
# single glyph is rendered, not partway through.
MAX_WORDART_GLYPHS = 20_000

# Digits and uppercase cover the letterforms that actually appear across SHX fonts without
# dragging in accents or punctuation whose width is not representative of a "normal" glyph --
# the same reference set `ascii._measure_aspect` uses, for the same reason.
_REFERENCE_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# How far a cell's own darkness can push its glyph away from cap_height_mm. A first version
# shipped 0.5..1.3 (a 2.6x range) because that was the widest span the contract's gradient
# passed at the time -- but rasterised against a real lit-sphere test image it read as a flat
# field of near-uniform type: the highlight and the shadow both drew nearly full-size letters,
# so the form never showed. 0.25..1.4 (5.6x) is wide enough that the lightest drawn glyph is
# visibly a small, sparse mark next to the darkest one; `_HIGHLIGHT_CUTOFF` below is what keeps
# it inside the monotonic contract at that width (see wordart()'s docstring for the measured
# gradient buckets with both changes in place).
_MIN_SCALE = 0.25
_MAX_SCALE = 1.4

# Below this, a stroke font stops reading as a letterform at a 0.3 mm nib -- the same floor
# ascii's quality_params documents, applied here to the SMALLEST glyph a dark-enough cell can
# still produce after _MIN_SCALE shrinks it, not to cap_height_mm itself (quality_params
# already floors that for the cell grid as a whole).
_MIN_CAP_HEIGHT_MM = 1.2

# Discrete sizes between _MIN_SCALE and _MAX_SCALE. Six levels is enough steps to read as
# continuous tone at normal viewing distance while keeping _glyph_polylines's cache bounded by
# (distinct characters in `text`) x 6, not by every darkness value a photo can produce.
_SCALE_LEVELS = 6

# The darkest scale level exactly fills the cell pitch (glyph_w == cell_w at _MAX_SCALE), so
# cells never overlap; the lightest level then covers _MIN_SCALE / _MAX_SCALE =~ 18% of the
# pitch, which is what reads as "sparse, small type" against the packed dark cells.
_GAP_FACTOR = _MAX_SCALE

# Row pitch is set well above _MAX_SCALE so a lowercase descender on the widest scale level
# never reaches into the row below: SHX cap_height_mm calibrates the CAP line, not descenders,
# and a descender can add another ~0.3 of cap height beneath the baseline.
_ROW_PITCH_FACTOR = 2.0

# Bound on _ink_correction -- see that function for why it exists at all.
_MAX_INK_CORRECTION = 1.6

# The bottom slice of the STRETCHED ramp (after `_layout` maps each passing cell's own
# min..max onto 0..1, the same rescue `ascii._char_grid` applies -- a real photo's cell-mean
# darkness sits in a narrow middle band before that stretch, and without it every cell picks
# from the same few ramp levels and the render reads as flat texture regardless of scale
# range) is dropped to nothing rather than drawn as the smallest legible glyph. A sphere's lit
# highlight should read as paper, not as a field of tiny grey letters -- the contract's own
# light-grey check (a UNIFORM field, so never stretched -- see `normalized`'s spread<=0 branch)
# measures 0.157 raw darkness, so 0.08 leaves that check comfortably on the "draws something"
# side while still cutting the lightest ~8% of any genuinely stretched ramp to bare paper.
_HIGHLIGHT_CUTOFF = 0.08


def _pick_font(font: str | None) -> str:
    if font:
        return font
    fonts = shx.list_fonts()
    if not fonts:
        raise ValueError("no SHX fonts available")
    return "zzsimplex" if "zzsimplex" in fonts else fonts[0]


@lru_cache(maxsize=32)
def _measure_aspect(font: str, cap_height_mm: float) -> float:
    """Average glyph advance / cap height, the same one-shot measurement `ascii` makes.

    SHX fonts are not monospaced, but one grid needs one nominal cell width; averaging over
    digits and uppercase avoids hardcoding a font-specific constant that goes stale if the
    font file changes.
    """
    widths = []
    for character in _REFERENCE_CHARS:
        width, _ = shx.text_extents(character, font=font, cap_height_mm=cap_height_mm)
        if width > 0:
            widths.append(width)
    if not widths:
        return 0.6
    return (sum(widths) / len(widths)) / cap_height_mm


@lru_cache(maxsize=4096)
def _glyph_polylines(character: str, font: str, cap_height_mm: float) -> tuple[tuple[tuple[float, float], ...], ...]:
    """One character's stroke polylines at one of the quantized sizes, cached by the triple
    that determines its shape -- see the module docstring for why the size is quantized."""
    polylines = shx.text_polylines(character, font=font, cap_height_mm=cap_height_mm, origin=(0.0, 0.0))
    return tuple(tuple(point for point in polyline) for polyline in polylines)


def _polyline_length(points: tuple[tuple[float, float], ...]) -> float:
    return sum(math.dist(points[index], points[index + 1]) for index in range(len(points) - 1))


@lru_cache(maxsize=1024)
def _reference_ink(character: str, font: str, cap_height_mm: float) -> float:
    """One character's own measured ink at cap_height_mm -- what `_layout` corrects against.

    A letter is not a uniform ink source: at the same cap height 'L' measures ~6.3 mm of
    stroke and 'R' ~12.9 mm on zzsimplex (measured for this module's default text), close to
    the whole 0.5x..1.3x range `_scale_levels` spans for TONE alone. Left uncorrected, which
    specific letters a cell happens to draw would rival or beat tone as the thing that decides
    how much ink lands there -- the exact trap the mode contract's monotonic check is built to
    catch, and it does: an early version of this mode, scaling every character by the same
    tone-only factor, put a bucket with a heavy 'R'+'A' pair at 1.6x its neighbour. Dividing
    the tone-driven scale by (this character's ink / a baseline ink, see `_ink_correction`)
    is what keeps a cell's OUTPUT ink tracking its tone, whichever letter lands there.
    """
    return sum(_polyline_length(polyline) for polyline in _glyph_polylines(character, font, cap_height_mm))


@lru_cache(maxsize=32)
def _baseline_ink(font: str, cap_height_mm: float) -> float:
    """Median ink of the reference alphabet at cap_height_mm -- the "typical letter" `_layout`
    corrects every actual glyph against. Median, not mean, so one unusually heavy or light
    reference glyph cannot shift the baseline every other letter is measured relative to.
    """
    inks = sorted(ink for character in _REFERENCE_CHARS if (ink := _reference_ink(character, font, cap_height_mm)) > 0)
    if not inks:
        return 1.0
    middle = len(inks) // 2
    if len(inks) % 2:
        return inks[middle]
    return (inks[middle - 1] + inks[middle]) / 2.0


def _ink_correction(character: str, font: str, cap_height_mm: float) -> float:
    """How much to shrink or grow a specific glyph so its ink matches the baseline letter's.

    Clamped to [1/_MAX_INK_CORRECTION, _MAX_INK_CORRECTION] so a genuinely sparse glyph (a
    thin '1', a stroke-light font) is nudged toward the baseline rather than blown up trying
    to fully match a much heavier one -- the correction's job is to flatten ordinary
    letter-to-letter variance, not to force every glyph to carry identical ink regardless of
    shape. A character with no ink at all (a space) has nothing to correct; it returns 1.0 and
    stays at zero ink, same as gating -- that is why the default text (see wordart's
    docstring) has no bare space in it at this mode's default size.
    """
    character_ink = _reference_ink(character, font, cap_height_mm)
    if character_ink <= 0:
        return 1.0
    baseline = _baseline_ink(font, cap_height_mm)
    return min(_MAX_INK_CORRECTION, max(1.0 / _MAX_INK_CORRECTION, baseline / character_ink))


def _scale_levels() -> tuple[float, ...]:
    if _SCALE_LEVELS == 1:
        return (_MIN_SCALE,)
    step = (_MAX_SCALE - _MIN_SCALE) / (_SCALE_LEVELS - 1)
    return tuple(_MIN_SCALE + index * step for index in range(_SCALE_LEVELS))


def _layout(
    tone: ToneGrid,
    cell_w: float,
    cell_h: float,
    text: str,
    min_darkness: float,
) -> list[list[tuple[str, float] | None]]:
    """The character and size scale chosen per cell, row-major, geometry-free.

    `text` is consumed by grid position alone -- row 0 left to right, then row 1, and so on --
    never by darkness, which is what keeps the sentence in order and flowing continuously
    across row boundaries: cell (row, col) always gets text[(row * cols + col) % len(text)],
    whether or not that cell ends up gated. A gated cell (below min_darkness, or below
    `_HIGHLIGHT_CUTOFF` once stretched -- see below) is recorded as None and draws nothing, but
    the character index still advances past it, exactly as it would past a drawn cell, so
    nothing downstream ever repeats or skips ahead of `text`.

    Sizing stretches the PASSING cells' own min..max onto 0..1 before mapping onto a scale
    level, the same rescue `ascii._char_grid` applies and for the same reason: a real photo's
    cell-mean darkness sits in a narrow middle band (area-averaging compresses it before this
    function ever sees it), so an unstretched value would pick from only the middle few of
    `_scale_levels` for most of the frame and the render would read as flat texture no matter
    how wide `_MIN_SCALE`..`_MAX_SCALE` is. Cells at the very bottom of that stretched range
    are then gated a second time by `_HIGHLIGHT_CUTOFF`, past min_darkness: a highlight should
    read as bare paper, not as the smallest size level still drawing a tiny letter.

    Kept separate from rendering so a test can assert the character sequence directly against
    `text`, without rendering a single glyph or reading pixels back out of a raster.
    """
    rows = max(1, int(tone.height_mm / cell_h))
    cols = max(1, int(tone.width_mm / cell_w))
    raw: list[list[float]] = []
    for row in range(rows):
        y0 = row * cell_h
        y1 = min(y0 + cell_h, tone.height_mm)
        raw.append(
            [
                cell_darkness(
                    tone.darkness,
                    col * cell_w,
                    y0,
                    min(col * cell_w + cell_w, tone.width_mm),
                    y1,
                    tone.width_mm,
                    tone.height_mm,
                )
                for col in range(cols)
            ]
        )
    passing = [value for line in raw for value in line if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    def normalized(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    levels = _scale_levels()
    grid: list[list[tuple[str, float] | None]] = []
    index = 0
    for row in range(rows):
        line: list[tuple[str, float] | None] = []
        for col in range(cols):
            character = text[index % len(text)]
            index += 1
            value = raw[row][col]
            if value < min_darkness:
                line.append(None)
                continue
            fraction = min(1.0, max(0.0, normalized(value)))
            if fraction < _HIGHLIGHT_CUTOFF:
                line.append(None)
                continue
            level_index = round(fraction * (len(levels) - 1))
            line.append((character, levels[level_index]))
        grid.append(line)
    return grid


def _place_glyph(
    glyph: tuple[tuple[tuple[float, float], ...], ...],
    cell_x0: float,
    cell_y0: float,
    cell_w: float,
    cell_h: float,
) -> list[list[tuple[float, float]]]:
    """Center a cached glyph on its cell. Unlike ascii's `_place_glyph`, this never shrinks a
    glyph back down to fit -- a glyph spilling past its own cell edges into the cell's own
    gap IS the "tighter spacing" a dark cell is supposed to produce (see module docstring);
    `_GAP_FACTOR` is what keeps that spill from ever reaching the NEXT cell's glyph instead.
    """
    if not glyph:
        return []
    xs = [x for polyline in glyph for x, _ in polyline]
    ys = [y for polyline in glyph for _, y in polyline]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    glyph_w, glyph_h = max_x - min_x, max_y - min_y
    offset_x = cell_x0 + (cell_w - glyph_w) / 2.0 - min_x
    offset_y = cell_y0 + (cell_h - glyph_h) / 2.0 - min_y
    return [[(offset_x + x, offset_y + y) for x, y in polyline] for polyline in glyph]


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Smaller cap heights at higher quality: cap_height_mm tracks the fader's spacing.

    1.6x reproduces this module's own default (spacing 2.5 -> cap_height 4.0, the signature's
    default) at draft and keeps every finer step legible: spacing 1.0 -> 1.6 mm, still above
    the 1.5 mm floor below. The floor itself stops the finest step asking for cells smaller
    than a 0.3 mm nib can resolve into a recognisable letterform -- the same number ascii's
    quality_params documents, since it is a property of the pen and the font, not this mode.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"cap_height_mm": max(1.5, spacing_mm * 1.6)}


def wordart(
    tone: ToneGrid,
    *,
    text: str = "NEJEORACLE",
    cap_height_mm: float = 4.0,
    min_darkness: float = 0.05,
    font: str | None = None,
    max_glyphs: int = MAX_WORDART_GLYPHS,
) -> Polylines:
    """Flow `text` left to right across a fixed grid of cap_height_mm cells, cycling with
    wraparound, sized per cell by that cell's own tone.

    Order and readability are the point of this mode (unlike `ascii`, which is free to reorder
    characters by ink), so `text` is never reordered, filtered by content, or restarted per
    row -- `_layout` walks the grid row-major and hands out the next character of `text` to
    every cell in turn, drawn or not. Only SIZE follows tone: a cell's own darkness
    (`cell_darkness` over that cell's footprint, the same area-averaged measurement every tone
    mode here uses) picks one of `_SCALE_LEVELS` discrete scales between `_MIN_SCALE` and
    `_MAX_SCALE`, then `_ink_correction` nudges that scale by how heavy or light THIS specific
    letter naturally is, and the glyph is rendered directly at the corrected cap height -- not
    drawn at one size and scaled after -- so its measured ink genuinely grows with the size,
    which is what the monotonic-ink contract checks.

    Measured on the contract's 80x20 mm darkness gradient at cap_height_mm=4.0 (16 columns, 2
    rows -- only ~2 cells per 10 mm bucket): without `_ink_correction`, a heavy 'R'+'A' bucket
    measured 1.6x a neighbouring 'space'+'O' bucket, over the contract's 1.15x tolerance --
    letter identity, not tone, was deciding bucket ink. Correcting each glyph toward the
    reference alphabet's median ink brought every adjacent pair under 1.10x. The one thing
    correction cannot fix is a literal space (zero ink stays zero whatever it is multiplied
    by), which is why the default text above has none: at this mode's default, legible size a
    canvas this small only fits ~2 letters per bucket, too few for one blank cell to average
    out. A caller's own longer text, or a larger sheet, dilutes that same space across many
    more cells and stops being a risk at all.

    Gated like every tone mode: a cell darker than min_darkness draws nothing, so white paper
    stays white paper.
    """
    if cap_height_mm <= 0:
        raise ValueError("cap_height_mm must be positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if max_glyphs <= 0:
        raise ValueError("max_glyphs must be positive")
    if not text:
        raise ValueError("text must be non-empty")

    resolved_font = _pick_font(font)
    aspect = _measure_aspect(resolved_font, cap_height_mm)
    cell_w = cap_height_mm * aspect * _GAP_FACTOR
    cell_h = cap_height_mm * _ROW_PITCH_FACTOR
    if cell_w <= 0:
        raise ValueError("resolved cell width must be positive")

    cols = max(1, int(tone.width_mm / cell_w))
    rows = max(1, int(tone.height_mm / cell_h))
    if cols * rows > max_glyphs:
        raise ValueError(
            f"wordart would place {cols * rows} glyph cells, exceeding max_glyphs={max_glyphs}; "
            "increase cap_height_mm or reduce the drawing size"
        )

    grid = _layout(tone, cell_w, cell_h, text, min_darkness)
    polylines: Polylines = []
    for row, line in enumerate(grid):
        y0 = row * cell_h
        for col, cell in enumerate(line):
            if cell is None:
                continue
            character, scale = cell
            corrected_scale = scale * _ink_correction(character, resolved_font, cap_height_mm)
            effective_cap_height = max(_MIN_CAP_HEIGHT_MM, cap_height_mm * corrected_scale)
            glyph = _glyph_polylines(character, resolved_font, effective_cap_height)
            if not glyph:
                continue
            x0 = col * cell_w
            for stroke in _place_glyph(glyph, x0, y0, cell_w, cell_h):
                if len(stroke) >= 2:
                    polylines.append([_clip_point(point, tone.width_mm, tone.height_mm) for point in stroke])
    return polylines
