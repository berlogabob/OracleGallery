"""PCB-style copper routing: Manhattan traces with a 45-degree corner cut, ending in pads.

Traces walk a grid of nodes spaced `pitch_mm` apart, one node at a time, always moving in one
of the eight grid directions -- so every drawn segment is axis-aligned or exactly 45 degrees,
the vocabulary that reads as a routed board rather than a street map. Non-crossing is not
policed after the fact: a shared mutable occupancy SET of visited (row, col) nodes is what the
router consults on every step, so two traces physically cannot occupy the same node, and a
trace that walks into an already-occupied node simply stops there instead of overlapping it.
Every trace that stops -- whether it reached its target or was cut short by traffic -- is
capped with a small square pad at each end, so even a one-segment stub reads as copper
terminating on a pad, not a dangling line.

Tone drives density, not trace length: whether a grid cell starts a trace at all is decided by
a 4x4 ordered-dither (Bayer) threshold against that cell's own darkness, the same test a
halftone uses to turn a continuous tone into a spatially even yes/no field -- see
`_participates`. Run length (2 to 10 grid steps, see `_pick_target`) is drawn independently of
darkness for every trace, so it never carries a tone signal of its own. An earlier version
instead scaled ATTEMPTS per cell by darkness while letting every eligible cell participate;
that made participation identical at every darkness above `min_darkness` (attempts>1 turned out
to almost never matter -- a cell's own start node is claimed by its first successful attempt,
so a second attempt from the same cell fails instantly), so light and dark regions produced
nearly the same trace count. Dithered participation is what actually ties trace COUNT to
darkness; darkness-independent reach is what keeps trace LENGTH from adding a second, noisier
copy of that same signal (an even earlier version scaled reach by darkness and a solid-black
field's few long traces saturated the grid before the darkness gradient could show up as a
count difference at all).

Darkness is stretched before it reaches that Bayer gate, the same fix `ascii._char_grid` makes
and for the same reason: area-averaging a real photo into `pitch_mm` cells compresses its
variance toward the middle of 0..1, so raw cell darkness only ever exercises the gate's middle
thresholds and the board reads as a uniform haze regardless of the source image. `_route_board`
takes every GATED cell's own darkness range (min..max, over the whole board) and remaps it
linearly onto 0..1 before comparing to the Bayer threshold -- exactly `_char_grid`'s
`normalized()` -- so the lightest gated patch of the sheet ends up bare and the darkest ends up
fully populated, whatever the raw darkness those extremes happened to average out to.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, cell_darkness

HELP = (
    "PCB traces: Manhattan routing with a 45-degree corner cut, capped with pads. Darker "
    "areas get denser routing; detail = routing pitch in mm."
)

MAX_TRACES_DEFAULT = 4_000
# Run length, in grid steps, drawn uniformly per trace -- see module docstring for why this is
# darkness-independent. The spread (not just a bigger fixed length) is what makes the board
# read as routed rather than as confetti: a few long runs with shorter spurs joining them,
# instead of every trace being the same short stub.
_MIN_RUN_CELLS = 2
_MAX_RUN_CELLS = 10
# Retries a participating cell gets if its first randomly-picked direction is blocked before
# it clears even one grid step -- a fairness patch, not a density lever (see module docstring).
_MAX_ATTEMPTS = 3
# Pad half-size as a fraction of pitch_mm -- see quality_params for why this sets the floor.
_PAD_HALF_FRACTION = 0.22
# The 8 grid directions a trace can run in -- diagonals included, since a straight diagonal
# run is itself a valid 45-degree segment, not just a corner cut between two straight ones.
_DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
# Classic 4x4 ordered-dither (Bayer) matrix. A cell participates when its darkness clears the
# matrix's own threshold at that cell's (row, col) mod 4 -- the standard halftone trick for
# turning a continuous tone into a spatially even yes/no field: any 4x4 patch always contains
# every threshold exactly once, so a patch's participation FRACTION tracks its own darkness
# almost exactly, with none of the plateau noise a small integer attempt-count produces.
_BAYER_4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def circuit(
    tone: ToneGrid,
    *,
    pitch_mm: float = 2.0,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_traces: int = MAX_TRACES_DEFAULT,
) -> Polylines:
    """Route copper traces on a `pitch_mm` grid, denser where the source is darker.

    Cells are visited in raster order (top to bottom, left to right) and darker cells are
    always visited before lighter ones AS LONG AS darkness falls with x, exactly the
    left-dark-to-right-light gradient the mode contract checks -- so on that gradient the
    darker side always gets first claim on free grid nodes, before the lighter side's own
    attempts can compete for them. That ordering, not just the attempt count, is part of what
    keeps ink monotonic: a light cell that runs late is more likely to find its neighbours
    already claimed and truncate short.

    `max_traces` is the one hard stop that matters: a flat black field would otherwise let
    every cell participate (see `_participates`) and the router would still terminate on its
    own (occupied nodes make later attempts fail in O(1)), but bounding the accepted-trace
    count directly is what keeps segment counts predictable across quality steps regardless of
    how many cells the grid has.
    """
    if pitch_mm <= 0:
        raise ValueError("pitch_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_traces < 1:
        raise ValueError("max_traces must be at least 1")

    traces = _route_board(tone, pitch_mm, min_darkness, seed, max_traces)
    lines: Polylines = []
    for path, junction in traces:
        lines.extend(_trace_polylines(path, junction, pitch_mm))
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in lines]


def _route_board(
    tone: ToneGrid, pitch_mm: float, min_darkness: float, seed: int, max_traces: int
) -> list[tuple[list[tuple[int, int]], tuple[int, int] | None]]:
    """The routing pass itself, kept separate from polyline drawing so it can be unit-tested.

    Returns one (node path, junction) pair per accepted trace -- junction is the neighbouring
    trace's node this one ran into, for drawing only (see `_walk`), or None if it ended in open
    space. The occupancy set is local to this call and accumulates as traces are accepted, so
    it is the single source of truth for collision-freedom: any node in it was claimed by an
    earlier trace in this same call, and only nodes in a trace's own returned path are ever
    added to it -- a junction node is never re-claimed, since it is already owned.
    """
    cols = max(1, math.ceil(tone.width_mm / pitch_mm))
    rows = max(1, math.ceil(tone.height_mm / pitch_mm))

    darkness_grid = _darkness_grid(tone, pitch_mm, rows, cols)
    # Stretch the GATED cells' own min..max onto 0..1 before the density gate sees it -- see
    # the module docstring and ascii._char_grid's normalized(), which this mirrors exactly.
    passing = [value for line in darkness_grid for value in line if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    def stretched(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    occupied: set[tuple[int, int]] = set()
    traces: list[tuple[list[tuple[int, int]], tuple[int, int] | None]] = []
    budget = max_traces
    for row in range(rows):
        if budget <= 0:
            break
        for col in range(cols):
            if budget <= 0:
                break
            if (row, col) in occupied:
                continue
            darkness = darkness_grid[row][col]
            if darkness < min_darkness or not _participates(stretched(darkness), row, col):
                continue
            rng = np.random.default_rng((seed, row, col))
            for _ in range(_MAX_ATTEMPTS):
                target_row, target_col = _pick_target(rng, row, col, rows, cols)
                path, junction = _walk(row, col, target_row, target_col, occupied)
                if len(path) < 2:
                    continue  # first grid step was already occupied -- retry a new direction
                occupied.update(path)
                traces.append((path, junction))
                budget -= 1
                break  # one trace per participating cell; see the module docstring
    return traces


def _darkness_grid(tone: ToneGrid, pitch_mm: float, rows: int, cols: int) -> list[list[float]]:
    """Mean darkness per grid cell, computed once up front so the density gate can be stretched
    against the board's own min..max before any routing happens (see `_route_board`)."""
    grid: list[list[float]] = []
    for row in range(rows):
        y0, y1 = row * pitch_mm, (row + 1) * pitch_mm
        grid.append(
            [
                cell_darkness(
                    tone.darkness, col * pitch_mm, y0, (col + 1) * pitch_mm, y1, tone.width_mm, tone.height_mm
                )
                for col in range(cols)
            ]
        )
    return grid


