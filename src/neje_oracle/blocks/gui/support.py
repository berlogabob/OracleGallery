from __future__ import annotations

import inspect
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ...shared.config import SYMBOL_FIT_RATIO, OracleSupervisorSettings, PlotterSettings, UploaderSettings, _repo_root, ensure_dir
from .modes import apply_mode_to_config, mode_policy
from ..gcode.layout import build_sheet_layout, calculate_layout_capacity
from ...shared.models import PlotterRuntimeConfig, SheetItem, SheetPlacement, SystemMode
from ...shared.origin_markers import (
    ALL_ORIGINS,
    DEFAULT_MARKER_DIAMETER_MM,
    ORIGIN_FILLER_MACBOOK,
    marker_position_for_origin,
    normalize_tags,
)
from ..gcode.sampling import compute_effective_sample_step
from ..symbols.session_generator import generate_filler_session_packages, generate_idle_symbols, generate_user_sessions
from ...shared.store import OracleRuntimeStore, PlotterStore
from ..gcode.svg_gcode import generate_absolute_svg_gcode, generate_sheet_gcode
from ..symbols.svg_normalizer import normalize_svg_file




@dataclass(frozen=True)
class DirectSvgPrintJob:
    sheet_id: str
    svg_path: Path
    original_name: str
    label: str
    gcode: str
    effective_sample_step_mm: float


GUI_DEFAULTS = {
    "system_mode": SystemMode.EXHIBITION.value,
    "sheet_width_mm": 250.0,
    "sheet_height_mm": 440.0,
    "sheet_margin_mm": 0.0,
    "cell_diameter_mm": 80.0,
    "gap_mm": 0.0,
    "organic_enabled": False,
    "organic_cell_size_mm": 18.0,
    "organic_rotation_ramp": 0.0,
    "organic_scale_ramp": 0.0,
    "organic_seed": 1007,
    "global_scale": 1.0,
    "randomness": 35.0,
    "randomness_fine": 0.0,
    "include_rings": True,
    "include_markers": True,
    "marker_diameter_mm": DEFAULT_MARKER_DIAMETER_MM,
    # G-code optimisation
    "sample_step_mm": 1.0,
    "sample_reference_cell_mm": 80.0,
    "sample_density_exponent": 1.0,
    "sample_min_step_mm": 0.25,
    "sample_max_step_mm": 3.0,
    "streaming_mode": "row",
    "travel_rate": 5000.0,
    "draw_rate": 1800.0,
    "xy_acceleration_mm_s2": 1000.0,
    "z_down_mm": -25.0,
    "z_up_mm": 0.0,
    "z_feed_mm_min": 1000.0,
    "direct_svg_origin_x_mm": 25.0,
    "direct_svg_origin_y_mm": 25.0,
}


def _field_or_default(fields: dict[str, Any], key: str) -> float:
    return float(fields[key].value or GUI_DEFAULTS[key])


