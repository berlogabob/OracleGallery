# ruff: noqa: I001 - import order here is load-bearing: the bottom-of-file
# settings_io/preview imports break a real cycle and must stay last.
from __future__ import annotations

import contextlib
import inspect
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from ...shared.config import OracleSupervisorSettings, PlotterSettings, _repo_root
from ...shared.gui_settings import (
    GUI_DEFAULTS as GUI_DEFAULTS,
)
from ...shared.gui_settings import (
    GuiSettings as GuiSettings,
)
from ...shared.gui_settings import (
    NumericGuiDefaultKey,
)
from ...shared.gui_settings import (
    _repair_xy_acceleration as _repair_xy_acceleration,
)
from ...shared.gui_settings import (
    gui_settings_to_plotter_config as gui_settings_to_plotter_config,
)
from ...shared.store import OracleRuntimeStore, PlotterStore
from ...shared.symbols import (
    default_idle_root as default_idle_root,
)
from ...shared.symbols import (
    default_scale_config_path as default_scale_config_path,
)
from ...shared.symbols import (
    default_symbol_root as default_symbol_root,
)
from ...shared.symbols import (
    list_base_symbols as list_base_symbols,
)
from ..gcode.direct_svg import DirectSvgPrintJob as DirectSvgPrintJob
from ..gcode.direct_svg import create_direct_svg_print_job_from_gui as create_direct_svg_print_job_from_gui
from ..gcode.dry_run import generate_dry_run_sheet as generate_dry_run_sheet
from ..gcode.pen_cal import generate_pen_cal_sheet as generate_pen_cal_sheet
from ..gcode.layout import _build_layout_for_settings as _build_layout_for_settings
from ..gcode.layout import layout_capacity as layout_capacity
from ..gcode.sampling import compute_effective_sample_step as compute_effective_sample_step


class _NumericField(Protocol):
    @property
    def value(self) -> str | int | float | None: ...


def _field_or_default(fields: Mapping[str, _NumericField], key: NumericGuiDefaultKey) -> float:
    default = cast(int | float, GUI_DEFAULTS.get(key))
    return float(fields[key].value or default)


def default_gui_settings_path() -> Path:
    # Env-overridable like every other writable path: save_gui_settings() writes here,
    # so without an override a test that persists settings overwrites the operator's
    # live machine calibration. tests/conftest.py redirects this to a sandbox.
    return Path(os.getenv("NEJE_GUI_SETTINGS_PATH", str(_repo_root() / "runtime" / "gui_settings.json")))


def default_filler_package_root() -> Path:
    return _repo_root() / "assets" / "generated_filler_sessions"


def read_upload_content_bytes(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")

    if hasattr(content, "seek"):
        with contextlib.suppress(OSError, ValueError):
            content.seek(0)
    value = content.getvalue() if hasattr(content, "getvalue") else content.read()
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value or b"")


async def read_upload_event_payload(event: Any) -> tuple[str, bytes]:
    upload_file = getattr(event, "file", None)
    if upload_file is not None:
        name = str(getattr(upload_file, "name", "") or getattr(event, "name", "") or "uploaded.svg")
        value = upload_file.read()
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, str):
            return name, value.encode("utf-8")
        return name, bytes(value or b"")

    content = getattr(event, "content", None)
    if content is None:
        raise ValueError("no file content")
    name = str(getattr(event, "name", "") or "uploaded.svg")
    return name, read_upload_content_bytes(content)


