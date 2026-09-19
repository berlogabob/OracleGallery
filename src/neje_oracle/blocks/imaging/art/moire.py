"""Two overlaid line gratings whose interference -- not their density -- carries the tone.

Field A is a calm, dead-straight grating at `field_angle_deg`. Field B is the SAME pitch at
`field_angle_deg + beat_deg`: two gratings a few degrees apart naturally drift in and out of
alignment across the sheet, which is genuine geometric moire, not a metaphor for it. Left alone
that drift is fixed by geometry and has nothing to do with the picture, so field B also carries
a phase-accumulated wobble (same trick as modes.wave / art.spiral) whose amplitude and frequency
both grow with the LOCAL image darkness at each sample: where the picture is light the wobble
collapses to ~0 and B settles back near its own straight line -- the two fields read as one open
grating. Where it is dark the wobble grows toward a full line_spacing_mm swing, so B swings
across A's own lines every cycle and the crossings read as a dense, busy interleave. That swing
is also the entire tone budget: a fixed angle/phase offset moves ink around without adding any,
so match must come from B's swing actually lengthening its own path, the same way wave's rows
get taller and busier in the dark, not from breaking either field into shorter runs.

Neither field's line is ever cut mid-run for tone -- see cell_darkness's docstring. A whole line
is dropped only if its OWN mean stretched darkness (see _stretch_fn) falls under that field's
gate -- mean, not a single dark point it grazes, so a line that is 95% light background and 5%
subject does not blanket the whole sheet at full length just because it touches something dark
once. Field A's gate sits above field B's (_FIELD_A_GATE_SCALE) for a reason explained where
that constant is defined. That is the point of this mode over hatch/crosshatch: every stroke
drawn is one pen-down for its whole length, and pen lifts are 52% of plot time on this machine.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

HELP = (
    "Two overlaid line gratings a few degrees apart; the picture steers how far the second "
    "grating swings off the first, thickening the beat where it is dark."
)

# Field A carries no darkness signal of its own (wobble_amplitude_mm=0), so if it used the same
# gate as B it would draw across almost any real photo -- backgrounds are rarely pure white, and
# min_darkness has to stay low for B's own gradation to start near black. Raising A's own bar
# means the calm reference grating only shows up where the picture is genuinely committing to
# something dark, which is what actually keeps light areas open on the sheet.
_FIELD_A_GATE_SCALE = 8.0


def moire(
    tone: ToneGrid,
    *,
    line_spacing_mm: float = 1.2,
    field_angle_deg: float = 0.0,
    beat_deg: float = 5.0,
    min_darkness: float = 0.05,
) -> Polylines:
    """Field A straight at field_angle_deg; field B the same pitch at +beat_deg, wobbling with
    the local tone (see module docstring for why wobble, not density, carries the picture).

    beat_deg is small on purpose: it is what makes field B's average heading distinguishable
    from field A's (the two are told apart in the test below by that very heading, not by
    tagging), while staying close enough to A's pitch that the two fields still read as one
    family of lines rather than a crosshatch. 5 degrees at line_spacing_mm=1.2 puts a full
    coincide-to-interleave cycle roughly every spacing/(2*sin(2.5deg)) =~ 13.7 mm, a beat an
    eye reads as texture rather than as a handful of widely spaced stripes.
    """
    if line_spacing_mm <= 0:
        raise ValueError("line_spacing_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")

    stretch = _stretch_fn(tone, line_spacing_mm, min_darkness)
    field_a = _field_polylines(
        tone,
        angle_deg=field_angle_deg,
        line_spacing_mm=line_spacing_mm,
        gate_darkness=min_darkness * _FIELD_A_GATE_SCALE,
        stretch=stretch,
        wobble_amplitude_mm=0.0,
    )
    field_b = _field_polylines(
        tone,
        angle_deg=field_angle_deg + beat_deg,
        line_spacing_mm=line_spacing_mm,
        gate_darkness=min_darkness,
        stretch=stretch,
        wobble_amplitude_mm=line_spacing_mm,
    )
    return field_a + field_b


def _stretch_fn(tone: ToneGrid, cell_mm: float, min_darkness: float) -> Callable[[float], float]:
    """Build the darkness->[0,1] map used for wobble strength, stretched over the GATED cells'
    own min..max -- exactly the move ascii._char_grid documents and for the same reason: a
    photo area-averaged into cells this coarse rarely reaches the ends of 0..1 on its own
    (ascii measured a real photo's gated cells sitting at 0.45-0.58), so feeding raw darkness
    into the wobble ramp would barely swing it at all. Cell size is line_spacing_mm: that is
    the footprint one wobble cycle actually samples, so it is what should decide the range.
    """
    rows = max(1, math.ceil(tone.height_mm / cell_mm))
    cols = max(1, math.ceil(tone.width_mm / cell_mm))
    gated = [
        value
        for r in range(rows)
        for c in range(cols)
        if (
            value := cell_darkness(
                tone.darkness,
                c * cell_mm,
                r * cell_mm,
                min((c + 1) * cell_mm, tone.width_mm),
                min((r + 1) * cell_mm, tone.height_mm),
                tone.width_mm,
                tone.height_mm,
            )
        )
        >= min_darkness
    ]
    low, high = (min(gated), max(gated)) if gated else (0.0, 0.0)
    spread = high - low

    def stretch(value: float) -> float:
        if value < min_darkness:
            return 0.0
        # Flat image (spread ~0): nothing to stretch against, fall back to the raw value --
        # the same fallback ascii._char_grid's normalized() uses, so a uniform grey still
        # wobbles proportionally to its own darkness instead of snapping to 0 or 1.
        return (value - low) / spread if spread > 1e-9 else value

    return stretch


def _field_polylines(
    tone: ToneGrid,
    *,
    angle_deg: float,
    line_spacing_mm: float,
    gate_darkness: float,
    stretch: Callable[[float], float],
    wobble_amplitude_mm: float,
) -> Polylines:
    """One grating: parallel lines at angle_deg, spaced line_spacing_mm, each either a
    straight run (wobble_amplitude_mm=0, field A) or a phase-accumulated sine swing scaled by
    local stretched darkness (field B). Sampling step is line_spacing_mm/4 -- a quarter of the
    shortest wobble half-cycle -- so the sine itself is resolved regardless of tone.cell_mm.
    """
    angle = math.radians(angle_deg)
    direction = (math.cos(angle), math.sin(angle))
    perpendicular = (-direction[1], direction[0])
    center = (tone.width_mm / 2.0, tone.height_mm / 2.0)
    radius = math.hypot(tone.width_mm, tone.height_mm) / 2.0
    half_footprint = line_spacing_mm / 2.0
    cycles_per_mm = 1.0 / (2.0 * line_spacing_mm)
    step_mm = line_spacing_mm / 4.0

    polylines: Polylines = []
    offset = -radius + line_spacing_mm / 2.0
    while offset < radius:
        origin = (center[0] + offset * perpendicular[0], center[1] + offset * perpendicular[1])
        offset += line_spacing_mm
        interval = _clip_to_rect(origin, direction, tone.width_mm, tone.height_mm)
        if interval is None:
            continue
        start, end = interval
        samples = max(1, math.ceil((end - start) / step_mm))
        step = (end - start) / samples
        points: list[tuple[float, float]] = []
        local_d_total = 0.0
        phase = 0.0
        for index in range(samples + 1):
            distance = start + step * index
            x = origin[0] + distance * direction[0]
            y = origin[1] + distance * direction[1]
            local_darkness = cell_darkness(
                tone.darkness,
                x - half_footprint,
                y - half_footprint,
                x + half_footprint,
                y + half_footprint,
                tone.width_mm,
                tone.height_mm,
            )
            local_d = stretch(local_darkness)
            local_d_total += local_d
            # Both frequency and amplitude ride on local_d, the same double-carry wave.py
            # uses: amplitude alone barely lengthens the path (a wide slow wobble is nearly
            # as short as a straight line), so the dark side needs the tighter spacing too.
            phase += math.tau * cycles_per_mm * (0.3 + local_d) * step
            displacement = math.sin(phase) * wobble_amplitude_mm * local_d
            points.append(
                _clip_point(
                    (x + displacement * perpendicular[0], y + displacement * perpendicular[1]),
                    tone.width_mm,
                    tone.height_mm,
                )
            )
        # Gate on the line's MEAN stretched darkness, not a point it merely brushes past: a
        # line that is background for 95% of its length and grazes the dark subject for the
        # other 5% must not blanket the whole sheet at full length just because of that graze
        # -- that is exactly the "sheet stays open" promise this mode makes for light areas.
        if len(points) and local_d_total / len(points) >= gate_darkness:
            polylines.append(points)
    return polylines


def _clip_to_rect(
    origin: tuple[float, float], direction: tuple[float, float], width_mm: float, height_mm: float
) -> tuple[float, float] | None:
    """Parametric [start, end] where origin + t*direction crosses the width x height rect."""
    lower = -math.inf
    upper = math.inf
    for coordinate, delta, maximum in zip(origin, direction, (width_mm, height_mm), strict=True):
        if abs(delta) < 1e-12:
            if not 0 <= coordinate <= maximum:
                return None
            continue
        first = -coordinate / delta
        second = (maximum - coordinate) / delta
        lower = max(lower, min(first, second))
        upper = min(upper, max(first, second))
    return (lower, upper) if upper > lower else None


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader straight onto line_spacing_mm.

    No floor beyond spacing_mm's own: a moire field's segment count scales as
    line_spacing_mm**-2 too (more lines AND more samples per line, same shape as truchet's
    tile_mm**-2), but the field-A gate (see _FIELD_A_GATE_SCALE) keeps most of a typical
    image's lines out of the straight, tone-blind reference grating, so measured segment
    counts sit well under every dense-150mm cap even at the fader's finest step (1.0 mm ->
    86 064 of a 640 000 budget) -- see the mode's own contract report for the full ladder.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"line_spacing_mm": spacing_mm}
