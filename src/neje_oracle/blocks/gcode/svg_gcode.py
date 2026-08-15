from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from svgpathtools import svg2paths2

from ...shared.config import SYMBOL_FIT_RATIO
from ...shared.models import SheetItem, SheetPlacement
from ...shared.origin_markers import DEFAULT_MARKER_DIAMETER_MM, marker_center_for_position, marker_position_for_origin
from ...shared.pathops import join_with_budget
from ..symbols.svg_normalizer import read_normalized_svg_metadata

DEFAULT_IMPORTED_SVG_SIMPLIFY_MM = 0.05
DEFAULT_MIN_EMITTED_SEGMENT_MM = 0.1


def symbol_diameter_for_cell(cell_diameter_mm: float) -> float:
    return max(0.0, cell_diameter_mm) * SYMBOL_FIT_RATIO


INNER_RING_RATIO = 0.43


def ring_radii_mm(cell_diameter_mm: float, source_kind: str) -> list[float]:
    """Ring radii the pen actually draws, in mm, outermost first.

    One definition, shared with the operator preview. Each side used to carry its own and
    they disagreed on every sheet: the plotter drew D/2 and D*0.43, while the preview
    drew D*0.43 and D*0.378 because it scaled by SYMBOL_FIT_RATIO first. So the preview's
    outer ring sat exactly where the pen drew its *inner* one, and the pale cell guide --
    which reads as decoration -- sat where the pen actually went.

    Anything that is not a claimed user job is filler and gets the second ring; callers
    spell that "idle" (preview) or "placeholder" (daemon), so only "user" is matched.
    """
    diameter = max(0.0, cell_diameter_mm)
    outer = diameter / 2.0
    if source_kind == "user":
        return [outer]
    return [outer, diameter * INNER_RING_RATIO]


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
    xy_acceleration_mm_s2: float = 0.0,
    title: str = "sheet",
    return_home: bool = True,
    include_rings: bool = True,
    include_markers: bool = False,
    marker_diameter_mm: float = DEFAULT_MARKER_DIAMETER_MM,
    use_z_servo: bool = False,
    z_down_mm: float = 0.0,
    z_up_mm: float = 25.0,
    z_feed_mm_min: float = 1000.0,
    pen_down_dwell_ms: float = 0.0,
) -> str:
    pen_up = _pen_up_command(pen_up_command, use_z_servo=use_z_servo, z_up_mm=z_up_mm)
    pen_down = _pen_down_command(
        pen_down_command, use_z_servo=use_z_servo, z_down_mm=z_down_mm, z_feed_mm_min=z_feed_mm_min
    )
    dwell = _dwell_command(pen_down_dwell_ms)
    lines = [
        f"; Neje Oracle {title}",
        f"; effective draw feed F{draw_rate:.2f} mm/min",
        _xy_acceleration_comment(xy_acceleration_mm_s2),
        "G21",
        "G90",
        f"G0 F{travel_rate:.2f}",
        f"G1 F{draw_rate:.2f}",
        pen_up,
    ]

    total_cells = len(items)
    for current_cell_index, (item, placement) in enumerate(zip(items, placements, strict=True)):
        lines.append(f"; item {item.session_id} ({item.source_kind})")
        lines.append(f"; cell-start {current_cell_index}/{total_cells}")
        if include_rings:
            for ring in _ring_polylines(placement, item.source_kind):
                _append_polyline_gcode(lines, ring, pen_down=pen_down, pen_up=pen_up, dwell=dwell)
        if include_markers:
            for marker in _marker_polylines(item, placement, marker_diameter_mm=marker_diameter_mm):
                _append_polyline_gcode(lines, marker, pen_down=pen_down, pen_up=pen_up, dwell=dwell)
        metadata = read_normalized_svg_metadata(item.svg_path)
        if metadata.normalized and metadata.scale > 1.0:
            lines.append(f"; warning normalized overscale {metadata.scale:.3f} may cross cell boundaries")
        for polyline in _svg_to_polylines(item.svg_path, placement, sample_step_mm, cell_diameter_mm):
            _append_polyline_gcode(lines, polyline, pen_down=pen_down, pen_up=pen_up, dwell=dwell)
        lines.append(f"; cell-end {current_cell_index}/{total_cells}")
        current_cell_index += 1

    lines.append(pen_up)
    if return_home:
        lines.append("G0 X0 Y0")
    return "\n".join(lines) + "\n"


