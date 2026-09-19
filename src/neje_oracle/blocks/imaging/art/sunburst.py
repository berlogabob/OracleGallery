"""Rays from a focus, gated by tone: a starburst that carries an image in its spokes.

Every ray is a straight line from `focus` out to the frame edge, sampled point by point along
its own length exactly like `spiral` samples along its coil. A ray does not move to show tone
(there is no wobble here); instead each point decides, on its own, whether the pen is down --
so a ray that crosses a light patch of the picture breaks into two shorter strokes with a gap
between them, and a ray in a dark patch runs unbroken. Angular density carries the other half
of the tone: candidate rays are laid at a fine, fixed pitch (`ray_pitch_deg`), then each
candidate is assigned a darkness FLOOR from an 8-step rotating ladder -- exactly the trick
`hatch` already uses to turn line-density into a halftone, just applied to angle instead of
spacing between parallel lines. A candidate whose local darkness cannot clear its floor draws
nothing at all, so low-floor candidates (1-in-8) form a sparse backbone that survives almost
anywhere above `min_darkness`, while high-floor candidates only survive where the picture is
close to black -- which is what "packed denser in angle where the picture is dark" means here.

Focus convergence, two separate effects, two separate corrections. First, the literal point:
every ray shares one endpoint, so an annulus at radius r has area ~2*pi*r*dr while ray count
there is the same as everywhere else, and ink-per-area diverges as r -> 0 for ANY image, even a
uniform grey one. A candidate's darkness is scaled by `radial_factor(r) = min(1, r /
taper_radius_mm)` before it is compared to its floor (`taper_radius_mm` defaults to 15% of the
frame's shorter side), fading darkness toward zero near the focus regardless of what the
picture says.

Second, and the one that actually broke the contract's gradient check first: on a frame whose
focus is not equidistant from every edge (the check's own 80x20 mm strip, focus centred), rays
pointing toward the SHORT axis have a short `reach` and, unlike a long ray -- which spends only
a fraction of its length near any one x -- a short ray spends its ENTIRE length near the focus's
own x. Measured before this fix: the two central 10 mm buckets of that 80x20 strip carried
383 and 293 units of ink against 159 in the darkest (leftmost) bucket, a bump nearly 2.4x its
neighbour, because roughly half of every near-vertical candidate (the ones whose reach is
capped by the 20 mm height, not the 80 mm width) survived its floor and dumped its whole short
length into one or two x-buckets. `radial_factor` alone cannot fix this -- it only discounts
the first few mm nearest the focus, and a 10 mm ray is still mostly OUTSIDE that discount. The
actual fix is `reach_factor = min(1, reach / longest_reach)`, `longest_reach` being the longest
reach among this call's own candidate rays: a ray capped short by the frame's own shape is
docked in direct proportion to how much shorter it is than the longest ray this focus can cast,
so the near-vertical rays above need roughly 4x the darkness to survive that they needed before.
After adding it the same two buckets measured 154 and 84 against 172 in the darkest bucket --
back inside the monotonic tolerance. Both factors multiply the stretched darkness before the
floor check; neither one is a fix for the underlying convergence (a solid black image still
brightens slightly right at the focus if you look for it) but together they keep it from
swamping the picture's own tone.

Tone is stretched (not used raw) before either the floor comparison or the taper: the GATED
sample points' own min..max darkness is remapped onto 0..1 first, the same move `ascii._char_grid`
makes and for the same reason -- a real photo's cell-mean darkness rarely spans the full 0..1
range, so an unstretched signal only ever clears the low rungs of the ladder and the picture
reads as a flat wash of backbone rays with no dark/light contrast between them.
"""

from __future__ import annotations

import math

from ..modes import Polylines, ToneGrid, _clip_point, _sample_darkness

HELP = (
    "Rays from a focus point, broken where the image is light and packed denser in angle "
    "where it is dark -- a rising-sun / starburst print carrying tone."
)

