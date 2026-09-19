"""Guilloche rosettes: epicyclic (spirograph) curves nested into banknote-style lace.

A hypotrochoid -- the classic spirograph curve, a small circle of radius r rolling inside a
fixed circle of radius R, tracing a point d from its centre -- is drawn per grid cell:

    x(t) = (R - r) cos t + d cos((R - r) / r * t)
    y(t) = (R - r) sin t - d sin((R - r) / r * t)

R is fixed to an exact integer multiple of r (R = r * lobes), which makes (R - r) / r equal
to lobes - 1, an integer, so the curve closes after exactly one sweep of t: 0 to 2*pi. That
exactness is what lets `_epicycle_ring` be tested for closure directly, and it is why lobes
must be an integer -- a non-integer ratio traces a curve that only closes after many turns,
if ever, and would fight the "one continuous rosette" economics this mode is built for.

Tone does NOT ride on amplitude. A single hypotrochoid's ink barely changes between a small
and a large d -- both are one loop of similar length -- so modulating amplitude alone is close
to the flat-gradient failure this mode was built to avoid (see the batch notes: [86, 72, 73,
75, 76, 75, 67, 67], a mode whose two tone effects cancelled). Instead each cell stacks
0..k nested, self-similar copies of the SAME rosette (same lobes, same d/r ratio, scaled down
by a shrinking factor) concentrically inward from the cell's own outer rosette -- more rings,
literally more ink, the same lever `truchet` uses for its concentric arcs. Measured on the
80x20mm gradient the contract feeds every tone mode (defaults throughout): buckets of
[252, 252, 233, 198, 147, 80, 80, 0] mm of ink per 10mm strip -- a real slope, > 3:1 from the
darkest strip to the lightest one that still clears min_darkness, before the paper-white strip
past it draws nothing at all.

Single stroke per rosette. All of a cell's nested rings are ONE polyline: each ring starts and
ends at its own t=0 point -- (R - r + d, 0) from the rosette centre, on the +x axis -- so
appending ring after ring (outer to inner) turns "k closed loops" into one open chain, joined
by a short radial hop between consecutive rings' own t=0 points. No `_stitch` pass is needed
because the join points are exact by construction, not merely nearby. This is the entire
reason a dense 150mm render comes in at strokes in the tens rather than the thousands: one
pen-down per rosette, not one per ring.
"""

from __future__ import annotations

import math

from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

HELP = (
    "Spirograph rosettes, nested rings stacked deeper where the tile is dark, banknote-lace "
    "style. One pen-down per rosette; detail = rosette size in mm."
)

MAX_TILES_DEFAULT = 20_000
# Concentric rings sampled every ~0.3 mm of arc length -- the plotter's own pen width
# (PEN_WIDTH_MM_DEFAULT in modes.py), same reasoning truchet's arc sampling uses: finer
# sampling than the nib resolves is only extra vertices, never extra visible curvature.
_SAMPLE_SPACING_MM = 0.3
_MIN_POINTS = 24
# Keep a rosette's own outer sweep inside its own tile, clear of the neighbour's -- the same
# margin role truchet's radius ladder plays by staying strictly under tile_mm/2.
_FILL_FRACTION = 0.92
# A ring closer than 2 pen widths to its neighbour fuses into a wash under the nib rather than
# reading as a separate line, so a finer request buys segments, not visible lace.
_LAYER_PITCH_FLOOR_MM = 0.6
# Hard ceiling on rings per rosette regardless of how fine layer_pitch_mm asks to go, so a
# tiny layer_pitch_mm on a big rosette cannot explode segment counts before any geometry runs.
_MAX_LAYERS_CAP = 8


