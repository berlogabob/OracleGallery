"""String art: the picture built from straight chords between pins around the frame.

Pins sit on the largest ELLIPSE the sheet holds, which is a circle on a square sheet and the
inscribed ellipse on any other. A true circle would be right for a round loom and wrong for
paper: on a 2:1 frame it covers a third of the sheet and leaves two bare quarters, and the
half of the picture outside it is simply never drawn. A chord is chosen greedily -- from the current
pin, the candidate whose line crosses the most remaining darkness wins -- and the darkness it
crosses is then subtracted, so the next chord has to find ink somewhere else. That subtraction
is the whole algorithm: without it every chord converges on the same darkest diameter and the
picture never appears.

Chords are drawn as one continuous polyline, pin to pin to pin, which is what real string art
is: a single thread. The plotter gets one stroke and no pen lifts at all, making this the
cheapest mode in the set to actually draw, whatever its segment count says.

What it will not do, and why: a screen-based string portrait lays thousands of near-transparent
threads, and its whole tonal range comes from how many overlap. A pen has one opacity, so a
chord is either there at full strength or not, and a large mid-grey mass -- a face filling the
frame -- has no rendering in straight full-length lines except a dark tangle. This mode is for
high-contrast subjects with the dark kept small; gamma above 1 or Enhance = photo is the knob
that gets a portrait there, and the mode is honest about the rest.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid

HELP = (
    "One thread wound between pins around the frame, each chord laid where the picture is "
    "darkest. One continuous stroke, no pen lifts. Wants contrast: raise gamma if it fills in."
)

MAX_CHORDS_DEFAULT = 4_000
# Samples per chord when measuring and when subtracting. The chord is scored on the tone
# raster, so sampling finer than its cells buys nothing.
_SAMPLES_PER_CELL = 1.2
# How much darkness one pass of thread removes from the cells it crosses, absolute rather than
# a fraction of what is there. A fractional subtraction is the obvious version and it stalls:
# it can never take a cell to zero, so the residual field decays towards the gate everywhere at
# once and the thread stops after ~200 chords whatever the picture holds. An absolute bite
# means a black region supports 1/_THREAD_INK passes and paper supports none, so chord count
# follows how much ink the picture actually asks for.
_THREAD_INK = 0.28
# Chords shorter than this fraction of the diameter are skipped: neighbouring pins produce a
# sliver that adds ink at the rim and carries no picture.
_MIN_CHORD_FRACTION = 0.22


def _pins(count: int, cx: float, cy: float, rx: float, ry: float) -> list[tuple[float, float]]:
    return [
        (cx + rx * math.cos(2.0 * math.pi * i / count), cy + ry * math.sin(2.0 * math.pi * i / count))
        for i in range(count)
    ]


def stringart(
    tone: ToneGrid,
    *,
    pins: int = 180,
    chords: int = 900,
    min_darkness: float = 0.08,
    max_chords: int = MAX_CHORDS_DEFAULT,
) -> Polylines:
    """Wind one thread between `pins` pins, `chords` times, following the darkest path.

    Returns a single polyline of `chords` + 1 points, or nothing at all when no chord can find
    darkness above `min_darkness` -- the white-paper gate. The greedy search is O(pins) per
    chord with a fixed sample count, so cost is chords * pins * samples and the caps are what
    keep a 200 mm sheet inside the perf budget.
    """
    if pins < 8 or chords <= 0:
        raise ValueError("pins must be at least 8 and chords positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")

    if tone.darkness.size == 0:
        return []

    rows, cols = tone.darkness.shape
    remaining = tone.darkness.astype(np.float64).copy()
    cx, cy = tone.width_mm / 2.0, tone.height_mm / 2.0
    pin_points = _pins(pins, cx, cy, cx, cy)
    span = max(tone.width_mm, tone.height_mm)
    samples = max(8, int(span / max(tone.cell_mm, 1e-6) * _SAMPLES_PER_CELL))
    # Measured against the SHORT axis: on a wide frame the short axis is what a "too short to
    # carry picture" chord is short against, and scaling the floor by the long one would throw
    # away every vertical chord on the sheet.
    min_length = 2.0 * min(cx, cy) * _MIN_CHORD_FRACTION
    steps = np.linspace(0.0, 1.0, samples)

    def indices(a: tuple[float, float], b: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
        xs = a[0] + (b[0] - a[0]) * steps
        ys = a[1] + (b[1] - a[1]) * steps
        col = np.clip((xs * cols / tone.width_mm).astype(int), 0, cols - 1)
        row = np.clip((ys * rows / tone.height_mm).astype(int), 0, rows - 1)
        return row, col

    thread: list[tuple[float, float]] = []
    current = 0
    for _ in range(min(chords, max_chords)):
        best_score, best_pin, best_index = 0.0, -1, None
        for candidate in range(pins):
            if candidate == current:
                continue
            start, end = pin_points[current], pin_points[candidate]
            if math.dist(start, end) < min_length:
                continue
            row, col = indices(start, end)
            score = float(remaining[row, col].mean())
            if score > best_score:
                best_score, best_pin, best_index = score, candidate, (row, col)
        if best_pin < 0 or best_score < min_darkness or best_index is None:
            break
        row, col = best_index
        # np.minimum.at, not remaining[row, col] -= ...: a chord crosses the same cell more
        # than once at these sample rates, and fancy-index assignment would apply the
        # subtraction once, leaving the cell darker than the thread already made it. Taking
        # the minimum of the reduced value is idempotent, so a repeated cell costs one bite.
        np.minimum.at(remaining, (row, col), remaining[row, col] - _THREAD_INK)
        np.clip(remaining, 0.0, None, out=remaining)
        if not thread:
            thread.append(pin_points[current])
        thread.append(pin_points[best_pin])
        current = best_pin
    return [thread] if len(thread) >= 2 else []


def quality_params(spacing_mm: float) -> dict[str, int]:
    """Pins and chords from the quality fader.

    Both rise as spacing falls and reproduce the defaults (180 / 900) at the draft rung
    (spacing 2.5). Chords are capped at MAX_CHORDS_DEFAULT: past a few thousand the thread
    stops adding picture and starts filling the disc grey, and the greedy search is linear in
    pins per chord, so the two together are what the perf budget actually sees.
    """
    factor = 2.5 / max(0.5, spacing_mm)
    return {"pins": int(min(400, 180 * factor**0.6)), "chords": int(min(MAX_CHORDS_DEFAULT, 900 * factor**1.2))}
