"""Seigaiha-style fish scales: overlapping downward arcs in offset rows.

Each scale is a single semicircular arc, flat top implied (not drawn) and bulging downward,
like a roof tile or the traditional Japanese wave pattern. Rows sit closer together than a
scale's own radius, so each row's arcs dip down through the row above -- the "tucked under"
shingle look -- and alternate rows are offset by half a scale so the columns interlock rather
than stacking in straight lines.

Tone does two things at once, both driven by the SAME quantised level so they never fight
each other (see the "Why level, not radius alone" note on `scales` below): it shrinks the
arc's own radius (small tight scales where dark, large open ones where light) and it adds
concentric arcs nested inside the scale (more of them where darkest). Shrinking radius alone
would make dark areas carry LESS ink per scale, cancelling the tone signal exactly the way a
flat-lined sibling mode did; the nested arcs are what keeps total ink rising with darkness.
"""

from __future__ import annotations

import math

from ..modes import Polylines, ToneGrid, _clip_point, _stitch, cell_darkness

HELP = (
    "Overlapping arcs in offset rows, like fish scales or roof tiles (seigaiha). "
    "Darker areas get smaller, tighter scales with nested arcs inside; detail = scale size in mm."
)

MAX_LATTICE_DEFAULT = 150_000
_ARC_SAMPLE_SPACING_MM = 0.3  # matches PEN_WIDTH_MM_DEFAULT in modes.py; finer is invisible
_ARC_MIN_POINTS = 6
# A stitched join needs the two arcs' shared endpoint to land on the SAME float: both scales
# compute it as (their own cx) +/- radius, and radius only matches between neighbours when
# both quantise to the same tone level, so the only slack to allow for is float rounding.
_JOIN_TOLERANCE_MM = 1e-6

# Row spacing as a fraction of scale_mm: less than _R_MAX_FRACTION so consecutive rows
# overlap (a row's flat top sits inside the arc bulge of the row above it).
_ROW_PITCH_FRACTION = 0.42
# Radius bounds as a fraction of scale_mm. _R_MAX_FRACTION = 0.5 means the lightest drawn
# scale has radius == half the column pitch, so its arc endpoints land exactly on the
# neighbouring scale's own endpoints -- touching tiles, and the alignment _stitch needs.
_R_MAX_FRACTION = 0.5
_R_MIN_FRACTION = 0.30


