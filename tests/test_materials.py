from __future__ import annotations

import json
from pathlib import Path

import pytest

from neje_oracle.shared.materials import (
    MATERIAL_FIELDS,
    STARTER_MATERIALS,
    apply_material,
    capture_material,
    delete_material,
    load_materials,
    rename_material,
    save_materials,
)

# --- material storage -----------------------------------------------------------


def test_missing_file_falls_back_to_starters(tmp_path: Path) -> None:
    materials = load_materials(tmp_path / "absent.json")
    assert materials == STARTER_MATERIALS


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "materials.json"
    save_materials({"mine": dict.fromkeys(MATERIAL_FIELDS, 1.5)}, path)
    assert load_materials(path) == {"mine": dict.fromkeys(MATERIAL_FIELDS, 1.5)}


def test_load_clamps_hand_edited_thickness_to_a_sane_range(tmp_path: Path) -> None:
    """The file is hand-editable; a thickness past the servo's travel must not reach it."""
    path = tmp_path / "materials.json"
    save_materials({"thick": {"thickness_mm": 40.0}, "negative": {"thickness_mm": -3.0}}, path)
    loaded = load_materials(path)
    assert loaded["thick"]["thickness_mm"] == 20.0
    assert loaded["negative"]["thickness_mm"] == 0.0


def test_unknown_keys_are_dropped_rather_than_fatal(tmp_path: Path) -> None:
    """The file is hand-editable; a stale key must not make every material unloadable."""
    path = tmp_path / "materials.json"
    path.write_text(json.dumps({"odd": {"thickness_mm": 0.4, "renamed_field": 3}}), encoding="utf-8")
    assert load_materials(path) == {"odd": {"thickness_mm": 0.4}}


def test_shipped_materials_are_complete() -> None:
    """Every starter carries every field; a missing one would read as 0 on apply."""
    for name, values in STARTER_MATERIALS.items():
        assert set(values) == set(MATERIAL_FIELDS), name


def test_the_starters_are_the_shipped_set(tmp_path: Path) -> None:
    """There is one definition of 'card' now: absent until the operator's first save."""
    assert load_materials(tmp_path / "never_saved.json") == STARTER_MATERIALS


def test_delete_keeps_the_last_material(tmp_path: Path) -> None:
    """An empty picker would leave no way back to a known offset."""
    path = tmp_path / "materials.json"
    save_materials({"only": dict(STARTER_MATERIALS["card"])}, path)
    materials = load_materials(path)

    with pytest.raises(ValueError, match="only material"):
        delete_material("only", materials)


def test_delete_removes_one_and_leaves_the_rest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "materials.json"
    monkeypatch.setattr("neje_oracle.shared.materials.MATERIAL_PATH", path)
    save_materials({name: dict(values) for name, values in STARTER_MATERIALS.items()}, path)

    remaining = delete_material("card", load_materials(path))

    assert "card" not in remaining
    assert set(remaining) == set(STARTER_MATERIALS) - {"card"}
    assert load_materials(path) == remaining


def test_rename_moves_the_value_and_refuses_an_existing_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Landing on an existing name would overwrite another material's measurement, and the
    only other copy of that number is on paper."""
    path = tmp_path / "materials.json"
    monkeypatch.setattr("neje_oracle.shared.materials.MATERIAL_PATH", path)
    save_materials({name: dict(values) for name, values in STARTER_MATERIALS.items()}, path)
    materials = load_materials(path)

    renamed = rename_material("card", "cardstock 300gsm", materials)

    assert "card" not in renamed
    assert renamed["cardstock 300gsm"] == STARTER_MATERIALS["card"]
    with pytest.raises(ValueError, match="already exists"):
        rename_material("paper", "plastic sheet", renamed)
    assert load_materials(path) == renamed


# --- applying and capturing ----------------------------------------------------


def test_apply_returns_the_thickness() -> None:
    assert apply_material("silicone mat") == STARTER_MATERIALS["silicone mat"]["thickness_mm"]


def test_apply_then_capture_round_trips() -> None:
    thickness = apply_material("thick card")
    assert capture_material(thickness) == load_materials()["thick card"]


def test_unknown_material_names_the_known_ones() -> None:
    with pytest.raises(ValueError, match="paper"):
        apply_material("styrofoam")
