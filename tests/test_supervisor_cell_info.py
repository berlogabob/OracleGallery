from pathlib import Path

from neje_oracle.blocks.gcode.svg_gcode import generate_sheet_gcode, parse_cell_progress_markers
from neje_oracle.shared.models import SheetItem, SheetPlacement


def _svg(path: Path) -> Path:
    path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )
    return path


def test_parse_cell_progress_markers_from_generated_gcode(tmp_path: Path) -> None:
    svg_path = _svg(tmp_path / "test.svg")
    items = [
        SheetItem(source_kind="user", session_id=f"test{i}", title=f"Test{i}", svg_path=svg_path) for i in range(3)
    ]
    placements = [
        SheetPlacement(index=i, center_x_mm=100 + (i * 50), center_y_mm=100, diameter_mm=40) for i in range(3)
    ]

    gcode = generate_sheet_gcode(
        items,
        placements,
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert parse_cell_progress_markers(gcode) == [(0, 3), (1, 3), (2, 3)]


def test_parse_cell_progress_markers_returns_empty_without_markers() -> None:
    assert parse_cell_progress_markers("G21\nG90\nG0 X0 Y0\n") == []
