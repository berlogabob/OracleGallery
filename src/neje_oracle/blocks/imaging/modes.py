from __future__ import annotations

import io
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

Polylines = list[list[tuple[float, float]]]

MAX_SEGMENTS_DEFAULT = 40_000


@dataclass(frozen=True)
class ToneGrid:
    darkness: np.ndarray
    cell_mm: float
    width_mm: float
    height_mm: float


def load_tone(
    data: bytes,
    *,
    width_mm: float,
    height_mm: float,
    cell_mm: float,
    invert: bool = False,
    gamma: float = 1.0,
    levels: int | None = None,
    autocontrast: bool = True,
) -> ToneGrid:
    if width_mm <= 0 or height_mm <= 0 or cell_mm <= 0:
        raise ValueError("width_mm, height_mm, and cell_mm must be positive")
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    if levels is not None and levels < 2:
        raise ValueError("levels must be at least 2")

    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("L")
            if autocontrast:
                image = ImageOps.autocontrast(image)
            size = (
                max(1, round(width_mm / cell_mm)),
                max(1, round(height_mm / cell_mm)),
            )
            image = image.resize(size, Image.Resampling.LANCZOS)
            luminance = np.asarray(image, dtype=np.float64) / 255.0
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError("unable to read raster image data") from error

    darkness = np.power(1.0 - luminance, gamma)
    if levels is not None:
        darkness = np.round(darkness * (levels - 1)) / (levels - 1)
    if invert:
        darkness = 1.0 - darkness
    return ToneGrid(darkness, cell_mm, width_mm, height_mm)


def halftone(
    tone: ToneGrid,
    *,
    min_dot_mm: float = 0.0,
    max_dot_mm: float | None = None,
    angle_deg: float = 45.0,
    sides: int = 0,
) -> Polylines:
    max_radius = tone.cell_mm * 0.5 if max_dot_mm is None else max_dot_mm
    if min_dot_mm < 0 or max_radius < min_dot_mm:
        raise ValueError("dot radii must be non-negative and max_dot_mm >= min_dot_mm")
    if sides != 0 and sides < 3:
        raise ValueError("sides must be 0 or at least 3")

    center_x = tone.width_mm / 2.0
    center_y = tone.height_mm / 2.0
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    polylines: Polylines = []

    # Build the lattice over the field's bounding circle, not its bounding box:
    # rotating a box-sized lattice leaves the corners of the sheet bare.
    reach = math.hypot(tone.width_mm, tone.height_mm) / 2.0
    steps = int(math.ceil(reach / tone.cell_mm))
    for grid_y in range(-steps, steps + 1):
        for grid_x in range(-steps, steps + 1):
            local_x = grid_x * tone.cell_mm
            local_y = grid_y * tone.cell_mm
            dot_x = center_x + local_x * cosine - local_y * sine
            dot_y = center_y + local_x * sine + local_y * cosine
            if not (0 <= dot_x <= tone.width_mm and 0 <= dot_y <= tone.height_mm):
                continue
            darkness = _sample_darkness(tone, dot_x, dot_y)
            if darkness <= 0.0:
                continue
            radius = min_dot_mm + (max_radius - min_dot_mm) * math.sqrt(darkness)
            if radius <= 0:
                continue
            dot_sides = sides or min(
                24,
                8 + round(16 * min(1.0, radius / max(tone.cell_mm * 0.5, 1e-12))),
            )
            points = [
                (
                    _clip(
                        dot_x + radius * math.cos(math.tau * index / dot_sides),
                        0,
                        tone.width_mm,
                    ),
                    _clip(
                        dot_y + radius * math.sin(math.tau * index / dot_sides),
                        0,
                        tone.height_mm,
                    ),
                )
                for index in range(dot_sides)
            ]
            polylines.append(points + [points[0]])
    return polylines