def read_plotter_status(db_path: Path | None = None, spool_root: Path | None = None) -> dict[str, Any]:
    plotter_settings = PlotterSettings()
    resolved_db_path = db_path or plotter_settings.db_path
    latest_manifest = latest_spool_manifest(spool_root or plotter_settings.spool_root)
    item_counts = _manifest_item_counts(latest_manifest)
    oracle_store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
    oracle_control = oracle_store.load_print_control()
    if not resolved_db_path.exists():
        return {
            "status": "daemon_not_started",
            "message": "Plotter daemon has not created runtime state yet",
            "current_sheet_id": "",
            "last_sheet_path": "",
            "print_enabled": oracle_control.print_enabled,
            "operator_paused": oracle_control.operator_paused,
            "run_mode": oracle_control.run_mode,
            "dry_run": oracle_control.dry_run,
            "gcode_lines_sent": 0,
            "gcode_lines_total": 0,
            "gcode_progress_percent": 0.0,
            "current_row_index": 0,
            "row_count": 0,
            "current_cell_index": 0,
            "current_cell_in_row": 0,
            "row_cell_count": 0,
            "cells_completed": 0,
            "rows_completed": 0,
            "sheet_progress_percent": 0.0,
            "updated_at": "",
            "latest_manifest": str(latest_manifest) if latest_manifest else "",
            "user_count": item_counts["user"],
            "idle_count": item_counts["idle"],
            "processed_symbols": item_counts["total"],
        }
    store = PlotterStore(resolved_db_path)
    state = store.load_runtime_state()
    control = oracle_store.load_print_control(store.load_control_state())
    return {
        "status": state.status.value,
        "message": state.message,
        "current_sheet_id": state.current_sheet_id,
        "last_sheet_path": state.last_sheet_path,
        "print_enabled": control.print_enabled,
        "operator_paused": control.operator_paused,
        "run_mode": control.run_mode,
        "dry_run": control.dry_run,
        "gcode_lines_sent": state.gcode_lines_sent,
        "gcode_lines_total": state.gcode_lines_total,
        "gcode_progress_percent": state.gcode_progress_percent,
        "current_row_index": state.current_row_index,
        "row_count": state.row_count,
        "current_cell_index": state.current_cell_index,
        "current_cell_in_row": state.current_cell_in_row,
        "row_cell_count": state.row_cell_count,
        "cells_completed": state.cells_completed,
        "rows_completed": state.rows_completed,
        "sheet_progress_percent": state.sheet_progress_percent,
        "updated_at": state.updated_at.isoformat(),
        "latest_manifest": str(latest_manifest) if latest_manifest else "",
        "user_count": item_counts["user"],
        "idle_count": item_counts["idle"],
        "processed_symbols": item_counts["total"],
    }


def latest_spool_manifest(spool_root: Path) -> Path | None:
    if not spool_root.exists():
        return None
    manifests = sorted(spool_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return manifests[0] if manifests else None


def effective_randomness(settings: GuiSettings) -> float:
    return max(0.0, min(settings.randomness * 0.5 + settings.randomness_fine, 100.0))


def _manifest_item_counts(manifest_path: Path | None) -> dict[str, int]:
    if not manifest_path or not manifest_path.exists():
        return {"user": 0, "idle": 0, "total": 0}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not items and isinstance(payload.get("rows"), list):
        items = [
            item
            for row in payload["rows"]
            if isinstance(row, dict)
            for item in row.get("items", [])
            if isinstance(item, dict)
        ]
    user = sum(1 for item in items if item.get("source_kind") == "user")
    idle = len(items) - user
    return {"user": user, "idle": idle, "total": len(items)}


# Settings persistence moved to settings_io.py; re-exported so callers/tests keep
# importing from `support`. Imported before preview.py: preview's own
# `from .support import ...` needs load_symbol_scales already bound here.
from .settings_io import (  # noqa: E402,F401
    load_gui_settings,
    load_symbol_scales,
    save_gui_settings,
    save_oracle_plotter_config,
    save_symbol_scales,
)
from ..firebase.queue_status import read_queue_status  # noqa: E402,F401

# Preview-svg rendering moved to preview.py; re-exported so callers/tests keep
# importing from `support`. Imported last so preview.py's own `from .support
# import ...` sees a fully-populated module (avoids a circular-import failure).
from .preview import (  # noqa: E402,F401
    PREVIEW_PX_PER_MM,
    LivePreviewItem,
    _build_live_preview_svg,
    _empty_preview_svg,
    _live_preview_items,
    _manifest_live_preview_item,
    _manifest_preview_items,
    _next_preview_ghost,
    _pending_user_queue_count,
    _placement_row_lookup,
    _preview_image_size,
    _preview_item_placement,
    _preview_rotation_transform,
    _preview_scale,
    _preview_symbol_images,
    _preview_symbol_index,
    _svg_file_data_uri,
    build_preview_svg,
    build_realtime_preview_svg,
    build_symbol_preview_svg,
)
