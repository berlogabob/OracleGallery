"""tsp: one continuous line built from a weighted blue-noise point cloud.

"TSP art": scatter points denser where the image is dark, then walk them in a short
tour so nearly the whole picture is one pen stroke. Unlike stipple (many short chained
rows) or squiggle (a sine that wanders regardless of where the points actually are),
the path here goes exactly where the points are, so the tour itself carries the shape.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

import numpy as np

from ..modes import Polylines, ToneGrid

HELP = (
    "One continuous line touring a cloud of darkness-weighted points. Fewest pen lifts; needs a short tour computation."
)

MAX_TSP_POINTS = 150_000
# Ring-search neighbourhood for both the acceptance grid and the tour's nearest-neighbour
# lookups. Capped rather than sized to the true worst-case reach (up to ~4.5x point_spacing_mm
# at min_darkness=0.05): most candidates sit at moderate-to-high darkness where reach=1 is
# already correct, and the rare very-light candidate that wants a wider berth is not worth
# scanning 121 cells for on every one of tens of thousands of candidates.
MAX_RING_REACH = 4
TWO_OPT_NEIGHBOURS = 8
TWO_OPT_PASSES = 2
# A 2-opt swap's cost is the length of the tour segment it reverses. Blue-noise points fed
# through a nearest-neighbour tour are already locally good, so almost every improving swap
# found through a small spatial neighbour list is short-range; skipping the rare swap whose
# reversal would be long keeps every pass O(n * neighbours) instead of occasionally O(n^2).
MAX_REVERSAL = 2_000
# Nearest-neighbour construction's classic flaw: as the walk exhausts a region it has to leap
# to the nearest UNVISITED point, however far, which strands single points and small clumps
# behind long jumps that no crossing-removal (2-opt reverses a segment; it cannot relocate a
# point) can fix. Bounded, so a handful of successful relocations cannot turn into an O(n)
# rebuild on every point in a large point cloud.
MAX_RELOCATIONS = 500
# 2-opt and relocation fix different failure modes and each can expose new work for the
# other: uncrossing an edge can leave a point better placed by relocation, and relocating a
# point can create a short crossing 2-opt now has the reach to remove. Measured on a solid
# 60mm disc at the default spacing: round 1 took 6 stray long jumps to 1, round 2 took that
# to 0 and held there — a fixed few rounds converges well before this stops paying for itself.
IMPROVEMENT_ROUNDS = 3


def tsp(
    tone: ToneGrid,
    *,
    point_spacing_mm: float = 1.0,
    min_darkness: float = 0.05,
    max_jump_mm: float | None = None,
    seed: int = 0,
    max_points: int = MAX_TSP_POINTS,
) -> Polylines:
    """Darkness-weighted points, toured nearest-neighbour + bounded 2-opt, cut at long jumps.

    Placement: a jittered grid at half point_spacing_mm supplies dart-throw candidates, each
    kept only if no already-accepted point sits inside its own local minimum spacing,
    point_spacing_mm / sqrt(darkness) -- so a fully dark cell packs points point_spacing_mm
    apart and a barely-gated cell (darkness == min_darkness, default 0.05) spaces them up to
    ~4.5x that. Candidates are shuffled before the accept/reject pass (seeded on `seed`), not
    walked in raster order, because a raster walk would bias acceptance toward the top-left
    of every dense region and print as a faint diagonal grain. Rejection is checked against a
    spatial hash grid, not all prior points, which is what keeps this O(n) rather than O(n^2)
    in the point count.

    Touring: a nearest-neighbour walk over the same spatial grid (never all-pairs) gives a
    reasonable starting order in roughly O(n), then IMPROVEMENT_ROUNDS rounds alternate a
    neighbourhood-limited 2-opt pass (uncrosses local zig-zags by reversing a segment) with a
    neighbourhood-limited relocation pass (moves one stray point next to a spatial neighbour).
    Both are bounded (MAX_REVERSAL, MAX_RELOCATIONS) and neither alone is enough: 2-opt cannot
    fix the single points and small clumps nearest-neighbour strands behind a long "return"
    jump when it exhausts a region, because that failure has no crossing to uncross; measured
    on a solid 60mm disc, 2-opt alone left 6 such jumps over 1000 points. Relocation targets
    exactly that case, and each pass can expose new work for the other, which is why they
    alternate for a few rounds rather than running once each.

    The tour is one path, not a loop, and it is emitted as several polylines rather than one:
    wherever consecutive tour points are farther apart than max_jump_mm (default 3x the
    larger of the two points' local spacing, i.e. past where the local spacing rule would ever
    have placed two NEIGHBOURING points), that jump is a crossing between two disconnected regions of ink
    (e.g. two ends of a dark shape separated by white), and drawing it would drag the pen
    across blank paper. This mode is registered CONTINUOUS: nothing downstream may reorder
    these polylines, because their order IS the tour.
    """
    if point_spacing_mm <= 0:
        raise ValueError("point_spacing_mm must be positive")
    if not 0.0 <= min_darkness < 1.0:
        raise ValueError("min_darkness must be in [0, 1)")
    if max_jump_mm is not None and max_jump_mm <= 0:
        raise ValueError("max_jump_mm must be positive")
    if max_points <= 0:
        raise ValueError("max_points must be positive")

    # Fail fast rather than freeze or blow through the segment cap. The densest this mode can
    # ever pack a fully-dark region is point_spacing_mm apart (darkness == 1), which upper-
    # bounds point count by area / point_spacing_mm**2; 1.3 pads that to the loosest
    # hexagonal-packing overshoot a real accept/reject pass can produce. Content never lowers
    # this estimate below the true worst case, so it is safe to check before doing any work,
    # the same way flow() and squiggle() budget on grid size alone.
    density_estimate = (tone.width_mm * tone.height_mm) / (point_spacing_mm**2) * 1.3
    if density_estimate > max_points:
        raise ValueError(
            f"tsp would place up to {int(density_estimate)} points, exceeding max_points={max_points}; "
            "widen point_spacing_mm, reduce the drawing size, or raise max_points"
        )

    points = _place_points(tone, point_spacing_mm, min_darkness, seed, max_points)
    if len(points) < 2:
        return []

    tour = _nearest_neighbour_tour(points, point_spacing_mm)
    for _ in range(IMPROVEMENT_ROUNDS):
        tour = _two_opt(points, tour, point_spacing_mm)
        tour = _relocate_strays(points, tour, point_spacing_mm)

    # The cut is relative to the LOCAL spacing, not a fixed multiple of point_spacing_mm: a
    # light area is gated in with points up to point_spacing_mm / sqrt(min_darkness) apart,
    # so a fixed 3 x point_spacing_mm limit cut every neighbour pair there and light tone
    # drew nothing at all (measured: uniform darkness 0.1 -> 0 mm of ink).
    def local_limit(index: int) -> float:
        x, y = points[index]
        column = min(tone.darkness.shape[1] - 1, int(x / tone.cell_mm))
        row = min(tone.darkness.shape[0] - 1, int(y / tone.cell_mm))
        darkness = max(float(tone.darkness[row, column]), min_darkness, 1e-6)
        return 3.0 * point_spacing_mm / math.sqrt(darkness)

    polylines: Polylines = []
    run: list[tuple[float, float]] = [points[tour[0]]]
    for previous_index, current_index in zip(tour, tour[1:], strict=False):
        previous_point = points[previous_index]
        current_point = points[current_index]
        limit = max(local_limit(previous_index), local_limit(current_index)) if max_jump_mm is None else max_jump_mm
        if _distance(previous_point, current_point) > limit:
            if len(run) >= 2:
                polylines.append(run)
            run = [current_point]
        else:
            run.append(current_point)
    if len(run) >= 2:
        polylines.append(run)
    return polylines


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Higher quality (smaller spacing_mm) packs points tighter, i.e. finer stipple detail."""
    return {"point_spacing_mm": round(spacing_mm * 0.6, 3)}


