from __future__ import annotations

from pathlib import Path

from svgpathtools import svg2paths2

from .models import SheetItem, SheetPlacement


def generate_sheet_gcode(
    items: list[SheetItem],
    placements: list[SheetPlacement],
    *,
    sample_step_mm: float,
    mark_diameter_mm: float,
    travel_rate: float,
    draw_rate: float,
    pen_up_command: str,
    pen_down_command: str,
) -> str:
    lines = [
        "; Neje Oracle sheet",
        "G21",
        "G90",
        f"G0 F{travel_rate:.2f}",
        f"G1 F{draw_rate:.2f}",
        pen_up_command,
    ]

    for item, placement in zip(items, placements, strict=True):
        lines.append(f"; item {item.session_id} ({item.source_kind})")
        for polyline in _svg_to_polylines(item.svg_path, placement, sample_step_mm, mark_diameter_mm):
            start_x, start_y = polyline[0]
            lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
            lines.append(pen_down_command)
            for x, y in polyline[1:]:
                lines.append(f"G1 X{x:.3f} Y{y:.3f}")
            lines.append(pen_up_command)

    lines.extend([pen_up_command, "G0 X0 Y0"])
    return "\n".join(lines) + "\n"


def _svg_to_polylines(
    svg_path: Path,
    placement: SheetPlacement,
    sample_step_mm: float,
    mark_diameter_mm: float,
) -> list[list[tuple[float, float]]]:
    paths, _, _ = svg2paths2(str(svg_path))
    non_empty_paths = [path for path in paths if path.length(error=1e-4) > 0]
    if not non_empty_paths:
        raise ValueError(f"SVG contains no drawable paths: {svg_path}")

    min_x = min(path.bbox()[0] for path in non_empty_paths)
    max_x = max(path.bbox()[1] for path in non_empty_paths)
    min_y = min(path.bbox()[2] for path in non_empty_paths)
    max_y = max(path.bbox()[3] for path in non_empty_paths)

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    scale = mark_diameter_mm / max(width, height)
    mid_x = (min_x + max_x) / 2.0
    mid_y = (min_y + max_y) / 2.0

    polylines: list[list[tuple[float, float]]] = []
    for path in non_empty_paths:
        path_points: list[tuple[float, float]] = []
        for segment in path:
            segment_length = max(float(segment.length(error=1e-4)), sample_step_mm)
            sample_count = max(2, int(segment_length / sample_step_mm))
            for index in range(sample_count + 1):
                point = segment.point(index / sample_count)
                path_points.append(
                    (
                        placement.center_x_mm + ((point.real - mid_x) * scale),
                        placement.center_y_mm - ((point.imag - mid_y) * scale),
                    )
                )
        if len(path_points) >= 2:
            polylines.append(_dedupe_points(path_points))
    return polylines


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return deduped
