"""GUI settings persistence: load/save GuiSettings + symbol-scale JSON files,
and pushing settings into the oracle runtime store.

Split out of support.py (mechanical extraction, no behavior change) to keep
that module under the repo's file-size budget.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ...shared.config import OracleSupervisorSettings, PlotterSettings, ensure_parent
from ...shared.gui_settings import GuiSettings, _repair_xy_acceleration, gui_settings_to_plotter_config
from ...shared.models import SystemMode
from ...shared.store import OracleRuntimeStore
from ...shared.symbols import (
    load_symbol_scales as load_symbol_scales,
)
from ...shared.symbols import (
    save_symbol_scales as save_symbol_scales,
)
from .support import default_gui_settings_path


def load_gui_settings(path: Path | None = None, plotter_settings: PlotterSettings | None = None) -> GuiSettings:
    settings_path = path or default_gui_settings_path()
    base = GuiSettings.from_plotter_settings(plotter_settings or PlotterSettings())
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
    settings = GuiSettings(**merged)
    plotter_defaults = plotter_settings or PlotterSettings()
    if plotter_defaults.use_z_servo and settings.z_up_mm == 25.0 and settings.z_down_mm == 0.0:
        settings.z_up_mm = plotter_defaults.z_up_mm
        settings.z_down_mm = plotter_defaults.z_down_mm
    settings.apply_system_mode()
    return settings


def save_gui_settings(settings: GuiSettings, path: Path | None = None) -> None:
    settings.apply_system_mode()
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
