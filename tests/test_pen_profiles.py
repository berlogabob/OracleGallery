from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from neje_oracle.blocks.gcode.pen_cal import (
    Z_ABSOLUTE_FLOOR_MM,
    Z_LADDER_SPAN_MM,
    PenCalRanges,
    build_pen_cal_gcode,
    generate_pen_cal_sheet,
)
from neje_oracle.blocks.gcode.svg_gcode import _dwell_command, generate_absolute_svg_gcode
from neje_oracle.shared.gui_settings import GuiSettings, gui_settings_to_plotter_config
from neje_oracle.shared.models import PlotterRuntimeConfig
from neje_oracle.shared.pen_profiles import (
    PEN_PROFILE_FIELDS,
    STARTER_PROFILES,
    apply_pen_profile,
    capture_pen_profile,
    delete_pen_profile,
    load_pen_profiles,
    profile_matches,
    rename_pen_profile,
    save_pen_profiles,
)

SQUARE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="50mm" height="50mm">
  <path d="M 10 10 L 90 10 L 90 90 L 10 90 Z" fill="none" stroke="black"/>
</svg>
"""


def _a4_settings() -> GuiSettings:
    settings = GuiSettings()
    settings.sheet_width_mm = 210.0
    settings.sheet_height_mm = 297.0
    settings.direct_svg_origin_x_mm = 15.0
    settings.direct_svg_origin_y_mm = 15.0
    return settings


# --- the dwell unit conversion -------------------------------------------------


def test_dwell_is_emitted_in_seconds_not_milliseconds() -> None:
    """GRBL and FluidNC read G4 P in SECONDS; Marlin is the one that uses ms.

    Profiles store milliseconds because that is what an operator types. Getting the
    conversion backwards turns a 150 ms dwell into 150 seconds on every stroke -- on a
    2000-stroke drawing that is three days of the pen sitting still.
    """
    assert _dwell_command(150) == "G4 P0.150"
    assert _dwell_command(60) == "G4 P0.060"
    assert _dwell_command(1000) == "G4 P1.000"


def test_zero_dwell_emits_nothing() -> None:
    assert _dwell_command(0) is None
    assert _dwell_command(-5) is None


def test_dwell_default_keeps_gcode_byte_identical(tmp_path: Path) -> None:
    """A fineliner profile has no dwell, so its G-code must not change at all."""
    svg = tmp_path / "square.svg"
    svg.write_text(SQUARE_SVG, encoding="utf-8")
    common = {
        "sample_step_mm": 1.0,
        "travel_rate": 5000.0,
        "draw_rate": 1800.0,
        "pen_up_command": "M5",
        "pen_down_command": "M3 S15",
    }
    assert generate_absolute_svg_gcode(svg, **common) == generate_absolute_svg_gcode(
        svg, **common, pen_down_dwell_ms=0.0
    )


def test_dwell_lands_after_pen_down_not_before(tmp_path: Path) -> None:
    """Dwelling before the pen touches the paper would do nothing at all."""
    svg = tmp_path / "square.svg"
    svg.write_text(SQUARE_SVG, encoding="utf-8")
    lines = generate_absolute_svg_gcode(
        svg,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        pen_down_dwell_ms=120.0,
    ).splitlines()
    index = lines.index("G4 P0.120")
    assert lines[index - 1] == "M3 S15"


# --- profile storage -----------------------------------------------------------


def test_missing_file_falls_back_to_starters(tmp_path: Path) -> None:
    profiles = load_pen_profiles(tmp_path / "absent.json")
    assert set(profiles) == set(STARTER_PROFILES)


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "pens.json"
    # z_down_mm -1.0 keeps every value inside the load-time travel clamp.
    save_pen_profiles({"mine": dict.fromkeys(PEN_PROFILE_FIELDS, -1.0)}, path)
    assert load_pen_profiles(path) == {"mine": dict.fromkeys(PEN_PROFILE_FIELDS, -1.0)}


def test_load_clamps_hand_edited_depth_to_servo_travel(tmp_path: Path) -> None:
    """The file is hand-editable; a past-travel depth must not reach the board."""
    path = tmp_path / "pens.json"
    save_pen_profiles({"deep": {"z_down_mm": -26.0}, "high": {"z_down_mm": 1.0}}, path)
    loaded = load_pen_profiles(path)
    assert loaded["deep"]["z_down_mm"] == -25.0
    assert loaded["high"]["z_down_mm"] == 0.0


def test_unknown_keys_are_dropped_rather_than_fatal(tmp_path: Path) -> None:
    """The file is hand-editable; a stale key must not make every profile unloadable."""
    path = tmp_path / "pens.json"
    path.write_text(json.dumps({"odd": {"draw_rate": 900.0, "renamed_field": 3}}), encoding="utf-8")
    assert load_pen_profiles(path) == {"odd": {"draw_rate": 900.0}}


def test_shipped_profiles_are_complete() -> None:
    """Every starter carries every field; a missing one would read as 0 on apply."""
    for name, values in STARTER_PROFILES.items():
        assert set(values) == set(PEN_PROFILE_FIELDS), name


def test_the_starters_are_the_shipped_set(tmp_path: Path) -> None:
    """There is one definition of 'gel' now.

    The four pens used to be spelled out twice, in STARTER_PROFILES and a tracked
    assets/pen_profiles.json, kept honest only by a byte-equality test. The file is now the
    operator's own measurements, written on first save, and absent until then.
    """
    assert load_pen_profiles(tmp_path / "never_saved.json") == STARTER_PROFILES


def test_a_z_target_from_a_hand_edited_file_is_clamped(tmp_path: Path) -> None:
    """z_fix_mm parks the pen about a millimetre off the mechanical end, so it gets the
    same clamp z_down_mm has: past-travel either trips the soft limit or stalls the servo."""
    path = tmp_path / "pens.json"
    save_pen_profiles({"deep": {"z_fix_mm": -40.0}, "high": {"z_fix_mm": 5.0}}, path)
    loaded = load_pen_profiles(path)
    assert loaded["deep"]["z_fix_mm"] == -25.0
    assert loaded["high"]["z_fix_mm"] == 0.0


def test_the_pen_fix_position_travels_with_the_pen(tmp_path: Path) -> None:
    """It is captured by SET AS PEN-FIX in the same card as the rest, and it is a property
    of how this pen sits in the holder -- it used to be left behind on every pen switch."""
    path = tmp_path / "pens.json"
    settings = GuiSettings(z_fix_mm=-12.5)
    save_pen_profiles({"mine": capture_pen_profile(settings)}, path)

    other = GuiSettings(z_fix_mm=0.0)
    apply_pen_profile(other, "mine", load_pen_profiles(path))

    assert other.z_fix_mm == -12.5


def test_delete_keeps_the_last_profile(tmp_path: Path) -> None:
    """An empty picker would leave no way back to a known-good pen."""
    path = tmp_path / "pens.json"
    save_pen_profiles({"only": dict(STARTER_PROFILES["gel"])}, path)
    profiles = load_pen_profiles(path)

    with pytest.raises(ValueError, match="only pen profile"):
        delete_pen_profile("only", profiles)


def test_delete_removes_one_and_leaves_the_rest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "pens.json"
    monkeypatch.setattr("neje_oracle.shared.pen_profiles.PROFILE_PATH", path)
    save_pen_profiles({name: dict(values) for name, values in STARTER_PROFILES.items()}, path)

    remaining = delete_pen_profile("gel", load_pen_profiles(path))

    assert "gel" not in remaining
    assert set(remaining) == set(STARTER_PROFILES) - {"gel"}
    assert load_pen_profiles(path) == remaining


def test_rename_moves_the_values_and_refuses_an_existing_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Landing on an existing name would overwrite another pen's measurements, and the
    only other copy of those numbers is on paper."""
    path = tmp_path / "pens.json"
    monkeypatch.setattr("neje_oracle.shared.pen_profiles.PROFILE_PATH", path)
    save_pen_profiles({name: dict(values) for name, values in STARTER_PROFILES.items()}, path)
    profiles = load_pen_profiles(path)

    renamed = rename_pen_profile("gel", "gel 0.5 black", profiles)

    assert "gel" not in renamed
    assert renamed["gel 0.5 black"] == STARTER_PROFILES["gel"]
    with pytest.raises(ValueError, match="already exists"):
        rename_pen_profile("fineliner", "ballpoint", renamed)
    assert load_pen_profiles(path) == renamed


