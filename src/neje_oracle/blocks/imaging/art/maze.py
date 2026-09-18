"""A real randomized-spanning-tree maze, dense where the image is dark.

Not a tiled pattern like `truchet` (arcs that merely look maze-like): this builds an actual
graph -- one node per grid cell -- and runs a maze-generation algorithm over it, so "maze" here
is the literal spanning-tree/wall-graph construction, not a tile that resembles one.

Tone controls resolution, not just density. A literal quadtree (cells that recursively split
into four) is the obvious way to do that, but its leaves are different sizes, and two
different-sized leaves can share only PART of a border (a T-junction) -- correct adjacency
then needs a real neighbour-finding walk up and down the tree. This mode gets the same effect
--corridors that pack tighter in dark areas, and open into big empty rooms in light ones--
without that: it keeps ONE uniform grid at `corridor_mm` resolution and randomly grows "rooms" by
merging adjacent squares, capping each room's cell COUNT at a target set by its local darkness
(see `_room_target`), before the maze algorithm ever sees the result. A first version picked
each edge's merge independently at random with probability `1 - darkness`; that is bond
percolation, which has a sharp phase transition around p=0.5 -- everything below roughly
darkness 0.5 collapsed into one giant room regardless of how light it actually was, so a
photograph's whole midtone range came out blank. Capping room SIZE instead of merge
PROBABILITY has no such threshold: the target area interpolates continuously from 1 cell at
darkness 1 to `_MAX_ROOM_CELLS` at darkness 0, so room size -- and the wall ink that survives
around it -- tracks darkness the whole way down, not just above one cliff.

That target still needs STRETCHED darkness, not the raw cell-averaged value, to actually use
its own range: area-averaging a photo into corridor_mm cells compresses darkness into a narrow band
around the middle before `_room_target` ever sees it, the same compression `ascii._char_grid`
measured and corrects for (see its docstring). Fed raw values, a lit sphere on a dark
background came out an even field of corridors but for the highlight -- `_stretch` rescales
each gated edge's darkness from the gated cells' own min..max onto the full 0-1 range first, the
same job ImageOps.autocontrast does at pixel level in load_tone, applied to this coarser signal.

Why this makes darker areas carry more ink (the contract's monotonic-ink check): on a FIXED
uniform grid, a spanning tree always has exactly (cells - 1) edges, so the number of leftover
"wall" edges -- (total edges - cells + 1) -- does not depend on which tree you pick, only on the
grid's own resolution. Density has to come from the number of cells actually reachable at full
resolution in an area, which is exactly what pre-merging removes: a pre-merged edge deletes a
node's chance to be its own room, so a dark region (few pre-merges, most edges survive as
distinct cells) ends up with far more wall edges per mm^2 than a light one (most edges
pre-merged away into a handful of big rooms).

Wall-drawing strategy (a) vs (b): this mode stitches wall segments (`_stitch`), not the
alternative of tracing one continuous corridor curve around the tree. The reason is the same
planar-duality fact truchet leans on: the retained WALLS of a spanning-tree maze are themselves
a spanning tree of the dual graph, so they are already one connected mesh of tiny straight
segments sharing exact endpoints (each wall's endpoints are `row * corridor_mm` / `col * corridor_mm`
arithmetic, so two walls that touch compute the SAME float for their shared corner) --
`_stitch` collapses that mesh into long chains for free, at the same near-zero tolerance
truchet uses, with no new geometry code. A "trace the corridor" walk would still need this
same edge-contracted grid underneath it and adds a second geometric construction on top for a
result that (per the module test) is not meaningfully fewer strokes than stitched walls.

Connected and acyclic, proved by construction, not inspected after the fact -- but the "cells"
that claim applies to are the ROOMS (post pre-merge), not the raw grid squares. Pre-merging
alone can and does connect two grid squares more than one way inside a blank room (that is what
lets a light area come out with zero interior clutter at all, rather than exactly one open seam
per square), so the raw grid-square graph is not literally a tree. The rooms it produces are:
contracting a connected graph's edges always leaves the rest connected, so the room graph
(rooms as nodes, the un-pre-merged edges between differently-roomed neighbours as its only
edges) is guaranteed connected too. `_wall_edges` then runs Kruskal on exactly that room graph:
each candidate edge becomes a door -- silently joining two rooms, nothing drawn -- the first
time it would connect two still-separate rooms, and a wall (returned here) every time after,
once its two ends already share a room. A join always shrinks the room-component count by
exactly one, so after every candidate is visited, joins = rooms - 1 and the room graph is in
one component: an M-room graph with exactly M-1 edges used IS a tree, by that arithmetic alone.
See test_maze_is_a_spanning_tree.
"""

