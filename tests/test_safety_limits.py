from __future__ import annotations

import re
from pathlib import Path

import pytest

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode
from neje_oracle.blocks.gui.support import GuiSettings, create_direct_svg_print_job_from_gui
from neje_oracle.shared.config import PlotterSettings


def test_oversized_svg_is_refused_x_axis(tmp_path: Path) -> None:
    """SVG whose drawable extent exceeds max_x_mm must raise ValueError with both dimensions in message."""
    svg_path = tmp_path / "oversized_x.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 100' width='200mm' height='100mm'>"
        "<path d='M10,10 L190,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        generate_absolute_svg_gcode(
            svg_path,
            sample_step_mm=1.0,
            travel_rate=5000.0,
            draw_rate=1800.0,
            pen_up_command="M5",
            pen_down_command="M3 S15",
            max_x_mm=100.0,
            max_y_mm=100.0,
        )

    error_msg = str(exc_info.value)
    assert "exceeds" in error_msg.lower()
    assert "100" in error_msg  # The configured limit
    # The actual size should be close to 200 (the viewBox width in mm)


def test_oversized_svg_is_refused_y_axis(tmp_path: Path) -> None:
    """SVG whose drawable extent exceeds max_y_mm must raise ValueError with both dimensions in message."""
    svg_path = tmp_path / "oversized_y.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 200' width='100mm' height='200mm'>"
        "<path d='M10,10 L90,190' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        generate_absolute_svg_gcode(
            svg_path,
            sample_step_mm=1.0,
            travel_rate=5000.0,
            draw_rate=1800.0,
            pen_up_command="M5",
            pen_down_command="M3 S15",
            max_x_mm=100.0,
            max_y_mm=100.0,
        )

    error_msg = str(exc_info.value)
    assert "exceeds" in error_msg.lower()
    assert "100" in error_msg  # The configured limit


def test_svg_exactly_at_limit_is_accepted(tmp_path: Path) -> None:
    """Art landing exactly on the sheet edge must NOT raise."""
    svg_path = tmp_path / "exact_limit.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' width='100mm' height='100mm'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    # Should not raise with the viewBox size exactly matching the limits
    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        max_x_mm=100.0,
        max_y_mm=100.0,
    )

    assert gcode
    assert len(gcode) > 0


def test_origin_offset_counts_toward_limit(tmp_path: Path) -> None:
    """Art that fits at origin but is pushed past edge by origin_x_mm/origin_y_mm MUST be refused."""
    svg_path = tmp_path / "offset_overflow.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80' width='80mm' height='80mm'>"
        "<path d='M10,10 L70,70' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    # This SVG fits within 80x80 mm at origin (0,0), but will exceed the limit when offset
    with pytest.raises(ValueError) as exc_info:
        generate_absolute_svg_gcode(
            svg_path,
            sample_step_mm=1.0,
            travel_rate=5000.0,
            draw_rate=1800.0,
            pen_up_command="M5",
            pen_down_command="M3 S15",
            origin_x_mm=40.0,  # Pushing it over the limit
            origin_y_mm=40.0,
            max_x_mm=100.0,
            max_y_mm=100.0,
        )

    error_msg = str(exc_info.value)
    assert "exceeds" in error_msg.lower()


def test_no_negative_coordinates_emitted(tmp_path: Path) -> None:
    """With keep_non_negative=True, parse every G0/G1 and assert no negative X or Y."""
    svg_path = tmp_path / "negative_coords.svg"
    # This SVG has negative coordinates in user space
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='-50 -50 100 100' width='100mm' height='100mm'>"
        "<path d='M-40,-40 L40,40' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        keep_non_negative=True,
    )

    # Parse all G0 X.. Y.. and G1 X.. Y.. lines
    for line in gcode.splitlines():
        if line.startswith(("G0 X", "G1 X")):
            match = re.search(r"X([-+]?[\d.]+)", line)
            if match:
                x_val = float(match.group(1))
                assert x_val >= 0.0, f"Negative X coordinate found: {x_val} in line: {line}"

            match = re.search(r"Y([-+]?[\d.]+)", line)
            if match:
                y_val = float(match.group(1))
                assert y_val >= 0.0, f"Negative Y coordinate found: {y_val} in line: {line}"


