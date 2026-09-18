"""Letter-density text art: cells of the source tone rendered as single-stroke characters.

Each character cell is filled with a glyph whose measured ink length best matches the cell's
mean darkness, using the repo's SHX single-stroke fonts (see ../../text/shx.py) so every glyph
is already a set of pen-plottable polylines. No new geometry is invented per pixel the way
hatch or stipple do -- the geometry is simply "which character", chosen from a ramp built by
actually rendering and measuring every candidate glyph rather than assuming their visual
weight order matches their plotted ink. .` and `,` are close in a proportional screen font but
not necessarily in a stroke font's own stroke count, so the ramp is sorted by measurement.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from functools import lru_cache

from ...text import shx
from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

# Ascending in *typical* screen weight; _build_ramp resorts this by measured ink, so this
# order is only a reasonable starting pool, never trusted for the final ramp. Measured on
# zzsimplex, ".,:;-~=+*o#%@&WM" (a more obvious first guess) leaves a cliff: 'o' measures
# 6.1 mm of ink and every symbol after it -- '#','%','@','&','W','M' -- clusters at 12.2-15.4,
# so nothing represents the whole 6.1-12.2 range and every mid-dark cell snaps straight from
# a small circle to a solid block. 'X' and 'Q' bridge that gap because the font simply has
# more letters in that ink range than symbols; they were picked by measuring candidates from
# string.punctuation + ascii_letters + digits and keeping the ones landing in the empty
# stretch, not for how they look on screen.
DEFAULT_CHARSET = ".:-~=*oXQ8#%@"

# Advance width is measured off these -- digits and uppercase cover the letterforms that
# actually appear across SHX fonts without dragging in accents or punctuation whose width
# is not representative of a "normal" character.
_REFERENCE_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# A 150 mm sheet at a 1 mm cell is already 150x150 = 22 500 cells; this is a backstop against
# a caller combining a small char_mm with a large sheet, the same shape of guard flow and
# stipple use for their own per-point loops.
MAX_ASCII_GLYPHS = 20_000

HELP = "Letter-density text art: darker cells get inkier single-stroke characters."


def _pick_font(font: str | None) -> str:
    if font:
        return font
    fonts = shx.list_fonts()
    if not fonts:
        raise ValueError("no SHX fonts available")
    return "zzsimplex" if "zzsimplex" in fonts else fonts[0]


@lru_cache(maxsize=32)
def _measure_aspect(font: str, cap_height_mm: float) -> float:
    """Average glyph advance / cap height -- a monospace-ish width for the character cell.

    SHX fonts are not actually monospaced ('i' and 'M' have different advances), but one
    grid needs one width per cell. Averaging the advance over digits and uppercase gives a
    representative figure without hardcoding a font-specific constant that would silently
    go stale if the font file changed.
    """
    widths = []
    for character in _REFERENCE_CHARS:
        width, _ = shx.text_extents(character, font=font, cap_height_mm=cap_height_mm)
        if width > 0:
            widths.append(width)
    if not widths:
        return 0.6
    return (sum(widths) / len(widths)) / cap_height_mm


@lru_cache(maxsize=1024)
def _glyph_polylines(character: str, font: str, cap_height_mm: float) -> tuple[tuple[tuple[float, float], ...], ...]:
    """One character's stroke polylines at a given size, cached by (glyph, font, size).

    Rendering a glyph is the expensive step (SHX shape parsing plus flattening); a frame at
    one char_mm reuses the same handful of glyphs across every one of its cells, so caching
    on the triple that actually determines the shape turns an O(cells) cost into O(charset).
    """
    polylines = shx.text_polylines(character, font=font, cap_height_mm=cap_height_mm, origin=(0.0, 0.0))
    return tuple(tuple(point for point in polyline) for polyline in polylines)


def _polyline_length(points: Sequence[tuple[float, float]]) -> float:
    return sum(math.dist(points[index], points[index + 1]) for index in range(len(points) - 1))


@lru_cache(maxsize=32)
def _build_ramp(font: str, cap_height_mm: float, charset: str) -> tuple[tuple[str, float], ...]:
    """Measure every candidate glyph's ink length and sort ascending; drop the empty ones.

    This is what makes `monotonic=True` a property of the render rather than a hope: darkness
    is mapped onto measured ink, not onto the charset's typed order, so a font whose '~' turns
    out inkier than its '=' does not invert the ramp -- it just moves in the sort.
    """
    seen: dict[str, None] = {}
    for character in charset:
        if character != " ":
            seen.setdefault(character, None)
    entries: list[tuple[str, float]] = []
    for character in seen:
        ink = sum(_polyline_length(polyline) for polyline in _glyph_polylines(character, font, cap_height_mm))
        if ink > 0:
            entries.append((character, ink))
    entries.sort(key=lambda entry: entry[1])
    return tuple(entries)


def _pick_glyph(ramp: tuple[tuple[str, float], ...], darkness: float) -> str | None:
    """Nearest-ink match: darkness 0..1 scaled onto the ramp's own ink range and snapped."""
    if not ramp:
        return None
    target = min(1.0, max(0.0, darkness)) * ramp[-1][1]
    inks = [ink for _, ink in ramp]
    index = bisect.bisect_left(inks, target)
    if index == 0:
        return ramp[0][0]
    if index == len(ramp):
        return ramp[-1][0]
    before, after = ramp[index - 1], ramp[index]
    return before[0] if abs(before[1] - target) <= abs(after[1] - target) else after[0]


