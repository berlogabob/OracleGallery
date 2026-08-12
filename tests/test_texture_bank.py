"""The texture bank on disk. Mirrors test_pattern_bank.py.

Every test passes bank_dir=tmp_path on purpose: conftest.py deliberately does NOT sandbox assets/,
so a test that omits it writes into the working tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from neje_oracle.blocks.imaging import texture, texture_bank

SHIPPED = Path(__file__).resolve().parents[1] / "assets" / "textures"


def test_missing_directory_is_empty_not_an_error(tmp_path):
    assert texture_bank.list_graphs(tmp_path / "nope") == []
    assert texture_bank.load_bank(tmp_path / "nope") == {}


def test_save_then_load_round_trip(tmp_path):
    texture_bank.save_graph("clouds", texture.default_graph(), bank_dir=tmp_path)
    assert texture_bank.list_graphs(tmp_path) == ["clouds"]
    loaded = texture_bank.load_graph("clouds", bank_dir=tmp_path)
    assert loaded == texture.TextureGraph.from_dict(texture.default_graph()).to_dict()


def test_listing_is_sorted(tmp_path):
    for name in ("zebra", "apple", "mango"):
        texture_bank.save_graph(name, texture.default_graph(), bank_dir=tmp_path)
    assert texture_bank.list_graphs(tmp_path) == ["apple", "mango", "zebra"]


def test_typed_label_is_sanitised_whole(tmp_path):
    """Not Path(name).stem: that would turn "clouds 2026/08/12" into "12" and silently lose the
    name the operator typed."""
    path = texture_bank.save_graph("clouds 2026/08/12", texture.default_graph(), bank_dir=tmp_path)
    assert path.parent == tmp_path
    assert "/" not in path.stem and "\\" not in path.stem
    assert "clouds" in path.stem and "2026" in path.stem


def test_duplicate_names_are_suffixed_not_overwritten(tmp_path):
    first = texture_bank.save_graph("marble", texture.default_graph(), bank_dir=tmp_path)
    second = texture_bank.save_graph("marble", texture.default_graph(), bank_dir=tmp_path)
    assert first.stem == "marble"
    assert second.stem == "marble-2"
    assert sorted(texture_bank.list_graphs(tmp_path)) == ["marble", "marble-2"]


def test_empty_name_falls_back(tmp_path):
    assert texture_bank.save_graph("   ", texture.default_graph(), bank_dir=tmp_path).stem == "texture"


def test_json_suffix_is_not_doubled(tmp_path):
    assert texture_bank.save_graph("mist.json", texture.default_graph(), bank_dir=tmp_path).name == "mist.json"


def test_invalid_graph_raises_and_leaves_no_file(tmp_path):
    """load_bank swallows invalid files, so an unvalidated save would fail silently -- the file
    sits in the folder and the texture just never appears in the picker."""
    with pytest.raises(ValueError, match="cycle"):
        texture_bank.save_graph(
            "broken",
            {"output": "a", "nodes": {"a": {"kind": "invert", "inputs": {"fac": "a"}}}},
            bank_dir=tmp_path,
        )
    assert texture_bank.list_graphs(tmp_path) == []
    assert list(tmp_path.glob("*")) == []


def test_unknown_name_names_what_is_available(tmp_path):
    texture_bank.save_graph("clouds", texture.default_graph(), bank_dir=tmp_path)
    with pytest.raises(ValueError, match="clouds"):
        texture_bank.load_graph("ghost", bank_dir=tmp_path)


def test_corrupt_file_is_skipped_not_fatal(tmp_path):
    """The operator hand-edits these mid-session; one bad file must not take the bank down."""
    texture_bank.save_graph("good", texture.default_graph(), bank_dir=tmp_path)
    (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "invalid.json").write_text(json.dumps({"output": "x", "nodes": {}}), encoding="utf-8")
    assert sorted(texture_bank.load_bank(tmp_path)) == ["good"]


# ---------------------------------------------------------------------------
# The shipped presets
# ---------------------------------------------------------------------------
def _shipped_names() -> list[str]:
    return texture_bank.list_graphs(SHIPPED)


def test_presets_are_shipped():
    assert set(_shipped_names()) >= {"clouds", "cracks", "dunes", "weave"}


@pytest.mark.parametrize("name", _shipped_names())
def test_preset_has_real_contrast_and_plots_in_reasonable_ink(name):
    """Two failure modes a preset can ship with, both invisible until paper is wasted:

    Flat mid-grey -- fbm's practical spread is about 0.5 +/- 0.12, which hatches uniformly and
    reads as broken. Every preset must end in a ramp that fixes that.

    Solid ink -- unlike a photograph a texture is dark everywhere, and a mean darkness near 1.0 is
    a genuine multi-hour plot rather than a picture. Measured at the shipped settings: these four
    land at 0.33-0.53 mean, roughly 10-12 minutes of hatch on a 150 mm sheet.
    """
    graph = texture_bank.load_graph(name, bank_dir=SHIPPED)
    field = texture.evaluate_field(graph, width_mm=150.0, height_mm=150.0, cell_mm=0.8)
    low, high = np.percentile(field, [5, 95])
    assert high - low > 0.4, f"{name} is too flat to read as a texture"
    assert field.mean() < 0.65, f"{name} is nearly solid ink"


@pytest.mark.parametrize("name", _shipped_names())
def test_preset_renders_to_strokes(name):
    graph = texture_bank.load_graph(name, bank_dir=SHIPPED)
    polylines = texture.texture_to_polylines(
        graph, mode="hatch", width_mm=100.0, height_mm=100.0, cell_mm=1.0, line_spacing_mm=1.6
    )
    assert len(polylines) > 20
