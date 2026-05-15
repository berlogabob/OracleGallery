from pathlib import Path
from random import Random

from neje_oracle.models import SheetItem, SheetPlacement
from neje_oracle.session_generator import build_variant_svg
from neje_oracle.svg_gcode import generate_sheet_gcode


def test_gcode_fits_symbol_inside_cell_with_internal_safety_ratio(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="a", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    points = [point for point in points if point != (0.0, 0.0)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    assert min(xs) >= 80
    assert max(xs) <= 120
    assert min(ys) >= 80
    assert max(ys) <= 120


def test_normalized_overscale_is_not_refit_to_cell(tmp_path: Path) -> None:
    source_svg = tmp_path / "source.svg"
    source_svg.write_text(
        "<svg width='800' height='800' xmlns='http://www.w3.org/2000/svg'>"
        "<polyline points='100,100 700,100 700,700 100,700'/>"
        "</svg>",
        encoding="utf-8",
    )
    small_svg = tmp_path / "small.svg"
    large_svg = tmp_path / "large.svg"
    small_svg.write_text(
        build_variant_svg(source_svg, marker_kind="user", scale=1.0, rng=Random(1), jitter_px=0),
        encoding="utf-8",
    )
    large_svg.write_text(
        build_variant_svg(source_svg, marker_kind="user", scale=5.0, rng=Random(1), jitter_px=0),
        encoding="utf-8",
    )

    small_width = _gcode_draw_width(small_svg)
    large_width = _gcode_draw_width(large_svg)

    assert large_width > small_width * 4.5


def test_z_servo_gcode_uses_z_commands_instead_of_spindle(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="a", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
        use_z_servo=True,
        z_down_mm=-12,
        z_up_mm=0,
        z_feed_mm_min=1000,
    )

    assert "M3" not in gcode
    assert "M5" not in gcode
    assert "$H=Z" in gcode
    assert "G0 Z0.000" not in gcode
    assert "G0 Z-25.000" in gcode
    assert "G0 Z-12.000" not in gcode


def test_svg_coordinates_use_top_left_origin_with_positive_y_down(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="a", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert "G0 X82.800 Y82.800" in gcode
    assert "G1 X117.200 Y117.200" in gcode


def test_rings_are_generated_at_print_time(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    with_rings = generate_sheet_gcode(
        [SheetItem(source_kind="placeholder", session_id="idle", title="idle", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)],
        sample_step_mm=20,
        cell_diameter_mm=80,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=True,
    )
    without_rings = generate_sheet_gcode(
        [SheetItem(source_kind="placeholder", session_id="idle", title="idle", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)],
        sample_step_mm=20,
        cell_diameter_mm=80,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert "G2 X" in with_rings
    assert "G2 X" not in without_rings


def test_origin_markers_are_generated_at_print_time(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    without_markers = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="real", title="real", svg_path=svg_path, origin="real_macmini")],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)],
        sample_step_mm=20,
        cell_diameter_mm=80,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
        include_markers=False,
    )
    with_markers = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="real", title="real", svg_path=svg_path, origin="real_macmini")],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)],
        sample_step_mm=20,
        cell_diameter_mm=80,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
        include_markers=True,
        marker_diameter_mm=1.5,
    )

    assert "G2 X" in with_markers
    assert "G2 X" not in without_markers


def _gcode_draw_width(svg_path: Path) -> float:
    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id=svg_path.stem, title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    points = [point for point in points if point != (0.0, 0.0)]
    xs = [point[0] for point in points]
    return max(xs) - min(xs)