def _char_grid(
    tone: ToneGrid,
    cell_w: float,
    cell_h: float,
    ramp: tuple[tuple[str, float], ...],
    min_darkness: float,
) -> list[list[str | None]]:
    """The character selected per cell, gated by min_darkness -- geometry-free so it is
    cheap to test on its own (see tests/test_mode_ascii.py).

    Character selection stretches the gated cells' own min..max onto the ramp before picking,
    rather than feeding raw darkness straight in. Measured on a real group photo (no per-pixel
    autocontrast, as photo_filter already handles it) at char_mm 3.0: cell-mean darkness has
    a 25th-75th percentile of only 0.45-0.58 out of the full 0-1 range -- area-averaging a
    cluttered photo into ~3x4 mm cells compresses variance before this function ever sees it
    -- so unstretched selection used only the 3 middle characters of the ramp for most of the
    frame and the render read as a flat texture. Stretching the gated cells' own range back
    onto the full ramp restores the contrast this mode is for, the same job
    ImageOps.autocontrast does at pixel level in load_tone, just applied to the coarser signal
    this function actually samples.
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

    return [[None if value < min_darkness else _pick_glyph(ramp, normalized(value)) for value in line] for line in raw]


def _place_glyph(
    character: str,
    font: str,
    cap_height_mm: float,
    cell_x0: float,
    cell_y0: float,
    cell_w: float,
    cell_h: float,
    fit: float = 0.85,
) -> list[list[tuple[float, float]]]:
    """Translate and, if needed, shrink a cached glyph so it lands centred inside its cell.

    Glyphs are cached at cap_height_mm, which sizes their height correctly by construction,
    but width is a font-and-letter matter (a 'W' is wider than an 'l' at the same cap
    height) -- so width alone gets the shrink check, and `fit` leaves a small margin so
    adjacent glyphs do not touch.
    """
    glyph = _glyph_polylines(character, font, cap_height_mm)
    if not glyph:
        return []
    xs = [x for polyline in glyph for x, _ in polyline]
    ys = [y for polyline in glyph for _, y in polyline]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    glyph_w, glyph_h = max_x - min_x, max_y - min_y
    scale = 1.0
    if glyph_w > 0:
        scale = min(scale, (cell_w * fit) / glyph_w)
    if glyph_h > 0:
        scale = min(scale, (cell_h * fit) / glyph_h)
    offset_x = cell_x0 + (cell_w - glyph_w * scale) / 2.0 - min_x * scale
    offset_y = cell_y0 + (cell_h - glyph_h * scale) / 2.0 - min_y * scale
    return [[(offset_x + x * scale, offset_y + y * scale) for x, y in polyline] for polyline in glyph]


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Smaller characters at higher quality: char_mm tracks the fader's spacing directly.

    1.5x keeps the mapping inside a plottable range across the fader's whole span (2.5 mm
    spacing -> 3.75 mm characters at draft, 1.0 mm spacing -> 1.5 mm characters at max) while
    the 1.2 mm floor stops the finest step asking for characters smaller than a 0.3 mm pen
    can resolve into a recognisable letterform.
    """
    return {"char_mm": max(1.2, spacing_mm * 1.5)}


def ascii(
    tone: ToneGrid,
    *,
    char_mm: float = 3.0,
    width_factor: float | None = None,
    font: str | None = None,
    charset: str = DEFAULT_CHARSET,
    min_darkness: float = 0.05,
    max_glyphs: int = MAX_ASCII_GLYPHS,
) -> Polylines:
    """Fill a grid of char_mm cells with the single-stroke character closest to their tone.

    The tone ramp is not assumed from the charset's typed order (`_build_ramp` measures each
    glyph's rendered ink and sorts by that), which is what keeps the mapping monotonic: a
    character that looks sparse on screen but happens to draw a long stroke in this font
    still lands in the correct place in the ramp rather than inverting it.

    Cell width comes from `width_factor` if given, else from `_measure_aspect`, which renders
    a sample of digits and uppercase letters once per (font, char_mm) and averages their
    advance width -- SHX fonts have no single documented monospace factor the way a terminal
    font does, so this measures one rather than guessing 0.6 and being wrong for every font
    that is not zzsimplex.

    Gated like every tone mode: a cell darker than min_darkness draws nothing, so white paper
    stays white paper rather than filling with the lightest glyph in the ramp.
    """
    if char_mm <= 0:
        raise ValueError("char_mm must be positive")
    if width_factor is not None and width_factor <= 0:
        raise ValueError("width_factor must be positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if max_glyphs <= 0:
        raise ValueError("max_glyphs must be positive")
    if not any(character != " " for character in charset):
        raise ValueError("charset must contain at least one non-space character")

    resolved_font = _pick_font(font)
    aspect = width_factor if width_factor is not None else _measure_aspect(resolved_font, char_mm)
    cell_w = char_mm * aspect
    cell_h = char_mm
    if cell_w <= 0:
        raise ValueError("resolved cell width must be positive; set width_factor explicitly")

    cols = max(1, int(tone.width_mm / cell_w))
    rows = max(1, int(tone.height_mm / cell_h))
    if cols * rows > max_glyphs:
        raise ValueError(
            f"ascii would place {cols * rows} glyph cells, exceeding max_glyphs={max_glyphs}; "
            "increase char_mm or reduce the drawing size"
        )

    ramp = _build_ramp(resolved_font, char_mm, charset)
    if not ramp:
        return []

    grid = _char_grid(tone, cell_w, cell_h, ramp, min_darkness)
    polylines: Polylines = []
    for row, line in enumerate(grid):
        y0 = row * cell_h
        for col, character in enumerate(line):
            if character is None:
                continue
            x0 = col * cell_w
            for stroke in _place_glyph(character, resolved_font, char_mm, x0, y0, cell_w, cell_h):
                if len(stroke) >= 2:
                    polylines.append([_clip_point(point, tone.width_mm, tone.height_mm) for point in stroke])
    return polylines
