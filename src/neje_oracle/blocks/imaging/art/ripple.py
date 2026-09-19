"""Water rings: one family of concentric circles around a focus, pushed by the tone they cross.

Unlike `rings` (independent hollow circles, one nest per lattice cell) this is a SINGLE global
family -- ring k sits at radius k * ring_spacing_mm from one focus, covering the whole sheet,
and every ring is one continuous polyline. Tone is not carried by the bare lattice: an
Archimedean/circular family spaced evenly has constant ink length per unit area regardless of k
(circumference / (2*pi*r*spacing) = 1/spacing for every r), the same baseline `spiral` starts
from and the same reason `spiral` cannot carry tone on its smooth path alone either. Tone comes
from two effects layered on top, both driven by the sampled darkness at each ring point: gating
drops a ring's arc entirely below min_darkness (a dark blob near the centre and nothing else
means most rings only draw a short arc, not a full circle), and a radial wobble, pushed IN AND
OUT by a sine tied to arc length, whose amplitude and frequency both rise with darkness exactly
as `spiral`'s own wobble does -- a smooth single-direction bulge barely lengthens a curve that is
already smooth, but a faster, deeper wiggle measurably does, which is what actually buys the
tonal range a flat push cannot. Because every ring samples the SAME darkness field, rings that
pass near a dark region wobble at close to the same phase and depth, so their spacing visibly
compresses where the on-page darkness is high and relaxes where it is not -- the bunch-and-bulge
water-ring look, riding on top of the concentric lattice rather than replacing it.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _sample_darkness

HELP = (
    "Concentric rings from one focus, water-ripple style. Darker tone pushes a ring's "
    "radius outward and holds its arc; light tone below min_darkness lifts the pen."
)

MAX_POINTS_DEFAULT = 400_000
_CHORD_MM = 0.3  # matches the plotter's own nib width, same reasoning as truchet's arc sampling


# Rungs in the ring ladder: how many tone levels the rings thin through between the gate and
# full coverage. 6 gives a visible step per ring group without the lightest water going bare.
_LEVELS = 6
# Samples per rung of the ladder. A rung one sample wide makes every dash a single point, and
# a one-point run is dropped (a polyline needs two), so the lightest water came back blank --
# which the contract catches as "light grey must draw less than black, but not nothing".
_DASH_STEPS = 4


def ripple(
    tone: ToneGrid,
    *,
    ring_spacing_mm: float = 2.0,
    amplitude_mm: float = 0.9,
    cycles_per_mm: float = 0.3,
    focus: tuple[float, float] | None = None,
    min_darkness: float = 0.12,
    max_points: int = MAX_POINTS_DEFAULT,
) -> Polylines:
    """Concentric rings from `focus` (default: frame centre), each one a single polyline.

    Wobble. `amplitude_mm` is clamped to ring_spacing_mm * 0.45 -- the same margin `wave`
    keeps its own swing inside row_pitch_mm for -- so a fully-displaced ring can never cross
    into the lane of its inner or outer neighbour and the "k-th ring" stays a meaningful,
    non-crossing curve. Within that cap, the radius carries a sine term whose phase accumulates
    with arc length (not with the sample index, so a fine or coarse chord samples the same
    wave) and whose amplitude AND rate both scale with the sampled darkness, stretched first --
    `_stretch_bounds` takes the min..max darkness among cells that already clear min_darkness
    (lesson 2: area-averaging compresses a photo's darkness into a narrow middle band, so an
    unstretched wobble barely moves at all) and maps that range onto [0, 1]. A merely-gated
    point (darkness just above min_darkness) gets a slow, shallow wobble that reads as a clean
    ring; a fully black one gets the fastest, deepest wave the spacing allows -- extra path
    length that a smooth single-direction push cannot buy, which is what gives this mode a
    real tonal range rather than a flat one. Below min_darkness a ring simply stops (lesson 3:
    paper stays paper, default min_darkness=0.12 keeps a near-white source from drawing a faint
    wash) and resumes as a new run, exactly like `spiral`'s own gate -- phase resets with it, so
    a new run always starts from a plain, unwobbled point.

    Frame. `reach` is measured to the far CORNER so the ring loop never stops short of the
    sheet's own extremes, which means a ring near that radius spends most of its circumference
    off the rectangular page -- for those angles the run breaks exactly like `spiral`'s own
    frame check (same reasoning: sampling and pushing a point that is nowhere near the canvas
    draws nothing meaningful and, worse, can smear a border-hugging streak across the whole
    width once clamped). What IS clipped, the way `truchet` and `contour` clip, is the push
    itself: once a point's own undisplaced position is confirmed on-page, `amplitude_mm`'s
    small nudge (at most `swing`, a couple of mm) can tip it just past an edge, and clamping
    that back in is invisible where lifting the pen for it would not be. So a ring that is
    substantially off-page breaks into separate arcs like any other gated mode; a ring that is
    on-page and merely pushed a little past its own edge stays one polyline.

    max_points bounds ring_count * points-per-ring before any ring is walked -- the closed
    form is a triangular series (ring k contributes ~2*pi*k*ring_spacing_mm / chord points),
    the same fail-fast shape truchet's tile count and rings' ring-count estimate use.
    """
    if ring_spacing_mm <= 0:
        raise ValueError("ring_spacing_mm must be positive")
    if amplitude_mm < 0:
        raise ValueError("amplitude_mm must be non-negative")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_points < 1:
        raise ValueError("max_points must be at least 1")

    fx, fy = focus if focus is not None else (tone.width_mm / 2.0, tone.height_mm / 2.0)
    reach = max(math.hypot(fx - cx, fy - cy) for cx in (0.0, tone.width_mm) for cy in (0.0, tone.height_mm))
    swing = min(amplitude_mm, ring_spacing_mm * 0.45)

    low, high = _stretch_bounds(tone.darkness, min_darkness)
    if low == 0.0 and high == 0.0:
        return []  # nothing in the whole grid clears the gate -- an all-white sheet

    ring_count = max(1, math.ceil((reach + swing) / ring_spacing_mm))
    estimated_points = math.pi * ring_spacing_mm * ring_count * (ring_count + 1) / _CHORD_MM
    if estimated_points > max_points:
        raise ValueError(
            f"ripple would need ~{int(estimated_points)} points, exceeding max_points={max_points}; "
            "increase ring_spacing_mm or reduce the drawing size"
        )

    polylines: Polylines = []
    for k in range(1, ring_count + 1):
        base_radius = k * ring_spacing_mm
        if base_radius - swing > reach:
            break
        steps = max(24, round(math.tau * base_radius / _CHORD_MM))
        run: list[tuple[float, float]] = []
        for index in range(steps + 1):
            theta = math.tau * index / steps
            x0 = fx + base_radius * math.cos(theta)
            y0 = fy + base_radius * math.sin(theta)
            if not (0.0 <= x0 <= tone.width_mm and 0.0 <= y0 <= tone.height_mm):
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                continue
            darkness = _sample_darkness(tone, x0, y0)
            if darkness < min_darkness:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                continue
            normalized = (darkness - low) / (high - low) if high - low > 1e-9 else darkness
            # Displacement alone carries no tone: pushing a ring in or out barely changes its
            # arc length, so every gated ring drew solid and the sheet came out flat (measured
            # buckets [115, 100, 99, 102, 104, 101, 105, 0] -- no picture at any setting). The
            # rings themselves have to thin out in the light, so each ring only draws where the
            # tone clears its own rung of an ordered ladder. The rung walks ALONG the ring
            # (and is offset per ring so the gaps do not line up radially), so the water
            # breaks into dashes that lengthen as it darkens -- rung-per-ring instead
            # quantised the tone into whole rings, which showed up as lumps in the contract's
            # strips ([148, 108, 119, 40, 31, 38, 21, 0]).
            if normalized < ((index // _DASH_STEPS + k) % _LEVELS) / _LEVELS:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                continue
            # In AND out, not just out: a ring that only ever bulges outward reads as a dent in
            # the spacing, where a wave riding along the ring reads as water.
            wobble = math.sin(math.tau * cycles_per_mm * base_radius * theta)
            radius = base_radius + swing * normalized * wobble
            point = (fx + radius * math.cos(theta), fy + radius * math.sin(theta))
            run.append(_clip_point(point, tone.width_mm, tone.height_mm))
        if len(run) >= 2:
            polylines.append(run)
    return polylines


def _stretch_bounds(darkness: np.ndarray, min_darkness: float) -> tuple[float, float]:
    """Min/max darkness among cells that already clear min_darkness -- see ripple's own
    docstring (lesson 2) and ascii._char_grid, which stretches the same way for the same
    reason. (0.0, 0.0) signals an empty gated set, distinct from any real darkness range."""
    passing = darkness[darkness >= min_darkness]
    if passing.size == 0:
        return 0.0, 0.0
    return float(passing.min()), float(passing.max())


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto ring_spacing_mm, with the same 1.2x headroom
    `truchet` and `rings` use: at the fader's loosest step (spacing_mm=2.5) the dense 150 mm
    segment cap is the tightest one (40 000), and a bare ring_spacing_mm=2.5 there needs
    ~39 000 points by the closed form above -- already over budget before the sheet's edges
    are even reached. *1.2 is the floor that buys back enough room to fit (~39 200, checked
    against the contract below); every finer fader step still shrinks ring_spacing_mm from
    there, so detail keeps rising as the fader promises, and the caps only get looser as
    spacing_mm falls.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"ring_spacing_mm": spacing_mm * 1.2}
