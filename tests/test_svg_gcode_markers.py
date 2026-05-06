"""Тесты для проверки G-code маркеров ячеек."""
from pathlib import Path
from random import Random

from neje_oracle.models import SheetItem, SheetPlacement
from neje_oracle.svg_gcode import generate_sheet_gcode

def test_gcode_contains_cell_markers(tmp_path: Path) -> None:
    """Проверяем, что G-code содержит маркеры cell-start и cell-end."""
    svg_path = tmp_path / "test.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="test", title="Test", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    assert "; cell-start 0/1" in gcode
    assert "; cell-end 0/1" in gcode

def test_gcode_markers_multiple_cells(tmp_path: Path) -> None:
    """Проверяем, что G-code содержит маркеры для нескольких ячеек."""
    svg_path = tmp_path / "test.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    items = [
        SheetItem(source_kind="user", session_id=f"test{i}", title=f"Test{i}", svg_path=svg_path)
        for i in range(3)
    ]
    placements = [
        SheetPlacement(index=i, center_x_mm=100 + i*200, center_y_mm=100, diameter_mm=160)
        for i in range(3)
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

    assert "; cell-start 0/3" in gcode
    assert "; cell-start 1/3" in gcode
    assert "; cell-start 2/3" in gcode
    assert "; cell-end 0/3" in gcode
    assert "; cell-end 1/3" in gcode
    assert "; cell-end 2/3" in gcode

def test_gcode_markers_order(tmp_path: Path) -> None:
    """Проверяем, что маркеры cell-start идут перед cell-end."""
    svg_path = tmp_path / "test.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="test", title="Test", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        include_rings=False,
    )

    lines = gcode.splitlines()
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if "; cell-start 0/1" in line:
            start_idx = i
        if "; cell-end 0/1" in line:
            end_idx = i
    assert start_idx is not None and end_idx is not None and start_idx < end_idx