def _participates(stretched_darkness: float, row: int, col: int) -> bool:
    """Ordered-dither gate: does this cell start a trace at all, at its own (stretched) darkness?"""
    threshold = (_BAYER_4[row % 4][col % 4] + 0.5) / 16.0
    return stretched_darkness >= threshold


def _pick_target(rng: np.random.Generator, row: int, col: int, rows: int, cols: int) -> tuple[int, int]:
    """A candidate end node 2-10 steps away in a random one of the 8 grid directions.

    Both the direction and the reach come from this trace's own draw of the per-cell RNG, so
    the same seed always produces the same run length -- deterministic, but with no tie to
    darkness (see the module docstring on why length stays out of the density signal).
    """
    reach = int(rng.integers(_MIN_RUN_CELLS, _MAX_RUN_CELLS + 1))
    delta_row, delta_col = _DIRECTIONS[int(rng.integers(0, len(_DIRECTIONS)))]
    return (
        min(rows - 1, max(0, row + delta_row * reach)),
        min(cols - 1, max(0, col + delta_col * reach)),
    )


def _walk(
    start_row: int, start_col: int, end_row: int, end_col: int, occupied: set[tuple[int, int]]
) -> tuple[list[tuple[int, int]], tuple[int, int] | None]:
    """Greedy Manhattan path from start to end, chamfered with a 45-degree corner cut.

    Stepping on both axes at once while both still have distance left -- then straight on
    whichever axis remains -- is what turns a right-angle L into the diagonal-cut corner a
    routed trace makes instead of a plain street grid. The walk stops the instant it steps
    onto an occupied node: this is the entire collision-handling strategy. No replanning, no
    backing off to try another target -- a trace that runs into traffic just ends there. The
    blocking node is returned as the "junction" (not added to the path, since it is already
    owned by another trace) purely so the caller can draw the line INTO it -- a T-junction
    against an existing trace instead of a dangling stub, cheap because the collision check
    already found the node; it costs nothing extra to remember it.
    """
    path = [(start_row, start_col)]
    junction: tuple[int, int] | None = None
    delta_row, delta_col = end_row - start_row, end_col - start_col
    step_row = (delta_row > 0) - (delta_row < 0)
    step_col = (delta_col > 0) - (delta_col < 0)
    row, col = start_row, start_col
    remaining_row, remaining_col = abs(delta_row), abs(delta_col)
    for _ in range(max(remaining_row, remaining_col)):
        if remaining_row > 0:
            row += step_row
            remaining_row -= 1
        if remaining_col > 0:
            col += step_col
            remaining_col -= 1
        if (row, col) in occupied:
            junction = (row, col)
            break
        path.append((row, col))
    return path, junction