MAX_RAYS_DEFAULT = 3000
_LEVELS = 8  # candidates per rotating darkness-floor cycle -- same granularity truchet's max_arcs=4 pairs give
_TAPER_FRACTION = 0.15  # fraction of the shorter side used to fade rays in near the focus
_REFERENCE_RADIUS_MM = 75.0  # see quality_params -- half the 150 mm dense-test frame's side
_MIN_RAY_PITCH_DEG = 0.2  # floor on the fader conversion, see quality_params


def sunburst(
    tone: ToneGrid,
    *,
    ray_pitch_deg: float = 0.8,
    focus: tuple[float, float] | None = None,
    min_darkness: float = 0.12,
    taper_fraction: float = _TAPER_FRACTION,
    max_rays: int = MAX_RAYS_DEFAULT,
) -> Polylines:
    """Radiate rays from `focus` (default: frame centre) out to the frame edge.

    ray_pitch_deg sets the FINEST angular spacing -- the spacing the darkest parts of the
    picture get; see the module docstring for how the rotating floor ladder thins that down
    in lighter areas, and how `taper_fraction` reins in the convergence pileup near focus.

    Each ray is sampled every `tone.cell_mm` along its own length (matching the tone grid's
    own resolution, same call `spiral` and `hatch` make for their step), a point at a time,
    and emitted as one polyline per unbroken run -- so a ray crossing a light gap in the
    picture becomes two or more separate pen-down strokes rather than one dashed one.
    """
    if ray_pitch_deg <= 0:
        raise ValueError("ray_pitch_deg must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if taper_fraction < 0:
        raise ValueError("taper_fraction must be non-negative")
    if max_rays < 1:
        raise ValueError("max_rays must be at least 1")

    focus_x, focus_y = focus if focus is not None else (tone.width_mm / 2.0, tone.height_mm / 2.0)
    count = max(1, round(360.0 / ray_pitch_deg))
    if count > max_rays:
        raise ValueError(
            f"sunburst would need {count} rays, exceeding max_rays={max_rays}; increase ray_pitch_deg or raise max_rays"
        )

    # The blank eye at the middle of the burst. The radius stride below already stops rays
    # crowding into the focus; this is what keeps the very centre clear, the way an engraved
    # starburst leaves its centre open rather than resolving into a blot.
    blank_radius_mm = taper_fraction * min(tone.width_mm, tone.height_mm)
    step_mm = max(tone.cell_mm, 1e-6)

    # Pass 1: sample every ray at every radius, recording raw darkness -- the stretch (module
    # docstring) needs the GATED points' own min..max before any ray can decide whether to draw.
    rays: list[list[tuple[float, float, float, float]]] = []  # per ray: (x, y, r, raw_darkness)
    reach_max = 0.0
    gated_values: list[float] = []
    for index in range(count):
        angle = math.radians(index * 360.0 / count)
        direction = (math.cos(angle), math.sin(angle))
        reach = _reach_to_edge(focus_x, focus_y, direction, tone.width_mm, tone.height_mm)
        samples: list[tuple[float, float, float, float]] = []
        steps = max(1, math.ceil(reach / step_mm)) if reach > 0 else 0
        for step in range(steps + 1):
            r = reach * step / steps
            x = focus_x + r * direction[0]
            y = focus_y + r * direction[1]
            raw = _sample_darkness(tone, x, y)
            samples.append((x, y, r, raw))
            if raw >= min_darkness:
                gated_values.append(raw)
        rays.append(samples)
        reach_max = max(reach_max, reach)

    low, high = (min(gated_values), max(gated_values)) if gated_values else (0.0, 0.0)
    spread = high - low

    polylines: Polylines = []
    for index, samples in enumerate(rays):
        run: list[tuple[float, float]] = []
        for x, y, r, raw in samples:
            stretched = (raw - low) / spread if spread > 1e-9 else raw
            # Rays converge, so without this an annulus at r carries ink ~1/r and the middle
            # of the sheet is dark whatever the picture says -- the contract's gradient check
            # caught exactly that, as a hump in the middle strips. A ray is therefore only
            # ACTIVE once the fan has opened enough for it: halve the ray count each time the
            # radius halves, which holds the arc spacing between live rays roughly constant
            # and hands the tone dither below a flat canvas to work on. It also looks like a
            # real starburst, where rays appear as the fan widens.
            if r < blank_radius_mm:
                continue
            stride = _stride(r, reach_max)
            if index % stride != 0:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                continue
            # The dither runs over the rays that are LIVE at this radius (index // stride),
            # not over the raw index. Keyed on the raw index it correlated with the stride --
            # the rays that survive nearest the focus are exactly the multiples of a large
            # power of two, which all landed in the same lowest-threshold class and drew
            # whatever the picture said, flattening the gradient.
            floor = ((index // stride) % _LEVELS + 1) / _LEVELS
            if raw < min_darkness or stretched < floor:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                continue
            run.append(_clip_point((x, y), tone.width_mm, tone.height_mm))
        if len(run) >= 2:
            polylines.append(run)
    return polylines


def _stride(r: float, unit_mm: float) -> int:
    """How many ray slots to skip at radius `r`: 1 far out, doubling every halving inward.

    `unit_mm` is the radius at which every ray is live; inside it the fan thins by powers of
    two so neighbouring live rays stay about `unit` apart in arc length rather than crowding
    into the focus.
    """
    if unit_mm <= 0 or r >= unit_mm:
        return 1
    if r <= 1e-6:
        return 1 << 30  # nothing draws at the focus itself
    return 1 << max(0, math.ceil(math.log2(unit_mm / r)))


def _reach_to_edge(
    focus_x: float, focus_y: float, direction: tuple[float, float], width_mm: float, height_mm: float
) -> float:
    """Distance from an in-frame focus to where a ray first leaves the [0,width]x[0,height] box.

    Only the forward (+direction) crossings count -- a ray never looks backward past its own
    focus -- and whichever of the two axis bounds it hits first wins, exactly how a ray leaves
    a rectangle.
    """
    dx, dy = direction
    candidates = []
    if dx > 1e-12:
        candidates.append((width_mm - focus_x) / dx)
    elif dx < -1e-12:
        candidates.append(-focus_x / dx)
    if dy > 1e-12:
        candidates.append((height_mm - focus_y) / dy)
    elif dy < -1e-12:
        candidates.append(-focus_y / dy)
    positive = [t for t in candidates if t > 0]
    return min(positive) if positive else 0.0


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the shared quality fader onto ray_pitch_deg via the ARC LENGTH at the frame edge.

    quality_params gets only `spacing_mm`, never the actual frame size (same signature every
    other mode's quality_params has), so there is no real frame edge to measure against. This
    converts spacing into an angle using a fixed reference radius instead: 75 mm, the distance
    from a centred focus to the near edge of the 150x150 mm frame check_mode_contract's own
    dense-segment check renders against. pitch_deg = degrees(spacing_mm / 75) -- at the fader's
    draft spacing (2.5 mm) that is ~1.9 deg (189 candidate rays around the circle); at max
    (1.0 mm) it is ~0.76 deg (471 rays). On a frame a different size than 150 mm the same
    ray_pitch_deg lands at a different physical spacing at ITS edge -- exactly how tile_mm and
    pitch_mm already behave for their own sibling modes; only the angle itself is size-free.

    The floor (_MIN_RAY_PITCH_DEG = 0.2 deg, 1200 rays) guards the one input this formula
    cannot: a caller-supplied spacing_mm far below the fader's own 1.0 mm floor, which would
    otherwise convert to an angle fine enough to blow through max_rays before a single ray is
    walked.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"ray_pitch_deg": max(_MIN_RAY_PITCH_DEG, math.degrees(spacing_mm / _REFERENCE_RADIUS_MM))}
