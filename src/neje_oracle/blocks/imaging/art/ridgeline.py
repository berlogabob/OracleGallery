"""Stacked ridge rows with hidden-line removal — the Joy Division / Unknown Pleasures look.

Each row is a horizontal scanline pushed UP by the darkness beneath it, so the picture reads
as a skyline of ridges. Rows are drawn front (bottom) to back (top) and every ridge occludes
whatever sits behind it wherever it rises above that ridge — exactly the classic pulsar-plot
rendering, not merely "draw N wavy rows".
"""

from __future__ import annotations

import math
from dataclasses import replace

from neje_oracle.blocks.imaging.modes import (
    Polylines,
    ToneGrid,
    _clip,
    _sample_darkness,
    _smoothed_darkness,
    simplify_polyline,
)

HELP = "Stacked ridge rows pushed up by darkness, nearer rows hiding the ones behind. Unknown Pleasures look."

# A row is one iteration of a pure-Python x-sample loop, and the segment cap in
# image_to_polylines only runs once this returns — the same trap flow/stipple/squiggle guard
# against. Worst case is every row at the finest row_pitch_mm/step_mm this call allows.
MAX_RIDGELINE_POINTS = 400_000


def ridgeline(
    tone: ToneGrid,
    *,
    row_pitch_mm: float = 2.0,
    step_mm: float = 0.4,
    lift_mm: float | None = None,
    min_darkness: float = 0.05,
    blur_px: float = 1.5,
    simplify_mm: float = 0.12,
    max_points: int = MAX_RIDGELINE_POINTS,
) -> Polylines:
    """Terrain ridges: each row's height is its own baseline minus darkness times a lift.

    Rows sit row_pitch_mm apart, base y measured from the bottom of the sheet up (row 0 is
    the frontmost, nearest the viewer). Every row is sampled every step_mm and displaced by
    `displaced_y = base_y - lift_mm * darkness(x, base_y)`, so a dark patch beneath a row
    pushes that row's line upward on the page. lift_mm defaults to 3x the row pitch, which is
    enough for one dark row to bury two rows behind it (9 mm of lift against a 3 mm pitch)
    while leaving most of a mid-tone field looking like a gentle rolling hill rather than a
    spike -- narrower lifts read flat, wider ones turn every row into a single vertical wall.

    Hidden-line removal is what makes this a 3D terrain instead of a stack of independent
    wavy rows: rows are walked front (bottom, largest base_y) to back (top, smallest base_y),
    and a running envelope holds the smallest y drawn so far at every x sample. A row's point
    is visible only where its displaced y sits above (numerically less than) the envelope at
    that x; the envelope is then updated with the row's own displaced y at every sample,
    whether or not that point ended up visible or inked, because the terrain occludes
    regardless of ink. Where visibility flips between two consecutive samples, the crossing x
    is solved by linear interpolation of both the row's segment and the envelope's segment
    (`_crossing`), so a polyline stops exactly on the occluding ridge instead of overshooting
    into hidden territory or leaving a gap before it.

    min_darkness gates ink the same way every other tone mode does: white paper draws
    nothing, but a gated point still updates the envelope, because a point too light to ink
    is still real terrain that can hide a row behind it -- the disturbance is invisible, not
    absent.

    blur_px smooths the darkness field before sampling (see hatch's docstring for why: a
    resampled source jitters cell to cell, and reacting to every jitter shatters one ridge
    into short runs). Measured on a real photo at the shipped defaults, smoothing collapsed a
    ridgeline from ~1400 fragments to 210 strokes for the same visible silhouette.
    """
    if row_pitch_mm <= 0:
        raise ValueError("row_pitch_mm must be positive")
    if step_mm <= 0:
        raise ValueError("step_mm must be positive")
    lift = row_pitch_mm * 3.0 if lift_mm is None else lift_mm
    if lift < 0:
        raise ValueError("lift_mm must be non-negative")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if blur_px < 0:
        raise ValueError("blur_px must be non-negative")
    if simplify_mm < 0:
        raise ValueError("simplify_mm must be non-negative")

    rows_count = max(1, int(tone.height_mm / row_pitch_mm))
    samples_count = max(1, int(tone.width_mm / step_mm) + 1)
    estimate = rows_count * samples_count
    if estimate > max_points:
        raise ValueError(
            f"ridgeline would sample more than max_points={max_points} points "
            f"({rows_count} rows x {samples_count} samples); widen row_pitch_mm or step_mm"
        )

    smoothed = replace(tone, darkness=_smoothed_darkness(tone.darkness, blur_px))

    samples = max(1, math.ceil(tone.width_mm / step_mm))
    xs = [tone.width_mm * index / samples for index in range(samples + 1)]
    envelope = [math.inf] * len(xs)

    polylines: Polylines = []
    row_y = tone.height_mm - row_pitch_mm / 2.0
    while row_y > 0:
        darkness = [_sample_darkness(smoothed, x, row_y) for x in xs]
        ys = [_clip(row_y - lift * d, 0.0, tone.height_mm) for d in darkness]
        visible = [y < envelope[index] for index, y in enumerate(ys)]

        run: list[tuple[float, float]] = []
        for index in range(len(xs)):
            if index > 0 and visible[index] != visible[index - 1]:
                crossing = _crossing(
                    xs[index - 1], ys[index - 1], envelope[index - 1], xs[index], ys[index], envelope[index]
                )
                if visible[index]:
                    run = [crossing]
                else:
                    if run:
                        run.append(crossing)
                        if len(run) >= 2:
                            polylines.append(run)
                    run = []
            if visible[index]:
                if darkness[index] >= min_darkness:
                    run.append((xs[index], ys[index]))
                else:
                    if len(run) >= 2:
                        polylines.append(run)
                    run = []
        if len(run) >= 2:
            polylines.append(run)

        for index, y in enumerate(ys):
            if y < envelope[index]:
                envelope[index] = y
        row_y -= row_pitch_mm

    if simplify_mm > 0:
        polylines = [
            simplified for polyline in polylines if len(simplified := simplify_polyline(polyline, simplify_mm)) >= 2
        ]
    return polylines


def _crossing(x0: float, y0: float, e0: float, x1: float, y1: float, e1: float) -> tuple[float, float]:
    """Where a row's segment crosses the envelope's segment between two samples.

    Both the row and the envelope are treated as piecewise-linear between adjacent x samples
    -- the same approximation the envelope array itself is built on. Solving
    (y0 - e0) + t*((y1 - e1) - (y0 - e0)) = 0 for t gives the crossing exactly when the two
    segments are genuinely straight between the samples, which is what makes a polyline stop
    on the occluding ridge instead of overshooting past it or leaving a visible gap.
    """
    d0, d1 = y0 - e0, y1 - e1
    if d1 == d0:
        return x1, y1
    t = _clip(-d0 / (d1 - d0), 0.0, 1.0)
    return x0 + t * (x1 - x0), y0 + t * (y1 - y0)


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Higher quality -> tighter row pitch and finer x sampling.

    spacing_mm is the quality fader's own ladder (2.5 draft .. 1.0 max). Passing it straight
    through as row_pitch_mm keeps the default look (row_pitch_mm=2.0) at the fader's own
    "balanced" position (1.6, close to it), and step_mm scales down with it so the ridge stays
    smooth as rows get denser -- a fixed step_mm would under-sample a fine pitch and a coarse
    step_mm would over-sample a wide one.
    """
    return {"row_pitch_mm": spacing_mm, "step_mm": max(0.15, round(spacing_mm * 0.2, 3))}
