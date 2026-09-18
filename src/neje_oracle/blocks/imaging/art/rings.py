"""Concentric-circle halftone: hollow rings instead of filled dots.

Compare with modes.halftone, which fills a dot solid (optionally spiralling in) once it
grows past the pen width. This mode never fills: every dot stays a set of nested hollow
rings, so the printed sheet always carries less ink than halftone at the same darkness --
an op-art look rather than a photographic one.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _sample_darkness

# A ring-count estimate (rows * cols * max_rings) above this raises before any geometry is
# built. At a 0.3 mm pitch on a 250x440 mm bed that estimate is ~4.6M rings; nothing this
# mode draws is worth a multi-minute freeze before the caller even sees an error.
MAX_RINGS_TOTAL_DEFAULT = 120_000

HELP = (
    "Halftone dots redrawn as hollow nested rings instead of filled discs. "
    "Lighter ink than halftone, op-art look; more rings where the image is dark."
)


def rings(
    tone: ToneGrid,
    *,
    pitch_mm: float = 3.0,
    hex: bool = True,
    pen_gap_mm: float = 0.3,
    max_rings: int = 4,
    min_ring_mm: float = 0.25,
    min_darkness: float = 0.05,
    chord_mm: float = 0.3,
    max_rings_total: int = MAX_RINGS_TOTAL_DEFAULT,
) -> Polylines:
    """Halftone dots replaced by nested hollow circles, one to several per cell.

    Each cell of a pitch_mm lattice (alternate rows offset by half a pitch when hex=True,
    for the tighter packing a hex grid gives over a square one) is scored by the MEAN
    darkness over its whole footprint, not one sampled point -- a single point aliases
    against a resampled tone grid exactly the way halftone's single-point dot placement
    does, and a mean over the cell is one numpy slice, cheap enough to always do.

    Outer radius R = (pitch/2 - pen_gap_mm) * sqrt(d) matches halftone's own area-linear
    radius law, and ring count k = max(1, round(d * max_rings)) with k radii spaced evenly
    up to R (R/k, 2R/k, ..., R) is what turns a single ring into a tone: both R and k grow
    with d, so ink length (the sum of the k circumferences) rises monotonically even though
    every individual ring is thin. Checked with the shipped defaults (pitch_mm=3.0,
    pen_gap_mm=0.3, max_rings=4) at six darkness levels:

        d=0.10 -> 1 ring,  2.4 mm ink
        d=0.30 -> 1 ring,  4.1 mm ink
        d=0.50 -> 2 rings, 8.0 mm ink
        d=0.70 -> 3 rings, 12.6 mm ink
        d=0.90 -> 4 rings, 17.9 mm ink
        d=1.00 -> 4 rings, 18.8 mm ink

    A ring thinner than min_ring_mm (the pen's own width -- default 0.25 mm) is dropped
    rather than drawn, since a pen cannot resolve it as a ring at all. A ring that would
    leave the frame is dropped too, individually: a cell near the sheet edge can still draw
    its small inner rings while its outer ones fall off the paper.
    """
    if pitch_mm <= 0:
        raise ValueError("pitch_mm must be positive")
    if pen_gap_mm < 0 or pen_gap_mm >= pitch_mm / 2.0:
        raise ValueError("pen_gap_mm must be non-negative and less than pitch_mm / 2")
    if max_rings < 1:
        raise ValueError("max_rings must be at least 1")
    if min_ring_mm < 0:
        raise ValueError("min_ring_mm must be non-negative")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if chord_mm <= 0:
        raise ValueError("chord_mm must be positive")
    if max_rings_total < 1:
        raise ValueError("max_rings_total must be at least 1")

    half_pitch = pitch_mm / 2.0
    max_radius = half_pitch - pen_gap_mm

    # Upper-bound estimate of cells x max_rings, checked before any circle is walked --
    # the same fail-fast shape as stipple's and flow's pre-generation estimates.
    row_estimate = max(1, int(tone.height_mm / pitch_mm) + 1)
    col_estimate = max(1, int(tone.width_mm / pitch_mm) + 1)
    ring_estimate = row_estimate * col_estimate * max_rings
    if ring_estimate > max_rings_total:
        raise ValueError(
            f"rings would place up to {ring_estimate} rings, exceeding max_rings_total={max_rings_total}; "
            "widen pitch_mm or lower max_rings"
        )

    polylines: Polylines = []
    row_index = 0
    row_y = half_pitch
    while row_y < tone.height_mm:
        col_x = half_pitch + (half_pitch if (hex and row_index % 2) else 0.0)
        while col_x < tone.width_mm:
            darkness = _cell_mean_darkness(tone, col_x, row_y, half_pitch)
            if darkness >= min_darkness:
                polylines.extend(
                    _cell_rings(
                        col_x,
                        row_y,
                        darkness,
                        max_radius,
                        max_rings,
                        min_ring_mm,
                        chord_mm,
                        tone.width_mm,
                        tone.height_mm,
                    )
                )
            col_x += pitch_mm
        row_y += pitch_mm
        row_index += 1
    return polylines


def _cell_mean_darkness(tone: ToneGrid, cx: float, cy: float, half_pitch: float) -> float:
    """Mean darkness over a cell's footprint -- one numpy slice, not a single sample.

    Falls back to the single-point sampler only for a cell that has no area left inside the
    frame (a corner cell whose pitch is wider than the strip of frame it sits over).
    """
    rows, cols = tone.darkness.shape
    step_x = tone.width_mm / cols
    step_y = tone.height_mm / rows
    x0 = max(0.0, cx - half_pitch)
    x1 = min(tone.width_mm, cx + half_pitch)
    y0 = max(0.0, cy - half_pitch)
    y1 = min(tone.height_mm, cy + half_pitch)
    if x1 <= x0 or y1 <= y0:
        return _sample_darkness(tone, cx, cy)
    col0 = min(cols - 1, max(0, int(x0 / step_x)))
    col1 = min(cols, max(col0 + 1, math.ceil(x1 / step_x)))
    row0 = min(rows - 1, max(0, int(y0 / step_y)))
    row1 = min(rows, max(row0 + 1, math.ceil(y1 / step_y)))
    return float(np.mean(tone.darkness[row0:row1, col0:col1]))


def _cell_rings(
    cx: float,
    cy: float,
    darkness: float,
    max_radius: float,
    max_rings: int,
    min_ring_mm: float,
    chord_mm: float,
    width_mm: float,
    height_mm: float,
) -> Polylines:
    """The k nested rings for one cell, inside-out, skipping any too small or off-sheet."""
    if max_radius <= 0:
        return []
    outer_radius = max_radius * math.sqrt(darkness)
    ring_count = max(1, round(darkness * max_rings))
    polylines: Polylines = []
    for index in range(ring_count):
        radius = outer_radius * (index + 1) / ring_count
        if radius < min_ring_mm:
            continue
        if cx - radius < 0.0 or cx + radius > width_mm or cy - radius < 0.0 or cy + radius > height_mm:
            continue
        polylines.append(_circle_polyline(cx, cy, radius, chord_mm))
    return polylines


def _circle_polyline(cx: float, cy: float, radius: float, chord_mm: float) -> list[tuple[float, float]]:
    """A closed ring, sampled at ~chord_mm arc length with at least 12 points."""
    circumference = math.tau * radius
    steps = max(12, round(circumference / chord_mm))
    points = [
        (cx + radius * math.cos(math.tau * index / steps), cy + radius * math.sin(math.tau * index / steps))
        for index in range(steps)
    ]
    points.append(points[0])
    return points


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the shared quality fader onto this mode's grid pitch.

    The fader's spacing ladder is 2.5 (draft) down to 1.0 (max); this mode's own natural
    pitch sits a bit wider, so spacing is scaled by 1.2 rather than used directly -- that
    lands draft on the function's own default pitch_mm=3.0 (spacing 2.5 * 1.2) while still
    shrinking, and thus adding detail, at every finer step.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"pitch_mm": spacing_mm * 1.2}