@dataclass
class GuiSettings:
    system_mode: str = GUI_DEFAULTS["system_mode"]
    layout_mode: str = "hex"
    sheet_width_mm: float = GUI_DEFAULTS["sheet_width_mm"]
    sheet_height_mm: float = GUI_DEFAULTS["sheet_height_mm"]
    sheet_margin_mm: float = GUI_DEFAULTS["sheet_margin_mm"]
    cell_diameter_mm: float = GUI_DEFAULTS["cell_diameter_mm"]
    gap_mm: float = GUI_DEFAULTS["gap_mm"]
    organic_enabled: bool = GUI_DEFAULTS["organic_enabled"]
    organic_cell_size_mm: float = GUI_DEFAULTS["organic_cell_size_mm"]
    organic_rotation_ramp: float = GUI_DEFAULTS["organic_rotation_ramp"]
    organic_scale_ramp: float = GUI_DEFAULTS["organic_scale_ramp"]
    organic_seed: int = GUI_DEFAULTS["organic_seed"]
    run_mode: str = "exhibition"
    # apply_system_mode() always resolves this from mode_policy(); keep the default in sync with that reality.
    dry_run: bool = False
    global_scale: float = GUI_DEFAULTS["global_scale"]
    randomness: float = GUI_DEFAULTS["randomness"]
    randomness_fine: float = GUI_DEFAULTS["randomness_fine"]
    include_rings: bool = GUI_DEFAULTS["include_rings"]
    include_markers: bool = GUI_DEFAULTS["include_markers"]
    marker_diameter_mm: float = GUI_DEFAULTS["marker_diameter_mm"]
    # G-code optimisation
    sample_step_mm: float = GUI_DEFAULTS["sample_step_mm"]
    sample_reference_cell_mm: float = GUI_DEFAULTS["sample_reference_cell_mm"]
    sample_density_exponent: float = GUI_DEFAULTS["sample_density_exponent"]
    sample_min_step_mm: float = GUI_DEFAULTS["sample_min_step_mm"]
    sample_max_step_mm: float = GUI_DEFAULTS["sample_max_step_mm"]
    streaming_mode: str = GUI_DEFAULTS["streaming_mode"]
    show_origins: list[str] = field(default_factory=lambda: list(ALL_ORIGINS))
    print_origins: list[str] = field(default_factory=lambda: list(ALL_ORIGINS))
    travel_rate: float = 5000.0
    draw_rate: float = 1800.0
    xy_acceleration_mm_s2: float = GUI_DEFAULTS["xy_acceleration_mm_s2"]
    z_down_mm: float = -25.0
    z_up_mm: float = 0.0
    z_feed_mm_min: float = 1000.0
    direct_svg_origin_x_mm: float = GUI_DEFAULTS["direct_svg_origin_x_mm"]
    direct_svg_origin_y_mm: float = GUI_DEFAULTS["direct_svg_origin_y_mm"]
    user_count: int = 1
    live_interval_seconds: float = 12.0
    idle_count: int = 8
    idle_variations_per_symbol: int = 2
    selected_symbol: str = "__cycle__"

    def apply_system_mode(self) -> None:
        policy = mode_policy(self.system_mode)
        self.system_mode = policy.mode.value
        self.run_mode = policy.run_mode
        self.dry_run = policy.dry_run

    @property
    def mode(self) -> SystemMode:
        return SystemMode(self.system_mode)

    @classmethod
    def from_plotter_settings(cls, settings: PlotterSettings) -> "GuiSettings":
        return cls(
            layout_mode=settings.layout_mode,
            sheet_width_mm=settings.sheet_width_mm,
            sheet_height_mm=settings.sheet_height_mm,
            sheet_margin_mm=settings.sheet_margin_mm,
            cell_diameter_mm=settings.cell_diameter_mm,
            gap_mm=settings.cell_gap_mm,
            organic_enabled=settings.organic_enabled,
            organic_cell_size_mm=settings.organic_cell_size_mm,
            organic_rotation_ramp=settings.organic_rotation_ramp,
            organic_scale_ramp=settings.organic_scale_ramp,
            organic_seed=settings.organic_seed,
            dry_run=settings.dry_run,
            travel_rate=settings.travel_rate,
            draw_rate=settings.draw_rate,
            xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
            z_down_mm=settings.z_down_mm,
            z_up_mm=settings.z_up_mm,
            z_feed_mm_min=settings.z_feed_mm_min,
            direct_svg_origin_x_mm=GUI_DEFAULTS["direct_svg_origin_x_mm"],
            direct_svg_origin_y_mm=GUI_DEFAULTS["direct_svg_origin_y_mm"],
            include_markers=settings.include_markers,
            marker_diameter_mm=settings.marker_diameter_mm,
            sample_step_mm=settings.sample_step_mm,
            sample_reference_cell_mm=settings.sample_reference_cell_mm,
            sample_density_exponent=settings.sample_density_exponent,
            sample_min_step_mm=settings.sample_min_step_mm,
            sample_max_step_mm=settings.sample_max_step_mm,
            streaming_mode=settings.streaming_mode,
        )


def default_gui_settings_path() -> Path:
    return _repo_root() / "runtime" / "gui_settings.json"


def default_scale_config_path() -> Path:
    return _repo_root() / "assets" / "symbols" / "symbol_scales.json"


def default_symbol_root() -> Path:
    return _repo_root() / "assets" / "symbols"


def default_idle_root() -> Path:
    return _repo_root() / "assets" / "generated_idle_symbols"


def default_filler_package_root() -> Path:
    return _repo_root() / "assets" / "generated_filler_sessions"


def _repair_xy_acceleration(value: float) -> float:
    if 0.0 < value < 100.0:
        return cast(float, GUI_DEFAULTS["xy_acceleration_mm_s2"])
    return value