def hatch(
    tone: ToneGrid,
    *,
    line_spacing_mm: float = 1.0,
    angle_deg: float = 0.0,
    wavy: bool = False,
    amplitude_mm: float = 0.4,
    min_darkness: float = 0.05,
) -> Polylines:
    if line_spacing_mm <= 0:
        raise ValueError("line_spacing_mm must be positive")
    if amplitude_mm < 0:
        raise ValueError("amplitude_mm must be non-negative")

    angle = math.radians(angle_deg)
    direction = (math.cos(angle), math.sin(angle))
    perpendicular = (-direction[1], direction[0])
    center = (tone.width_mm / 2.0, tone.height_mm / 2.0)
    radius = math.hypot(tone.width_mm, tone.height_mm) / 2.0
    polylines: Polylines = []
    offset = -radius + line_spacing_mm / 2.0
    # Tone must come from line DENSITY, not presence: a fixed threshold turns any
    # photo into a solid block, because nearly every pixel clears it. Each scanline
    # gets its own threshold from a rotating ladder, so `levels` greys emerge from
    # how many of every `levels` lines survive at a given darkness.
    levels = max(1, int(round(line_spacing_mm / max(tone.cell_mm, 1e-6))) * 4)
    line_index = 0

    while offset < radius:
        floor = min_darkness + (1.0 - min_darkness) * (line_index % levels) / levels
        line_index += 1
        origin = (
            center[0] + offset * perpendicular[0],
            center[1] + offset * perpendicular[1],
        )
        interval = _line_interval(origin, direction, tone.width_mm, tone.height_mm)
        if interval is not None:
            start, end = interval
            sample_count = max(1, math.ceil((end - start) / tone.cell_mm))
            run: list[tuple[float, float]] = []
            for index in range(sample_count + 1):
                distance = start + (end - start) * index / sample_count
                x = origin[0] + distance * direction[0]
                y = origin[1] + distance * direction[1]
                darkness = _sample_darkness(tone, x, y)
                if darkness < floor:
                    if len(run) >= 2:
                        polylines.append(run)
                    run = []
                    continue
                displacement = math.sin(distance) * amplitude_mm * darkness if wavy else 0.0
                run.append(
                    (
                        _clip(x + displacement * perpendicular[0], 0, tone.width_mm),
                        _clip(y + displacement * perpendicular[1], 0, tone.height_mm),
                    )
                )
            if len(run) >= 2:
                polylines.append(run)
        offset += line_spacing_mm
    return polylines