def generate_absolute_svg_gcode(
    svg_path: Path,
    *,
    sample_step_mm: float,
    travel_rate: float,
    draw_rate: float,
    pen_up_command: str,
    pen_down_command: str,
    xy_acceleration_mm_s2: float = 0.0,
    title: str = "direct SVG",
    return_home: bool = True,
    use_z_servo: bool = False,
    z_down_mm: float = 0.0,
    z_up_mm: float = 25.0,
    z_feed_mm_min: float = 1000.0,
    pen_down_dwell_ms: float = 0.0,
    origin_x_mm: float = 0.0,
    origin_y_mm: float = 0.0,
    keep_non_negative: bool = False,
    max_x_mm: float | None = None,
    max_y_mm: float | None = None,
) -> str:
    pen_up = _pen_up_command(pen_up_command, use_z_servo=use_z_servo, z_up_mm=z_up_mm)
    pen_down = _pen_down_command(
        pen_down_command, use_z_servo=use_z_servo, z_down_mm=z_down_mm, z_feed_mm_min=z_feed_mm_min
    )
    dwell = _dwell_command(pen_down_dwell_ms)
    polylines = svg_to_polylines_mm(svg_path, sample_step_mm)
    safety_shift_x = 0.0
    safety_shift_y = 0.0
    if origin_x_mm or origin_y_mm:
        polylines = _offset_polylines(polylines, origin_x_mm, origin_y_mm)
    if keep_non_negative:
        polylines, safety_shift_x, safety_shift_y = _shift_polylines_non_negative(polylines)
    if max_x_mm is not None or max_y_mm is not None:
        points = [point for polyline in polylines for point in polyline]
        if points:
            actual_x = max(x for x, _ in points)
            actual_y = max(y for _, y in points)
            if max_x_mm is not None and actual_x > max_x_mm:
                raise ValueError(
                    f"SVG extends to {actual_x:.1f}mm which exceeds the configured sheet width of {max_x_mm:.1f}mm"
                )
            if max_y_mm is not None and actual_y > max_y_mm:
                raise ValueError(
                    f"SVG extends to {actual_y:.1f}mm which exceeds the configured sheet height of {max_y_mm:.1f}mm"
                )
    lines = [
        f"; Neje Oracle {title}",
        "; absolute SVG coordinates: origin is upper-left, +X right, +Y down",
        f"; SVG reference origin maps to X{origin_x_mm:.3f} Y{origin_y_mm:.3f}",
        f"; non-negative safety shift X{safety_shift_x:.3f} Y{safety_shift_y:.3f}",
        f"; effective draw feed F{draw_rate:.2f} mm/min",
        _xy_acceleration_comment(xy_acceleration_mm_s2),
        "G21",
        "G90",
        f"G0 F{travel_rate:.2f}",
        f"G1 F{draw_rate:.2f}",
        pen_up,
    ]

    for polyline in polylines:
        _append_polyline_gcode(lines, polyline, pen_down=pen_down, pen_up=pen_up, dwell=dwell)

    lines.append(pen_up)
    if return_home:
        lines.append("G0 X0 Y0")
    return "\n".join(lines) + "\n"


def _pen_up_command(command: str, *, use_z_servo: bool, z_up_mm: float) -> str:
    return f"G0 Z{z_up_mm:.3f}" if use_z_servo else command


def _pen_down_command(command: str, *, use_z_servo: bool, z_down_mm: float, z_feed_mm_min: float) -> str:
    return f"G1 Z{z_down_mm:.3f} F{z_feed_mm_min:.2f}" if use_z_servo else command


def _xy_acceleration_comment(xy_acceleration_mm_s2: float) -> str:
    if xy_acceleration_mm_s2 <= 0:
        return "; XY acceleration uses controller saved settings"
    return f"; XY acceleration setting {xy_acceleration_mm_s2:.3f} mm/s^2 is recorded only; controller settings are not changed during print"


def _dwell_command(pen_down_dwell_ms: float) -> str | None:
    """G4 after pen-down, or None when no dwell is wanted.

    GRBL and FluidNC read `G4 P` in SECONDS -- Marlin is the one that uses milliseconds.
    Profiles store ms because that is what an operator wants to type, so the conversion
    happens here and nowhere else. Getting it backwards is a 1000x error: a 150 ms dwell
    would become 150 seconds on every single stroke.
    """
    if pen_down_dwell_ms <= 0:
        return None
    return f"G4 P{pen_down_dwell_ms / 1000.0:.3f}"


def _append_polyline_gcode(
    lines: list[str],
    polyline: list[tuple[float, float]],
    *,
    pen_down: str,
    pen_up: str,
    dwell: str | None = None,
) -> None:
    start_x, start_y = polyline[0]
    lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
    lines.append(pen_down)
    if dwell is not None:
        lines.append(dwell)
    for x, y in polyline[1:]:
        lines.append(f"G1 X{x:.3f} Y{y:.3f}")
    lines.append(pen_up)