def test_pen_up_down_are_balanced(tmp_path: Path) -> None:
    """Every pen-down is matched by a later pen-up, file never ends pen-down."""
    svg_path = tmp_path / "multi_path.svg"
    # Multi-path SVG to ensure multiple pen-up/down cycles
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' width='100mm' height='100mm'>"
        "<path d='M10,10 L30,30' stroke='black' fill='none'/>"
        "<path d='M50,50 L70,70' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )

    lines = gcode.splitlines()

    # Walk the pen state rather than counting. Counting passes M3,M3,M5,M5,M5 —
    # two pen-downs in a row means the laser stays on through the rapid travel
    # between them, burning a line across the work.
    pen_is_down = False
    pen_down_count = 0
    for number, line in enumerate(lines, start=1):
        if "M3 S15" in line:
            assert not pen_is_down, f"line {number}: pen-down while already down"
            pen_is_down = True
            pen_down_count += 1
        elif "M5" in line:
            pen_is_down = False

    assert pen_down_count > 1, "fixture must exercise more than one pen-down cycle"
    assert not pen_is_down, "G-code ends pen-down — the laser would stay on"


def test_gcode_ends_at_home_when_requested(tmp_path: Path) -> None:
    """With return_home=True the last motion line is G0 X0 Y0; with False it is not."""
    svg_path = tmp_path / "home_test.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' width='100mm' height='100mm'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    # Test with return_home=True
    gcode_home = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        return_home=True,
    )

    motion_lines = [line for line in gcode_home.splitlines() if line.startswith("G0 X") or line.startswith("G1 X")]
    assert len(motion_lines) > 0, "No motion lines found"
    assert motion_lines[-1] == "G0 X0 Y0", f"Last motion should be home, got: {motion_lines[-1]}"

    # Test with return_home=False
    gcode_no_home = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        return_home=False,
    )

    motion_lines_no_home = [
        line for line in gcode_no_home.splitlines() if line.startswith("G0 X") or line.startswith("G1 X")
    ]
    assert len(motion_lines_no_home) > 0, "No motion lines found"
    assert motion_lines_no_home[-1] != "G0 X0 Y0", "Should NOT end at home when return_home=False"


def test_every_pen_down_is_preceded_by_a_positioning_move(tmp_path: Path) -> None:
    """A pen-down must follow a G0 positioning move; drawing line from unknown position is unsafe."""
    svg_path = tmp_path / "positioning_test.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' width='100mm' height='100mm'>"
        "<path d='M20,20 L80,80' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )

    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )

    lines = gcode.splitlines()

    for i, line in enumerate(lines):
        if "M3 S15" in line:  # Pen-down command
            # The previous non-comment line should be a G0 positioning move
            prev_line_idx = i - 1
            while prev_line_idx >= 0:
                prev = lines[prev_line_idx].strip()
                if prev and not prev.startswith(";"):
                    assert prev.startswith("G0 X"), (
                        f"Pen-down at line {i} not preceded by positioning move. Previous line: {prev}"
                    )
                    break
                prev_line_idx -= 1


def test_direct_print_job_enforces_sheet_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct print job creation enforces sheet bounds via create_direct_svg_print_job_from_gui."""
    # Create a small SVG that will exceed a small sheet
    svg_bytes = (
        b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200' width='200mm' height='200mm'>"
        b"<path d='M10,10 L190,190' stroke='black' fill='none'/>"
        b"</svg>"
    )

    # Create GUI settings with a small sheet
    settings = GuiSettings(
        sheet_width_mm=100.0,
        sheet_height_mm=100.0,
        direct_svg_origin_x_mm=0.0,
        direct_svg_origin_y_mm=0.0,
    )

    # Create PlotterSettings with matching small sheet
    plotter_settings = PlotterSettings(
        sheet_width_mm=100.0,
        sheet_height_mm=100.0,
    )

    # The function writes to plotter_settings.spool_root by default; use tmp_path instead
    output_root = tmp_path / "spool_test"

    # Should raise ValueError because the 200x200mm SVG exceeds 100x100mm sheet
    with pytest.raises(ValueError) as exc_info:
        create_direct_svg_print_job_from_gui(
            settings,
            svg_bytes=svg_bytes,
            original_name="oversized.svg",
            output_root=output_root,
            plotter_settings=plotter_settings,
        )

    error_msg = str(exc_info.value)
    assert "exceeds" in error_msg.lower()
    assert "100" in error_msg  # The configured limit should be mentioned
