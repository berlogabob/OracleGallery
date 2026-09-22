"""Stacked barcode: each horizontal band is a 1-D barcode of its own tone.

A barcode is a one-dimensional signal -- bar width and gap against position along one axis --
so a whole picture rendered as ONE barcode throws away everything vertical. The sheet is split
into bands instead, each band read left to right as its own barcode, which keeps the picture
two-dimensional and still reads as barcode at a glance: the bands share a baseline grid, so
the eye groups them the way it groups the rows of a stacked symbology (PDF417, Codablock).

A pen has one width, so a "thick bar" is several vertical lines side by side at pen pitch --
the same trick `halftone` uses to fill a dot past two pen widths. Darkness sets how many lines
a column's bar gets, so a black column is a solid block of ink and a light one is a single
hairline, with the unused width left as the quiet zone that makes the bars read as bars.
"""

from __future__ import annotations

from ..modes import Polylines, ToneGrid, cell_darkness

HELP = (
    "Stacked barcode: every horizontal band is a 1-D barcode of its own tone. "
    "Darker columns get wider bars, lighter ones a hairline; detail = bar pitch in mm."
)

MAX_BARS_DEFAULT = 40_000
# A bar narrower than one pen line cannot exist, so the line count is what carries tone and
# this is the pitch those lines sit at. 0.3 mm is PEN_WIDTH_MM_DEFAULT in modes.py: closer
# than the nib is ink laid on ink.
_LINE_PITCH_MM = 0.3


def barcode(
    tone: ToneGrid,
    *,
    bar_pitch_mm: float = 2.0,
    band_height_mm: float = 8.0,
    min_darkness: float = 0.12,
    max_bars: int = MAX_BARS_DEFAULT,
) -> Polylines:
    """Bands of vertical bars, bar width rising with the column's darkness.

    Each band is `band_height_mm` tall and each bar occupies `bar_pitch_mm` of width. Within
    that pitch the bar is drawn as `lines` vertical strokes at _LINE_PITCH_MM, centred, so the
    gap to the next bar shrinks as the bar thickens -- which is what a barcode does, and what
    makes a run of black columns merge into one block instead of staying a fence.

    Bars are drawn at 90% of the band height, never the full height: a 10% alley between bands
    is what keeps the stack readable as rows. Fill the alley and a dark region becomes one
    undivided rectangle, which is a black box, not a barcode.
    """
    if bar_pitch_mm <= 0 or band_height_mm <= 0:
        raise ValueError("bar_pitch_mm and band_height_mm must be positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")

    darkness = tone.darkness
    if darkness.size == 0:
        return []

    cols = max(1, int(tone.width_mm / bar_pitch_mm))
    rows = max(1, int(tone.height_mm / band_height_mm))
    # The pitch the loop actually uses, so the last bar ends exactly on the edge rather than
    # leaving a ragged strip the eye reads as a missing bar.
    pitch_x = tone.width_mm / cols
    pitch_y = tone.height_mm / rows
    max_lines = max(1, int(pitch_x / _LINE_PITCH_MM))
    bar_height = pitch_y * 0.9

    polylines: Polylines = []
    drawn = 0
    for row in range(rows):
        y0 = row * pitch_y + (pitch_y - bar_height) / 2.0
        y1 = y0 + bar_height
        for col in range(cols):
            x0 = col * pitch_x
            value = cell_darkness(darkness, x0, y0, x0 + pitch_x, y1, tone.width_mm, tone.height_mm)
            if value < min_darkness:
                continue
            lines = max(1, int(round(value * max_lines)))
            if drawn + lines > max_bars:
                return polylines
            span = (lines - 1) * _LINE_PITCH_MM
            start = x0 + (pitch_x - span) / 2.0
            for index in range(lines):
                x = min(tone.width_mm, start + index * _LINE_PITCH_MM)
                # Alternating direction costs nothing and halves the travel between bars.
                polylines.append([(x, y1), (x, y0)] if index % 2 else [(x, y0), (x, y1)])
            drawn += lines
    return polylines


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Bar pitch and band height from the quality fader.

    Both track spacing_mm and hit the defaults (2.0 / 8.0) exactly at the draft rung
    (spacing 2.5), the same convention the other art modes use. Bar pitch is floored at
    _LINE_PITCH_MM * 2 -- one line and one gap -- because below that every bar is the same
    single line and the mode stops carrying tone at all.
    """
    return {
        "bar_pitch_mm": max(_LINE_PITCH_MM * 2, spacing_mm * 0.8),
        "band_height_mm": max(3.0, spacing_mm * 3.2),
    }
