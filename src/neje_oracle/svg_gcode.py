from __future__ import annotations

import math
from pathlib import Path
from typing import NamedTuple

from svgpathtools import svg2paths2

from .config import SYMBOL_FIT_RATIO
from .models import SheetItem, SheetPlacement
from .origin_markers import DEFAULT_MARKER_DIAMETER_MM, marker_center_for_position, marker_position_for_origin
from .svg_normalizer import read_normalized_svg_metadata


Z_SERVO_PEN_DOWN_COMMAND = "G0 Z-25.000"


class CircleArc(NamedTuple):
    center_x: float
    center_y: float
    radius: float


def symbol_diameter_for_cell(cell_diameter_mm: float) -> float:
    return max(0.0, cell_diameter_mm) * SYMBOL_FIT_RATIO


def parse_cell_progress_markers(gcode: str) -> list[tuple[int, int]]:
    """Return cell-start markers as ``(current_cell, total_cells)`` pairs."""
    markers: list[tuple[int, int]] = []
    for line in gcode.splitlines():
        stripped = line.strip()
        if not stripped.startswith("; cell-start "):
            continue
        raw = stripped.removeprefix("; cell-start ").strip()
        try:
            current, total = raw.split("/", 1)
            markers.append((int(current), int(total)))
        except ValueError:
            continue
    return markers


def generate_sheet_gcode(
    items: list[SheetItem],
    placements: list[SheetPlacement],
    *,
    sample_step_mm: float,
    cell_diameter_mm: float,
    travel_rate: float,
    draw_rate: float,
    pen_up_command: str,
    pen_down_command: str,
    title: str = "sheet",
    return_home: bool = True,
    include_rings: bool = True,
    include_markers: bool = False,
    marker_diameter_mm: float = DEFAULT_MARKER_DIAMETER_MM,
    use_z_servo: bool = False,
    z_down_mm: float = 0.0,
    z_up_mm: float = 25.0,
    z_feed_mm_min: float = 1000.0,
) -> str:
    pen_up = _pen_up_command(pen_up_command, use_z_servo=use_z_servo)
    pen_down = _pen_down_command(pen_down_command, use_z_servo=use_z_servo)
    lines = [
        f"; Neje Oracle {title}",
        "G21",
        "G90",
        f"G0 F{travel_rate:.2f}",
        f"G1 F{draw_rate:.2f}",
        pen_up,
    ]

    current_cell_index = 0
    total_cells = len(items)
    for item, placement in zip(items, placements, strict=True):
        lines.append(f"; item {item.session_id} ({item.source_kind})")
        lines.append(f"; cell-start {current_cell_index}/{total_cells}")
        if include_rings:
            for ring in _ring_arcs(placement, item.source_kind):
                _append_circle_arc_gcode(lines, ring, pen_down=pen_down, pen_up=pen_up)
        if include_markers:
            for marker in _marker_arcs(item, placement, marker_diameter_mm=marker_diameter_mm):
                _append_circle_arc_gcode(lines, marker, pen_down=pen_down, pen_up=pen_up)
        metadata = read_normalized_svg_metadata(item.svg_path)
        if metadata.normalized and metadata.scale > 1.0:
            lines.append(f"; warning normalized overscale {metadata.scale:.3f} may cross cell boundaries")
        _append_polylines_one_pen_down_gcode(
            lines,
            _svg_to_polylines(item.svg_path, placement, sample_step_mm, cell_diameter_mm),
            pen_down=pen_down,
            pen_up=pen_up,
        )
        lines.append(f"; cell-end {current_cell_index}/{total_cells}")
        current_cell_index += 1

    lines.append(pen_up)
    if return_home:
        lines.append("G0 X0 Y0")
    return "\n".join(lines) + "\n"


def _pen_up_command(command: str, *, use_z_servo: bool) -> str:
    return "$H=Z" if use_z_servo else command


def _pen_down_command(command: str, *, use_z_servo: bool) -> str:
    return Z_SERVO_PEN_DOWN_COMMAND if use_z_servo else command


def _append_polyline_gcode(
    lines: list[str],
    polyline: list[tuple[float, float]],
    *,
    pen_down: str,
    pen_up: str,
) -> None:
    start_x, start_y = polyline[0]
    lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
    lines.append(pen_down)
    for x, y in polyline[1:]:
        lines.append(f"G1 X{x:.3f} Y{y:.3f}")
    lines.append(pen_up)