def dither(
    tone: ToneGrid,
    *,
    method: str = "floyd",
    dot_mm: float | None = None,
) -> Polylines:
    size = tone.cell_mm * 0.6 if dot_mm is None else dot_mm
    if size < 0:
        raise ValueError("dot_mm must be non-negative")
    values = np.rint(tone.darkness * 255).astype(np.uint8)
    if method == "floyd":
        pixels = np.asarray(Image.fromarray(values, mode="L").convert("1"), dtype=bool)
    elif method == "bayer":
        bayer = np.array(
            [
                [0, 48, 12, 60, 3, 51, 15, 63],
                [32, 16, 44, 28, 35, 19, 47, 31],
                [8, 56, 4, 52, 11, 59, 7, 55],
                [40, 24, 36, 20, 43, 27, 39, 23],
                [2, 50, 14, 62, 1, 49, 13, 61],
                [34, 18, 46, 30, 33, 17, 45, 29],
                [10, 58, 6, 54, 9, 57, 5, 53],
                [42, 26, 38, 22, 41, 25, 37, 21],
            ],
            dtype=np.float64,
        )
        rows, cols = tone.darkness.shape
        threshold = np.tile((bayer + 0.5) / 64.0, ((rows + 7) // 8, (cols + 7) // 8))
        pixels = tone.darkness > threshold[:rows, :cols]
    else:
        raise ValueError("unknown dither method; valid methods: bayer, floyd")
    if size == 0:
        return []

    rows, cols = tone.darkness.shape
    step_x = tone.width_mm / cols
    step_y = tone.height_mm / rows
    radius = size / 2.0
    polylines: Polylines = []
    for row, col in np.argwhere(pixels):
        x = (float(col) + 0.5) * step_x
        y = (float(row) + 0.5) * step_y
        points = [
            (x, _clip(y - radius, 0, tone.height_mm)),
            (_clip(x + radius, 0, tone.width_mm), y),
            (x, _clip(y + radius, 0, tone.height_mm)),
            (_clip(x - radius, 0, tone.width_mm), y),
        ]
        polylines.append(points + [points[0]])
    return polylines


_MARCHING_CASES: tuple[tuple[tuple[int, int], ...], ...] = (
    (),
    ((3, 0),),
    ((0, 1),),
    ((3, 1),),
    ((1, 2),),
    ((3, 0), (1, 2)),
    ((0, 2),),
    ((3, 2),),
    ((2, 3),),
    ((0, 2),),
    ((0, 1), (2, 3)),
    ((1, 2),),
    ((3, 1),),
    ((0, 1),),
    ((3, 0),),
    (),
)


def contour(tone: ToneGrid, *, bands: int = 4, smooth: bool = True) -> Polylines:
    if bands <= 0:
        raise ValueError("bands must be positive")
    minimum = float(np.min(tone.darkness))
    maximum = float(np.max(tone.darkness))
    if minimum == maximum:
        return []

    rows, cols = tone.darkness.shape
    step_x = tone.width_mm / cols
    step_y = tone.height_mm / rows
    x_coordinates = np.concatenate(([-step_x / 2], (np.arange(cols) + 0.5) * step_x, [tone.width_mm + step_x / 2]))
    y_coordinates = np.concatenate(([-step_y / 2], (np.arange(rows) + 0.5) * step_y, [tone.height_mm + step_y / 2]))
    padded = np.pad(tone.darkness, 1, constant_values=minimum - (maximum - minimum))
    polylines: Polylines = []

    for level in np.linspace(minimum, maximum, bands + 2)[1:-1]:
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        cases = (
            (padded[:-1, :-1] >= level).astype(np.uint8)
            + 2 * (padded[:-1, 1:] >= level)
            + 4 * (padded[1:, 1:] >= level)
            + 8 * (padded[1:, :-1] >= level)
        )
        for row, col in np.argwhere((cases != 0) & (cases != 15)):
            top_left = float(padded[row, col])
            top_right = float(padded[row, col + 1])
            bottom_right = float(padded[row + 1, col + 1])
            bottom_left = float(padded[row + 1, col])
            x0 = float(x_coordinates[col])
            x1 = float(x_coordinates[col + 1])
            y0 = float(y_coordinates[row])
            y1 = float(y_coordinates[row + 1])
            edges = (
                _interpolate((x0, y0), (x1, y0), top_left, top_right, level),
                _interpolate((x1, y0), (x1, y1), top_right, bottom_right, level),
                _interpolate((x1, y1), (x0, y1), bottom_right, bottom_left, level),
                _interpolate((x0, y1), (x0, y0), bottom_left, top_left, level),
            )
            for first, second in _MARCHING_CASES[int(cases[row, col])]:
                start = _clip_point(edges[first], tone.width_mm, tone.height_mm)
                end = _clip_point(edges[second], tone.width_mm, tone.height_mm)
                if _point_key(start) != _point_key(end):
                    segments.append((start, end))
        runs = _join_segments(segments)
        polylines.extend(_chaikin(run) if smooth else run for run in runs)
    return polylines


MODES: dict[str, Callable[..., Polylines]] = {
    "halftone": halftone,
    "hatch": hatch,
    "dither": dither,
    "contour": contour,
}


def order_serpentine(polylines: Polylines) -> Polylines:
    rows: dict[int, Polylines] = defaultdict(list)
    for polyline in polylines:
        if polyline:
            rows[math.floor(polyline[0][1])].append(list(polyline))

    ordered: Polylines = []
    previous: tuple[float, float] | None = None
    for row_number, row in enumerate(rows[key] for key in sorted(rows)):
        left_to_right = row_number % 2 == 0
        row.sort(key=lambda line: min(line[0][0], line[-1][0]) if left_to_right else -max(line[0][0], line[-1][0]))
        for polyline in row:
            if previous is not None and _distance(previous, polyline[-1]) < _distance(previous, polyline[0]):
                polyline.reverse()
            ordered.append(polyline)
            previous = polyline[-1]
    return ordered


def travel_length_mm(polylines: Polylines) -> tuple[float, float]:
    draw = sum(
        _distance(start, end) for polyline in polylines for start, end in zip(polyline, polyline[1:], strict=False)
    )
    travel = sum(
        _distance(previous[-1], current[0])
        for previous, current in zip(polylines, polylines[1:], strict=False)
        if previous and current
    )
    return draw, travel


def image_to_polylines(
    data: bytes,
    *,
    mode: str,
    width_mm: float,
    height_mm: float,
    cell_mm: float = 1.0,
    invert: bool = False,
    gamma: float = 1.0,
    levels: int | None = None,
    max_segments: int = MAX_SEGMENTS_DEFAULT,
    **params: Any,
) -> Polylines:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; valid modes: {', '.join(sorted(MODES))}")
    tone = load_tone(
        data,
        width_mm=width_mm,
        height_mm=height_mm,
        cell_mm=cell_mm,
        invert=invert,
        gamma=gamma,
        levels=levels,
    )
    polylines = order_serpentine(MODES[mode](tone, **params))
    polylines = [polyline for polyline in polylines if len(polyline) >= 2]
    segment_count = sum(len(polyline) - 1 for polyline in polylines)
    if segment_count > max_segments:
        raise ValueError(
            f"generated {segment_count} segments, exceeding max_segments={max_segments}; "
            "increase cell_mm or line_spacing_mm, or raise max_segments"
        )
    return polylines


def polylines_to_svg(polylines: Polylines, *, width_mm: float, height_mm: float) -> str:
    """Serialize mm polylines for the direct-SVG print path.

    data-neje-simplify-mm="0" matters: svg_gcode reads it, and the default tolerance
    would otherwise flatten small halftone dots away.
    """
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width_mm:g} {height_mm:g}" width="{width_mm:g}mm" '
        f'height="{height_mm:g}mm" data-neje-simplify-mm="0">'
    ]
    lines.extend(
        f'<polyline points="{" ".join(f"{x:.3f},{y:.3f}" for x, y in polyline)}" '
        'fill="none" stroke="black" stroke-width="0.3"/>'
        for polyline in polylines
    )
    lines.append("</svg>")
    return "\n".join(lines)