def gui_settings_to_plotter_config(settings: GuiSettings) -> PlotterRuntimeConfig:
    settings.apply_system_mode()
    plotter_settings = PlotterSettings()
    return apply_mode_to_config(PlotterRuntimeConfig(
        layout_mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        sheet_margin_mm=settings.sheet_margin_mm,
        cell_diameter_mm=settings.cell_diameter_mm,
        gap_mm=settings.gap_mm,
        organic_enabled=settings.organic_enabled,
        organic_cell_size_mm=settings.organic_cell_size_mm,
        organic_rotation_ramp=settings.organic_rotation_ramp,
        organic_scale_ramp=settings.organic_scale_ramp,
        organic_seed=settings.organic_seed,
        run_mode=settings.run_mode,
        dry_run=settings.dry_run,
        include_rings=settings.include_rings,
        include_markers=settings.include_markers,
        marker_diameter_mm=settings.marker_diameter_mm,
        travel_rate=settings.travel_rate,
        draw_rate=settings.draw_rate,
        xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
        use_z_servo=plotter_settings.use_z_servo,
        z_down_mm=settings.z_down_mm,
        z_up_mm=settings.z_up_mm,
        z_feed_mm_min=settings.z_feed_mm_min,
        work_zero_command=plotter_settings.work_zero_command,
        # G-code optimisation
        sample_step_mm=settings.sample_step_mm,
        sample_reference_cell_mm=settings.sample_reference_cell_mm,
        sample_density_exponent=settings.sample_density_exponent,
        sample_min_step_mm=settings.sample_min_step_mm,
        sample_max_step_mm=settings.sample_max_step_mm,
        streaming_mode=settings.streaming_mode,
    ), settings.mode)


def list_base_symbols(symbol_root: Path | None = None) -> list[Path]:
    root = symbol_root or default_symbol_root()
    return sorted(path for path in root.glob("*.svg") if path.is_file())


def layout_capacity(settings: GuiSettings) -> int:
    return calculate_layout_capacity(
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
    )


def _build_layout_for_settings(settings: GuiSettings, count: int) -> list[SheetPlacement]:
    return build_sheet_layout(
        count,
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
        organic_enabled=settings.organic_enabled,
        organic_cell_size_mm=settings.organic_cell_size_mm,
        organic_rotation_ramp=settings.organic_rotation_ramp,
        organic_scale_ramp=settings.organic_scale_ramp,
        organic_seed=settings.organic_seed,
    )


def create_user_sessions_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
    start_index: int = 0,
) -> list[Path]:
    destination = output_root or UploaderSettings().session_root
    generated = generate_user_sessions(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=settings.user_count,
        jitter_px=effective_randomness(settings) / 100.0 * 8.0,
        symbol_name=settings.selected_symbol,
        global_scale=settings.global_scale,
        include_rings=False,
        start_index=start_index,
    )
    return [session.session_dir for session in generated]


def create_next_filler_upload_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
    start_index: int = 0,
) -> list[Path]:
    destination = output_root or UploaderSettings().session_root
    generated = generate_filler_session_packages(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=1,
        jitter_px=effective_randomness(settings) / 100.0 * 6.0,
        symbol_name=settings.selected_symbol,
        global_scale=settings.global_scale,
        include_rings=False,
        start_index=start_index,
        upload_to_firebase=True,
    )
    return [session.session_dir for session in generated]


def create_direct_svg_print_job_from_gui(
    settings: GuiSettings,
    *,
    svg_bytes: bytes,
    original_name: str,
    output_root: Path | None = None,
    plotter_settings: PlotterSettings | None = None,
) -> DirectSvgPrintJob:
    svg_text = _validated_svg_text(svg_bytes)
    resolved_plotter_settings = plotter_settings or PlotterSettings()
    destination = output_root or (resolved_plotter_settings.spool_root / "uploaded_svg")
    ensure_dir(destination)
    now = datetime.now(tz=UTC)
    sheet_id = _direct_svg_sheet_id(destination, now)
    label = _label_from_upload_name(original_name)
    svg_file = destination / f"{sheet_id}_{_safe_upload_stem(original_name)}.svg"
    svg_file.write_text(svg_text, encoding="utf-8")

    config = gui_settings_to_plotter_config(settings)
    effective_step = compute_effective_sample_step(
        sample_step_mm=config.sample_step_mm,
        cell_diameter_mm=config.cell_diameter_mm,
        sample_reference_cell_mm=config.sample_reference_cell_mm,
        sample_density_exponent=config.sample_density_exponent,
        sample_min_step_mm=config.sample_min_step_mm,
        sample_max_step_mm=config.sample_max_step_mm,
    )
    gcode = generate_absolute_svg_gcode(
        svg_file,
        sample_step_mm=effective_step,
        travel_rate=config.travel_rate,
        draw_rate=config.draw_rate,
        xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
        pen_up_command=resolved_plotter_settings.pen_up_command,
        pen_down_command=resolved_plotter_settings.pen_down_command,
        title=f"direct SVG {label}",
        return_home=True,
        use_z_servo=resolved_plotter_settings.use_z_servo,
        z_down_mm=config.z_down_mm,
        z_up_mm=config.z_up_mm,
        z_feed_mm_min=config.z_feed_mm_min,
        origin_x_mm=settings.direct_svg_origin_x_mm,  # not part of PlotterRuntimeConfig
        origin_y_mm=settings.direct_svg_origin_y_mm,  # not part of PlotterRuntimeConfig
        keep_non_negative=True,
        max_x_mm=resolved_plotter_settings.sheet_width_mm,
        max_y_mm=resolved_plotter_settings.sheet_height_mm,
    )
    return DirectSvgPrintJob(
        sheet_id=sheet_id,
        svg_path=svg_file,
        original_name=original_name,
        label=label,
        gcode=gcode,
        effective_sample_step_mm=effective_step,
    )


