from __future__ import annotations

from pathlib import Path

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode
from neje_oracle.blocks.gui.workspaces.generative import should_send_frame

SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200mm" height="200mm">'
    '<circle cx="100" cy="100" r="40" fill="none" stroke="black" stroke-width="0.5"/>'
    '<polyline points="10,10 50,50 90,10" fill="none" stroke="black" stroke-width="0.5"/>'
    "</svg>"
)


def test_generative_svg_produces_valid_gcode(tmp_path: Path) -> None:
    svg_path = tmp_path / "generative_test.svg"
    svg_path.write_text(SAMPLE_SVG)
    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )
    assert "G21" in gcode and "G90" in gcode
    assert "M3 S15" in gcode and "M5" in gcode
    lines = gcode.splitlines()
    assert any(line.startswith("G1 ") for line in lines)


def test_generative_svg_coordinates_within_bounds(tmp_path: Path) -> None:
    svg_path = tmp_path / "generative_bounds_test.svg"
    svg_path.write_text(SAMPLE_SVG)
    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
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


def test_should_send_frame_combinations() -> None:
    """Two states now, not three.

    It used to also require bytes sitting in a process-global capture buffer. That buffer is
    gone: the browser no longer pushes SVG at the server, so the tick pulls the frame that is
    on screen when it fires. There is nothing left to check but our own state.
    """
    # Disabled: never send.
    assert should_send_frame({"enabled": False, "busy": False}) is False

    # Busy: don't send while a previous frame is still plotting.
    assert should_send_frame({"enabled": True, "busy": True}) is False

    # All-go: enabled and idle.
    assert should_send_frame({"enabled": True, "busy": False}) is True


def test_the_capture_buffer_is_gone() -> None:
    """The buffer both producers wrote to is what let a texture be plotted by the sketch.

    The node editor POSTed into the same slot the sketch's stream timer drained, so a texture
    rendered for preview could reach paper unattended. Keeping this assertion means the slot
    cannot quietly come back as a convenience.
    """
    from neje_oracle.blocks.gui.workspaces import generative

    assert not hasattr(generative, "LATEST")
    assert not hasattr(generative, "_handle_generative_svg")


def test_stamp_lift_budget_marks_the_svg_root() -> None:
    from neje_oracle.blocks.gui.workspaces.generative import stamp_lift_budget

    svg = b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><path d='M0,0 L1,1'/></svg>"
    assert stamp_lift_budget(svg, 1024) == svg
    stamped = stamp_lift_budget(svg, 3)
    assert b'data-neje-lift-budget="3"' in stamped
    assert stamped.count(b"<svg") == 1


def test_stamp_lift_budget_survives_hostile_but_legal_svg() -> None:
    from neje_oracle.blocks.gui.workspaces.generative import stamp_lift_budget

    # Namespace-prefixed root: attribute must land inside the root tag, after the name.
    prefixed = b"<svg:svg xmlns:svg='http://www.w3.org/2000/svg'><svg:path d='M0,0 L1,1'/></svg:svg>"
    stamped = stamp_lift_budget(prefixed, 5)
    assert b'data-neje-lift-budget="5"' in stamped
    import xml.etree.ElementTree as ET

    ET.fromstring(stamped)  # must stay well-formed

    # A comment mentioning <svg before the real root must not swallow the stamp.
    commented = b"<!-- <svg decoy --><svg xmlns='http://www.w3.org/2000/svg'><path d='M0,0 L1,1'/></svg>"
    stamped = stamp_lift_budget(commented, 4)
    root = ET.fromstring(stamped)
    assert root.get("data-neje-lift-budget") == "4"

    # Re-stamping replaces the value instead of stacking duplicate attributes.
    once = stamp_lift_budget(b"<svg xmlns='http://www.w3.org/2000/svg'/>", 7)
    twice = stamp_lift_budget(once, 3)
    assert twice.count(b"data-neje-lift-budget") == 1
    assert ET.fromstring(twice).get("data-neje-lift-budget") == "3"
