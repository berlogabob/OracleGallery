"""The Z range sheet: absolute depth sweep + pen-up clearance ladder."""

from __future__ import annotations

import re

from neje_oracle.blocks.gcode.pen_cal import (
    Z_ABSOLUTE_FLOOR_MM,
    PenCalRanges,
    build_pen_cal_gcode,
    build_z_range_gcode,
)
from neje_oracle.shared.gui_settings import GuiSettings


def _settings() -> GuiSettings:
    settings = GuiSettings()
    settings.sheet_width_mm = 300.0
    settings.sheet_height_mm = 400.0
    settings.direct_svg_origin_x_mm = 15.0
    settings.direct_svg_origin_y_mm = 15.0
    return settings


def _z_values(gcode: str) -> list[float]:
    return [float(match) for match in re.findall(r"Z(-?\d+(?:\.\d+)?)", gcode)]


def test_depth_sweep_never_passes_the_floor() -> None:
    gcode, manifest = build_z_range_gcode(_settings(), depth_stop_mm=-50.0, depth_step_mm=5.0)
    assert all(z >= Z_ABSOLUTE_FLOOR_MM for z in _z_values(gcode))
    assert manifest["z_floor_mm"] == Z_ABSOLUTE_FLOOR_MM


def test_both_blocks_are_present_and_ordered() -> None:
    gcode, manifest = build_z_range_gcode(_settings())
    assert "; --- pen-down Z mm (absolute) ---" in gcode
    assert "; --- pen-up clearance Z mm ---" in gcode
    rows = manifest["rows"]
    depths = [row["z_down_mm"] for row in rows if row["block"] == "depth"]
    clearances = [row["z_up_mm"] for row in rows if row["block"] == "clearance"]
    assert depths == sorted(depths, reverse=True)  # 0 down to the stop
    assert depths[0] == 0.0 and depths[-1] == -12.0
    assert clearances == sorted(clearances)  # deepest first
    assert all(height <= 0.0 for height in clearances)


def test_nothing_commands_deeper_than_the_swept_stop() -> None:
    # After a mechanics change the profile's z_down may sit far past the new physical
    # stop; labels and headers must not trust it.
    settings = _settings()
    settings.z_down_mm = -25.0
    gcode, _ = build_z_range_gcode(settings, depth_stop_mm=-12.0)
    assert min(_z_values(gcode)) == -12.0


def test_oversized_sheet_raises() -> None:
    settings = _settings()
    settings.sheet_height_mm = 40.0
    try:
        build_z_range_gcode(settings)
    except ValueError as exc:
        assert "exceeds" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected the bounds check to raise")


def test_pen_cal_ladder_honours_a_wider_span() -> None:
    settings = _settings()
    settings.z_down_mm = -10.0
    narrow, _ = build_pen_cal_gcode(settings)
    wide, _ = build_pen_cal_gcode(settings, ranges=PenCalRanges(z_span_mm=5.0))
    narrow_span = max(_z_values(narrow)) - min(_z_values(narrow))
    wide_span = max(_z_values(wide)) - min(_z_values(wide))
    assert wide_span > narrow_span
