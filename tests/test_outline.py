"""The outline trace: walk the paper and the artwork with the pen up, before a long print.

A sheet here runs for hours, and nothing used to answer "does the drawing fit, and is the
origin where I think it is" until ink was already on paper.
"""

from __future__ import annotations

import re

import pytest

from neje_oracle.blocks.gcode.direct_svg import build_svg_polylines
from neje_oracle.blocks.gcode.pen_cal import outline_gcode
from neje_oracle.shared.config import PlotterSettings
from neje_oracle.shared.gui_settings import GuiSettings

_DIAGONAL = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' width='100mm' height='100mm'>"
    b"<path d='M10,10 L90,90' stroke='black' fill='none'/></svg>"
)
_EMPTY = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' width='100mm' height='100mm'>"
    b"<title>nothing drawable</title></svg>"
)


def _settings() -> GuiSettings:
    return GuiSettings(
        sheet_width_mm=200.0,
        sheet_height_mm=120.0,
        sheet_margin_mm=5.0,
        direct_svg_origin_x_mm=25.0,
        direct_svg_origin_y_mm=25.0,
    )


def _moves(gcode: str) -> list[tuple[float, float]]:
    moves = []
    for line in gcode.splitlines():
        match = re.match(r"G0 X(-?[\d.]+) Y(-?[\d.]+)", line.strip())
        if match:
            moves.append((float(match.group(1)), float(match.group(2))))
    return moves


def test_the_field_rectangle_is_the_sheet_inset_by_its_margin() -> None:
    settings = _settings()

    corners = _moves(outline_gcode(settings, PlotterSettings()))[:5]

    assert corners == [(30.0, 30.0), (195.0, 30.0), (195.0, 115.0), (30.0, 115.0), (30.0, 30.0)]


def test_the_pen_never_goes_down() -> None:
    """The one outcome that would make this worse than not checking: a fed Z would put ink
    on the sheet the operator is about to print on."""
    gcode = outline_gcode(_settings(), PlotterSettings(), svg_bytes=_DIAGONAL)

    assert "G1 Z" not in gcode
    assert not re.search(r"^G1 ", gcode, flags=re.MULTILINE), "an outline must not draw at all"
    depths = [float(value) for value in re.findall(r"^G0 Z(-?[\d.]+)", gcode, flags=re.MULTILINE)]
    assert depths, "the pen has to be commanded up at least once"
    assert all(depth >= _settings().z_up_mm for depth in depths)


def test_the_artwork_rectangle_is_the_geometry_the_print_would_send() -> None:
    settings = _settings()

    art = _moves(outline_gcode(settings, PlotterSettings(), svg_bytes=_DIAGONAL))[5:10]

    points = [point for polyline in build_svg_polylines(settings, _DIAGONAL) for point in polyline]
    x0 = min(x for x, _ in points) + settings.direct_svg_origin_x_mm
    y0 = min(y for _, y in points) + settings.direct_svg_origin_y_mm
    x1 = max(x for x, _ in points) + settings.direct_svg_origin_x_mm
    y1 = max(y for _, y in points) + settings.direct_svg_origin_y_mm
    assert art == [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def test_an_svg_with_nothing_drawable_traces_only_the_paper() -> None:
    gcode = outline_gcode(_settings(), PlotterSettings(), svg_bytes=_EMPTY)

    assert "artwork bounds" not in gcode
    assert len(_moves(gcode)) == 6  # four corners, the closing corner, and home


def test_the_head_comes_home() -> None:
    assert outline_gcode(_settings(), PlotterSettings()).strip().endswith("G0 X0 Y0")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