def _append_polylines_one_pen_down_gcode(
    lines: list[str],
    polylines: list[list[tuple[float, float]]],
    *,
    pen_down: str,
    pen_up: str,
) -> None:
    drawable = [polyline for polyline in polylines if len(polyline) >= 2]
    if not drawable:
        return
    start_x, start_y = drawable[0][0]
    lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
    lines.append(pen_down)
    for polyline in drawable:
        first_x, first_y = polyline[0]
        lines.append(f"G1 X{first_x:.3f} Y{first_y:.3f}")
        for x, y in polyline[1:]:
            lines.append(f"G1 X{x:.3f} Y{y:.3f}")
    lines.append(pen_up)


def _append_circle_arc_gcode(
    lines: list[str],
    circle: CircleArc,
    *,
    pen_down: str,
    pen_up: str,
) -> None:
    start_x = circle.center_x + circle.radius
    start_y = circle.center_y
    lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
    lines.append(pen_down)
    lines.append(
        f"G2 X{circle.center_x - circle.radius:.3f} Y{circle.center_y:.3f} "
        f"I{-circle.radius:.3f} J0.000"
    )
    lines.append(
        f"G2 X{start_x:.3f} Y{start_y:.3f} "
        f"I{circle.radius:.3f} J0.000"
    )
    lines.append(pen_up)


def _ring_arcs(placement: SheetPlacement, source_kind: str) -> list[CircleArc]:
    outer = CircleArc(placement.center_x_mm, placement.center_y_mm, placement.diameter_mm / 2.0)
    if source_kind == "user":
        return [outer]
    inner = CircleArc(placement.center_x_mm, placement.center_y_mm, placement.diameter_mm * 0.43)
    return [outer, inner]


def _marker_arcs(
    item: SheetItem,
    placement: SheetPlacement,
    *,
    marker_diameter_mm: float,
) -> list[CircleArc]:
    position = item.marker_position or marker_position_for_origin(item.origin)
    center_x, center_y = marker_center_for_position(placement, position, marker_diameter_mm=marker_diameter_mm)
    return [CircleArc(center_x, center_y, max(marker_diameter_mm, 0.1) / 2.0)]


def _svg_to_polylines(
    svg_path: Path,
    placement: SheetPlacement,
    sample_step_mm: float,
    cell_diameter_mm: float,
) -> list[list[tuple[float, float]]]:
    paths, _, _ = svg2paths2(str(svg_path))
    non_empty_paths = [path for path in paths if path.length(error=1e-4) > 0]
    if not non_empty_paths:
        raise ValueError(f"SVG contains no drawable paths: {svg_path}")

    min_x = min(path.bbox()[0] for path in non_empty_paths)
    max_x = max(path.bbox()[1] for path in non_empty_paths)
    min_y = min(path.bbox()[2] for path in non_empty_paths)
    max_y = max(path.bbox()[3] for path in non_empty_paths)

    metadata = read_normalized_svg_metadata(svg_path)
    if metadata.normalized:
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        scale = symbol_diameter_for_cell(cell_diameter_mm) * metadata.scale / max(width, height)
        mid_x = (min_x + max_x) / 2.0
        mid_y = (min_y + max_y) / 2.0
    else:
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        scale = min(symbol_diameter_for_cell(cell_diameter_mm), cell_diameter_mm) / max(width, height)
        mid_x = (min_x + max_x) / 2.0
        mid_y = (min_y + max_y) / 2.0

    polylines: list[list[tuple[float, float]]] = []
    for path in non_empty_paths:
        path_points: list[tuple[float, float]] = []
        for segment in path:
            segment_length_mm = max(float(segment.length(error=1e-4)) * abs(scale), sample_step_mm)
            sample_count = max(2, math.ceil(segment_length_mm / sample_step_mm))
            for index in range(sample_count + 1):
                point = segment.point(index / sample_count)
                path_points.append(
                    (
                        placement.center_x_mm + ((point.real - mid_x) * scale),
                        placement.center_y_mm + ((point.imag - mid_y) * scale),
                    )
                )
        if len(path_points) >= 2:
            deduped = _dedupe_points(path_points)
            simplified = _simplify_points(deduped, tolerance_mm=min(max(sample_step_mm * 0.2, 0.25), 0.8))
            if len(simplified) >= 2:
                polylines.append(simplified)
    return polylines


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return deduped


def _simplify_points(points: list[tuple[float, float]], *, tolerance_mm: float) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points

    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        max_distance = -1.0
        max_index = start
        for index in range(start + 1, end):
            distance = _point_line_distance(points[index], points[start], points[end])
            if distance > max_distance:
                max_distance = distance
                max_index = index
        if max_distance > tolerance_mm:
            keep.add(max_index)
            stack.append((start, max_index))
            stack.append((max_index, end))
    return [point for index, point in enumerate(points) if index in keep]


def _point_line_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    return abs((dy * px) - (dx * py) + (ex * sy) - (ey * sx)) / math.hypot(dx, dy)
