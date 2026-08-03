from __future__ import annotations

from pathlib import Path

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode


SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200mm" height="200mm">'
    '<circle cx="100" cy="100" r="40" fill="none" stroke="black" stroke-width="0.5"/>'
    '<polyline points="10,10 50,50 90,10" fill="none" stroke="black" stroke-width="0.5"/>'
    '</svg>'
)


def test_generative_svg_produces_valid_gcode(tmp_path: Path) -> None:
    svg_path = tmp_path / "generative_test.svg"
    svg_path.write_text(SAMPLE_SVG)
    gcode = generate_absolute_svg_gcode(
        svg_path, sample_step_mm=1.0, travel_rate=5000.0, draw_rate=1800.0,
        pen_up_command="M5", pen_down_command="M3 S15",
    )
    assert "G21" in gcode and "G90" in gcode
    assert "M3 S15" in gcode and "M5" in gcode
    lines = gcode.splitlines()
    assert any(l.startswith("G1 ") for l in lines)


def test_generative_svg_coordinates_within_bounds(tmp_path: Path) -> None:
    svg_path = tmp_path / "generative_bounds_test.svg"
    svg_path.write_text(SAMPLE_SVG)
    gcode = generate_absolute_svg_gcode(
        svg_path, sample_step_mm=1.0, travel_rate=5000.0, draw_rate=1800.0,
        pen_up_command="M5", pen_down_command="M3 S15",
    )

    # Extract all X/Y coordinates from the gcode
    points = []
    for line in gcode.splitlines():
        if line.startswith(("G0 X", "G1 X")):
            parts = line.split()
            x_val = None
            y_val = None
            for part in parts:
                if part.startswith("X"):
                    x_val = float(part[1:])
                elif part.startswith("Y"):
                    y_val = float(part[1:])
            if x_val is not None and y_val is not None:
                points.append((x_val, y_val))

    # Assert all points are within 0..200 mm
    assert len(points) > 0, "No coordinates found in gcode"
    for x, y in points:
        assert 0 <= x <= 200, f"X coordinate {x} outside [0, 200] mm"
        assert 0 <= y <= 200, f"Y coordinate {y} outside [0, 200] mm"
