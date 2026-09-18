from __future__ import annotations

import io
import itertools

import pytest
from PIL import Image, ImageDraw

from neje_oracle.blocks.imaging.modes import MODES
from neje_oracle.blocks.imaging.sheet import GRID_SIZES, grid_cells, grid_to_polylines, photo_filter

CANVAS = {"width_mm": 185.0, "height_mm": 272.0}


def _png(width: int = 120, height: int = 60) -> bytes:
    image = Image.new("L", (width, height), 255)
    ImageDraw.Draw(image).ellipse((width // 4, 5, 3 * width // 4, height - 5), fill=0)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _inside(polylines, width_mm: float, height_mm: float) -> bool:
    return all(-1e-6 <= x <= width_mm + 1e-6 and -1e-6 <= y <= height_mm + 1e-6 for p in polylines for x, y in p)


@pytest.mark.parametrize("n", GRID_SIZES)
def test_cells_fit_the_canvas_and_never_overlap(n: int) -> None:
    cells = grid_cells(n, **CANVAS)
    assert len(cells) == n * n
    for left, top, side in cells:
        assert left >= 0 and top >= 0 and left + side <= CANVAS["width_mm"] and top + side <= CANVAS["height_mm"]
    for (l1, t1, s), (l2, t2, _) in itertools.combinations(cells, 2):
        assert l1 + s <= l2 or l2 + s <= l1 or t1 + s <= t2 or t2 + s <= t1


def test_grid_size_outside_one_to_nine_is_refused() -> None:
    with pytest.raises(ValueError):
        grid_cells(10, **CANVAS)


def test_every_mode_renders_in_its_own_cell_inside_the_canvas() -> None:
    polylines, failures = grid_to_polylines(
        _png(), list(MODES), n=4, **CANVAS, params_for=lambda mode: {"cell_mm": 1.0}
    )
    assert failures == []
    assert polylines and _inside(polylines, **CANVAS)


def test_empty_cells_draw_nothing() -> None:
    polylines, _ = grid_to_polylines(
        _png(), [None, "", None, None], n=2, **CANVAS, params_for=lambda mode: {"cell_mm": 1.0}
    )
    assert polylines == []


def test_a_failing_cell_is_reported_and_the_rest_still_print() -> None:
    # A segment cap of 1 is the same ValueError a real cap breach raises on a dense photo.
    def params_for(mode: str) -> dict:
        return {"cell_mm": 1.0, "max_segments": 1} if mode == "hatch" else {"cell_mm": 1.0}

    with_hatch, failures = grid_to_polylines(
        _png(), ["hatch", "contour"], n=2, **CANVAS, params_for=params_for, labels=False
    )
    contour_only, _ = grid_to_polylines(_png(), [None, "contour"], n=2, **CANVAS, params_for=params_for, labels=False)
    assert len(failures) == 1 and "hatch" in failures[0]
    assert with_hatch == contour_only and contour_only


def _letterboxed(bar: tuple[int, ...], mode: str) -> bytes:
    image = Image.new(mode, (100, 100), bar)
    content = Image.new("L", (100, 40))
    content.putdata([(x * 7 + y * 13) % 256 for y in range(40) for x in range(100)])
    image.paste(content.convert(mode), (0, 30))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize(
    ("bar", "mode"),
    [((0, 0, 0), "RGB"), ((255, 255, 255), "RGB"), ((0, 0, 0, 0), "RGBA")],
    ids=["black", "white", "transparent"],
)
def test_photo_filter_crops_letterbox_bars(bar: tuple[int, ...], mode: str) -> None:
    with Image.open(io.BytesIO(photo_filter(_letterboxed(bar, mode)))) as filtered:
        assert filtered.size == (100, 40)
