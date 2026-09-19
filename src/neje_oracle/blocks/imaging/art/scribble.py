"""One continuous chaotic scribble, looping tighter and revisiting more where the image is
dark -- the classic hand-scribbled portrait. Unlike squiggle (a row-based sine sweep) and
spiral (one Archimedean spiral wobbling with tone), the path here has no fixed shape at all:
it wanders the frame freely, pulled step by step toward whatever darkness it has not yet
inked, so ink accumulates into the picture the way a hand scribbling a likeness does.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point

HELP = (
    "One unbroken scribble that loops tighter and revisits more where the image is dark. "
    "Almost no pen lifts; detail = step size in mm."
)

# Hard ceiling on steps regardless of sheet size or darkness -- a perf-only safety valve, not
# a contrast lever. Termination is normally the residual field running out (see scribble());
# this only guards a caller-supplied width_mm/height_mm/darkness combination pathological
# enough that the walk cannot spend its own ink budget efficiently.
MAX_STEPS_DEFAULT = 300_000
# max_steps, when not given, is a generous multiple of the theoretical minimum
# (total residual mm / step_mm) rather than an independent estimate, since the walk wastes
# some steps travelling through cells it isn't targeting on the way to one it is.
_STEP_BUDGET_MULTIPLIER = 8.0
# Ink laid per mm^2 of a cell at full (stretched) darkness, in mm of stroke length -- the ONE
# knob that sets how much ink darkness earns, in physical units instead of a tone-curve
# exponent. residual[cell] = stretched_darkness[cell] * _INK_MM_PER_MM2 * cell_area_mm2 is
# then literally "how many mm of stroke this cell still owes", the walk subtracts exactly
# what it draws (see _deposit), and a cell stops pulling the pen the moment that's paid off --
# so ink per unit area is proportional to darkness BY CONSTRUCTION, with no exponent anywhere
# to separately tune or retune. An earlier design instead scaled total STEP COUNT by mean
# darkness and reshaped local pull with a gamma exponent; measured across three photo
# renders, that gamma was what kept trading one failure for the other (gentle -> uniform
# wash, aggressive -> a hard-edged silhouette) because it was fighting the geometry rather
# than describing it. 0.4 (== a full-darkness cell earning the ink density of roughly a 2.5 mm
# hatch pitch) was measured against a real photo to keep even the darkest region well short of
# a solid mass -- a first attempt at 2.2 (a ~0.45 mm pitch, near-solid at full darkness)
# oversaturated almost the entire gated area, because on a real photo even the MID-tones cover
# most of the frame -- see test_mode_scribble.py's contract report for the resulting segment
# counts.
_INK_MM_PER_MM2 = 0.4
# How many steps the walker takes toward one target before a fresh one is drawn, and how far
# (in cells) that target may be picked from -- both bound the per-retarget numpy work to a
# small window rather than ever scanning the whole residual grid every step, and both also
# set how tightly the path tracks local structure: wider values let the walk commute long,
# mostly-straight runs between distant targets, which blurs a subject into its background.
_RETARGET_STEPS = 5
_SEARCH_RADIUS_CELLS = 4
# Stop once remaining residual falls to this fraction of the frame's own starting total --
# not exactly 0, because some residual mm always sits in cells the walk cannot land on
# exactly (a step lands where step_mm and the walk's own heading put it, not wherever would
# perfectly zero a cell), so a literal 0 target is never reached in finite time. Relative,
# not absolute, so it scales the same way between a postage stamp and a poster.
_DONE_FRACTION = 0.02
_MOMENTUM = 0.82  # heading kept each step; (1 - this) is how fast a new pull bends the path
_WOBBLE_RAD = 0.5  # per-step heading tremor (std, radians) -- the hand-shake that reads as
# scribbled rather than as a vector routed straight at each target


def scribble(
    tone: ToneGrid,
    *,
    step_mm: float = 1.5,
    min_darkness: float = 0.12,
    seed: int = 0,
    max_steps: int | None = None,
) -> Polylines:
    """Walk one unbroken path, pulled toward nearby unspent darkness, until it runs out.

    Residual field, in millimetres of ink. Every gated cell starts owing
    `stretched_darkness * _INK_MM_PER_MM2 * cell_area_mm2` of stroke length -- see
    _INK_MM_PER_MM2 above for why this is the only ink-vs-darkness lever, with no separate
    tone-curve exponent. Every step subtracts exactly the length it actually draws from the
    cells it crosses (see _deposit), floored at zero, so a cell that has had its ink stops
    attracting the pen -- the walk may still cross it on the way somewhere else, but nothing
    pulls it back once its own residual is spent. Retargeting (every `_RETARGET_STEPS` steps,
    or sooner on arrival) picks a darkness-weighted random cell within `_SEARCH_RADIUS_CELLS`,
    so the walk keeps circling back into whatever of that window is still unspent; darker
    cells simply own more residual, so they naturally draw more revisits before that supply
    runs out. That is the entire "tighter where it's dark" effect. If the local window is
    fully spent the search falls back to the single darkest cell left anywhere, so a sparse
    image with one remaining dark island still gets found rather than stalling the walk in
    exhausted territory.

    Stretch. Exactly ascii._char_grid's move: the GATED cells' own min..max is mapped onto
    [0, 1] before it scales anything, because a real photo's cell darkness usually only
    occupies a narrow slice of the full range (area-averaging compresses variance), and
    scaling ink off the raw values would starve everything but the darkest handful of cells
    of any residual at all. Cells below min_darkness own no residual and are never a target,
    which is the only gating this mode does -- unlike spiral/squiggle it does NOT lift the pen
    when the path itself happens to cross a light or gated-out cell; a scribble that lifted
    every time it crossed white paper would give up its entire reason to exist. min_darkness
    governs where the walker is PULLED, not whether ink is laid while passing through -- so it
    is also the only thing standing between a genuinely light background and the paper it
    should leave blank; the default (0.12) sits above a typical soft-gradient background
    (measured ~0.08 on a real render) but below the usual light-grey-foreground test (~0.16).

    One polyline. There is no other lift condition either, so this always returns a single
    polyline (or none, if nothing clears min_darkness) -- see the "stroke count" test for the
    measured number on a dense render.

    Smoothing. Momentum blends each step's pull-to-target with the previous heading, and a
    small per-step Gaussian wobble is added on top before that blend -- together these are
    what makes the result read as a hand scribbling rather than a router tracing straight
    lines between waypoints or a jittery random walk with no throughline.

    Boundary. A step that would leave the frame has the crossed axis of its heading flipped
    (bounced) rather than being clamped onto the edge, which would otherwise drag several
    consecutive points onto the same border and read as a ruled line.

    max_steps, when not given, is a generous multiple of the frame's own total residual /
    step_mm (see _STEP_BUDGET_MULTIPLIER) -- a perf safety valve, since the walk normally
    stops on its own once residual is spent (_DONE_FRACTION), well before that cap.
    """
    if step_mm <= 0:
        raise ValueError("step_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")

    rows, cols = tone.darkness.shape
    cell_w = tone.width_mm / cols
    cell_h = tone.height_mm / rows
    cell_area = cell_w * cell_h

    gate = tone.darkness >= min_darkness
    if not gate.any():
        return []
    gated_values = tone.darkness[gate]
    low, high = float(gated_values.min()), float(gated_values.max())
    spread = high - low
    stretched = (tone.darkness - low) / spread if spread > 1e-9 else tone.darkness
    linear = np.where(gate, stretched, 0.0)
    # Ink owed, in mm of stroke length -- see the module docstring's "Residual field".
    residual = linear * _INK_MM_PER_MM2 * cell_area

    remaining = float(residual.sum())
    if max_steps is None:
        max_steps = min(MAX_STEPS_DEFAULT, math.ceil(_STEP_BUDGET_MULTIPLIER * remaining / step_mm))

    rng = np.random.default_rng(seed)

    start_row, start_col = (int(index) for index in np.unravel_index(np.argmax(residual), residual.shape))
    point = ((start_col + 0.5) * cell_w, (start_row + 0.5) * cell_h)
    heading_vec = _rotate((1.0, 0.0), float(rng.uniform(0.0, math.tau)))

    path: list[tuple[float, float]] = [point]
    done_at = remaining * _DONE_FRACTION
    target = _pick_target(residual, start_row, start_col, cell_w, cell_h, rng)
    since_retarget = 0

    for _ in range(max_steps):
        if remaining <= done_at:
            break

        dx, dy = target[0] - point[0], target[1] - point[1]
        distance = math.hypot(dx, dy)
        if distance < step_mm or since_retarget >= _RETARGET_STEPS:
            row = min(rows - 1, max(0, int(point[1] / cell_h)))
            col = min(cols - 1, max(0, int(point[0] / cell_w)))
            target = _pick_target(residual, row, col, cell_w, cell_h, rng)
            since_retarget = 0
            dx, dy = target[0] - point[0], target[1] - point[1]
            distance = math.hypot(dx, dy)

        desired = (dx / distance, dy / distance) if distance > 1e-9 else heading_vec
        desired = _rotate(desired, float(rng.normal(0.0, _WOBBLE_RAD)))
        heading_vec = _normalize(
            (
                _MOMENTUM * heading_vec[0] + (1 - _MOMENTUM) * desired[0],
                _MOMENTUM * heading_vec[1] + (1 - _MOMENTUM) * desired[1],
            )
        )

        next_point = (point[0] + heading_vec[0] * step_mm, point[1] + heading_vec[1] * step_mm)
        if not 0.0 <= next_point[0] <= tone.width_mm:
            heading_vec = (-heading_vec[0], heading_vec[1])
            next_point = (point[0] + heading_vec[0] * step_mm, next_point[1])
        if not 0.0 <= next_point[1] <= tone.height_mm:
            heading_vec = (heading_vec[0], -heading_vec[1])
            next_point = (next_point[0], point[1] + heading_vec[1] * step_mm)
        next_point = _clip_point(next_point, tone.width_mm, tone.height_mm)

        remaining -= _deposit(residual, cell_w, cell_h, rows, cols, point, next_point)
        path.append(next_point)
        point = next_point
        since_retarget += 1

    return [path] if len(path) >= 2 else []


def _pick_target(
    residual: np.ndarray,
    row: int,
    col: int,
    cell_w: float,
    cell_h: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """A darkness-weighted point near (row, col); falls back to the single darkest cell left
    anywhere once the local window is fully spent (see the module docstring's "Residual
    field" section).
    """
    rows, cols = residual.shape
    r0, r1 = max(0, row - _SEARCH_RADIUS_CELLS), min(rows, row + _SEARCH_RADIUS_CELLS + 1)
    c0, c1 = max(0, col - _SEARCH_RADIUS_CELLS), min(cols, col + _SEARCH_RADIUS_CELLS + 1)
    window = residual[r0:r1, c0:c1]
    total = window.sum()
    if total > 0:
        choice = int(rng.choice(window.size, p=(window / total).ravel()))
        target_row = r0 + choice // window.shape[1]
        target_col = c0 + choice % window.shape[1]
    else:
        target_row, target_col = (int(index) for index in np.unravel_index(np.argmax(residual), residual.shape))
    jitter_x = float(rng.uniform(-0.5, 0.5)) * cell_w
    jitter_y = float(rng.uniform(-0.5, 0.5)) * cell_h
    return (target_col + 0.5) * cell_w + jitter_x, (target_row + 0.5) * cell_h + jitter_y


def _deposit(
    residual: np.ndarray,
    cell_w: float,
    cell_h: float,
    rows: int,
    cols: int,
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Subtract this step's own length from every cell the a->b segment crosses, split by how
    much of that length falls in each one, so the total removed is exactly the segment's
    length (== step_mm, except the rare boundary-clamped step) as long as every crossed cell
    still owes at least that much. Returns the amount actually removed (less than the full
    length once a crossed cell is already nearly spent), so the caller can track remaining
    demand without re-summing the whole grid every step.
    """
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    samples = max(1, math.ceil(length / min(cell_w, cell_h)))
    share = length / samples
    removed = 0.0
    for index in range(1, samples + 1):
        t = index / samples
        col = min(cols - 1, max(0, int((a[0] + (b[0] - a[0]) * t) / cell_w)))
        row = min(rows - 1, max(0, int((a[1] + (b[1] - a[1]) * t) / cell_h)))
        before = residual[row, col]
        after = max(0.0, before - share)
        removed += before - after
        residual[row, col] = after
    return removed


def _rotate(vector: tuple[float, float], angle: float) -> tuple[float, float]:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return vector[0] * cos_a - vector[1] * sin_a, vector[0] * sin_a + vector[1] * cos_a


def _normalize(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*vector)
    return (vector[0] / length, vector[1] / length) if length > 1e-9 else (1.0, 0.0)


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto step_mm, floored at 0.6 mm.

    step_mm = spacing_mm * 0.6 lines the draft tier (spacing 2.5) up with this mode's own
    default (step_mm 1.5) and keeps shrinking as spacing shrinks -- so every finer step still
    adds detail, as the fader promises. Below 0.6 mm the floor takes over: a finer step means
    more of them are needed to spend the same residual (see scribble()), so an unfloored step
    at the finest tier (spacing 1.0) would multiply the per-step Python loop's own iteration
    count for no visible gain -- 0.6 mm is already finer than the plotter's pen width and well
    past where extra steps resolve more curvature.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"step_mm": max(0.6, spacing_mm * 0.6)}
