"""The campaign sheet builder: headless, on-bed, and every cell actually draws."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from neje_oracle.blocks.gcode.svg_gcode import svg_to_polylines_mm
from neje_oracle.blocks.gui.workspaces.generative import sketch_canvas_mm
from neje_oracle.shared.gui_settings import GuiSettings

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "build_campaign_sheets", REPO_ROOT / "scripts" / "build_campaign_sheets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_campaign_sheets", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    if shutil.which("node") is None:
        pytest.skip("node not available (generator sheet needs the JS sketch)")
    settings = GuiSettings()
    settings.sheet_width_mm = 300.0
    settings.sheet_height_mm = 400.0
    settings.direct_svg_origin_x_mm = 15.0
    settings.direct_svg_origin_y_mm = 15.0
    out = tmp_path_factory.mktemp("campaign")
    stats = _load_script().build_sheets("fineliner", out, settings=settings)
    return out, stats, settings


def test_emits_the_three_numbered_sheets(built) -> None:
    out, stats, _ = built
    names = sorted(path.name for path in out.glob("*.svg"))
    assert names == [
        "10_modes_fineliner.svg",
        "11_generators_fineliner.svg",
        "12_liftbudget_fineliner.svg",
    ]
    assert set(stats) == set(names)


def test_every_cell_draws_something(built) -> None:
    _, stats, _ = built
    for sheet in stats.values():
        for name, count in sheet["cells"].items():
            assert count > 0, name


def test_sheets_parse_and_fit_the_bed(built) -> None:
    out, _, settings = built
    width_mm, height_mm = sketch_canvas_mm(settings)
    for path in out.glob("*.svg"):
        polylines = svg_to_polylines_mm(path, 1.0)
        assert polylines, path.name
        for line in polylines:
            for x, y in line:
                # Sampling tolerance only; a real overhang is whole millimetres.
                assert -0.1 <= x <= width_mm + 0.1, path.name
                assert -0.1 <= y <= height_mm + 0.1, path.name


def test_lift_budgets_actually_bind(built) -> None:
    _, stats, _ = built
    cells = stats["12_liftbudget_fineliner.svg"]["cells"]
    assert cells["lifts-off"] > cells["lifts-256"] > cells["lifts-64"] > cells["lifts-8"] > cells["lifts-0"]
    assert cells["lifts-0"] == 1