def image_to_svg(
    data: bytes,
    *,
    mode: str,
    width_mm: float,
    height_mm: float,
    **kwargs: Any,
) -> str:
    polylines = image_to_polylines(
        data,
        mode=mode,
        width_mm=width_mm,
        height_mm=height_mm,
        **kwargs,
    )
    return polylines_to_svg(polylines, width_mm=width_mm, height_mm=height_mm)


def _clip(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clip_point(point: tuple[float, float], width: float, height: float) -> tuple[float, float]:
    return _clip(point[0], 0, width), _clip(point[1], 0, height)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _sample_darkness(tone: ToneGrid, x: float, y: float) -> float:
    rows, cols = tone.darkness.shape
    column = min(cols - 1, max(0, int(x * cols / tone.width_mm)))
    row = min(rows - 1, max(0, int(y * rows / tone.height_mm)))
    return float(tone.darkness[row, column])


def _line_interval(
    origin: tuple[float, float],
    direction: tuple[float, float],
    width: float,
    height: float,
) -> tuple[float, float] | None:
    lower = -math.inf
    upper = math.inf
    for coordinate, delta, maximum in zip(origin, direction, (width, height), strict=True):
        if abs(delta) < 1e-12:
            if not 0 <= coordinate <= maximum:
                return None
            continue
        first = -coordinate / delta
        second = (maximum - coordinate) / delta
        lower = max(lower, min(first, second))
        upper = min(upper, max(first, second))
    return (lower, upper) if upper > lower else None


def _interpolate(
    start: tuple[float, float],
    end: tuple[float, float],
    start_value: float,
    end_value: float,
    level: float,
) -> tuple[float, float]:
    ratio = 0.5 if start_value == end_value else (level - start_value) / (end_value - start_value)
    return (
        start[0] + _clip(ratio, 0, 1) * (end[0] - start[0]),
        start[1] + _clip(ratio, 0, 1) * (end[1] - start[1]),
    )


def _point_key(point: tuple[float, float]) -> tuple[int, int]:
    return round(point[0] * 1_000_000), round(point[1] * 1_000_000)


def _join_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> Polylines:
    adjacency: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (start, end) in enumerate(segments):
        adjacency[_point_key(start)].append(index)
        adjacency[_point_key(end)].append(index)
    unused = set(range(len(segments)))
    starts = [key for key, indexes in adjacency.items() if len(indexes) == 1]
    starts.extend(key for key, indexes in adjacency.items() if len(indexes) != 1)
    polylines: Polylines = []

    for start_key in starts:
        available = [index for index in adjacency[start_key] if index in unused]
        while available:
            points: list[tuple[float, float]] = []
            current_key = start_key
            while True:
                candidates = [index for index in adjacency[current_key] if index in unused]
                if not candidates:
                    break
                index = candidates[0]
                unused.remove(index)
                first, second = segments[index]
                if not points:
                    points.append(first if _point_key(first) == current_key else second)
                next_point = second if _point_key(first) == current_key else first
                points.append(next_point)
                current_key = _point_key(next_point)
            if len(points) >= 2:
                polylines.append(points)
            available = [index for index in adjacency[start_key] if index in unused]
    return polylines


def _chaikin(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    closed = _point_key(points[0]) == _point_key(points[-1])
    source = points[:-1] if closed else points
    smoothed = [] if closed else [source[0]]
    pairs = zip(source, source[1:] + ([source[0]] if closed else []), strict=False)
    for start, end in pairs:
        smoothed.extend(
            (
                (0.75 * start[0] + 0.25 * end[0], 0.75 * start[1] + 0.25 * end[1]),
                (0.25 * start[0] + 0.75 * end[0], 0.25 * start[1] + 0.75 * end[1]),
            )
        )
    if closed:
        smoothed.append(smoothed[0])
    else:
        smoothed.append(source[-1])
    return smoothed