from __future__ import annotations

import math

import numpy as np

from ..modes import Polylines, ToneGrid, _clip_point, _stitch, cell_darkness

HELP = (
    "A real maze: a randomized spanning tree over a grid, not tiles. Dark areas keep full "
    "grid resolution as tight corridors; light areas merge into open rooms."
)

MAX_CELLS_DEFAULT = 60_000
_JOIN_TOLERANCE_MM = 1e-6
# A room's cell-count cap at darkness 0 (see _room_target). 12 cells (a ~3x4 block) turned out
# not coarse enough to read as "open" once darkness was stretched to use its full range -- next
# to a 1-cell room it was still visibly a small room, not emptiness. 80 cells (roughly 9x9) is
# where a light patch stops reading as "fine maze, thin walls" and starts reading as "no maze
# here": see maze2.png in the module test for the rasterised check this was tuned against.
_MAX_ROOM_CELLS = 80
# 1.0 (linear): once darkness is stretched (see _stretch) it already spans the full 0-1 range,
# so -- unlike hilbert, which shapes an UNSTRETCHED signal still bunched at mid-grey -- there is
# no compression left here for a gamma > 1 to correct for; a linear target tracked the
# stretched range better in the rasterised check than any gamma tried above 1.
_ROOM_GAMMA = 1.0


def maze(
    tone: ToneGrid,
    *,
    corridor_mm: float = 2.0,
    min_darkness: float = 0.05,
    seed: int = 0,
    max_cells: int = MAX_CELLS_DEFAULT,
) -> Polylines:
    """A grid maze whose local resolution -- and so its local ink -- tracks darkness.

    All randomness comes from one `np.random.default_rng(seed)`, drawn in a fixed order (a
    permutation of the grid's own edge list, never dict/set iteration order), so the same tone
    and seed always grow the same rooms and route the same doors -- never time or hash().

    Edges under min_darkness always merge (unconditionally, not subject to the room-size cap)
    so a light area never survives as a stray wall no matter how big the resulting room gets;
    above that, an edge merges only while doing so keeps both rooms' combined cell count under
    `_room_target(edge_darkness)` -- see the module docstring for why that is a size cap and not
    a per-edge probability. `edge_darkness` there is STRETCHED (gated cells' own min..max
    rescaled onto 0..1, `ascii._char_grid`'s trick, see `_stretch`) before it reaches
    `_room_target`, not the raw cell-averaged value -- see the module docstring's "Tone controls
    resolution" section for why unstretched input read as a flat field of corridors.

    max_cells is the same guard truchet's max_tiles is: a small corridor_mm on a big sheet is a
    rows*cols blow-up worth catching before a single edge is visited.
    """
    if corridor_mm <= 0:
        raise ValueError("corridor_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_cells < 1:
        raise ValueError("max_cells must be at least 1")

    cols = max(1, math.ceil(tone.width_mm / corridor_mm))
    rows = max(1, math.ceil(tone.height_mm / corridor_mm))
    if rows * cols > max_cells:
        raise ValueError(
            f"maze would need {rows * cols} cells, exceeding max_cells={max_cells}; "
            "increase corridor_mm or reduce the drawing size"
        )

    darkness = np.empty((rows, cols))
    for row in range(rows):
        y0, y1 = row * corridor_mm, (row + 1) * corridor_mm
        for col in range(cols):
            x0, x1 = col * corridor_mm, (col + 1) * corridor_mm
            darkness[row, col] = cell_darkness(tone.darkness, x0, y0, x1, y1, tone.width_mm, tone.height_mm)

    passing = darkness[darkness >= min_darkness]
    low, high = (float(passing.min()), float(passing.max())) if passing.size else (0.0, 0.0)

    rng = np.random.default_rng(seed)
    walls, _room_count = _wall_edges(rows, cols, darkness, min_darkness, low, high, rng)
    segments = [_wall_segment(row, col, corridor_mm, horizontal) for row, col, horizontal in walls]

    joined = _stitch(segments, _JOIN_TOLERANCE_MM)
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in joined]