def _place_points(
    tone: ToneGrid,
    point_spacing_mm: float,
    min_darkness: float,
    seed: int,
    max_points: int,
) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    candidate_step = point_spacing_mm / 2.0
    columns = max(1, int(math.ceil(tone.width_mm / candidate_step)))
    rows = max(1, int(math.ceil(tone.height_mm / candidate_step)))

    column_index, row_index = np.meshgrid(np.arange(columns), np.arange(rows))
    jitter_x = rng.random((rows, columns))
    jitter_y = rng.random((rows, columns))
    xs = np.clip((column_index + jitter_x) * candidate_step, 0.0, tone.width_mm).ravel()
    ys = np.clip((row_index + jitter_y) * candidate_step, 0.0, tone.height_mm).ravel()

    grid_rows, grid_cols = tone.darkness.shape
    col_lookup = np.clip((xs * grid_cols / tone.width_mm).astype(np.int64), 0, grid_cols - 1)
    row_lookup = np.clip((ys * grid_rows / tone.height_mm).astype(np.int64), 0, grid_rows - 1)
    darkness = tone.darkness[row_lookup, col_lookup]

    keep = darkness >= min_darkness
    xs, ys, darkness = xs[keep], ys[keep], darkness[keep]
    if xs.size == 0:
        return []

    order = rng.permutation(xs.size)
    accept_cell = point_spacing_mm
    buckets: dict[tuple[int, int], list[tuple[float, float, float]]] = defaultdict(list)
    accepted: list[tuple[float, float]] = []

    for index in order:
        x, y = float(xs[index]), float(ys[index])
        required = point_spacing_mm / math.sqrt(float(darkness[index]))
        reach = min(int(math.ceil(required / accept_cell)), MAX_RING_REACH)
        cell_x, cell_y = int(x // accept_cell), int(y // accept_cell)
        blocked = False
        for offset_y in range(-reach, reach + 1):
            for offset_x in range(-reach, reach + 1):
                for other_x, other_y, other_required in buckets.get((cell_x + offset_x, cell_y + offset_y), ()):
                    limit = max(required, other_required)
                    if (x - other_x) ** 2 + (y - other_y) ** 2 < limit * limit:
                        blocked = True
                        break
                if blocked:
                    break
            if blocked:
                break
        if blocked:
            continue
        buckets[(cell_x, cell_y)].append((x, y, required))
        accepted.append((x, y))
        if len(accepted) >= max_points:
            break

    return accepted


class _PointGrid:
    """Spatial hash over a fixed point list, for expanding-ring nearest-neighbour search."""

    def __init__(self, points: Sequence[tuple[float, float]], cell_size: float) -> None:
        self.points = points
        self.cell_size = max(cell_size, 1e-6)
        self.buckets: dict[tuple[int, int], set[int]] = defaultdict(set)
        for index, (x, y) in enumerate(points):
            self.buckets[self._cell(x, y)].add(index)

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell_size), int(y // self.cell_size)

    def remove(self, index: int) -> None:
        x, y = self.points[index]
        self.buckets[self._cell(x, y)].discard(index)

    def _ring(self, cx: int, cy: int, radius: int) -> list[tuple[int, int]]:
        if radius == 0:
            return [(cx, cy)]
        cells = []
        for dx in range(-radius, radius + 1):
            cells.append((cx + dx, cy - radius))
            cells.append((cx + dx, cy + radius))
        for dy in range(-radius + 1, radius):
            cells.append((cx - radius, cy + dy))
            cells.append((cx + radius, cy + dy))
        return cells

    def nearest(self, x: float, y: float, max_radius: int) -> int | None:
        """Expanding-ring search for the closest remaining point to (x, y)."""
        cx, cy = self._cell(x, y)
        best: int | None = None
        best_d2 = math.inf
        radius = 0
        while radius <= max_radius:
            for cell in self._ring(cx, cy, radius):
                for index in self.buckets.get(cell, ()):
                    other_x, other_y = self.points[index]
                    d2 = (x - other_x) ** 2 + (y - other_y) ** 2
                    if d2 < best_d2:
                        best_d2, best = d2, index
            # Any point outside the ring just scanned is at least `radius * cell_size` away
            # (Chebyshev distance in grid cells lower-bounds Euclidean distance in mm), so once
            # the best candidate found is already closer than that, expanding further cannot
            # improve it.
            if best is not None and (radius * self.cell_size) ** 2 >= best_d2:
                return best
            radius += 1
        return best

    def k_nearest(self, index: int, k: int, max_radius: int) -> list[int]:
        x, y = self.points[index]
        cx, cy = self._cell(x, y)
        found: list[tuple[float, int]] = []
        radius = 0
        while radius <= max_radius:
            for cell in self._ring(cx, cy, radius):
                for other_index in self.buckets.get(cell, ()):
                    if other_index == index:
                        continue
                    other_x, other_y = self.points[other_index]
                    found.append(((x - other_x) ** 2 + (y - other_y) ** 2, other_index))
            # Enough candidates AND the ring already scanned is wide enough that nothing
            # farther out could beat the k-th best found so far.
            if len(found) >= k:
                found.sort(key=lambda item: item[0])
                if (radius * self.cell_size) ** 2 >= found[min(k, len(found)) - 1][0]:
                    return [item[1] for item in found[:k]]
            radius += 1
        found.sort(key=lambda item: item[0])
        return [item[1] for item in found[:k]]


def _nearest_neighbour_tour(points: list[tuple[float, float]], point_spacing_mm: float) -> list[int]:
    # A handful of points per bucket on average keeps ring searches shallow; too fine and the
    # search radius has to grow past 0 for almost every step, too coarse and each ring scans
    # many more points than needed.
    grid = _PointGrid(points, cell_size=point_spacing_mm * 3.0)
    span_x = max(x for x, _ in points) - min(x for x, _ in points)
    span_y = max(y for _, y in points) - min(y for _, y in points)
    max_radius = max(1, int(math.ceil(max(span_x, span_y) / grid.cell_size)) + 1)
    current = 0
    grid.remove(current)
    tour = [current]
    for _ in range(len(points) - 1):
        x, y = points[current]
        nxt = grid.nearest(x, y, max_radius)
        if nxt is None:
            break
        grid.remove(nxt)
        tour.append(nxt)
        current = nxt
    return tour


def _two_opt(points: list[tuple[float, float]], tour: list[int], point_spacing_mm: float) -> list[int]:
    n = len(tour)
    if n < 4:
        return tour

    neighbour_grid = _PointGrid(points, cell_size=point_spacing_mm * 3.0)
    ring_cap = max(2, MAX_RING_REACH)
    neighbours = [neighbour_grid.k_nearest(idx, TWO_OPT_NEIGHBOURS, ring_cap) for idx in range(len(points))]

    order = list(tour)
    position = [0] * len(points)
    for tour_position, point_index in enumerate(order):
        position[point_index] = tour_position

    def dist(a: int, b: int) -> float:
        return _distance(points[a], points[b])

    for _ in range(TWO_OPT_PASSES):
        improved = False
        for i in range(n - 1):
            a, b = order[i], order[i + 1]
            edge_ab = dist(a, b)
            for c in neighbours[a]:
                j = position[c]
                if j <= i + 1 or j >= n - 1:
                    continue
                if j - i > MAX_REVERSAL:
                    continue
                d = order[j + 1]
                gain = edge_ab + dist(order[j], d) - dist(a, order[j]) - dist(b, d)
                if gain > 1e-9:
                    order[i + 1 : j + 1] = order[i + 1 : j + 1][::-1]
                    for k in range(i + 1, j + 1):
                        position[order[k]] = k
                    improved = True
                    b = order[i + 1]
                    edge_ab = dist(a, b)
        if not improved:
            break
    return order


def _relocate_strays(points: list[tuple[float, float]], tour: list[int], point_spacing_mm: float) -> list[int]:
    """Pull single stranded points out of their long jump and reinsert them by a near neighbour.

    2-opt can only reverse a segment, so it never touches the case that actually produces the
    disconnected chains this mode has to cut at: a lone point (or tiny clump) that nearest-
    neighbour construction visited last, arriving and leaving on two long edges neither of
    which crosses anything a swap could fix. Removing the point and splicing it in next to one
    of its own spatial neighbours is what actually collapses those into one chain. Bounded to
    MAX_RELOCATIONS successful moves — this is a targeted repair for a handful of stragglers,
    not a general optimiser, and each move's list-splice is O(n) worst case.
    """
    order = list(tour)
    n = len(order)
    if n < 4:
        return order

    neighbour_grid = _PointGrid(points, cell_size=point_spacing_mm * 3.0)
    ring_cap = max(2, MAX_RING_REACH)
    neighbours = [neighbour_grid.k_nearest(idx, TWO_OPT_NEIGHBOURS, ring_cap) for idx in range(len(points))]

    def dist(a: int, b: int) -> float:
        return _distance(points[a], points[b])

    moves = 0
    for _ in range(TWO_OPT_PASSES):
        position = {point_index: pos for pos, point_index in enumerate(order)}
        changed = False
        i = 1
        while i < len(order) - 1 and moves < MAX_RELOCATIONS:
            current_point = order[i]
            previous_point, next_point = order[i - 1], order[i + 1]
            removal_gain = (
                dist(previous_point, current_point) + dist(current_point, next_point) - dist(previous_point, next_point)
            )
            if removal_gain <= 1e-9:
                i += 1
                continue
            best_delta = 1e-9
            best_j = -1
            for neighbour in neighbours[current_point]:
                j = position.get(neighbour)
                if j is None or j in (i, i - 1) or j + 1 >= len(order):
                    continue
                u, v = order[j], order[j + 1]
                insertion_cost = dist(u, current_point) + dist(current_point, v) - dist(u, v)
                delta = removal_gain - insertion_cost
                if delta > best_delta:
                    best_delta = delta
                    best_j = j
            if best_j < 0:
                i += 1
                continue
            order.pop(i)
            target = best_j - 1 if best_j > i else best_j
            order.insert(target + 1, current_point)
            moves += 1
            changed = True
            position = {point_index: pos for pos, point_index in enumerate(order)}
        if not changed or moves >= MAX_RELOCATIONS:
            break
    return order


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
