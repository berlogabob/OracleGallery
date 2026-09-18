"""Contract + maze-specific coverage for the randomized-spanning-tree maze mode."""

from __future__ import annotations

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.maze import (
    _grid_edges,
    _rooms,
    _wall_edges,
    maze,
    quality_params,
)
from neje_oracle.blocks.imaging.modes import ToneGrid

# A stroke is worth its pen lift only if the maze is drawn in a handful of strokes rather than
# one per wall edge; this is the number the mode exists to hit -- see the module docstring's
# "Wall-drawing strategy" section for why stitching walls gets there instead of tracing corridors.
# 2500 gives headroom over the ~1500 strokes measured for the scenario below while still catching
# a real regression (e.g. stitching silently breaking) long before it reaches the segment caps.
_DENSE_150MM_STROKE_BOUND = 2500


def _uniform_tone(darkness: float, *, size_mm: float = 60.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_maze_contract() -> None:
    report = check_mode_contract(maze, quality_params, monotonic=True)
    print(report)


def test_maze_is_a_spanning_tree() -> None:
    """Connected and acyclic, proved by counting -- but at the level of ROOMS, not raw squares.

    A room can (and in a light area, does) end up internally connected by more than one
    pre-merged edge -- that is what lets a light area come out with no interior clutter at all
    rather than exactly one open seam per square, and it means the raw rows*cols square graph is
    not literally a tree. The rooms `_wall_edges` routes between are: two independent rng streams
    of the same seed reproduce the same pre-merge draws (already covered by the contract's own
    determinism check), so calling `_rooms` and `_wall_edges` with separate `default_rng(seed)`
    instances yields a `room_of` array that matches what `_wall_edges` used internally.
    """
    rows, cols = 9, 13
    seed = 7
    # A mid-grey, slightly textured field: uniform darkness would make every edge's decision
    # identical in expectation, which is the case the arithmetic proof cares about least; a
    # gradient exercises pre-merge and Kruskal-door edges side by side in the same grid.
    darkness = np.linspace(0.05, 0.95, rows * cols).reshape(rows, cols)

    passing = darkness[darkness >= 0.1]
    low, high = float(passing.min()), float(passing.max())
    room_of, _candidates = _rooms(rows, cols, darkness, 0.1, low, high, np.random.default_rng(seed))
    walls, room_count = _wall_edges(rows, cols, darkness, 0.1, low, high, np.random.default_rng(seed))

    # Reconstruct the room graph from `walls` alone: any grid edge NOT drawn as a wall either
    # pre-merged (already the same room -- a harmless no-op union) or was a genuine door (a
    # real join). Counting only the joins that actually changed the component count -- exactly
    # what a fresh union-find does -- must land on rooms - 1 if the room graph is a tree.
    wall_set = {(row, col, horizontal) for row, col, horizontal in walls}
    parent = {room: room for room in set(room_of)}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    joins = 0
    for a, b, row, col, horizontal in _grid_edges(rows, cols):
        if (row, col, horizontal) not in wall_set:
            root_a, root_b = find(room_of[a]), find(room_of[b])
            if root_a != root_b:
                parent[root_a] = root_b
                joins += 1

    assert joins == room_count - 1, f"expected exactly {room_count - 1} joins for {room_count} rooms, got {joins}"
    roots = {find(room) for room in set(room_of)}
    assert len(roots) == 1, f"maze is not fully connected: {len(roots)} separate rooms"


def test_dense_150mm_stroke_count_is_low() -> None:
    """The whole point of this mode: a servo pen pays for pen lifts, not ink, so strokes must
    be few. Stitching the wall mesh (see module docstring) should turn thousands of individual
    grid-edge segments into a low hundreds-to-low-thousands count of long chains.

    Uses the mode's own default cell_mm (what a user gets without cranking the quality fader to
    its absolute floor) at near-solid darkness, the worst case for corridor density.
    """
    dense = _uniform_tone(0.95, size_mm=150.0, cell_mm=1.0)
    polylines = maze(dense, seed=3)
    stroke_count = len(polylines)
    print(f"dense 150mm maze stroke count: {stroke_count}")
    assert stroke_count > 0, "a dense maze must draw something"
    assert stroke_count < _DENSE_150MM_STROKE_BOUND, (
        f"{stroke_count} strokes is too many pen lifts to be worth this mode over truchet/hilbert"
    )