def _grid_edges(rows: int, cols: int) -> list[tuple[int, int, int, int, bool]]:
    """Every edge of the rows x cols grid, once each, as (cell_a, cell_b, row, col, horizontal).

    `horizontal` means cell_a and cell_b are side-by-side neighbours (their shared wall is a
    VERTICAL segment); otherwise they are stacked neighbours (a HORIZONTAL wall segment).
    """
    edges: list[tuple[int, int, int, int, bool]] = []
    for row in range(rows):
        for col in range(cols):
            cell = row * cols + col
            if col + 1 < cols:
                edges.append((cell, cell + 1, row, col, True))
            if row + 1 < rows:
                edges.append((cell, cell + cols, row, col, False))
    return edges


def _find(parent: dict[int, int], node: int) -> int:
    root = node
    while parent[root] != root:
        root = parent[root]
    while parent[node] != root:
        parent[node], node = root, parent[node]
    return root


def _union(parent: dict[int, int], a: int, b: int) -> bool:
    """Merge a and b's rooms; returns whether that actually joined two distinct components."""
    root_a, root_b = _find(parent, a), _find(parent, b)
    if root_a == root_b:
        return False
    parent[root_a] = root_b
    return True


def _stretch(value: float, low: float, high: float) -> float:
    """Rescale value from the gated cells' own [low, high] onto [0, 1] -- ascii._char_grid's trick.

    Area-averaging a photo into corridor_mm cells compresses darkness into a narrow band around the
    middle (ascii's docstring measured a real photo's cells at a 25th-75th percentile of only
    0.45-0.58 out of the full 0-1 range) -- an earlier version fed raw cell darkness straight
    into `_room_target` and the render came out an almost-even field of corridors, exactly what
    the contract's gradient_buckets caught ([80, 88, 88, 86, 86, 76, 70, 52], flat across the
    middle). Stretching each gated edge's darkness back onto the full 0-1 range before it
    reaches `_room_target` is the same fix ImageOps.autocontrast makes at pixel level, applied
    to the coarser cell-averaged signal this mode actually samples.
    """
    spread = high - low
    return (value - low) / spread if spread > 1e-9 else value


def _room_target(darkness: float) -> float:
    """The cell-count a room may grow to before this darkness stops it merging further.

    Interpolates 1 cell (darkness 1: never merge, full resolution) up to _MAX_ROOM_CELLS
    (darkness 0), the same "lands exactly on both bounds" shape hilbert's own target formula
    uses and for the same reason -- see hilbert.py's docstring. `darkness` here is expected to
    already be stretched (see `_stretch`), not raw.
    """
    return 1.0 + (_MAX_ROOM_CELLS - 1) * (1.0 - darkness) ** _ROOM_GAMMA