def guilloche(
    tone: ToneGrid,
    *,
    rosette_mm: float = 10.0,
    lobes: int = 5,
    amplitude_mm: float = 1.5,
    min_darkness: float = 0.12,
    layer_pitch_mm: float = 0.9,
    max_tiles: int = MAX_TILES_DEFAULT,
) -> Polylines:
    """Lay a grid of rosettes, each 1..k nested hypotrochoids deep where the tile is dark.

    Geometry. rosette_mm sets the tile pitch and, via _FILL_FRACTION, the outer rosette's
    reach from its own centre. amplitude_mm (d) is taken literally in mm; lobes (R/r, must be
    an integer >= 2) and that reach then pin down r and R for the OUTERMOST ring:

        r = (reach - amplitude_mm) / (lobes - 1)
        R = r * lobes

    Every ring nested inside it is the same shape scaled by a factor s < 1 (R, r and d all
    scaled together), so the d/r ratio -- what makes a spirograph loop tight or loose -- never
    changes with darkness, only how many concentric copies are drawn.

    Tone. Darkness is averaged per tile (cell_darkness, an area mean, not a point sample) and,
    for cells clearing min_darkness, stretched onto its own gated min..max before mapping to a
    ring count -- the same rescue ascii._char_grid documents: without it, a photo whose cell
    means cluster in the middle of 0..1 would use only the top one or two ring counts and read
    as a flat texture. k = ceil(stretched * available_layers), available_layers itself capped
    by how many layer_pitch_mm-spaced rings fit inside the outer reach (see quality_params).

    min_darkness defaults to 0.12, well above the usual 0.05: a rosette's outer ring is not a
    faint mark even at k=1, so a low gate would ink a visibly-not-white background under
    "light" areas. Above it, near-white paper draws nothing at all.
    """
    if rosette_mm <= 0:
        raise ValueError("rosette_mm must be positive")
    if lobes < 2 or lobes != int(lobes):
        raise ValueError("lobes must be an integer >= 2")
    if amplitude_mm <= 0:
        raise ValueError("amplitude_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if layer_pitch_mm <= 0:
        raise ValueError("layer_pitch_mm must be positive")
    if max_tiles < 1:
        raise ValueError("max_tiles must be at least 1")

    lobes = int(lobes)
    cols = max(1, math.ceil(tone.width_mm / rosette_mm))
    rows = max(1, math.ceil(tone.height_mm / rosette_mm))
    if rows * cols > max_tiles:
        raise ValueError(
            f"guilloche would need {rows * cols} rosettes, exceeding max_tiles={max_tiles}; "
            "increase rosette_mm or reduce the drawing size"
        )

    reach = (rosette_mm / 2.0) * _FILL_FRACTION
    if amplitude_mm >= reach:
        raise ValueError(
            f"amplitude_mm={amplitude_mm} leaves no room inside a {rosette_mm} mm rosette "
            f"(usable reach is {reach:.2f} mm); shrink amplitude_mm or grow rosette_mm"
        )
    r_outer = (reach - amplitude_mm) / (lobes - 1)
    R_outer = r_outer * lobes
    available_layers = max(1, min(_MAX_LAYERS_CAP, math.floor(reach / layer_pitch_mm)))

    raw = [
        [
            cell_darkness(
                tone.darkness,
                col * rosette_mm,
                row * rosette_mm,
                min((col + 1) * rosette_mm, tone.width_mm),
                min((row + 1) * rosette_mm, tone.height_mm),
                tone.width_mm,
                tone.height_mm,
            )
            for col in range(cols)
        ]
        for row in range(rows)
    ]
    passing = [value for line in raw for value in line if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    def normalized(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    polylines: Polylines = []
    for row in range(rows):
        y0 = row * rosette_mm
        for col in range(cols):
            darkness = raw[row][col]
            if darkness < min_darkness:
                continue
            x0 = col * rosette_mm
            k = max(1, min(available_layers, math.ceil(normalized(darkness) * available_layers)))
            center = (x0 + rosette_mm / 2.0, y0 + rosette_mm / 2.0)
            scales = [1.0 - i * (layer_pitch_mm / reach) for i in range(k)]
            polylines.append(_rosette_polyline(center, R_outer, r_outer, amplitude_mm, lobes, scales))

    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in polylines]


def _rosette_polyline(
    center: tuple[float, float],
    R_outer: float,
    r_outer: float,
    d_outer: float,
    lobes: int,
    scales: list[float],
) -> list[tuple[float, float]]:
    """One rosette as a single polyline: scales' rings, outer to inner, chained end to end.

    Each ring starts and ends at its own t=0 point, so simply concatenating ring point lists
    turns "k closed loops" into one open chain -- the segment between one ring's last point
    (== its own first point) and the next ring's first point is the connecting hop, already
    correct with no extra stitching.
    """
    polyline: list[tuple[float, float]] = []
    for scale in scales:
        radius_big, radius_small, offset = R_outer * scale, r_outer * scale, d_outer * scale
        points = _points_for_ring(radius_big, radius_small, offset, lobes)
        polyline.extend(_epicycle_ring(center, radius_big, radius_small, offset, lobes, points))
    return polyline


def _epicycle_ring(
    center: tuple[float, float], R: float, r: float, d: float, lobes: int, points: int
) -> list[tuple[float, float]]:
    """One closed hypotrochoid loop, t = 0..2*pi, first point == last point by construction.

    ratio = (R - r) / r simplifies to lobes - 1 exactly, since R was built as r * lobes; using
    that integer directly (instead of recomputing a float division) is what makes the t=2*pi
    sample land on the t=0 sample to float precision, not merely close.
    """
    ratio = lobes - 1
    cx, cy = center
    big = R - r
    return [
        (
            cx + big * math.cos(t) + d * math.cos(ratio * t),
            cy + big * math.sin(t) - d * math.sin(ratio * t),
        )
        for t in (math.tau * index / points for index in range(points + 1))
    ]


def _points_for_ring(R: float, r: float, d: float, lobes: int) -> int:
    """Sample count from an upper bound on arc length: |dP/dt| <= (R - r) + d * (lobes - 1),
    by the triangle inequality on the two sinusoids' own velocity contributions.
    """
    speed_bound = (R - r) + d * (lobes - 1)
    circumference_bound = speed_bound * math.tau
    return max(_MIN_POINTS, math.ceil(circumference_bound / _SAMPLE_SPACING_MM))


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto layer_pitch_mm: finer spacing, more nested rings.

    layer_pitch_mm is the mm gap between consecutive ring reaches, so the fader speaks in the
    same unit it already uses everywhere else (like engraving's line_spacing_mm) -- no scaling
    needed. Floored at _LAYER_PITCH_FLOOR_MM (2x the 0.3mm pen width): a tighter pitch cannot
    read as separate rings under the nib, only add segments. The fader's own finest step
    (1.0mm) already sits above that floor, so every step still buys a real extra ring.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"layer_pitch_mm": max(_LAYER_PITCH_FLOOR_MM, spacing_mm)}
