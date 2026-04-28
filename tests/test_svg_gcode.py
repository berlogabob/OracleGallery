from pathlib import Path

from neje_oracle.models import SheetItem, SheetPlacement
from neje_oracle.svg_gcode import generate_sheet_gcode


def test_gcode_uses_mark_diameter_independent_from_cell_size(tmp_path: Path) -> None:
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
        mark_diameter_mm=40,
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

    assert min(xs) >= 80
    assert max(xs) <= 120
    assert min(ys) >= 80
    assert max(ys) <= 120