def _rooms(
    rows: int,
    cols: int,
    darkness: np.ndarray,
    min_darkness: float,
    low: float,
    high: float,
    rng: np.random.Generator,
) -> tuple[list[int], list[tuple[int, int, int, int, bool]]]:
    """Lightest-first region growth: which raw grid squares share a room, and which edges did not.

    Visits edges in ascending RAW edge_darkness order (ties broken by an rng draw, so a uniform
    field still grows organically shaped rooms rather than always the same grid-snapped ones),
    not a uniformly random order: growing the lightest regions first, everywhere at once, keeps
    a room's final size a function of ITS darkness rather than of how lucky its edges got in an
    unordered scan -- an earlier, order-agnostic version of this (random order, same size cap)
    let two same-darkness patches end up with visibly different room sizes purely from draw
    order, which is exactly the noise the contract's per-strip monotonic-ink check exists to
    catch. The min_darkness gate itself stays on the RAW value (gating is "did this patch of
    paper have any mark on it at all", which `_stretch`'s rescaling must not affect: a lone dark
    speck in an otherwise-blank photo has to stay gated in, not get pulled toward 1.0 by the
    stretch and no longer compared against the ungated min_darkness). `_room_target` sees the
    STRETCHED darkness instead, via `low`/`high` computed once in `maze` over all gated cells.
    Each visited edge merges -- unless doing so would push either room over its local target
    size -- into one room; rejected edges become wall candidates for `_wall_edges` to route
    doors and walls between rooms with. Returns each square's fully-compressed room id, so two
    squares are roommates iff their ids are equal.
    """
    parent = {cell: cell for cell in range(rows * cols)}
    size = dict.fromkeys(range(rows * cols), 1)
    edges = _grid_edges(rows, cols)
    edge_darkness = np.fromiter(
        (0.5 * (darkness.flat[a] + darkness.flat[b]) for a, b, *_ in edges), dtype=float, count=len(edges)
    )
    order = np.lexsort((rng.random(len(edges)), edge_darkness))

    candidates: list[tuple[int, int, int, int, bool]] = []
    for index in order:
        a, b, row, col, horizontal = edges[int(index)]
        root_a, root_b = _find(parent, a), _find(parent, b)
        if root_a == root_b:
            continue  # already the same room: neither a merge nor a wall candidate
        d = edge_darkness[index]
        if d < min_darkness or size[root_a] + size[root_b] <= _room_target(_stretch(d, low, high)):
            parent[root_a] = root_b
            size[root_b] += size[root_a]
        else:
            candidates.append((a, b, row, col, horizontal))
    return [_find(parent, cell) for cell in range(rows * cols)], candidates


def _wall_edges(
    rows: int,
    cols: int,
    darkness: np.ndarray,
    min_darkness: float,
    low: float,
    high: float,
    rng: np.random.Generator,
) -> tuple[list[tuple[int, int, bool]], int]:
    """Kruskal's algorithm over the ROOM graph (see `_rooms`), not the raw grid.

    An edge whose two squares already share a room (via pre-merging elsewhere, not necessarily
    this edge) is interior to that room and is dropped outright -- drawing it would put a
    stray wall inside what pre-merging already decided should be one open space. Every other
    edge connects two distinct rooms and becomes a door (silently unioned) the first time it
    would join them, or a wall (returned here) once they are already joined some other way.
    Returns the walls plus the room count, so a caller (the module test) can check the count of
    doors used against rooms - 1 without re-deriving rooms from scratch.
    """
    room_of, candidates = _rooms(rows, cols, darkness, min_darkness, low, high, rng)
    room_count = len(set(room_of))

    tree_parent = {room: room for room in set(room_of)}
    walls: list[tuple[int, int, bool]] = []
    for index in rng.permutation(len(candidates)):
        a, b, row, col, horizontal = candidates[int(index)]
        room_a, room_b = room_of[a], room_of[b]
        if room_a != room_b and not _union(tree_parent, room_a, room_b):
            walls.append((row, col, horizontal))
    return walls, room_count


def _wall_segment(row: int, col: int, corridor_mm: float, horizontal_pair: bool) -> list[tuple[float, float]]:
    """The shared border between two adjacent cells, as a 2-point polyline."""
    if horizontal_pair:
        x = (col + 1) * corridor_mm
        return [(x, row * corridor_mm), (x, (row + 1) * corridor_mm)]
    y = (row + 1) * corridor_mm
    return [(col * corridor_mm, y), ((col + 1) * corridor_mm, y)]


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Map the fader's spacing straight onto corridor_mm, floored at 1.0 mm.

    Below ~1 mm a corridor is 3-4 nib-widths wide at the plotter's 0.3 mm pen (PEN_WIDTH_MM_DEFAULT
    in modes.py); narrower than that and the walls-and-corridor structure stops reading as a maze
    and just looks like scribble, so the floor is where a real maze photograph stops helping and
    starts hurting. The fader's own densest spacing (1.0) lands exactly on that floor.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"corridor_mm": max(1.0, spacing_mm)}
