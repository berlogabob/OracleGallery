from __future__ import annotations

import io

import pytest
from PIL import Image

from neje_oracle.blocks.imaging.modes import polylines_to_svg
from neje_oracle.blocks.imaging.sheet import (
    build_frame_grid,
    cell_outline,
    frame_grid_capacity,
    images_to_sheet_polylines,
)

SHEET = {"sheet_width_mm": 200.0, "sheet_height_mm": 200.0, "margin_mm": 10.0}
FRAME = {"cell_width_mm": 40.0, "cell_height_mm": 60.0}


def _png(value: int = 90, size: int = 64) -> bytes:
    output = io.BytesIO()
    Image.new("L", (size, size), value).save(output, format="PNG")
    return output.getvalue()


def test_capacity_matches_hand_arithmetic() -> None:
    # 180 mm printable. With a 5 mm gap: (180+5)//45 = 4 columns, (180+5)//65 = 2 rows.
    # A third row would need 3*60 + 2*5 = 190 mm.
    assert frame_grid_capacity(**SHEET, **FRAME, gap_mm=5.0) == 8
    # Butted up, the gap no longer costs a row: 180//40 = 4 columns, 180//60 = 3 rows.
    assert frame_grid_capacity(**SHEET, **FRAME, gap_mm=0.0) == 12
    # A cell larger than the paper fits nothing rather than raising.
    assert frame_grid_capacity(**SHEET, cell_width_mm=500.0, cell_height_mm=500.0) == 0


def test_gap_separates_cells_and_no_gap_butts_them() -> None:
    for gap in (0.0, 5.0):
        centers = build_frame_grid(4, **SHEET, **FRAME, gap_mm=gap)
        assert centers[1][0] - centers[0][0] == pytest.approx(FRAME["cell_width_mm"] + gap)


def test_cells_stay_inside_the_margin() -> None:
    centers = build_frame_grid(12, **SHEET, **FRAME, gap_mm=5.0)
    assert len(centers) == 8
    for x, y in centers:
        assert x - FRAME["cell_width_mm"] / 2.0 >= 10.0 and x + FRAME["cell_width_mm"] / 2.0 <= 190.0
        assert y - FRAME["cell_height_mm"] / 2.0 >= 10.0 and y + FRAME["cell_height_mm"] / 2.0 <= 190.0


def test_partial_last_sheet_is_still_centred() -> None:
    """Two images on a 12-up sheet should sit in the middle, not the top-left corner."""
    centers = build_frame_grid(2, **SHEET, **FRAME, gap_mm=5.0)
    span_center_x = (centers[0][0] + centers[-1][0]) / 2.0
    assert span_center_x == pytest.approx(100.0)
    assert centers[0][1] == pytest.approx(100.0)


def test_outline_shapes() -> None:
    assert cell_outline(50, 50, 40, 60, "none") == []
    rect = cell_outline(50, 50, 40, 60, "rect")[0]
    assert rect[0] == rect[-1] == (30.0, 20.0)
    ellipse = cell_outline(50, 50, 40, 60, "ellipse")[0]
    assert ellipse[0] == ellipse[-1]
    assert all(((x - 50) / 20) ** 2 + ((y - 50) / 30) ** 2 == pytest.approx(1.0) for x, y in ellipse)
    with pytest.raises(ValueError, match="unknown shape"):
        cell_outline(0, 0, 10, 10, "hexagon")


def test_sheet_places_art_inside_its_own_cell() -> None:
    images = [_png() for _ in range(4)]
    polylines, placed = images_to_sheet_polylines(
        images, **SHEET, **FRAME, gap_mm=5.0, padding_mm=2.0, shape="rect", mode="hatch", line_spacing_mm=3.0
    )
    assert placed == 4
    centers = build_frame_grid(4, **SHEET, **FRAME, gap_mm=5.0)
    for x, y in (point for polyline in polylines for point in polyline):
        assert any(
            abs(x - cx) <= FRAME["cell_width_mm"] / 2.0 + 0.01 and abs(y - cy) <= FRAME["cell_height_mm"] / 2.0 + 0.01
            for cx, cy in centers
        ), f"({x:.2f}, {y:.2f}) fell outside every cell"
    assert polylines_to_svg(polylines, width_mm=200, height_mm=200).startswith("<svg")


def test_more_images_than_cells_places_only_what_fits() -> None:
    _, placed = images_to_sheet_polylines(
        [_png() for _ in range(30)], **SHEET, **FRAME, gap_mm=5.0, shape="none", mode="hatch", line_spacing_mm=3.0
    )
    assert placed == 8


def test_padding_that_swallows_the_cell_raises() -> None:
    with pytest.raises(ValueError, match="no room for art"):
        images_to_sheet_polylines([_png()], **SHEET, **FRAME, padding_mm=25.0)
