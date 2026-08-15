from pathlib import Path
from random import Random

import pytest

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode, generate_sheet_gcode
from neje_oracle.blocks.symbols.session_generator import build_variant_svg
from neje_oracle.blocks.symbols.svg_normalizer import normalize_svg_file, read_normalized_svg_metadata
from neje_oracle.shared.models import SheetItem, SheetPlacement


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


def test_kind_soul_normalized_symbol_has_upward_center_correction(tmp_path: Path) -> None:
    source_svg = Path("assets/symbols/test_the_kind_soul_220047_plotter.svg")
    normalized_svg = tmp_path / "kind.svg"
    normalized_svg.write_text(normalize_svg_file(source_svg, marker_kind="user", scale=1.0), encoding="utf-8")

    metadata = read_normalized_svg_metadata(normalized_svg)
    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="kind", title="kind", svg_path=normalized_svg)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)],
        sample_step_mm=2,
        cell_diameter_mm=80,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
        return_home=False,
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    ys = [point[1] for point in points]

    assert metadata.center_y_offset < 0
    assert (min(ys) + max(ys)) / 2 < 100


def test_sheet_gcode_accepts_zero_sample_step(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'>"
        "<path d='M0,0 L0.001,0' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="a", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=0,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert gcode


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
        z_down_mm=-25,
        z_up_mm=0,
        z_feed_mm_min=750.0,
    )

    assert "M3" not in gcode
    assert "M5" not in gcode
    assert "G0 Z0.000" in gcode
    assert "G1 Z-25.000 F750.00" in gcode
    assert "G0 Z-25.000" not in gcode


def test_xy_acceleration_setting_does_not_write_fluidnc_axis_settings(tmp_path: Path) -> None:
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
        xy_acceleration_mm_s2=1000,
        include_rings=False,
    )

    assert "$120=" not in gcode
    assert "$121=" not in gcode
    assert "recorded only" in gcode


def test_zero_xy_acceleration_uses_controller_saved_settings(tmp_path: Path) -> None:
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
        xy_acceleration_mm_s2=0,
        include_rings=False,
    )

    assert "$120=" not in gcode
    assert "$121=" not in gcode
    assert "; XY acceleration uses controller saved settings" in gcode


def test_svg_y_axis_is_not_mirrored_for_upper_left_work_zero(tmp_path: Path) -> None:
    svg_path = tmp_path / "mark.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M50,10 L50,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="a", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=100,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    move_lines = [line for line in gcode.splitlines() if line.startswith(("G0 X", "G1 X"))]
    start_y = float(move_lines[0].split("Y", 1)[1])
    end_y = float(move_lines[1].split("Y", 1)[1])

    assert start_y < end_y


def test_sheet_placement_rotation_and_symbol_scale_affect_gcode(tmp_path: Path) -> None:
    svg_path = tmp_path / "line.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,50 L90,50' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    base = _gcode_points_for_placement(
        svg_path, SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)
    )
    scaled = _gcode_points_for_placement(
        svg_path, SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80, symbol_scale=0.5)
    )
    rotated = _gcode_points_for_placement(
        svg_path, SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80, rotation_deg=90)
    )

    assert _axis_span(scaled, axis=0) < _axis_span(base, axis=0) * 0.6
    assert _axis_span(rotated, axis=1) > _axis_span(rotated, axis=0) * 5


def test_absolute_svg_gcode_preserves_inkscape_mm_page_coordinates(tmp_path: Path) -> None:
    svg_path = tmp_path / "inkscape_rect.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='210mm' height='297mm' viewBox='0 0 210 297'>"
        "<path d='M 5,5 H 105 V 155 H 5 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=200,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    points = [point for point in points if point != (0.0, 0.0)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    assert min(xs) == 5.0
    assert max(xs) == 105.0
    assert min(ys) == 5.0
    assert max(ys) == 155.0


def test_absolute_svg_gcode_rejects_coordinates_outside_configured_sheet(tmp_path: Path) -> None:
    svg_path = tmp_path / "oversized.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='2000mm' height='2000mm' viewBox='0 0 2000 2000'>"
        "<path d='M 0,0 L 2000,2000' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exceeds the configured sheet width"):
        generate_absolute_svg_gcode(
            svg_path,
            sample_step_mm=2000,
            travel_rate=5000,
            draw_rate=1800,
            pen_up_command="M5",
            pen_down_command="M3 S15",
            keep_non_negative=True,
            max_x_mm=250.0,
            max_y_mm=440.0,
        )


def test_absolute_svg_gcode_accepts_coordinates_inside_configured_sheet(tmp_path: Path) -> None:
    svg_path = tmp_path / "in_bounds.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='100mm' height='100mm' viewBox='0 0 100 100'>"
        "<path d='M 0,0 L 100,100' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=100,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        keep_non_negative=True,
        max_x_mm=250.0,
        max_y_mm=440.0,
    )


