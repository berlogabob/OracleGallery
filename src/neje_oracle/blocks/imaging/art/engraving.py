"""Iso-tone engraving: banknote/woodcut streamlines that wrap the form.

Hatch and crosshatch lay strokes at a FIXED angle and let only line density (and, for
crosshatch, how many angle layers survive) carry tone. Engraving instead steers each stroke
along the LOCAL iso-tone direction -- perpendicular to the darkness gradient, same rotation
flow() uses to hug equal-tone contours -- so a line follows the surface it is shading rather
than crossing it: a cheek turns into a curve of ink, a fold into a fold. Tone is still carried
by density, never by stroke width (a pen only has one), through a coverage grid that spaces
streamline seeds by how dark the paper is there.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _sample_darkness, _smoothed_darkness

HELP = (
    "Iso-tone streamlines, woodcut-style: lines follow the surface instead of crossing it. "
    "Darker areas seed lines closer together; detail = line spacing in mm."
)

MAX_STROKES_DEFAULT = 100_000
# RK2 (midpoint) step: small enough that direction is effectively constant across one step,
# which is the assumption midpoint integration relies on; half of flow's own 0.6 mm Euler
# step because RK2 already buys curvature accuracy that a coarser step would spend right back.
_STEP_MM = 0.5
# 60 steps each way at 0.5 mm is a 60 mm streamline -- long enough to wrap a real form, short
# enough that no single stroke can dominate one bucket of the monotonic-ink check by carrying
# disproportionate length past a darkness boundary.
_MAX_STEPS = 60
# A turn sharper than this between two RK2 steps means the field is near a singularity (a
# gradient zero-crossing the blend below did not fully smooth) rather than following the
# image; stopping the stroke there reads as a clean line end, not a kink.
_MAX_TURN_COS = math.cos(math.radians(60.0))
# Below this gradient magnitude the image is, for practical purposes, flat: a central-
# difference gradient on a smoothed field almost never lands on EXACTLY zero except on a truly
# uniform field, so a hard "== 0" test would leave near-flat regions (paper grain, resample
# noise) pointed wherever their last nonzero neighbour happened to aim -- a visible seam where
# real gradient hands off to noise. Below the floor the direction is BLENDED toward a fixed
# fallback angle in proportion to how far under the floor it is, so the handoff is a gradient
# no eye can find, and a perfectly flat field (gradient == 0 everywhere, the contract's solid
# black case) lands on the fallback outright rather than drawing nothing.
_GRADIENT_FLOOR = 5e-4
# Off-axis (not 0/45/90/135) so a flat region's fallback strokes never alias with hatch's or
# crosshatch's own angles and read as a stray layer of one of those modes instead of this one.
_FALLBACK_ANGLE_DEG = 30.0
# A streamline's target spacing widens as darkness falls toward min_darkness (spacing_for
# below), which is unbounded as darkness -> min_darkness. Capping it keeps the occupancy
# grid's neighbour search (reach in _free) from blowing up on the lightest accepted cells
# without changing the look: past this factor a line is already sparse enough to read as gone.
_MAX_SPACING_FACTOR = 6.0
# Candidate seeds oversample the darkest achievable spacing by 2x so the occupancy grid, not
# the candidate grid, is what actually sets density -- the same role min_spacing_mm plays as
# flow's candidate pitch.
_CANDIDATE_PITCH_FACTOR = 0.5
# Small and symmetric: enough to break the seed lattice's own visible grid, not enough to
# carry a seed across a darkness bucket boundary and bias the monotonic-ink check.
_JITTER_FACTOR = 0.3


def engraving(
    tone: ToneGrid,
    *,
    line_spacing_mm: float = 1.2,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_strokes: int = MAX_STROKES_DEFAULT,
    blur_px: float = 2.0,
) -> Polylines:
    """Seed streamlines darkness-first and trace each one along the iso-tone direction.

    Seeding. Candidate points sit on a fine grid (pitch = line_spacing_mm * 0.5), each nudged
    by a small per-cell-seeded jitter so the result does not read as a lattice. A candidate is
    accepted, darkest first, only if it clears every already-accepted point within its own
    darkness-driven target spacing (spacing_for) on a coverage grid -- the same greedy
    darkest-first / occupancy-grid shape flow() uses for its own seeds, so an unbroken dark
    region seeds tightly and a light one barely seeds at all, smoothly rather than in steps.

    Tracing. Each accepted seed grows a stroke both ways along the local direction field,
    integrated with the midpoint method (RK2): sample the direction at the current point,
    step half a step with it to get a midpoint, resample there, and take the full step along
    THAT direction. A stroke stops at the frame edge, after _MAX_STEPS, when it turns sharper
    than _MAX_TURN_COS, or when the next point is no longer clear on the same coverage grid
    the seeding pass used (so strokes thin out where they would otherwise overlap, instead of
    piling ink on top of ink).

    seed is the only source of randomness (per-candidate-cell RNGs keyed on (seed, row, col),
    never on time or iteration order), so the same tone grid always produces the same strokes.
    """
    if line_spacing_mm <= 0:
        raise ValueError("line_spacing_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_strokes < 1:
        raise ValueError("max_strokes must be at least 1")
    if blur_px < 0:
        raise ValueError("blur_px must be non-negative")

    direction_x, direction_y = _direction_field(tone.darkness, blur_px)
    rows, cols = tone.darkness.shape

    def sample_direction(x: float, y: float) -> tuple[float, float]:
        row = min(max(int(y * rows / tone.height_mm), 0), rows - 1)
        col = min(max(int(x * cols / tone.width_mm), 0), cols - 1)
        return float(direction_x[row, col]), float(direction_y[row, col])

    def spacing_for(darkness_value: float) -> float:
        return min(line_spacing_mm / max(darkness_value, min_darkness), line_spacing_mm * _MAX_SPACING_FACTOR)

    occupancy_cell = line_spacing_mm
    occupancy: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def free(x: float, y: float, spacing: float) -> bool:
        key = (int(x / occupancy_cell), int(y / occupancy_cell))
        reach = max(1, math.ceil(spacing / occupancy_cell))
        for offset_x in range(-reach, reach + 1):
            for offset_y in range(-reach, reach + 1):
                for occupied_x, occupied_y in occupancy.get((key[0] + offset_x, key[1] + offset_y), ()):
                    if math.hypot(occupied_x - x, occupied_y - y) < spacing:
                        return False
        return True

    def mark(x: float, y: float) -> None:
        occupancy.setdefault((int(x / occupancy_cell), int(y / occupancy_cell)), []).append((x, y))

    candidate_pitch = line_spacing_mm * _CANDIDATE_PITCH_FACTOR
    seed_cols = max(1, int(tone.width_mm / candidate_pitch))
    seed_rows = max(1, int(tone.height_mm / candidate_pitch))
    if seed_rows * seed_cols > max_strokes * 50:
        raise ValueError(
            f"engraving would scan {seed_rows * seed_cols} candidate seeds, exceeding "
            f"50x max_strokes={max_strokes}; widen line_spacing_mm or raise max_strokes"
        )

    jitter = candidate_pitch * _JITTER_FACTOR
    candidates: list[tuple[float, float, float]] = []
    for row in range(seed_rows):
        for col in range(seed_cols):
            rng = np.random.default_rng((seed, row, col))
            x = min(tone.width_mm, max(0.0, (col + 0.5) * candidate_pitch + rng.uniform(-jitter, jitter)))
            y = min(tone.height_mm, max(0.0, (row + 0.5) * candidate_pitch + rng.uniform(-jitter, jitter)))
            darkness_value = _sample_darkness(tone, x, y)
            if darkness_value < min_darkness:
                continue
            candidates.append((-darkness_value, x, y))
    # Darkest first, so a dense dark region claims its tight spacing before a lighter
    # neighbour's looser candidates can crowd the coverage grid ahead of it.
    candidates.sort()

    polylines: Polylines = []
    for _, start_x, start_y in candidates:
        if len(polylines) >= max_strokes:
            break
        spacing = spacing_for(_sample_darkness(tone, start_x, start_y))
        if not free(start_x, start_y, spacing):
            continue
        pending = [(start_x, start_y)]
        path = [(start_x, start_y)]
        for sign in (1, -1):
            x, y = start_x, start_y
            direction_x_at, direction_y_at = sample_direction(x, y)
            side: list[tuple[float, float]] = []
            for _step in range(_MAX_STEPS):
                mid_x = x + 0.5 * _STEP_MM * sign * direction_x_at
                mid_y = y + 0.5 * _STEP_MM * sign * direction_y_at
                mid_direction_x, mid_direction_y = sample_direction(mid_x, mid_y)
                if direction_x_at * mid_direction_x + direction_y_at * mid_direction_y < _MAX_TURN_COS:
                    break
                new_x = x + _STEP_MM * sign * mid_direction_x
                new_y = y + _STEP_MM * sign * mid_direction_y
                if not (0.0 <= new_x <= tone.width_mm and 0.0 <= new_y <= tone.height_mm):
                    break
                new_darkness = _sample_darkness(tone, new_x, new_y)
                if new_darkness < min_darkness or not free(new_x, new_y, spacing_for(new_darkness) * 0.6):
                    break
                x, y, direction_x_at, direction_y_at = new_x, new_y, mid_direction_x, mid_direction_y
                side.append((x, y))
                pending.append((x, y))
            path = path + side if sign == 1 else side[::-1] + path
        for point_x, point_y in pending:
            mark(point_x, point_y)
        if len(path) >= 2:
            polylines.append([_clip_point(point, tone.width_mm, tone.height_mm) for point in path])
    return polylines


def _direction_field(darkness: np.ndarray, blur_px: float) -> tuple[np.ndarray, np.ndarray]:
    """Unit iso-tone direction at every cell: the gradient rotated 90 deg, blended to a
    fixed fallback angle where the gradient is too weak to trust (see _GRADIENT_FLOOR).
    """
    smoothed = _smoothed_darkness(darkness, blur_px)
    gradient_y, gradient_x = np.gradient(smoothed)
    iso_x, iso_y = -gradient_y, gradient_x
    magnitude = np.hypot(iso_x, iso_y)
    safe_magnitude = np.where(magnitude > 0, magnitude, 1.0)
    normal_x, normal_y = iso_x / safe_magnitude, iso_y / safe_magnitude

    fallback_x = math.cos(math.radians(_FALLBACK_ANGLE_DEG))
    fallback_y = math.sin(math.radians(_FALLBACK_ANGLE_DEG))
    weight = np.clip(magnitude / _GRADIENT_FLOOR, 0.0, 1.0)
    blended_x = weight * normal_x + (1.0 - weight) * fallback_x
    blended_y = weight * normal_y + (1.0 - weight) * fallback_y
    blended_magnitude = np.hypot(blended_x, blended_y)
    blended_magnitude = np.where(blended_magnitude > 0, blended_magnitude, 1.0)
    return blended_x / blended_magnitude, blended_y / blended_magnitude


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader directly onto line_spacing_mm -- no scaling.

    Unlike tile/ring/pitch modes whose natural unit sits wider than the fader's own numbers,
    engraving's spacing IS a streamline spacing already, in the same mm the fader speaks. The
    floor is the fader's own finest step, 1.0 mm: below that, the RK2 step (_STEP_MM = 0.5 mm)
    stops leaving two step-widths of clearance between neighbouring streamlines, so tighter
    spacing would start starving the occupancy grid rather than adding real density. 1.0 mm
    sits comfortably above that floor, so every finer fader step still means visibly finer
    engraving.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"line_spacing_mm": spacing_mm}
