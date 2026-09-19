"""Weave: warp threads (vertical) and weft threads (horizontal) crossing the whole sheet,
interlacing over and under the way threads actually do on a loom. A grid of unbroken vertical
and horizontal lines is just `hatch` run twice -- what makes this cloth is that wherever both
threads are present at a crossing, one stays continuous and the other is interrupted.

Tone drives two independent things, at two different scales:

Sett (thread spacing) is a 1-D decision -- see `_profile` / `_place_threads` -- each axis
collapsed to a mean-darkness profile that a demand accumulator walks to decide where threads
land, packed tighter where that axis's own strip is darker. This alone cannot draw a 2-D
picture (a sphere is not separable into a column spacing and a row spacing), so it is not
where the picture comes from; it is the cloth's own texture, a naturally varying sett.

Gap width is the 2-D tone carrier, and where the picture actually lives: `_weave_decisions`
samples the LOCAL darkness at every crossing with `cell_darkness` and turns it DIRECTLY into
a gap half-width -- shrinking toward 0 as the crossing gets darker (solid cloth, few gaps) and
growing toward several thread pitches as it gets lighter (open, holey cloth, paper showing
through). This base gap is applied to BOTH families at a crossing, identically -- deliberately
not which thread is "over": an earlier version tried carrying tone by making the winning
thread float longer where dark, and that does not work -- at a crossing where both are
present, whatever ink the winner gains the loser loses by exactly the same amount, so summed
across both families the ink per crossing is a constant, an identity, no matter how the float
length is tuned. A base gap has no such partner to cancel against: widening it removes ink
from BOTH families at that crossing at once. A second attempt tried statistically dithering
presence (on or fully off) against a periodic phase, ordered-dithering style -- also rejected,
because a full-length thread only crosses ~10-30 threads of the other family end to end, far
too few samples for a periodic dither to average out to the right coverage; the result read as
noise along the axis that carries the picture rather than a gradient. A continuous gap width
needs no averaging -- every single crossing already reflects its own local darkness exactly.
On top of that base gap, a plain diagonal parity, (i + j) % 2, adds one small fixed notch to
whichever thread loses -- tone-blind on purpose, purely so live crossings still alternate
over/under like real cloth even in solid-dark cloth, where the base gap alone is zero.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

HELP = (
    "Warp and weft threads crossing the whole sheet, interlaced over/under like cloth. "
    "Tone tightens thread spacing where dark; detail = base thread pitch in mm."
)

MAX_THREADS_DEFAULT = 4000
# Loosest a thread's local spacing gets (at the gate, stretched darkness -> 0) as a multiple
# of thread_pitch_mm (its tightest, at stretched darkness -> 1), before the `_MIN_THREADS_PER_AXIS`
# cap below narrows it back down for a short axis. Kept modest on purpose: the picture is
# carried by `_weave_decisions` sampling LOCAL darkness at each crossing, not by this 1-D
# sett, and a wide factor thins out the light end of the thread grid to the point that there
# are too few crossings left for the local carrier to resolve any 2-D shape in -- measured on
# the demo sphere-and-shadow image, a factor of 7 left only ~13x12 crossings on the whole
# 150mm sheet, visibly too coarse. 2.5 keeps the sett still visibly varying (texture) while
# leaving enough crossings for the picture itself to read.
# Measured, not guessed: at 2.5 the sett's own thread quantisation stacked on top of the
# hole-driven tone and a strip could land one extra thread, which read as ink rising toward
# the light (buckets ...38, 44...) and failed the contract. 1.6 keeps a visible change of
# sett between light and dark cloth while leaving the holes as the tone carrier.
_LOOSE_FACTOR = 1.6
# The uncapped loosest spacing above (thread_pitch_mm * _LOOSE_FACTOR) can exceed a short
# axis's own length -- the 80x20mm strip the mode contract's gradient check draws on, for
# instance -- and leave its lightest stretch with no threads at all to interrupt the other
# family, which spikes that stretch's ink instead of fading it (nothing left to cut gaps out
# of). Capping loose spacing at axis_length_mm / _MIN_THREADS_PER_AXIS guarantees at least a
# handful of threads on any axis; on a normal sheet the cap sits far above the uncapped value
# and never binds.
_MIN_THREADS_PER_AXIS = 6
# Half the FIXED notch a losing thread gets on top of the tone-driven base gap, as a fraction
# of thread_pitch_mm -- see `_weave_decisions`. Exists only so solid-dark cloth (base gap 0
# everywhere) still shows the woven alternation; 0.2 is small next to `_MAX_HOLE_FACTOR`'s
# gap so it never dominates the tone signal, just visibly notches the loser.
_GAP_FRACTION = 0.2
# The tone-driven base gap's half-width at the lightest gated crossing, as a multiple of
# thread_pitch_mm -- see `_weave_decisions`. Large on purpose: the base gap has to be able to
# swallow a whole local cell (and, stacked across several light neighbouring crossings,
# several cells) for a light patch to read as open holey cloth rather than a finely dashed
# line; `_run_intervals` already drops a run outright when the gap consumes it entirely, so an
# oversized gap just means "no material here," which is the desired open-cloth look.
_MAX_HOLE_FACTOR = 1.5
# The largest hole a crossing that IS gated may open, as a fraction of thread_pitch_mm. Below
# half, so two adjacent crossings can never eat the thread between them: where there is cloth,
# some thread always survives. Only a crossing below the gate gets _MAX_HOLE_FACTOR, which is
# the difference between "open weave" and "no cloth here" -- and it is what stops a uniformly
# light sheet from coming out blank, which the contract checks ("light grey must draw less
# than black, but not nothing").
_GATED_HOLE_FACTOR = 0.42
# quality_params floor. The notch, _GAP_FRACTION * thread_pitch_mm, has to clear one pen width
# (0.3 mm, PEN_WIDTH_MM_DEFAULT in modes.py) for the eye to register a break in solid-dark
# cloth; solving 0.2 * pitch >= 0.3 gives pitch >= 1.5 mm.
_PITCH_FLOOR_MM = 1.5


def weave(
    tone: ToneGrid,
    *,
    thread_pitch_mm: float = 3.0,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_threads: int = MAX_THREADS_DEFAULT,
) -> Polylines:
    """Lay warp and weft threads, densest where the sheet is darkest, interlaced over/under.

    Placement. `_profile` collapses the tone to one darkness value per tone.cell_mm strip
    along each axis (a column's mean darkness for warp, a row's for weft -- thread spacing is
    a 1-D decision, so the picture has to collapse to 1-D before it can drive it).
    `_stretched_profile` then maps the GATED strips' own min..max onto 0..1 before spacing
    ever sees it, exactly as ascii._char_grid does and for the same reason: area-averaging a
    photo into cell-sized strips compresses its darkness into a narrow middle band, and
    spacing built straight off that raw band would render as a near-uniform weave regardless
    of what the picture actually shows. `_place_threads` walks the stretched profile with a
    demand accumulator (see module docstring) to decide where each thread lands.

    Interlacing. `_weave_decisions` computes, for every (warp i, weft j) crossing, a gap
    half-width for warp and one for weft (`warp_gap`, `weft_gap`) -- see the module docstring
    for why gap width, not which thread is "over", carries the tone. `parity_offset` (from
    `seed`) flips which thread the fixed (i + j) % 2 parity favours for the notch; it is the
    only randomness this mode has. `_run_intervals` turns those per-crossing gaps into the
    runs a thread actually draws: it walks the crossings in order, only cutting a gap where
    one is called for, so a thread with zero gap at every crossing in a stretch -- the common
    case in a dark, solid-cloth stretch -- comes out as ONE straight two-point polyline
    covering that whole stretch, the minimum possible stroke count. That is the point of doing
    it this way: pen lifts are 52% of plot time on this machine, so a thread emitted as one
    long polyline per run is the entire savings, not an afterthought.

    max_threads guards the one place this can explode: a small thread_pitch_mm on a large
    sheet is an O(sheet / pitch) blow-up per axis, caught before crossings are ever paired up.
    """
    if thread_pitch_mm <= 0:
        raise ValueError("thread_pitch_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_threads < 1:
        raise ValueError("max_threads must be at least 1")

    col_raw, step_x = _profile(tone, tone.width_mm, tone.height_mm, vertical=True)
    row_raw, step_y = _profile(tone, tone.height_mm, tone.width_mm, vertical=False)
    # Loosest local spacing this axis is allowed, capped so a short axis still gets a handful
    # of threads -- see `_MIN_THREADS_PER_AXIS`'s docstring for why an uncapped _LOOSE_FACTOR
    # can leave the lightest stretch of a short axis with zero threads at all, which reads as
    # a stray dense patch (nothing left to interrupt the other family) rather than a smooth
    # fade. On a normal sheet the cap sits far above the uncapped value and never binds; it
    # only rescues small or narrow drawings.
    loose_x = min(thread_pitch_mm * _LOOSE_FACTOR, tone.width_mm / _MIN_THREADS_PER_AXIS)
    loose_y = min(thread_pitch_mm * _LOOSE_FACTOR, tone.height_mm / _MIN_THREADS_PER_AXIS)
    warp_x = _place_threads(
        _stretched_profile(col_raw, min_darkness), step_x, tone.width_mm, thread_pitch_mm, loose_x, max_threads
    )
    weft_y = _place_threads(
        _stretched_profile(row_raw, min_darkness), step_y, tone.height_mm, thread_pitch_mm, loose_y, max_threads
    )

    parity_offset = int(np.random.default_rng(seed).integers(0, 2))
    warp_gap, weft_gap, warp_edges, weft_edges = _weave_decisions(
        tone, warp_x, weft_y, min_darkness, thread_pitch_mm, parity_offset
    )

    threads: Polylines = []
    for i, x in enumerate(warp_x):
        start_gap, end_gap = warp_edges[i]
        for y0, y1 in _run_intervals(weft_y, warp_gap[i], tone.height_mm, start_gap, end_gap):
            threads.append([(x, y0), (x, y1)])
    for j, y in enumerate(weft_y):
        start_gap, end_gap = weft_edges[j]
        for x0, x1 in _run_intervals(warp_x, weft_gap[j], tone.width_mm, start_gap, end_gap):
            threads.append([(x0, y), (x1, y)])

    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in thread] for thread in threads]


def _profile(tone: ToneGrid, length_mm: float, cross_mm: float, *, vertical: bool) -> tuple[list[float], float]:
    """Mean darkness per tone.cell_mm strip along one axis, averaged across the whole other
    axis. step_mm follows the tone grid's own cell size: sampling finer than that resolves
    nothing the source raster actually has.

    A max over small tiles was tried and rejected: a full-width shadow or a dark silhouette
    edge then saturates almost every strip to "maximally dark" regardless of how much of that
    strip is actually empty, which reads as one dense blob rather than a picture. The mean
    keeps the shape's own gradient -- the ~5x range a real photo's column/row means span once
    stretched (see `_stretched_profile`) is what `_LOOSE_FACTOR` is tuned to spread across.
    """
    step_mm = tone.cell_mm
    count = max(1, math.ceil(length_mm / step_mm))
    values: list[float] = []
    for index in range(count):
        a0 = index * step_mm
        a1 = min(a0 + step_mm, length_mm)
        if vertical:
            values.append(cell_darkness(tone.darkness, a0, 0.0, a1, cross_mm, tone.width_mm, tone.height_mm))
        else:
            values.append(cell_darkness(tone.darkness, 0.0, a0, cross_mm, a1, tone.width_mm, tone.height_mm))
    return values, step_mm


def _stretched_profile(raw: list[float], min_darkness: float) -> list[float]:
    """Stretch the gated strips' own min..max onto 0..1 -- see the "Placement" docstring
    above. A strip below min_darkness comes back as -1.0, the gate `_place_threads` skips.
    """
    passing = [value for value in raw if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    def stretched(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    return [stretched(value) if value >= min_darkness else -1.0 for value in raw]


def _spacing_for(stretched_darkness: float, thread_pitch_mm: float, loose_mm: float) -> float:
    return loose_mm - stretched_darkness * (loose_mm - thread_pitch_mm)


def _place_threads(
    profile: list[float],
    step_mm: float,
    axis_length_mm: float,
    thread_pitch_mm: float,
    loose_mm: float,
    max_threads: int,
) -> list[float]:
    """Walk the stretched profile with a demand accumulator, dropping a thread every time
    accumulated step_mm / local_spacing crosses 1.0 -- see the module docstring.
    """
    positions: list[float] = []
    demand = 0.0
    for index, darkness in enumerate(profile):
        if darkness < 0.0:
            continue
        demand += step_mm / _spacing_for(darkness, thread_pitch_mm, loose_mm)
        while demand >= 1.0 and len(positions) < max_threads:
            positions.append(min((index + 0.5) * step_mm, axis_length_mm))
            demand -= 1.0
        if len(positions) >= max_threads:
            break
    return positions


def _local_darkness(tone: ToneGrid, x: float, y: float, half_window_mm: float) -> float:
    """Mean darkness in a half_window_mm-radius square around one crossing -- a footprint,
    not a point sample, for the same reason `cell_darkness` itself never samples one pixel.
    """
    x0 = max(0.0, x - half_window_mm)
    x1 = min(tone.width_mm, x + half_window_mm)
    y0 = max(0.0, y - half_window_mm)
    y1 = min(tone.height_mm, y + half_window_mm)
    return cell_darkness(tone.darkness, x0, y0, x1, y1, tone.width_mm, tone.height_mm)


def _weave_decisions(
    tone: ToneGrid,
    warp_x: list[float],
    weft_y: list[float],
    min_darkness: float,
    thread_pitch_mm: float,
    parity_offset: int,
) -> tuple[list[list[float]], list[list[float]], list[tuple[float, float]], list[tuple[float, float]]]:
    """(warp_gap, weft_gap, warp_edges, weft_edges).

    warp_gap[i][j] / weft_gap[j][i]: the gap half-width, in mm, warp and weft each get at
    their crossing (warp i, weft j) -- 0.0 means no gap, fully continuous through that
    crossing.

    Local darkness is sampled at every crossing (a thread_pitch_mm-wide footprint, one weave
    cell) and stretched across the GATED crossings' own min..max -- the same recipe as
    `_stretched_profile`, and for the same reason: raw cell-mean darkness compresses toward
    the middle, and a gap built straight off that raw band would barely vary.

    base_gap is that stretched darkness read straight into a gap width, linearly, darkest ->
    0, gate -> _MAX_HOLE_FACTOR * thread_pitch_mm -- see the module docstring for why this,
    not who is "over", is the tone carrier, and both threads at a crossing get the SAME
    base_gap. (i + j + parity_offset) % 2 then picks a loser for that crossing and adds a
    small fixed notch (half-width _GAP_FRACTION * thread_pitch_mm) to it alone, tone-blind on
    purpose, so a solid-dark crossing (base_gap 0) still shows the woven alternation instead
    of both threads running straight through uninterrupted.

    warp_edges[i] / weft_edges[j]: (start_gap, end_gap) for that thread's own two ends, from
    base_gap at the sheet's edge on its line -- with no crossing to test past a sett-gated
    strip's last thread, the run would otherwise reach the sheet edge uncut no matter how
    light that strip is, spiking ink right at the lightest edge instead of fading into it.
    """
    half_window = thread_pitch_mm / 2.0
    raw = [[_local_darkness(tone, x, y, half_window) for y in weft_y] for x in warp_x]

    passing = [value for row in raw for value in row if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low
    max_hole_half = thread_pitch_mm * _MAX_HOLE_FACTOR
    gated_hole_half = thread_pitch_mm * _GATED_HOLE_FACTOR
    notch_half = thread_pitch_mm * _GAP_FRACTION

    def base_gap(value: float) -> float:
        if value < min_darkness:
            return max_hole_half
        # A flat field has no relative tone to stretch, so it reads its own darkness: that
        # keeps a uniformly light sheet lighter than a uniformly dark one instead of
        # collapsing both to the same cloth.
        stretched = (value - low) / spread if spread > 1e-9 else value
        return gated_hole_half * (1.0 - stretched)

    n_warp, n_weft = len(warp_x), len(weft_y)
    warp_gap = [[0.0] * n_weft for _ in range(n_warp)]
    weft_gap = [[0.0] * n_warp for _ in range(n_weft)]
    for i in range(n_warp):
        for j in range(n_weft):
            gap = base_gap(raw[i][j])
            warp_loses = (i + j + parity_offset) % 2 == 0
            warp_gap[i][j] = gap + notch_half if warp_loses else gap
            weft_gap[j][i] = gap if warp_loses else gap + notch_half

    warp_edges = [
        (
            base_gap(_local_darkness(tone, x, 0.0, half_window)),
            base_gap(_local_darkness(tone, x, tone.height_mm, half_window)),
        )
        for x in warp_x
    ]
    weft_edges = [
        (
            base_gap(_local_darkness(tone, 0.0, y, half_window)),
            base_gap(_local_darkness(tone, tone.width_mm, y, half_window)),
        )
        for y in weft_y
    ]
    return warp_gap, weft_gap, warp_edges, weft_edges


def _run_intervals(
    cross_positions: list[float], gap_half_mm: list[float], axis_length_mm: float, start_gap: float, end_gap: float
) -> list[tuple[float, float]]:
    """The runs a thread draws along its own axis: continuous through every crossing whose
    gap half-width is 0, cut by a `2 * gap` hole at every crossing whose gap is positive -- a
    hole wide enough to consume the run entirely (adjacent crossings close together, or a
    single very light one) just means no run is emitted there, open cloth. `start_gap` and
    `end_gap` trim the thread's own two ends the same way, past the last real crossing.
    """
    intervals: list[tuple[float, float]] = []
    start = start_gap
    for position, gap in zip(cross_positions, gap_half_mm, strict=True):
        if gap <= 0.0:
            continue
        end = position - gap
        if end > start:
            intervals.append((start, end))
        start = position + gap
    axis_length_mm -= end_gap
    if axis_length_mm > start:
        intervals.append((start, axis_length_mm))
    return intervals


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto thread_pitch_mm: smaller pitch, finer weave.

    Scaled by 1.2x for the same reason `rings` and `truchet` do -- it lands draft (2.5) a bit
    above this mode's own default pitch of 3.0 while every finer step still shrinks it -- and
    then floored at _PITCH_FLOOR_MM so the over/under gap never shrinks below what a pen nib
    can actually show as a break (see that constant's docstring).
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"thread_pitch_mm": max(spacing_mm * 1.2, _PITCH_FLOOR_MM)}