def test_absolute_svg_gcode_can_offset_negative_reference_artwork(tmp_path: Path) -> None:
    svg_path = tmp_path / "negative_frame.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='160mm' height='200mm' viewBox='0 0 160 200'>"
        "<path d='M -6,-26 H 154 V 174 H -6 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=200,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        origin_x_mm=25,
        origin_y_mm=25,
        keep_non_negative=True,
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    points = [point for point in points if point != (0.0, 0.0)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    assert min(xs) == 19.0
    assert min(ys) == 0.0
    assert "; SVG reference origin maps to X25.000 Y25.000" in gcode
    assert "; non-negative safety shift X0.000 Y1.000" in gcode


def test_absolute_svg_gcode_simplifies_dense_frame_segments(tmp_path: Path) -> None:
    svg_path = tmp_path / "negative_frame.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='160mm' height='200mm' viewBox='0 0 160 200'>"
        "<path d='M -6,-26 H 154 V 174 H -6 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=0.5,
        travel_rate=8000,
        draw_rate=5000,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        origin_x_mm=25,
        origin_y_mm=25,
        keep_non_negative=True,
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    assert _gcode_draw_line_count(gcode) < 50
    assert min(xs) == 0.0
    assert max(xs) == 179.0
    assert min(ys) == 0.0
    assert max(ys) == 200.0


def test_symbol_sheet_gcode_filters_tiny_svg_segments() -> None:
    svg_path = Path("assets/symbols/test_the_kind_soul_220047_plotter.svg")
    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="kind", title="Kind", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)],
        sample_step_mm=0.05,
        cell_diameter_mm=18,
        travel_rate=8000,
        draw_rate=5000,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3]) for line in gcode.splitlines() if line.startswith("G1 X")
    ]
    distances = [_distance(points[index - 1], points[index]) for index in range(1, len(points))]

    assert distances
    assert sorted(distances)[len(distances) // 2] >= 0.1


def test_single_stroke_symbol_metadata_keeps_pen_down_across_paths(tmp_path: Path) -> None:
    svg_path = tmp_path / "spiral.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<g data-neje-single-stroke='true'>"
        "<path d='M10,50 L50,50' stroke='black' fill='none'/>"
        "<path d='M50,50 L90,50' stroke='black' fill='none'/>"
        "</g>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="a", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=100,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert gcode.count("M3 S15") == 1


def test_20260421_223735_draws_as_single_stroke_for_speed() -> None:
    svg_path = Path("assets/symbols/20260421_223735_plotter.svg")

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="20260421_223735", title="A", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert svg_path.read_text(encoding="utf-8").count("<polyline") == 2
    assert 'data-neje-single-stroke="true"' in svg_path.read_text(encoding="utf-8")
    assert 'data-neje-simplify-mm="0.04"' in svg_path.read_text(encoding="utf-8")
    assert gcode.count("M3 S15") == 1
    assert _gcode_draw_line_count(gcode) < 400


def test_kind_soul_draws_as_single_stroke_for_speed() -> None:
    svg_path = Path("assets/symbols/test_the_kind_soul_220047_plotter.svg")

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="kind", title="Kind", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert svg_path.read_text(encoding="utf-8").count("<polyline") == 3
    assert 'data-neje-single-stroke="true"' in svg_path.read_text(encoding="utf-8")
    assert 'data-neje-simplify-mm="0.02"' in svg_path.read_text(encoding="utf-8")
    assert gcode.count("M3 S15") == 1
    assert _gcode_draw_line_count(gcode) < 100


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

    assert with_rings.count("G1 X") > without_rings.count("G1 X")


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

    assert with_markers.count("G1 X") > without_markers.count("G1 X")


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


def _gcode_points_for_placement(svg_path: Path, placement: SheetPlacement) -> list[tuple[float, float]]:
    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id=svg_path.stem, title="A", svg_path=svg_path)],
        [placement],
        sample_step_mm=20,
        cell_diameter_mm=80,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
        return_home=False,
    )
    return [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]


def _axis_span(points: list[tuple[float, float]], *, axis: int) -> float:
    values = [point[axis] for point in points]
    return max(values) - min(values)


def _gcode_draw_line_count(gcode: str) -> int:
    return sum(1 for line in gcode.splitlines() if line.startswith("G1 X"))


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def test_lift_budget_metadata_caps_pen_downs(tmp_path: Path) -> None:
    svg_path = tmp_path / "budget.svg"
    paths = "".join(
        f"<path d='M{10 + i * 15},{10 + (i % 3) * 30} L{20 + i * 15},{10 + (i % 3) * 30}' stroke='black' fill='none'/>"
        for i in range(6)
    )
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<g data-neje-lift-budget='2'>" + paths + "</g>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="b", title="B", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=100,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert 1 <= gcode.count("M3 S15") <= 3


def test_lift_budget_1024_is_the_off_position(tmp_path: Path) -> None:
    # A stamped 1024 must mean "no budget", matching the GUI slider where the
    # max position means "no limit" — not a real budget of 1024 lifts.
    from neje_oracle.blocks.gcode.svg_gcode import _pen_lift_budget

    def _svg_with(budget: int) -> Path:
        svg_path = tmp_path / f"b{budget}.svg"
        svg_path.write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
            f"<g data-neje-lift-budget='{budget}'>"
            "<path d='M10,10 L20,10' stroke='black' fill='none'/>"
            "</g></svg>",
            encoding="utf-8",
        )
        return svg_path

    assert _pen_lift_budget(_svg_with(8)) == 8
    assert _pen_lift_budget(_svg_with(1024)) is None
    assert _pen_lift_budget(_svg_with(2048)) is None
