"""Тесты для метода get_current_cell_info в supervisor.py."""
from pathlib import Path
from random import Random

from neje_oracle.models import SheetItem, SheetPlacement, ComponentStatus, PlotStatus
from neje_oracle.svg_gcode import generate_sheet_gcode
from neje_oracle.supervisor import SupervisorService
from neje_oracle.config import PlotterSettings
from neje_oracle.runtime_store import RuntimeStore

def test_get_current_cell_info(tmp_path: Path) -> None:
    """Проверяем, что метод get_current_cell_info возвращает правильную ячейку."""
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

    gcode_path = tmp_path / "test.gcode"
    gcode_path.write_text(gcode, encoding="utf-8")

    runtime_store = RuntimeStore()
    runtime_store.set_component("plotter", ComponentStatus.RUNNING, message="Running")
    runtime_store.set_component("fluidnc", ComponentStatus.RUNNING, message="Connected")

    supervisor = SupervisorService(
        settings=PlotterSettings(),
        runtime_store=runtime_store,
        gcode_file=str(gcode_path),
    )

    cell_info = supervisor.get_current_cell_info()
    assert cell_info is not None
    current_cell, total_cells = cell_info
    assert current_cell == 0
    assert total_cells == 3

def test_get_current_cell_info_no_markers(tmp_path: Path) -> None:
    """Проверяем, что метод возвращает None, если нет маркеров."""
    svg_path = tmp_path / "test.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    items = [SheetItem(source_kind="user", session_id="test", title="Test", svg_path=svg_path)]
    placements = [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)]

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

    # Удаляем маркеры
    gcode_without_markers = "".join(
        line for line in gcode.splitlines() if "; cell-start" not in line and "; cell-end" not in line
    )
    gcode_path = tmp_path / "test.gcode"
    gcode_path.write_text(gcode_without_markers, encoding="utf-8")

    runtime_store = RuntimeStore()
    runtime_store.set_component("plotter", ComponentStatus.RUNNING, message="Running")
    runtime_store.set_component("fluidnc", ComponentStatus.RUNNING, message="Connected")

    supervisor = SupervisorService(
        settings=PlotterSettings(),
        runtime_store=runtime_store,
        gcode_file=str(gcode_path),
    )

    cell_info = supervisor.get_current_cell_info()
    assert cell_info is None