def _trace_polylines(path: list[tuple[int, int]], junction: tuple[int, int] | None, pitch_mm: float) -> Polylines:
    """One trace's own line plus a pad at each free end -- the pad/via vocabulary the mode
    promises. The end that ran into a junction gets no pad of its own: that node's pad (or via)
    belongs to the trace that claimed it first, and the line simply touches it."""
    points = [_node_point(node, pitch_mm) for node in path]
    lines: Polylines = [points, _pad(points[0], pitch_mm)]
    if junction is not None:
        points.append(_node_point(junction, pitch_mm))
    else:
        lines.append(_pad(points[-1], pitch_mm))
    return lines


def _node_point(node: tuple[int, int], pitch_mm: float) -> tuple[float, float]:
    row, col = node
    return (col + 0.5) * pitch_mm, (row + 0.5) * pitch_mm


def _pad(center: tuple[float, float], pitch_mm: float) -> list[tuple[float, float]]:
    """A small closed square outline -- a plotted line has no fill, so this is the pad/via mark."""
    half = pitch_mm * _PAD_HALF_FRACTION
    x, y = center
    return [
        (x - half, y - half),
        (x + half, y - half),
        (x + half, y + half),
        (x - half, y + half),
        (x - half, y - half),
    ]


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the shared quality fader to routing pitch and trace budget.

    pitch_mm follows spacing directly, floored at 1.0 mm: a pad's half-size is
    _PAD_HALF_FRACTION (0.22) of pitch_mm, and below 1.0 mm that half-size drops under a third
    of the plotter's own 0.3 mm pen width (PEN_WIDTH_MM_DEFAULT in modes.py) -- the square stops
    reading as a pad and becomes a dot the nib can't resolve. The fader's own ladder never asks
    for anything finer than 1.0 mm, so this floor is a backstop, not a live clamp.

    max_traces scales with 1/pitch_mm**2 (cell count grows the same way as pitch shrinks) so
    the fader buys more routing, not just a finer grid with the same trace count -- while
    staying well under every step's segment cap on the dense 150 mm drawing (measured: draft
    2.5mm 3649 of a 40 000 cap, max 1.0mm 21450 of a 640 000 cap; see test_mode_circuit.py).
    The router's own dithered density (not this budget) is usually what limits trace count in
    practice -- the budget is the backstop for pathological inputs, not the everyday lever.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    pitch_mm = max(1.0, spacing_mm)
    max_traces = round(MAX_TRACES_DEFAULT * (2.0 / pitch_mm) ** 2)
    return {"pitch_mm": pitch_mm, "max_traces": max_traces}