def read_upload_content_bytes(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")

    if hasattr(content, "seek"):
        try:
            content.seek(0)
        except (OSError, ValueError):
            pass
    if hasattr(content, "getvalue"):
        value = content.getvalue()
    else:
        value = content.read()
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


def create_idle_bank_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[Path]:
    symbol_count = len(list_base_symbols(symbol_root))
    count = max(settings.idle_count, symbol_count * max(settings.idle_variations_per_symbol, 1))
    destination = output_root or default_idle_root()
    if destination.exists():
        for old_svg in destination.glob("*.svg"):
            old_svg.unlink()
    return generate_idle_symbols(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=count,
        jitter_px=effective_randomness(settings) / 100.0 * 6.0,
        global_scale=settings.global_scale,
        include_rings=False,
    )


def create_filler_packages_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[Path]:
    symbol_count = len(list_base_symbols(symbol_root))
    count = max(settings.idle_count, symbol_count * max(settings.idle_variations_per_symbol, 1))
    destination = output_root or default_filler_package_root()
    if destination.exists():
        for old_dir in destination.iterdir():
            if old_dir.is_dir() and old_dir.name.startswith("filler_"):
                for child in sorted(old_dir.rglob("*"), reverse=True):
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                old_dir.rmdir()
    generated = generate_filler_session_packages(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=count,
        jitter_px=effective_randomness(settings) / 100.0 * 6.0,
        global_scale=settings.global_scale,
        include_rings=False,
    )
    return [session.session_dir for session in generated]


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


def generate_dry_run_sheet(settings: GuiSettings, *, spool_root: Path | None = None, symbol_root: Path | None = None) -> dict[str, Path]:
    output_root = spool_root or PlotterSettings().spool_root
    ensure_dir(output_root)
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        raise FileNotFoundError("No symbols available for G-code-only sheet generation")
    scales = load_symbol_scales(symbol_root=symbol_root)
    cache_dir = output_root / "cache"
    ensure_dir(cache_dir)
    config = gui_settings_to_plotter_config(settings)
    scaled_symbols: list[Path] = []
    for symbol in symbols:
        scale = scales.get(symbol.name, 1.0) * settings.global_scale  # not part of PlotterRuntimeConfig
        cached = cache_dir / f"dry_run_{symbol.stem}.svg"
        cached.write_text(
            normalize_svg_file(symbol, marker_kind="idle", scale=scale, include_rings=False),
            encoding="utf-8",
        )
        scaled_symbols.append(cached)
    capacity = layout_capacity(settings)
    count = capacity
    placements = _build_layout_for_settings(settings, count)
    items = [
        SheetItem(
            source_kind="placeholder",
            session_id=f"gui_dry_run_{index + 1:03d}",
            title=symbols[index % len(symbols)].stem,
            svg_path=scaled_symbols[index % len(scaled_symbols)],
            origin=ORIGIN_FILLER_MACBOOK,
            tags=normalize_tags(["filler", "local", "macbook"]),
            marker_position=marker_position_for_origin(ORIGIN_FILLER_MACBOOK),
        )
        for index in range(len(placements))
    ]
    sheet_id = datetime.now(tz=UTC).strftime("gui_sheet_%Y%m%d_%H%M%S")
    effective_step = compute_effective_sample_step(
        sample_step_mm=config.sample_step_mm,
        cell_diameter_mm=config.cell_diameter_mm,
        sample_reference_cell_mm=config.sample_reference_cell_mm,
        sample_density_exponent=config.sample_density_exponent,
        sample_min_step_mm=config.sample_min_step_mm,
        sample_max_step_mm=config.sample_max_step_mm,
    )
    gcode = generate_sheet_gcode(
        items,
        placements,
        sample_step_mm=effective_step,
        cell_diameter_mm=config.cell_diameter_mm,
        travel_rate=config.travel_rate,
        draw_rate=config.draw_rate,
        xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
        pen_up_command=PlotterSettings().pen_up_command,
        pen_down_command=PlotterSettings().pen_down_command,
        include_rings=config.include_rings,
        include_markers=config.include_markers,
        marker_diameter_mm=config.marker_diameter_mm,
        use_z_servo=PlotterSettings().use_z_servo,
        z_down_mm=config.z_down_mm,
        z_up_mm=config.z_up_mm,
        z_feed_mm_min=config.z_feed_mm_min,
    )
    gcode_path = output_root / f"{sheet_id}.gcode"
    manifest_path = output_root / f"{sheet_id}.json"
    gcode_path.write_text(gcode, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "sheet_id": sheet_id,
                "generated_by": "neje-gui",
                "layout_mode": config.layout_mode,
                "cell_diameter_mm": config.cell_diameter_mm,
                "gap_mm": config.gap_mm,
                "organic_enabled": config.organic_enabled,
                "organic_cell_size_mm": config.organic_cell_size_mm,
                "organic_rotation_ramp": config.organic_rotation_ramp,
                "organic_scale_ramp": config.organic_scale_ramp,
                "organic_seed": config.organic_seed,
                "symbol_fit_ratio": SYMBOL_FIT_RATIO,
                "include_markers": config.include_markers,
                "marker_diameter_mm": config.marker_diameter_mm,
                # G-code optimisation
                "sample_step_mm": config.sample_step_mm,
                "sample_reference_cell_mm": config.sample_reference_cell_mm,
                "sample_density_exponent": config.sample_density_exponent,
                "sample_min_step_mm": config.sample_min_step_mm,
                "sample_max_step_mm": config.sample_max_step_mm,
                "effective_sample_step_mm": effective_step,
                "streaming_mode": config.streaming_mode,
                "xy_acceleration_mm_s2": config.xy_acceleration_mm_s2,
                "items": [
                    {
                        "session_id": item.session_id,
                        "source_kind": item.source_kind,
                        "origin": item.origin,
                        "tags": item.tags,
                        "marker_position": item.marker_position,
                        "marker_diameter_mm": config.marker_diameter_mm,
                        "svg_path": str(item.svg_path),
                        "sheet_index": index,
                        "center_x_mm": placements[index].center_x_mm,
                        "center_y_mm": placements[index].center_y_mm,
                        "cell_diameter_mm": placements[index].diameter_mm,
                        "rotation_deg": placements[index].rotation_deg,
                        "symbol_scale": placements[index].symbol_scale,
                        "row_y_mm": placements[index].row_y_mm,
                    }
                    for index, item in enumerate(items)
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"gcode": gcode_path, "manifest": manifest_path}


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


def _validated_svg_text(svg_bytes: bytes) -> str:
    if not svg_bytes or not svg_bytes.strip():
        raise ValueError("Uploaded SVG file is empty")
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Uploaded file is not valid SVG XML: {exc}") from exc
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag != "svg":
        raise ValueError("Uploaded file root element must be <svg>")
    try:
        return svg_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Uploaded SVG must be UTF-8 encoded") from exc


def _direct_svg_sheet_id(output_root: Path, now: datetime) -> str:
    base = now.strftime("testsvg_%Y%m%d_%H%M%S")
    candidate = base
    suffix = 1
    while (output_root / f"{candidate}.gcode").exists() or any(output_root.glob(f"{candidate}_*.svg")):
        suffix += 1
        candidate = f"{base}_{suffix:03d}"
    return candidate


def _safe_upload_stem(original_name: str) -> str:
    stem = Path(original_name).stem or "uploaded_svg"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    return safe or "uploaded_svg"


def _label_from_upload_name(original_name: str) -> str:
    stem = Path(original_name).stem or "uploaded_svg"
    label = re.sub(r"[^A-Za-z0-9]+", " ", stem).strip().upper()
    return label or "UPLOADED SVG"


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

# Preview-svg rendering moved to preview.py; re-exported so callers/tests keep
# importing from `support`. Imported last so preview.py's own `from .support
# import ...` sees a fully-populated module (avoids a circular-import failure).
from .preview import (  # noqa: E402,F401
    PREVIEW_PX_PER_MM,
    LivePreviewItem,
    build_preview_svg,
    build_realtime_preview_svg,
    build_symbol_preview_svg,
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
)

from ..firebase.queue_status import read_queue_status  # noqa: E402,F401