def _ring_polylines(placement: SheetPlacement, source_kind: str) -> list[list[tuple[float, float]]]:
    return [
        _circle_polyline(placement.center_x_mm, placement.center_y_mm, radius)
        for radius in ring_radii_mm(placement.diameter_mm, source_kind)
    ]


def _marker_polylines(
    item: SheetItem,
    placement: SheetPlacement,
    *,
    marker_diameter_mm: float,
) -> list[list[tuple[float, float]]]:
    position = item.marker_position or marker_position_for_origin(item.origin)
    center_x, center_y = marker_center_for_position(placement, position, marker_diameter_mm=marker_diameter_mm)
    return [_circle_polyline(center_x, center_y, max(marker_diameter_mm, 0.1) / 2.0, segments=24)]


def _circle_polyline(center_x: float, center_y: float, radius: float, segments: int = 72) -> list[tuple[float, float]]:
    import math

    return [
        (
            center_x + (math.cos((math.tau * index) / segments) * radius),
            center_y + (math.sin((math.tau * index) / segments) * radius),
        )
        for index in range(segments + 1)
    ]


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
        symbol_diameter = symbol_diameter_for_cell(cell_diameter_mm)
        scale = symbol_diameter * metadata.scale / max(width, height)
        center_y_offset_mm = metadata.center_y_offset * symbol_diameter / metadata.base_diameter
        mid_x = (min_x + max_x) / 2.0
        mid_y = (min_y + max_y) / 2.0
    else:
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        scale = min(symbol_diameter_for_cell(cell_diameter_mm), cell_diameter_mm) / max(width, height)
        center_y_offset_mm = 0.0
        mid_x = (min_x + max_x) / 2.0
        mid_y = (min_y + max_y) / 2.0

    polylines: list[list[tuple[float, float]]] = []
    placement_scale = max(0.0, placement.symbol_scale)
    rotation_rad = math.radians(placement.rotation_deg)
    rotation_cos = math.cos(rotation_rad)
    rotation_sin = math.sin(rotation_rad)
    for path in non_empty_paths:
        path_points: list[tuple[float, float]] = []
        for segment in path:
            segment_length = max(float(segment.length(error=1e-4)), sample_step_mm)
            sample_count = max(2, int(segment_length / max(sample_step_mm, 0.001)))
            for index in range(sample_count + 1):
                point = segment.point(index / sample_count)
                local_x = (point.real - mid_x) * scale * placement_scale
                local_y = (center_y_offset_mm + ((point.imag - mid_y) * scale)) * placement_scale
                path_points.append(_transform_local_point(placement, local_x, local_y, rotation_cos, rotation_sin))
        if len(path_points) >= 2:
            polylines.append(_dedupe_points(path_points))
    lift_budget = _pen_lift_budget(svg_path)
    if lift_budget is not None:
        polylines = join_with_budget(polylines, lift_budget)
    simplify_tolerance = _simplify_tolerance_mm(svg_path)
    return _postprocess_svg_polylines(polylines, simplify_tolerance=simplify_tolerance)


def _transform_local_point(
    placement: SheetPlacement,
    local_x: float,
    local_y: float,
    rotation_cos: float,
    rotation_sin: float,
) -> tuple[float, float]:
    return (
        placement.center_x_mm + (local_x * rotation_cos) - (local_y * rotation_sin),
        placement.center_y_mm + (local_x * rotation_sin) + (local_y * rotation_cos),
    )


def svg_to_polylines_mm(svg_path: Path, sample_step_mm: float) -> list[list[tuple[float, float]]]:
    """Sample an SVG's paths into millimetre polylines, in the SVG's own coordinate frame."""
    paths, _, _ = svg2paths2(str(svg_path))
    non_empty_paths = [path for path in paths if path.length(error=1e-4) > 0]
    if not non_empty_paths:
        raise ValueError(f"SVG contains no drawable paths: {svg_path}")

    min_x, min_y, scale_x, scale_y = _svg_user_unit_to_mm_transform(svg_path)
    polylines: list[list[tuple[float, float]]] = []
    for path in non_empty_paths:
        path_points: list[tuple[float, float]] = []
        for segment in path:
            segment_length = max(float(segment.length(error=1e-4)), sample_step_mm)
            sample_count = max(2, int(segment_length / max(sample_step_mm, 0.001)))
            for index in range(sample_count + 1):
                point = segment.point(index / sample_count)
                path_points.append(
                    (
                        (point.real - min_x) * scale_x,
                        (point.imag - min_y) * scale_y,
                    )
                )
        if len(path_points) >= 2:
            polylines.append(_dedupe_points(path_points))
    return _postprocess_svg_polylines(polylines)