# --- applying and capturing ----------------------------------------------------


def test_apply_touches_only_the_instrument_fields() -> None:
    """Switching pens must not disturb sheet size, layout or sampling."""
    settings = _a4_settings()
    before = asdict(settings)
    apply_pen_profile(settings, "gel")
    after = asdict(settings)

    changed = {key for key in before if before[key] != after[key]}
    assert changed <= set(PEN_PROFILE_FIELDS) | {"pen_profile"}
    assert settings.sheet_width_mm == 210.0
    assert settings.pen_profile == "gel"


def test_apply_then_capture_round_trips() -> None:
    settings = GuiSettings()
    apply_pen_profile(settings, "ballpoint")
    assert capture_pen_profile(settings) == load_pen_profiles()["ballpoint"]
    assert profile_matches(settings, "ballpoint")


def test_tuning_away_from_a_profile_is_detectable() -> None:
    """This is what tells the operator a tuned setting still needs saving."""
    settings = GuiSettings()
    apply_pen_profile(settings, "gel")
    settings.draw_rate += 200.0
    assert not profile_matches(settings, "gel")


def test_unknown_profile_names_the_known_ones() -> None:
    with pytest.raises(ValueError, match="fineliner"):
        apply_pen_profile(GuiSettings(), "sharpie")


