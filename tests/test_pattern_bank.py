from __future__ import annotations

from pathlib import Path

import pytest

from neje_oracle.blocks.gui.workspaces.generative import sketch_canvas_mm
from neje_oracle.blocks.patterns import bank
from neje_oracle.shared.gui_settings import GuiSettings

SQUARE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="20mm" height="20mm">
  <path d="M 10 10 L 90 10 L 90 90 L 10 90 Z" fill="none" stroke="black"/>
</svg>
"""

# Twice as wide as it is tall, so a non-uniform scale would show up as a
# stretched motif on paper.
WIDE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="20mm" height="20mm">
  <path d="M 10 30 L 90 30 L 90 70 L 10 70 Z" fill="none" stroke="black"/>
</svg>
"""


@pytest.fixture
def bank_dir(tmp_path: Path) -> Path:
    (tmp_path / "square.svg").write_text(SQUARE, encoding="utf-8")
    (tmp_path / "wide.svg").write_text(WIDE, encoding="utf-8")
    return tmp_path


def _bounds(polylines: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    points = [point for polyline in polylines for point in polyline]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), max(xs), min(ys), max(ys)


def test_list_motifs_is_sorted(bank_dir: Path) -> None:
    # The bank generator walks this order round-robin, so it has to be stable.
    assert bank.list_motifs(bank_dir) == ["square", "wide"]


def test_missing_directory_is_empty_not_an_error(tmp_path: Path) -> None:
    assert bank.list_motifs(tmp_path / "nope") == []
    assert bank.load_bank(tmp_path / "nope") == {}


def test_motif_fills_the_unit_box(bank_dir: Path) -> None:
    min_x, max_x, min_y, max_y = _bounds(bank.motif_polylines("square", bank_dir))
    assert (min_x, min_y) == pytest.approx((-0.5, -0.5), abs=1e-6)
    assert (max_x, max_y) == pytest.approx((0.5, 0.5), abs=1e-6)


def test_aspect_ratio_is_preserved(bank_dir: Path) -> None:
    min_x, max_x, min_y, max_y = _bounds(bank.motif_polylines("wide", bank_dir))
    assert max_x - min_x == pytest.approx(1.0, abs=1e-6), "longest side must be exactly 1"
    assert max_y - min_y == pytest.approx(0.5, abs=1e-6), "2:1 source must stay 2:1"


def test_motif_is_centred_on_the_origin(bank_dir: Path) -> None:
    min_x, max_x, min_y, max_y = _bounds(bank.motif_polylines("wide", bank_dir))
    assert (min_x + max_x) / 2 == pytest.approx(0.0, abs=1e-6)
    assert (min_y + max_y) / 2 == pytest.approx(0.0, abs=1e-6)


def test_unknown_motif_names_what_is_available(bank_dir: Path) -> None:
    with pytest.raises(ValueError, match="square"):
        bank.motif_polylines("absent", bank_dir)


def test_load_bank_skips_broken_svg_instead_of_failing(bank_dir: Path) -> None:
    # The operator drops files into this folder by hand while the app runs; one
    # bad file must not take the whole sketch down.
    (bank_dir / "broken.svg").write_text("not xml at all", encoding="utf-8")
    assert sorted(bank.load_bank(bank_dir)) == ["square", "wide"]


def test_shipped_bank_loads() -> None:
    motifs = bank.load_bank()
    assert motifs, "assets/patterns should ship a starter set"
    for name, polylines in motifs.items():
        min_x, max_x, min_y, max_y = _bounds(polylines)
        assert max(max_x - min_x, max_y - min_y) == pytest.approx(1.0, abs=1e-6), name
        assert min_x >= -0.5001 and max_x <= 0.5001, name
        assert min_y >= -0.5001 and max_y <= 0.5001, name


def test_canvas_subtracts_the_direct_svg_origin() -> None:
    # A canvas the full width of the sheet would run off the bed by exactly the
    # origin offset that the direct-SVG path adds.
    settings = GuiSettings()
    settings.sheet_width_mm = 250.0
    settings.sheet_height_mm = 440.0
    settings.direct_svg_origin_x_mm = 25.0
    settings.direct_svg_origin_y_mm = 25.0
    assert sketch_canvas_mm(settings) == (225.0, 415.0)


def test_canvas_stays_positive_with_an_absurd_origin() -> None:
    settings = GuiSettings()
    settings.sheet_width_mm = 250.0
    settings.sheet_height_mm = 440.0
    settings.direct_svg_origin_x_mm = 400.0
    settings.direct_svg_origin_y_mm = 500.0
    width, height = sketch_canvas_mm(settings)
    assert width > 0 and height > 0
