"""GUI settings persistence: load/save GuiSettings + symbol-scale JSON files,
and pushing settings into the oracle runtime store.

Split out of support.py (mechanical extraction, no behavior change) to keep
that module under the repo's file-size budget.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ...shared.config import OracleSupervisorSettings, ensure_parent
from ...shared.gui_settings import (
    GuiSettings,
    _repair_xy_acceleration,
    gui_settings_to_plotter_config,
    sync_z_from_pulses,
)
from ...shared.models import SystemMode
from ...shared.store import OracleRuntimeStore
from ...shared.symbols import (
    load_symbol_scales as load_symbol_scales,
)
from ...shared.symbols import (
    save_symbol_scales as save_symbol_scales,
)
from ...shared.z_positions import ZPulseRange, pulse_for_z
from .support import default_gui_settings_path


def load_gui_settings(path: Path | None = None) -> GuiSettings:
    settings_path = path or default_gui_settings_path()
    base = GuiSettings()
    if not settings_path.exists():
        base.apply_system_mode()
        return base
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    merged = asdict(base)
    if "system_mode" not in payload:
        run_mode = str(payload.get("run_mode", base.run_mode))
        if run_mode == "test":
            payload["system_mode"] = SystemMode.TEST.value
        else:
            payload["system_mode"] = SystemMode.EXHIBITION.value
    merged.update({key: value for key, value in payload.items() if key in merged})
    merged["xy_acceleration_mm_s2"] = _repair_xy_acceleration(float(merged.get("xy_acceleration_mm_s2", 0.0) or 0.0))
    _migrate_z_pulses(payload, merged)
    settings = GuiSettings(**merged)
    settings.apply_system_mode()
    sync_z_from_pulses(settings)
    return settings


def _migrate_z_pulses(payload: dict, merged: dict) -> None:
    """A settings file written before the five named positions has only millimetres.

    Derive the microseconds from them so the first launch after the change leaves the pen
    exactly where it was, instead of snapping to the shipped defaults. The round trip can
    shift a target by up to half a microsecond of rounding -- 0.04 Z units, about 11 microns
    of real pen travel -- which is far below the servo's own dead band.
    """
    if "z_top_soft_us" in payload:
        return
    pulses = ZPulseRange(top_us=int(merged["z_pulse_top_us"]), bottom_us=int(merged["z_pulse_bottom_us"]))
    merged["z_top_soft_us"] = pulse_for_z(float(merged["z_up_mm"]), pulses)
    merged["z_bottom_soft_us"] = pulse_for_z(float(merged["z_down_mm"]), pulses)
    merged["z_load_us"] = pulse_for_z(float(merged["z_fix_mm"]), pulses)
    merged["z_top_mech_us"] = merged["z_top_soft_us"]
    merged["z_bottom_mech_us"] = max(int(merged["z_bottom_soft_us"]), int(merged["z_pulse_bottom_us"]))


def save_gui_settings(settings: GuiSettings, path: Path | None = None) -> None:
    settings.apply_system_mode()
    sync_z_from_pulses(settings)
    settings.xy_acceleration_mm_s2 = _repair_xy_acceleration(settings.xy_acceleration_mm_s2)
    settings_path = path or default_gui_settings_path()
    ensure_parent(settings_path)
    settings_path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def save_oracle_plotter_config(settings: GuiSettings) -> None:
    settings.apply_system_mode()
    store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
    store.save_system_mode(settings.mode)
    store.save_plotter_config(gui_settings_to_plotter_config(settings))
    store.save_origin_filters(show_origins=settings.show_origins, print_origins=settings.print_origins)