# --- the dwell survives every hop to the plotter --------------------------------


def test_dwell_survives_the_runtime_config_round_trip() -> None:
    """PlotterRuntimeConfig has three separate field lists; missing one drops it silently."""
    settings = GuiSettings()
    apply_pen_profile(settings, "gel")
    config = gui_settings_to_plotter_config(settings)
    assert config.pen_down_dwell_ms == STARTER_PROFILES["gel"]["pen_down_dwell_ms"]

    restored = PlotterRuntimeConfig.from_dict(config.to_dict())
    assert restored.pen_down_dwell_ms == config.pen_down_dwell_ms


# --- the calibration sheet ------------------------------------------------------


def test_every_ladder_appears_on_the_sheet() -> None:
    settings = _a4_settings()
    apply_pen_profile(settings, "gel")
    gcode, manifest = build_pen_cal_gcode(settings)

    feeds = {float(m) for m in re.findall(r"^G1 F([\d.]+)$", gcode, re.M)}
    depths = {float(m) for m in re.findall(r"^G1 Z(-[\d.]+) F", gcode, re.M)}
    dwells = {float(m) for m in re.findall(r"^G4 P([\d.]+)$", gcode, re.M)}

    assert set(PenCalRanges().draw_rates) <= feeds
    assert len(depths) == PenCalRanges().z_steps
    # 0 ms emits no G4 at all, so the dwell rungs on the sheet are the non-zero ones.
    assert {v / 1000.0 for v in PenCalRanges().dwell_ms if v} <= dwells
    assert manifest["rows"]


def test_z_ladder_stays_within_the_safe_span() -> None:
    """The one block that can wreck a nib: bounded offset, never an absolute sweep.

    Only deeper wrecks a nib. A profile parked at the travel floor shifts the whole
    ladder shallower to keep its rungs distinct, so the deep bound is the hard one:
    never more than the span past the profile depth, never past the floor.
    """
    settings = _a4_settings()
    apply_pen_profile(settings, "fineliner")
    gcode, _ = build_pen_cal_gcode(settings)
    depths = [float(m) for m in re.findall(r"^G1 Z(-[\d.]+) F", gcode, re.M)]

    assert min(depths) >= settings.z_down_mm - Z_LADDER_SPAN_MM - 1e-9
    assert max(depths) <= 0.0
    assert min(depths) >= Z_ABSOLUTE_FLOOR_MM
    ladder = set(depths)
    assert len({d for d in ladder if d <= settings.z_down_mm + 2 * Z_LADDER_SPAN_MM}) >= PenCalRanges().z_steps


def test_z_ladder_respects_the_absolute_floor() -> None:
    settings = _a4_settings()
    settings.z_down_mm = Z_ABSOLUTE_FLOOR_MM - 5.0
    gcode, _ = build_pen_cal_gcode(settings)
    depths = [float(m) for m in re.findall(r"^G1 Z(-[\d.]+) F", gcode, re.M)]
    assert min(depths) >= Z_ABSOLUTE_FLOOR_MM


def test_sheet_fits_the_bed_and_starts_at_the_origin() -> None:
    settings = _a4_settings()
    gcode, manifest = build_pen_cal_gcode(settings)
    points = [(float(x), float(y)) for x, y in re.findall(r"^G[01] X(-?[\d.]+) Y(-?[\d.]+)$", gcode, re.M)]
    drawing = [p for p in points if p != (0.0, 0.0)]  # the final park move

    assert max(x for x, _ in drawing) <= settings.sheet_width_mm
    assert max(y for _, y in drawing) <= settings.sheet_height_mm
    assert min(x for x, _ in drawing) >= settings.direct_svg_origin_x_mm - 1e-6
    assert manifest["extent_mm"][1] <= settings.sheet_height_mm


def test_a_sheet_too_big_for_the_bed_raises_rather_than_clipping() -> None:
    settings = _a4_settings()
    settings.sheet_height_mm = 90.0
    with pytest.raises(ValueError, match="exceeds"):
        build_pen_cal_gcode(settings)


def test_sheet_writes_gcode_and_manifest(tmp_path: Path) -> None:
    settings = _a4_settings()
    apply_pen_profile(settings, "gel")
    output = generate_pen_cal_sheet(settings, spool_root=tmp_path)
    assert output["gcode"].exists() and output["manifest"].exists()

    manifest = json.loads(output["manifest"].read_text())
    # The manifest is how a sheet found later is traced back to its settings.
    assert manifest["profile"] == "gel"
    assert manifest["base"]["pen_down_dwell_ms"] == STARTER_PROFILES["gel"]["pen_down_dwell_ms"]
