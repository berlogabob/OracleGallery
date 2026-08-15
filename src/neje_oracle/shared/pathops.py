import heapq
import math

Polylines = list[list[tuple[float, float]]]


def join_with_budget(
    polylines: Polylines,
    max_lifts: int,
    speck_mm: float = 0.0,
    simplify_mm: float = 0.0,
) -> Polylines:
    """Join the globally closest stroke endpoints until the lift budget is met."""
    strokes = [list(stroke) for stroke in polylines if stroke and not _is_speck(stroke, speck_mm)]
    if not strokes:
        return []
    if max_lifts >= len(strokes) - 1:
        return [_simplify(stroke, simplify_mm) for stroke in strokes]

    coordinates = [point for stroke in strokes for point in (stroke[0], stroke[-1])]
    span_x = max(x for x, _ in coordinates) - min(x for x, _ in coordinates)
    span_y = max(y for _, y in coordinates) - min(y for _, y in coordinates)
    cell_size = max(span_x, span_y) / math.sqrt(len(coordinates)) or 1.0
    cells: dict[tuple[int, int], set[int]] = {}
    endpoint_cells: list[tuple[int, int]] = []
    for endpoint, (x, y) in enumerate(coordinates):
        cell = (math.floor(x / cell_size), math.floor(y / cell_size))
        endpoint_cells.append(cell)
        cells.setdefault(cell, set()).add(endpoint)

    min_cell_x = min(x for x, _ in cells)
    max_cell_x = max(x for x, _ in cells)
    min_cell_y = min(y for _, y in cells)
    max_cell_y = max(y for _, y in cells)
    active = [True] * len(coordinates)
    owners = [endpoint // 2 for endpoint in range(len(coordinates))]
    paths = dict(enumerate(strokes))
    ends = {index: (index * 2, index * 2 + 1) for index in range(len(strokes))}

    def nearest(endpoint: int) -> tuple[float, int] | None:
        x, y = coordinates[endpoint]
        cell_x, cell_y = endpoint_cells[endpoint]
        best_endpoint = -1
        best_distance = math.inf
        max_radius = max(
            cell_x - min_cell_x,
            max_cell_x - cell_x,
            cell_y - min_cell_y,
            max_cell_y - cell_y,
        )
        for radius in range(max_radius + 1):
            for cell in _ring_cells(cell_x, cell_y, radius):
                for other in cells.get(cell, ()):
                    if other == endpoint or owners[other] == owners[endpoint]:
                        continue
                    other_x, other_y = coordinates[other]
                    distance = (x - other_x) ** 2 + (y - other_y) ** 2
                    if distance < best_distance or (distance == best_distance and other < best_endpoint):
                        best_distance = distance
                        best_endpoint = other
            if best_endpoint >= 0:
                left = (cell_x - radius) * cell_size
                right = (cell_x + radius + 1) * cell_size
                bottom = (cell_y - radius) * cell_size
                top = (cell_y + radius + 1) * cell_size
                unseen_distance = min(x - left, right - x, y - bottom, top - y)
                if best_distance <= unseen_distance**2:
                    break
        return None if best_endpoint < 0 else (best_distance, best_endpoint)

    candidates: list[tuple[float, int, int]] = []
    for endpoint in range(len(coordinates)):
        candidate = nearest(endpoint)
        if candidate is not None:
            heapq.heappush(candidates, (candidate[0], endpoint, candidate[1]))

    target_strokes = max(1, max_lifts + 1)
    next_owner = len(strokes)
    while len(paths) > target_strokes:
        distance, endpoint_a, endpoint_b = heapq.heappop(candidates)
        if not active[endpoint_a] or not active[endpoint_b] or owners[endpoint_a] == owners[endpoint_b]:
            if active[endpoint_a]:
                candidate = nearest(endpoint_a)
                if candidate is not None:
                    heapq.heappush(candidates, (candidate[0], endpoint_a, candidate[1]))
            continue

        owner_a = owners[endpoint_a]
        owner_b = owners[endpoint_b]
        path_a = paths.pop(owner_a)
        path_b = paths.pop(owner_b)
        left_a, right_a = ends.pop(owner_a)
        left_b, right_b = ends.pop(owner_b)
        if endpoint_a == left_a:
            path_a.reverse()
            outer_a = right_a
        else:
            outer_a = left_a
        if endpoint_b == right_b:
            path_b.reverse()
            outer_b = left_b
        else:
            outer_b = right_b

        if path_a[-1] == path_b[0]:
            path_a.extend(path_b[1:])
        else:
            path_a.extend(path_b)
        paths[next_owner] = path_a
        ends[next_owner] = (outer_a, outer_b)
        owners[outer_a] = owners[outer_b] = next_owner
        for endpoint in (endpoint_a, endpoint_b):
            active[endpoint] = False
            cells[endpoint_cells[endpoint]].remove(endpoint)
        next_owner += 1

    return [_simplify(path, simplify_mm) for path in paths.values()]


def _ring_cells(center_x: int, center_y: int, radius: int):
    if radius == 0:
        yield center_x, center_y
        return
    for x in range(center_x - radius, center_x + radius + 1):
        yield x, center_y - radius
        yield x, center_y + radius
    for y in range(center_y - radius + 1, center_y + radius):
        yield center_x - radius, y
        yield center_x + radius, y


def _is_speck(points: list[tuple[float, float]], threshold: float) -> bool:
    if threshold <= 0:
        return False
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 < threshold**2


def _simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) <= 2 or tolerance <= 0:
        return list(points)
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    tolerance_squared = tolerance**2
    while pending:
        start, end = pending.pop()
        split = -1
        furthest = -1.0
        for index in range(start + 1, end):
            distance = _point_segment_distance_squared(points[index], points[start], points[end])
            if distance > furthest:
                split = index
                furthest = distance
        if furthest > tolerance_squared:
            keep.add(split)
            pending.append((start, split))
            pending.append((split, end))
    return [point for index, point in enumerate(points) if index in keep]


def _point_segment_distance_squared(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == dy == 0:
        return (point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    projected_x = start[0] + ratio * dx
    projected_y = start[1] + ratio * dy
    return (point[0] - projected_x) ** 2 + (point[1] - projected_y) ** 2