def _offset_polylines(
    polylines: list[list[tuple[float, float]]],
    offset_x_mm: float,
    offset_y_mm: float,
) -> list[list[tuple[float, float]]]:
    return [[(x + offset_x_mm, y + offset_y_mm) for x, y in polyline] for polyline in polylines]


def _shift_polylines_non_negative(
    polylines: list[list[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], float, float]:
    points = [point for polyline in polylines for point in polyline]
    if not points:
        return polylines, 0.0, 0.0
    shift_x = max(0.0, -min(x for x, _ in points))
    shift_y = max(0.0, -min(y for _, y in points))
    if shift_x == 0.0 and shift_y == 0.0:
        return polylines, 0.0, 0.0
    return _offset_polylines(polylines, shift_x, shift_y), shift_x, shift_y


def _svg_user_unit_to_mm_transform(svg_path: Path) -> tuple[float, float, float, float]:
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError:
        return 0.0, 0.0, 1.0, 1.0
    view_box = str(root.get("viewBox", "") or "").strip()
    values = [float(value) for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", view_box)]
    if len(values) == 4 and values[2] != 0 and values[3] != 0:
        width_mm = _svg_length_to_mm(root.get("width"))
        height_mm = _svg_length_to_mm(root.get("height"))
        scale_x = width_mm / values[2] if width_mm is not None else 1.0
        scale_y = height_mm / values[3] if height_mm is not None else 1.0
        return values[0], values[1], scale_x, scale_y
    return 0.0, 0.0, 1.0, 1.0


def _svg_length_to_mm(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    match = re.fullmatch(r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-z%]*)\s*", raw_value)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"", "mm"}:
        return value
    if unit == "cm":
        return value * 10.0
    if unit == "in":
        return value * 25.4
    if unit == "pt":
        return value * 25.4 / 72.0
    if unit in {"px", "user"}:
        return value * 25.4 / 96.0
    return None


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return deduped


def _postprocess_svg_polylines(
    polylines: list[list[tuple[float, float]]],
    *,
    simplify_tolerance: float = 0.0,
) -> list[list[tuple[float, float]]]:
    tolerance = max(simplify_tolerance, DEFAULT_IMPORTED_SVG_SIMPLIFY_MM)
    processed = [_simplify_polyline(polyline, tolerance) for polyline in polylines if len(polyline) >= 2]
    return [
        _filter_short_segments(polyline, DEFAULT_MIN_EMITTED_SEGMENT_MM) for polyline in processed if len(polyline) >= 2
    ]


def _filter_short_segments(points: list[tuple[float, float]], min_segment_mm: float) -> list[tuple[float, float]]:
    if len(points) <= 2 or min_segment_mm <= 0:
        return points
    filtered = [points[0]]
    for point in points[1:-1]:
        if _distance(filtered[-1], point) >= min_segment_mm:
            filtered.append(point)
    if filtered[-1] != points[-1]:
        filtered.append(points[-1])
    return filtered


def _pen_lift_budget(svg_path: Path) -> int | None:
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError:
        return None
    truthy = {"1", "true", "yes", "on", "single-stroke"}
    lift_budget = None
    for element in root.iter():
        if str(element.get("data-neje-single-stroke", "")).strip().lower() in truthy:
            return 0
        if str(element.get("data-neje-pen-mode", "")).strip().lower() == "single-stroke":
            return 0
        raw_value = str(element.get("data-neje-lift-budget", "")).strip()
        if raw_value and lift_budget is None:
            try:
                lift_budget = max(0, int(raw_value))
                # 1024 is the shared off sentinel used by the GUI slider.
                if lift_budget >= 1024:
                    return None
            except ValueError:
                continue
    return lift_budget


def _simplify_tolerance_mm(svg_path: Path) -> float:
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError:
        return 0.0
    for element in root.iter():
        raw_value = str(element.get("data-neje-simplify-mm", "")).strip()
        if not raw_value:
            continue
        try:
            return max(0.0, float(raw_value))
        except ValueError:
            return 0.0
    return 0.0


def _simplify_polyline(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) <= 2 or tolerance <= 0:
        return points
    max_distance = -1.0
    split_index = 0
    start = points[0]
    end = points[-1]
    for index, point in enumerate(points[1:-1], start=1):
        distance = _point_line_distance(point, start, end)
        if distance > max_distance:
            max_distance = distance
            split_index = index
    if max_distance > tolerance:
        left = _simplify_polyline(points[: split_index + 1], tolerance)
        right = _simplify_polyline(points[split_index:], tolerance)
        return left[:-1] + right
    return [start, end]


def _point_line_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    if start == end:
        return _distance(point, start)
    x, y = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    ratio = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ((dx * dx) + (dy * dy))))
    projected = (x1 + ratio * dx, y1 + ratio * dy)
    return _distance(point, projected)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
