"""Shatter: cracks radiating from impact points, like broken glass.

Real fracture is not a field of independent wandering scratches; it is radial. An impact is a
point that throws several cracks outward, roughly evenly spaced in angle, each running a long
way -- a good fraction of the frame -- before it dies or meets another crack. Neighbouring
radials from the same impact are often tied together by a short crack running between them some
distance out, which is what makes the pattern read as a shattered pane rather than as scribbles:
the radial-plus-ring combination IS the signature. So an impact places N radials (`_RADIALS_MIN`
.. `_RADIALS_MAX`, more where the image is dark) and a handful of cross-links between adjacent
ones; a radial can also fork further out, a lesser, secondary effect. Every crack -- radial,
cross-link or fork -- still stops dead the instant it meets another one: that termination is a
proper segment-segment intersection test (see `_intersect`), not an endpoint-proximity check,
because a crack must be able to stop in the MIDDLE of an earlier one, which is what turns a
meeting into an honest T-junction instead of a crossing. Compare with the sibling `voronoi`
mode: that one closes cells into a mosaic; this one never closes anything, cracks are open
curves that terminate against each other.

The image drives where the glass breaks. Impact probability, radial count and radial length all
come from one per-cell darkness grid (pitch = crack_spacing_mm), gated by min_darkness and then
STRETCHED -- the gated cells' own min..max mapped onto 0..1 -- exactly as `ascii._char_grid`
does before picking a glyph. Without that stretch, a typical photo's cell-mean darkness clusters
in a narrow middle band (area-averaging compresses contrast the same way it does for ascii) and
every impact would look the same regardless of how dark its neighbourhood really is.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _stitch, cell_darkness

HELP = (
    "Cracks radiating from impact points, like shattered glass. Darkness sets how many impacts "
    "there are and how much each one branches; a crack stops dead where it meets another one."
)

MAX_CRACKS_DEFAULT = 20_000
_MAX_IMPACT_CELLS = 250_000  # cols * rows before impact placement runs; see the guard below.

_STEP_FRACTION = 0.15  # one propagation step, as a fraction of crack_spacing_mm.
_STEP_MM_FLOOR = 0.35  # steps this short would only add vertices a plotter nib can't resolve.
_JITTER_RAD = math.radians(5.0)  # per-step heading noise -- kept small so a LONG radial still
# reads as "roughly straight", not a random walk that has forgotten where it started.

_IMPACT_PROB_FLOOR, _IMPACT_PROB_CEIL = 0.1, 0.7  # chance a gated cell becomes an impact.
_IMPACT_TRIALS_PER_CELL = 20  # independent placement rolls per cell; see the seeding loop.
_RADIALS_MIN, _RADIALS_MAX = 3, 7  # cracks thrown from one impact, more where it's darker.
_RADIAL_ANGLE_JITTER = math.radians(18.0)  # scatter around perfectly even angular spacing.
_RADIAL_LEN_FRAC_FLOOR, _RADIAL_LEN_FRAC_CEIL = 0.06, 0.42  # radial length as a fraction of
# min(width_mm, height_mm) -- "a good fraction of the frame" at full darkness, still a real
# crack (not a stub) near the gate.

_CROSS_LINKS_MAX = 3  # rings tying adjacent radials together, more where it's darker.
_CROSS_FRAC_MIN, _CROSS_FRAC_MAX = 0.25, 0.65  # how far out along each radial a link lands.
_CROSS_LINK_MAX_STEPS = 60  # a link aims at a specific point; this is a sanity cap, not a target.

_FORK_PROB_MAX = 0.035  # per-step chance a radial (or link) throws a secondary branch; the
# radial/cross-link structure carries the tone now, forking is a lesser, occasional effect.
_FORK_ANGLE_MIN, _FORK_ANGLE_MAX = math.radians(20.0), math.radians(55.0)
_MIN_CHILD_ENERGY = 6  # a fork with less budget than this reads as a stub, not a branch.
_CHILD_ENERGY_FRACTION = 0.5  # a branch carries about half the parent's remaining energy.

_JOIN_TOLERANCE_MM = 1e-6  # exact float match only -- see truchet.py for why.
_HIT_EPS = 1e-9  # excludes a segment's own start point from hitting itself at t=0.


def shatter(
    tone: ToneGrid,
    *,
    crack_spacing_mm: float = 4.0,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_cracks: int = MAX_CRACKS_DEFAULT,
) -> Polylines:
    """Grow a field of glass cracks radiating from impact points, following the tone.

    Impacts. The sheet is scored on a crack_spacing_mm lattice (mean darkness per cell, via
    `cell_darkness`), gated at min_darkness, then stretched (see module docstring). Whether a
    gated cell becomes an impact at all is a coin flip biased by the stretched value
    (IMPACT_PROB_FLOOR at the gate, IMPACT_PROB_CEIL at full darkness) -- impacts stay sparse
    even in solid black, because the tone here is meant to ride on branching and radial length,
    not on carpeting the sheet with impact points.

    Radials. Each impact throws RADIALS_MIN..RADIALS_MAX cracks (more where it's darker),
    evenly spaced in angle with a little jitter so they don't look drafted, each with its own
    length budget: RADIAL_LEN_FRAC_FLOOR..CEIL of the sheet's shorter side, scaled by the same
    stretched darkness. This is the fix for "cracks read as short ticks": length now rides on
    darkness the way count used to, so a dark impact's radials genuinely run most of the way
    across the frame while a faint one still draws a real, if shorter, crack.

    Cross-links. After an impact's radials are drawn, up to CROSS_LINKS_MAX short cracks are
    aimed from a point partway out on one radial toward the matching point on its angular
    neighbour -- rings tying the spokes together, the second half of what makes this read as
    fracture and not as a starburst of independent lines. A link that misses its target for any
    reason (jitter, an intervening crack) just stops wherever it stops; it does not need to
    land exactly.

    Propagation (shared by radials, cross-links, and forks). A crack advances in fixed steps of
    step_mm, adding small Gaussian heading jitter every step. Every step is checked, in order,
    against: (1) the frame -- outside it, the crack is clipped to the boundary and ends; (2)
    every previously drawn segment, via a proper segment-segment intersection test (not an
    endpoint-proximity one, since a crack must be able to stop in the MIDDLE of an earlier one)
    -- a hit clips the step to the intersection point and ends the crack there, the T-junction;
    (3) its own energy, spent one step at a time -- out of energy is "leaves out of steam". Fork
    probability at each surviving step is stretched-darkness-at-that-point * FORK_PROB_MAX, a
    lesser effect layered on top of the radial/cross-link structure.

    Budget. Total cracks (radials + cross-links + forks) never exceeds max_cracks -- decremented
    the instant one is granted, before it is walked, so it is an exact cap, not a soft target.
    Every individual crack's own step count is bounded too (a radial by its length fraction of
    the sheet, a cross-link by CROSS_LINK_MAX_STEPS, a fork by its parent's remaining energy),
    so total segments are bounded with no dependence on input pathology.

    Joining (52% of plot time is pen lifts). A crack is naturally one long polyline already; the
    only break in that is a fork, which starts a new chain sharing its parent's exact current
    point. Every chain is handed to `_stitch` in one pass at near-zero tolerance, so wherever
    float endpoints coincide exactly (they do: both sides compute the fork point identically)
    the fork rejoins its parent into one stroke, exactly like truchet's edge-midpoint joins.
    """
    if crack_spacing_mm <= 0:
        raise ValueError("crack_spacing_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_cracks < 1:
        raise ValueError("max_cracks must be at least 1")

    cols = max(1, math.ceil(tone.width_mm / crack_spacing_mm))
    rows = max(1, math.ceil(tone.height_mm / crack_spacing_mm))
    if rows * cols > _MAX_IMPACT_CELLS:
        raise ValueError(
            f"shatter would need {rows * cols} impact cells, exceeding _MAX_IMPACT_CELLS={_MAX_IMPACT_CELLS}; "
            "increase crack_spacing_mm or reduce the drawing size"
        )

    density = _stretched_density(tone, rows, cols, crack_spacing_mm, min_darkness)
    step_mm = max(_STEP_MM_FLOOR, crack_spacing_mm * _STEP_FRACTION)
    short_side = min(tone.width_mm, tone.height_mm)
    index = _SegmentIndex(max(step_mm * 2.0, 1e-3))
    chains: Polylines = []
    pending: list[tuple[float, float, float, int]] = []
    remaining = [max_cracks]

    for row in range(rows):
        if remaining[0] <= 0:
            break
        for col in range(cols):
            if remaining[0] <= 0:
                break
            d = density[row, col]
            if d < 0.0:
                continue
            # Several cheap, independently-rolled trials per cell rather than one Bernoulli
            # draw at the cell's own probability: same expected impact density, but a lot less
            # sample-count noise -- one trial per cell put so few impacts in a lightly-gated
            # bucket that ink swung up and down between neighbouring buckets by pure chance,
            # which is exactly what the monotonic-gradient check exists to catch.
            prob = (_IMPACT_PROB_FLOOR + d * (_IMPACT_PROB_CEIL - _IMPACT_PROB_FLOOR)) / _IMPACT_TRIALS_PER_CELL
            for sub in range(_IMPACT_TRIALS_PER_CELL):
                if remaining[0] <= 0:
                    break
                impact_rng = np.random.default_rng((seed, row, col, sub))
                if impact_rng.random() > prob:
                    continue
                ix = min(tone.width_mm, (col + impact_rng.uniform(0.1, 0.9)) * crack_spacing_mm)
                iy = min(tone.height_mm, (row + impact_rng.uniform(0.1, 0.9)) * crack_spacing_mm)
                pending.extend(
                    _spawn_impact(
                        tone,
                        density,
                        crack_spacing_mm,
                        step_mm,
                        short_side,
                        ix,
                        iy,
                        d,
                        index,
                        chains,
                        remaining,
                        (seed, row, col, sub),
                    )
                )

    cursor = 0
    while cursor < len(pending) and remaining[0] > 0:
        x, y, angle, energy = pending[cursor]
        remaining[0] -= 1
        rng = np.random.default_rng((seed, 2, cursor))
        forks, _ = _propagate(
            tone, density, crack_spacing_mm, step_mm, x, y, angle, energy, index, chains, rng, remaining
        )
        pending.extend(forks)
        cursor += 1

    joined = _stitch(chains, _JOIN_TOLERANCE_MM)
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in joined]


def _spawn_impact(
    tone: ToneGrid,
    density: np.ndarray,
    crack_spacing_mm: float,
    step_mm: float,
    short_side: float,
    ix: float,
    iy: float,
    d: float,
    index: _SegmentIndex,
    chains: Polylines,
    remaining: list[int],
    rng_key: tuple[int, int, int, int],
) -> list[tuple[float, float, float, int]]:
    """One impact: RADIALS_MIN..MAX cracks out from (ix, iy), then a few cross-links between
    adjacent ones. Returns the forks any of them spawned, for the caller's own queue.
    """
    radial_count = round(_RADIALS_MIN + d * (_RADIALS_MAX - _RADIALS_MIN))
    length_frac = _RADIAL_LEN_FRAC_FLOOR + d * (_RADIAL_LEN_FRAC_CEIL - _RADIAL_LEN_FRAC_FLOOR)
    radial_energy = max(4, round(short_side * length_frac / step_mm))

    pending: list[tuple[float, float, float, int]] = []
    trunks: list[list[tuple[float, float]]] = []
    for i in range(radial_count):
        if remaining[0] <= 0:
            break
        remaining[0] -= 1
        rng = np.random.default_rng((*rng_key, 0, i))
        angle = (math.tau * i / radial_count) + float(rng.uniform(-_RADIAL_ANGLE_JITTER, _RADIAL_ANGLE_JITTER))
        forks, trunk = _propagate(
            tone, density, crack_spacing_mm, step_mm, ix, iy, angle, radial_energy, index, chains, rng, remaining
        )
        pending.extend(forks)
        trunks.append(trunk)

    n_cross = min(len(trunks) - 1, round(d * _CROSS_LINKS_MAX))
    for k in range(max(0, n_cross)):
        if remaining[0] <= 0:
            break
        a_trunk, b_trunk = trunks[k], trunks[(k + 1) % len(trunks)]
        if len(a_trunk) < 2 or len(b_trunk) < 2:
            continue
        rng = np.random.default_rng((*rng_key, 1, k))
        frac = float(rng.uniform(_CROSS_FRAC_MIN, _CROSS_FRAC_MAX))
        a_point = a_trunk[max(1, round(frac * (len(a_trunk) - 1)))]
        b_point = b_trunk[max(1, round(frac * (len(b_trunk) - 1)))]
        distance = math.dist(a_point, b_point)
        if distance < 1e-6:
            continue
        remaining[0] -= 1
        aim = math.atan2(b_point[1] - a_point[1], b_point[0] - a_point[0])
        cross_energy = max(2, min(_CROSS_LINK_MAX_STEPS, math.ceil(distance / step_mm * 1.3)))
        forks, _ = _propagate(
            tone,
            density,
            crack_spacing_mm,
            step_mm,
            a_point[0],
            a_point[1],
            aim,
            cross_energy,
            index,
            chains,
            rng,
            remaining,
        )
        pending.extend(forks)

    return pending


def _stretched_density(
    tone: ToneGrid, rows: int, cols: int, crack_spacing_mm: float, min_darkness: float
) -> np.ndarray:
    """Per-cell darkness, gated then stretched onto 0..1 -- see module docstring. -1 = ungated."""
    raw = np.empty((rows, cols))
    for row in range(rows):
        y0, y1 = row * crack_spacing_mm, min((row + 1) * crack_spacing_mm, tone.height_mm)
        for col in range(cols):
            x0, x1 = col * crack_spacing_mm, min((col + 1) * crack_spacing_mm, tone.width_mm)
            raw[row, col] = cell_darkness(tone.darkness, x0, y0, x1, y1, tone.width_mm, tone.height_mm)

    gate = raw >= min_darkness
    if not gate.any():
        return np.full((rows, cols), -1.0)
    low, high = float(raw[gate].min()), float(raw[gate].max())
    spread = high - low
    # Degenerate case (all gated cells equally dark, e.g. a flat test swatch): fall back to the
    # raw value rather than a constant, exactly as ascii._char_grid's normalized() does -- a
    # flat 0/0 stretch must not erase the one signal a uniform image still carries (how dark).
    normalized = (raw - low) / spread if spread > 1e-9 else raw
    return np.where(gate, np.clip(normalized, 0.0, 1.0), -1.0)


def _density_at(density: np.ndarray, point: tuple[float, float], crack_spacing_mm: float) -> float:
    """Stretched darkness of the cell a crack is currently passing through (0.0 if ungated)."""
    rows, cols = density.shape
    row = min(rows - 1, max(0, int(point[1] / crack_spacing_mm)))
    col = min(cols - 1, max(0, int(point[0] / crack_spacing_mm)))
    value = density[row, col]
    return value if value > 0.0 else 0.0


def _propagate(
    tone: ToneGrid,
    density: np.ndarray,
    crack_spacing_mm: float,
    step_mm: float,
    x: float,
    y: float,
    angle: float,
    energy: int,
    index: _SegmentIndex,
    chains: Polylines,
    rng: np.random.Generator,
    remaining: list[int],
) -> tuple[list[tuple[float, float, float, int]], list[tuple[float, float]]]:
    """Walk one crack to its end, appending finished chains to `chains` in place.

    Returns (forks, trunk): forks are (x, y, angle, energy) starts for the caller's own queue,
    kept separate from `chains` so the caller decides processing order. trunk is every point
    this call actually visited, in order, regardless of any fork-driven chain split -- the
    caller uses it (for a radial) to pick a point partway out for a cross-link to aim at.
    """
    forks: list[tuple[float, float, float, int]] = []
    points: list[tuple[float, float]] = [(x, y)]
    trunk: list[tuple[float, float]] = [(x, y)]
    pos = (x, y)
    while energy > 0:
        angle += float(rng.normal(0.0, _JITTER_RAD))
        nxt = (pos[0] + step_mm * math.cos(angle), pos[1] + step_mm * math.sin(angle))

        # Both the frame boundary and an existing crack can cut this step short; whichever one
        # the step reaches FIRST (smaller t) is the one that actually ends it -- checking only
        # one, unconditionally, let an exiting step sail through another crack it should have
        # stopped at, right at a corner where an out-of-frame check alone never looks.
        t_exit = _exit_t(pos, nxt, tone.width_mm, tone.height_mm)
        hit = index.first_hit(pos, nxt)

        if hit is not None and (t_exit is None or hit[0] <= t_exit):
            index.add(pos, hit[1])
            points.append(hit[1])
            trunk.append(hit[1])
            break
        if t_exit is not None:
            end = _clip_point(
                (pos[0] + (nxt[0] - pos[0]) * t_exit, pos[1] + (nxt[1] - pos[1]) * t_exit),
                tone.width_mm,
                tone.height_mm,
            )
            if end != pos:
                index.add(pos, end)
                points.append(end)
                trunk.append(end)
            break

        index.add(pos, nxt)
        points.append(nxt)
        trunk.append(nxt)
        pos = nxt
        energy -= 1

        d = _density_at(density, pos, crack_spacing_mm)
        if energy >= _MIN_CHILD_ENERGY and remaining[0] > 0 and d > 0.0 and rng.random() < d * _FORK_PROB_MAX:
            remaining[0] -= 1
            sign = 1.0 if rng.random() < 0.5 else -1.0
            branch_angle = angle + sign * rng.uniform(_FORK_ANGLE_MIN, _FORK_ANGLE_MAX)
            child_energy = max(_MIN_CHILD_ENERGY, round(energy * _CHILD_ENERGY_FRACTION))
            forks.append((pos[0], pos[1], branch_angle, child_energy))
            chains.append(points)
            points = [pos]  # parent continues as a fresh chain sharing this exact point.

    chains.append(points)
    return forks, trunk


def _exit_t(
    inside: tuple[float, float], outside: tuple[float, float], width_mm: float, height_mm: float
) -> float | None:
    """t in (0, 1] where inside->outside first crosses the frame, or None if it never leaves."""
    if 0.0 <= outside[0] <= width_mm and 0.0 <= outside[1] <= height_mm:
        return None
    dx, dy = outside[0] - inside[0], outside[1] - inside[1]
    candidates = [1.0]
    if dx > 0:
        candidates.append((width_mm - inside[0]) / dx)
    elif dx < 0:
        candidates.append(-inside[0] / dx)
    if dy > 0:
        candidates.append((height_mm - inside[1]) / dy)
    elif dy < 0:
        candidates.append(-inside[1] / dy)
    return min(c for c in candidates if c >= 0.0)


class _SegmentIndex:
    """Grid-bucketed segments, so a new step only tests the handful of cracks near it.

    Bucketed on a segment's full bounding box (a step can span several cells), because this
    needs a real segment-segment intersection test -- a new crack must be able to stop against
    the MIDDLE of an earlier one, not just its endpoints, or two cracks could visibly cross.
    """

    def __init__(self, cell_mm: float) -> None:
        self._cell = max(cell_mm, 1e-6)
        self._buckets: dict[tuple[int, int], list[tuple[tuple[float, float], tuple[float, float]]]] = defaultdict(list)

    def _keys(self, p: tuple[float, float], q: tuple[float, float]) -> list[tuple[int, int]]:
        x0, x1 = sorted((p[0], q[0]))
        y0, y1 = sorted((p[1], q[1]))
        col0, col1 = int(x0 // self._cell), int(x1 // self._cell)
        row0, row1 = int(y0 // self._cell), int(y1 // self._cell)
        return [(row, col) for row in range(row0, row1 + 1) for col in range(col0, col1 + 1)]

    def add(self, p: tuple[float, float], q: tuple[float, float]) -> None:
        segment = (p, q)
        for key in self._keys(p, q):
            self._buckets[key].append(segment)

    def first_hit(self, p: tuple[float, float], q: tuple[float, float]) -> tuple[float, tuple[float, float]] | None:
        """(t, point) for the nearest place p->q meets an already-drawn segment, if any."""
        best: tuple[float, tuple[float, float]] | None = None
        seen: set[int] = set()
        for key in self._keys(p, q):
            for other in self._buckets.get(key, ()):
                if id(other) in seen:
                    continue
                seen.add(id(other))
                hit = _intersect(p, q, other[0], other[1])
                if hit is not None and (best is None or hit[0] < best[0]):
                    best = hit
        return best


def _intersect(
    p: tuple[float, float], q: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> tuple[float, tuple[float, float]] | None:
    """Where segment p->q meets segment a->b, as (t along p->q, point) -- or None.

    t is restricted to (HIT_EPS, 1] so a segment never "hits" its own start point (t=0), which
    is where it always touches whatever segment it just grew from; u covers the whole of a->b
    (including its endpoints) so a crack can end exactly at another crack's tip, not just its
    interior -- both are legitimate T-junctions.
    """
    r = (q[0] - p[0], q[1] - p[1])
    s = (b[0] - a[0], b[1] - a[1])
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-12:
        return None
    diff = (a[0] - p[0], a[1] - p[1])
    t = (diff[0] * s[1] - diff[1] * s[0]) / denom
    u = (diff[0] * r[1] - diff[1] * r[0]) / denom
    if _HIT_EPS < t <= 1.0 and -_HIT_EPS <= u <= 1.0 + _HIT_EPS:
        return t, (p[0] + t * r[0], p[1] + t * r[1])
    return None


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto crack_spacing_mm, with a floor.

    crack_spacing_mm is the impact lattice's pitch, not a crack's own length (that now scales
    off the sheet's own size, see RADIAL_LEN_FRAC_*), but a finer pitch still means more impact
    CANDIDATES -- cols*rows grows quadratically as crack_spacing_mm shrinks -- and each surviving
    impact still costs several radials plus cross-links. Measured on dense_line_art at 150 mm:
    with the old scale (0.9) draft (spacing 2.5) landed at 41_480 segments against its own
    40_000 cap -- the *radials* made cracks long, but nothing had shrunk the CANDIDATE count to
    match, so draft (the coarsest, cheapest tier, the one an operator reaches for first) was the
    one tier that actually blew its budget. 1.1 pulls every tier's crack_spacing_mm up (fewer
    impact candidates everywhere, not just at draft), which is enough on its own: draft now
    lands at 34_859/40_000 with the rest of the ladder still using well under half its own cap,
    so nothing needed trimming beyond this one number. The floor keeps crack_spacing_mm from
    ever dropping so low that a max-quality render's candidate count blows ITS OWN (much larger)
    cap instead, while every finer step still shrinks the pitch and so still adds detail.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"crack_spacing_mm": max(1.4, spacing_mm * 1.1)}