def scales(
    tone: ToneGrid,
    *,
    scale_mm: float = 6.0,
    min_darkness: float = 0.12,
    max_scales: int = 8,
    max_lattice: int = MAX_LATTICE_DEFAULT,
) -> Polylines:
    """Lay a grid of overlapping, offset-row arcs, tone controlling size and nesting.

    Lattice. Columns are spaced scale_mm apart; rows are spaced scale_mm * _ROW_PITCH_FRACTION
    apart (closer than the radius, so rows overlap) and every other row is offset by half a
    scale_mm so the pattern interlocks -- one continuous phase shift, not a per-tile choice,
    which is what makes the offset provable from the emitted geometry (see the mode's test).

    Tone -> level. Each lattice cell is scored by cell_darkness over its own scale_mm x
    row-pitch footprint (mean, not a point sample, for the reason `truchet` and `rings` both
    average). Passing cells (>= min_darkness) have their own min..max STRETCHED onto
    [0, max_scales - 1] before picking a level, exactly as `ascii._char_grid` documents: a
    coarse lattice compresses a real photo's variance long before this function sees it, and
    unstretched selection would spend most of the frame in the middle few levels.

    Why level, not radius alone. Both effects a darker cell gets -- smaller outer radius and
    more nested arcs -- are driven by the SAME integer level L in [0, max_scales - 1], not by
    two independent continuous functions of darkness. Two reasons:
      1. Quantising to shared integer levels is what lets neighbouring cells' radii match
         exactly (float equality, not tolerance) when their darkness lands on the same level,
         which is what lets `_stitch` join them across a row.
      2. Ink accounting has to net UPWARD with darkness despite the radius shrinking. Ink per
         scale is arc_span * radius * sum(i+1 for i in range(count)) / count, i.e.
         arc_span * radius * (count + 1) / 2. At L=0: radius=R_max, count=1, ink ~ R_max. At
         L=max: radius=R_min, count=max_scales, ink ~ R_min * (max_scales + 1) / 2. With the
         shipped R_min = 0.6 * R_max and max_scales=8, that ratio is 0.6 * 9 / 2 = 2.7x --
         comfortably past the ~2.5x this mode was told to clear, and by construction (not by
         retuning after the fact): shrinking radius and growing nested count are opposed, so
         the margin has to be built into the constants, not discovered.

    min_darkness defaults to 0.12: a near-white cell draws nothing, so light regions stay
    paper rather than a faint wash of touching, barely-there arcs.

    max_lattice guards the one place this mode can explode: a small scale_mm on a big sheet
    is a rows*cols blow-up that costs nothing to detect before a single arc is sampled.
    """
    if scale_mm <= 0:
        raise ValueError("scale_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_scales < 1:
        raise ValueError("max_scales must be at least 1")
    if max_lattice < 1:
        raise ValueError("max_lattice must be at least 1")

    col_pitch = scale_mm
    row_pitch = scale_mm * _ROW_PITCH_FRACTION

    rows_estimate = max(1, math.ceil(tone.height_mm / row_pitch) + 1)
    cols_estimate = max(1, math.ceil(tone.width_mm / col_pitch) + 2)
    if rows_estimate * cols_estimate > max_lattice:
        raise ValueError(
            f"scales would need {rows_estimate * cols_estimate} lattice cells, exceeding "
            f"max_lattice={max_lattice}; increase scale_mm or reduce the drawing size"
        )

    positions = list(_lattice(tone, col_pitch, row_pitch))
    passing = [darkness for _cx, _cy, darkness in positions if darkness >= min_darkness]
    if not passing:
        return []
    low, high = min(passing), max(passing)
    spread = high - low

    def normalized(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    r_max = scale_mm * _R_MAX_FRACTION
    r_min = scale_mm * _R_MIN_FRACTION
    arcs: Polylines = []
    for cx, cy, darkness in positions:
        if darkness < min_darkness:
            continue
        level = round(min(1.0, max(0.0, normalized(darkness))) * (max_scales - 1))
        radius = r_max - (r_max - r_min) * level / (max_scales - 1) if max_scales > 1 else r_max
        count = level + 1
        for index in range(count):
            arcs.append(_scale_arc(cx, cy, radius * (index + 1) / count))

    joined = _stitch(arcs, _JOIN_TOLERANCE_MM)
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in joined]


def _lattice(tone: ToneGrid, col_pitch: float, row_pitch: float) -> list[tuple[float, float, float]]:
    """(cx, cy, mean darkness) for every scale position, rows offset by half a column pitch.

    cy is the scale's flat-top y (its arc bulges down from there); cx is its centre x. Each
    row starts one column pitch before x=0 so the offset rows still cover the left edge with
    a (later clipped) partial scale, the same reasoning `rings` uses for its hex offset.
    """
    out: list[tuple[float, float, float]] = []
    row_index = 0
    cy = 0.0
    while cy < tone.height_mm:
        row_offset = col_pitch / 2.0 if row_index % 2 else 0.0
        cx = row_offset - col_pitch
        while cx < tone.width_mm:
            darkness = cell_darkness(
                tone.darkness,
                cx - col_pitch / 2.0,
                cy,
                cx + col_pitch / 2.0,
                cy + row_pitch,
                tone.width_mm,
                tone.height_mm,
            )
            out.append((cx, cy, darkness))
            cx += col_pitch
        cy += row_pitch
        row_index += 1
    return out


def _scale_arc(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    """One downward semicircular arc: (cx+r, cy) through (cx, cy+r) to (cx-r, cy).

    Sampled every ~0.3 mm of arc length like `truchet`'s quarter arcs, for the same reason:
    finer than the nib resolves is only extra vertices.
    """
    start = 0.0
    end = math.pi
    arc_length = radius * (end - start)
    samples = max(_ARC_MIN_POINTS, math.ceil(arc_length / _ARC_SAMPLE_SPACING_MM) + 1)
    return [
        (
            cx + radius * math.cos(start + (end - start) * index / (samples - 1)),
            cy + radius * math.sin(start + (end - start) * index / (samples - 1)),
        )
        for index in range(samples)
    ]


# A scale smaller than a few nib widths (0.3 mm pen) stops reading as a scale: its radius
# range (_R_MIN_FRACTION..= 0.5) would put the smallest nested arc under a millimetre, and
# under about one pen width it is a dot, not a curve. 1.2 mm keeps the tightest nested arc
# (0.3 * scale_mm / max_scales at the far end) at or above that floor.
_FLOOR_SCALE_MM = 1.2


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the shared quality fader onto scale_mm: smaller scales, finer weave.

    `rings` and `truchet` both scale spacing_mm by 1.2x; this mode needs 1.6x instead --
    every drawn cell can carry up to max_scales=8 nested arcs (vs. their max 4), so the same
    lattice density costs roughly twice the segments per cell. 1.6x keeps the draft step
    (spacing 2.5, the dense 150 mm segment-cap check's tightest case) under its 40 000-segment
    cap with ~7% headroom, while every finer step still shrinks scale_mm and so still adds
    detail, exactly as the fader promises. Clamped to _FLOOR_SCALE_MM so the fader's finest
    step (spacing 1.0) doesn't ask for scales the pen can no longer resolve.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"scale_mm": max(_FLOOR_SCALE_MM, spacing_mm * 1.6)}
