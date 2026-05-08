from __future__ import annotations

import json
import random
from base64 import b64encode
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SYMBOL_FIT_RATIO, FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings, _repo_root, ensure_dir, ensure_parent
from .firebase_io import FirebaseRemoteRepository
from .gui_modes import apply_mode_to_config, mode_policy
from .layout import build_sheet_layout, calculate_layout_capacity
from .models import PlotterControlState, PlotterRuntimeConfig, RuntimeStatus, SheetItem, SystemMode
from .session_generator import build_variant_svg, generate_idle_symbols, generate_user_sessions
from .store import OracleRuntimeStore, PlotterStore
from .svg_gcode import generate_sheet_gcode, symbol_diameter_for_cell
from .transport import FluidNCTransport


_QUEUE_STATUS_CACHE: tuple[datetime, dict[str, Any]] | None = None


GUI_DEFAULTS = {
    "system_mode": SystemMode.EXHIBITION_DRY.value,
    "sheet_width_mm": 250.0,
    "sheet_height_mm": 440.0,
    "sheet_margin_mm": 0.0,
    "cell_diameter_mm": 80.0,
    "gap_mm": 0.0,
    "global_scale": 1.0,
    "randomness": 35.0,
    "randomness_fine": 0.0,
    "include_rings": True,
}


@dataclass
class GuiSettings:
    system_mode: str = GUI_DEFAULTS["system_mode"]
    layout_mode: str = "hex"
    sheet_width_mm: float = GUI_DEFAULTS["sheet_width_mm"]
    sheet_height_mm: float = GUI_DEFAULTS["sheet_height_mm"]
    sheet_margin_mm: float = GUI_DEFAULTS["sheet_margin_mm"]
    cell_diameter_mm: float = GUI_DEFAULTS["cell_diameter_mm"]
    gap_mm: float = GUI_DEFAULTS["gap_mm"]
    run_mode: str = "exhibition"
    dry_run: bool = True
    global_scale: float = GUI_DEFAULTS["global_scale"]
    randomness: float = GUI_DEFAULTS["randomness"]
    randomness_fine: float = GUI_DEFAULTS["randomness_fine"]
    include_rings: bool = GUI_DEFAULTS["include_rings"]
    travel_rate: float = 5000.0
    draw_rate: float = 1800.0
    z_down_mm: float = 0.0
    z_up_mm: float = 25.0
    z_feed_mm_min: float = 1000.0
    user_count: int = 1
    live_interval_seconds: float = 12.0
    idle_count: int = 8
    idle_variations_per_symbol: int = 2
    selected_symbol: str = "__cycle__"

    def apply_system_mode(self) -> None:
        policy = mode_policy(self.system_mode)
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
            dry_run=settings.dry_run,
            travel_rate=settings.travel_rate,
            draw_rate=settings.draw_rate,
            z_down_mm=settings.z_down_mm,
            z_up_mm=settings.z_up_mm,
            z_feed_mm_min=settings.z_feed_mm_min,
        )


def default_gui_settings_path() -> Path:
    return _repo_root() / "runtime" / "gui_settings.json"


def default_scale_config_path() -> Path:
    return _repo_root() / "assets" / "symbols" / "symbol_scales.json"


def default_symbol_root() -> Path:
    return _repo_root() / "assets" / "symbols"


def default_idle_root() -> Path:
    return _repo_root() / "assets" / "generated_idle_symbols"


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
        dry_run = bool(payload.get("dry_run", base.dry_run))
        if run_mode == "test":
            payload["system_mode"] = SystemMode.TEST.value
        elif dry_run:
            payload["system_mode"] = SystemMode.EXHIBITION_DRY.value
        else:
            payload["system_mode"] = SystemMode.EXHIBITION_REAL.value
    merged.update({key: value for key, value in payload.items() if key in merged})
    settings = GuiSettings(**merged)
    settings.apply_system_mode()
    return settings


def save_gui_settings(settings: GuiSettings, path: Path | None = None) -> None:
    settings.apply_system_mode()
    settings_path = path or default_gui_settings_path()
    ensure_parent(settings_path)
    settings_path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


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
        run_mode=settings.run_mode,
        dry_run=settings.dry_run,
        include_rings=settings.include_rings,
        travel_rate=settings.travel_rate,
        draw_rate=settings.draw_rate,
        use_z_servo=plotter_settings.use_z_servo,
        z_down_mm=settings.z_down_mm,
        z_up_mm=settings.z_up_mm,
        z_feed_mm_min=settings.z_feed_mm_min,
        work_zero_command=plotter_settings.work_zero_command,
    ), settings.mode)


def save_oracle_plotter_config(settings: GuiSettings) -> None:
    settings.apply_system_mode()
    store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
    store.save_system_mode(settings.mode)
    store.save_plotter_config(gui_settings_to_plotter_config(settings))


def list_base_symbols(symbol_root: Path | None = None) -> list[Path]:
    root = symbol_root or default_symbol_root()
    return sorted(path for path in root.glob("*.svg") if path.is_file())


def load_symbol_scales(scale_path: Path | None = None, symbol_root: Path | None = None) -> dict[str, float]:
    symbols = list_base_symbols(symbol_root)
    path = scale_path or default_scale_config_path()
    payload: dict[str, Any] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    return {symbol.name: float(payload.get(symbol.name, 1.0)) for symbol in symbols}


def save_symbol_scales(scales: dict[str, float], scale_path: Path | None = None, symbol_root: Path | None = None) -> None:
    symbols = list_base_symbols(symbol_root)
    payload = {symbol.name: float(scales.get(symbol.name, 1.0)) for symbol in symbols}
    path = scale_path or default_scale_config_path()
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def layout_capacity(settings: GuiSettings) -> int:
    return calculate_layout_capacity(
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
    )


def build_preview_svg(
    settings: GuiSettings,
    *,
    user_count: int = 2,
    idle_count: int | None = None,
    highlighted_row_index: int | None = None,
    highlighted_cell_index: int | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> str:
    capacity = layout_capacity(settings)
    if capacity <= 0:
        return _empty_preview_svg(settings, "No printable cells")
    item_count = capacity
    user_count = max(0, min(user_count, item_count))
    idle_count = max(0, item_count - user_count) if idle_count is None else max(0, min(idle_count, item_count - user_count))
    placements = build_sheet_layout(
        user_count + idle_count,
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
    )
    scale = _preview_scale(settings)
    width = settings.sheet_width_mm * scale
    height = settings.sheet_height_mm * scale
    circles: list[str] = []
    symbol_images = _preview_symbol_images(settings, symbol_root=symbol_root, scale_path=scale_path)
    overscale = any(symbol_scale > 1.0 for _, symbol_scale in symbol_images)
    row_lookup = _placement_row_lookup(placements)
    for index, placement in enumerate(placements):
        kind = "user" if index < user_count else "idle"
        row_index = row_lookup.get(placement.index, 0)
        highlighted_row = highlighted_row_index is not None and row_index == highlighted_row_index
        highlighted_cell = highlighted_cell_index is not None and placement.index == highlighted_cell_index
        stroke = "#9a5b24" if kind == "user" else "#1f1a17"
        fill = "#fff0d4" if highlighted_cell else ("#f9f4ea" if kind == "user" else "#f3eadb")
        cx = placement.center_x_mm * scale
        cy = placement.center_y_mm * scale
        cell_radius = placement.diameter_mm * scale / 2.0
        mark_size = symbol_diameter_for_cell(placement.diameter_mm) * scale
        cell_stroke = "#c7472f" if highlighted_cell else ("#c78d2d" if highlighted_row else "#d8c7aa")
        cell_stroke_width = "4.0" if highlighted_cell else ("2.4" if highlighted_row else "1.0")
        circles.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{cell_radius:.2f}" fill="{fill}" '
            f'stroke="{cell_stroke}" stroke-width="{cell_stroke_width}"/>'
        )
        if settings.include_rings:
            circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size / 2.0:.2f}" fill="none" stroke="{stroke}" stroke-width="1.4" data-ring="outer"/>')
            if kind == "idle":
                circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.44:.2f}" fill="none" stroke="{stroke}" stroke-width="0.9" data-ring="inner"/>')
        if symbol_images:
            href, symbol_scale = symbol_images[index % len(symbol_images)]
            image_size = mark_size * max(symbol_scale, 1.0)
            circles.append(
                f'<image href="{href}" x="{cx - image_size / 2.0:.2f}" y="{cy - image_size / 2.0:.2f}" '
                f'width="{image_size:.2f}" height="{image_size:.2f}" preserveAspectRatio="xMidYMid meet"/>'
            )
        else:
            circles.append(
                f'<text x="{cx:.2f}" y="{cy + 4:.2f}" text-anchor="middle" font-size="12" '
                f'fill="{stroke}" font-family="monospace">{index + 1}</text>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<rect x="{settings.sheet_margin_mm * scale:.2f}" y="{settings.sheet_margin_mm * scale:.2f}" '
        f'width="{(settings.sheet_width_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        f'height="{(settings.sheet_height_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        'fill="none" stroke="#d4c3a5" stroke-width="1"/>'
        + (
            '<text x="10" y="18" font-size="11" fill="#9a5b24" font-family="monospace">'
            'overscale may overlap cells</text>'
            if overscale
            else ""
        )
        + "".join(circles)
        + "</svg>"
    )


def build_symbol_preview_svg(
    symbol_path: Path,
    *,
    marker_kind: str,
    scale: float,
    include_rings: bool,
    randomness: float,
) -> str:
    # Preview SVGs are displayed much smaller than the 800px source canvas, so the
    # UI uses amplified jitter to make the Randomness slider visually legible.
    jitter_px = max(0.0, min(randomness, 100.0)) / 100.0 * 80.0
    return build_variant_svg(
        symbol_path,
        marker_kind=marker_kind,
        scale=scale,
        rng=random.Random(1),
        jitter_px=jitter_px,
        include_rings=include_rings,
    )


def _preview_symbol_images(
    settings: GuiSettings,
    *,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[tuple[str, float]]:
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        return []
    scales = load_symbol_scales(scale_path, symbol_root)
    images: list[tuple[str, float]] = []
    for symbol in symbols:
        symbol_scale = scales.get(symbol.name, 1.0) * settings.global_scale
        svg = build_symbol_preview_svg(
            symbol,
            marker_kind="user",
            scale=symbol_scale,
            include_rings=False,
            randomness=effective_randomness(settings),
        )
        encoded = b64encode(svg.encode("utf-8")).decode("ascii")
        images.append((f"data:image/svg+xml;base64,{encoded}", symbol_scale))
    return images


def _placement_row_lookup(placements) -> dict[int, int]:
    rows: dict[float, int] = {}
    lookup: dict[int, int] = {}
    for placement in sorted(placements, key=lambda item: (item.center_y_mm, item.center_x_mm)):
        row_key = next((key for key in rows if abs(key - placement.center_y_mm) < 0.001), None)
        if row_key is None:
            row_key = placement.center_y_mm
            rows[row_key] = len(rows) + 1
        lookup[placement.index] = rows[row_key]
    return lookup


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
            "pending_reload": False,
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
        "pending_reload": state.pending_reload,
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


def read_queue_status(*, force: bool = False, ttl_seconds: float = 10.0) -> dict[str, Any]:
    global _QUEUE_STATUS_CACHE
    now = datetime.now(tz=UTC)
    if not force and _QUEUE_STATUS_CACHE is not None:
        cached_at, cached_payload = _QUEUE_STATUS_CACHE
        if (now - cached_at).total_seconds() < ttl_seconds:
            return cached_payload

    firebase_settings = FirebaseSettings()
    if not firebase_settings.enabled:
        payload = _queue_status_offline("Firebase is not configured")
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload

    try:
        oracle_store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
        baseline = oracle_store.load_run_started_at()
        payload = FirebaseRemoteRepository(firebase_settings).get_plot_job_counts(run_started_at=baseline)
        payload["runStartedAt"] = baseline.isoformat() if baseline else ""
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        payload = _queue_status_offline(str(exc))
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload


def _queue_status_offline(message: str) -> dict[str, Any]:
    return {
        "online": False,
        "total": 0,
        "limitedTo": 0,
        "pending": 0,
        "pendingAfterBaseline": 0,
        "pendingBeforeBaseline": 0,
        "leased": 0,
        "plotting": 0,
        "printed": 0,
        "failed": 0,
        "skipped": 0,
        "hidden": 0,
        "unknown": 0,
        "runStartedAt": "",
        "message": message,
    }


def confirm_plotter_reload(db_path: Path | None = None) -> bool:
    plotter_settings = PlotterSettings()
    store = PlotterStore(db_path or plotter_settings.db_path)
    state = store.load_runtime_state()
    if not state.pending_reload:
        return False
    state.pending_reload = False
    state.status = RuntimeStatus.IDLE
    state.message = "Operator confirmed reload from GUI"
    state.updated_at = datetime.now(tz=UTC)
    store.save_runtime_state(state)
    return True


def check_fluidnc_connection(settings: PlotterSettings | None = None) -> dict[str, Any]:
    resolved_settings = settings or PlotterSettings()
    probe = FluidNCTransport(resolved_settings).probe(timeout_seconds=resolved_settings.fluidnc_connect_timeout_seconds)
    return {
        **probe.to_dict(),
        "online": probe.online,
        "status": "online" if probe.online else "offline",
        "message": probe.message,
        "host": resolved_settings.fluidnc_telnet_host,
        "port": resolved_settings.fluidnc_telnet_port,
    }


def set_plotter_control(
    *,
    print_enabled: bool | None = None,
    run_mode: str | None = None,
    dry_run: bool | None = None,
    db_path: Path | None = None,
) -> PlotterControlState:
    plotter_settings = PlotterSettings()
    store = PlotterStore(db_path or plotter_settings.db_path)
    oracle_store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
    state = oracle_store.load_print_control(store.load_control_state())
    if print_enabled is not None:
        state.print_enabled = print_enabled
        state.operator_paused = not print_enabled
    if run_mode is not None:
        state.run_mode = run_mode
    if dry_run is not None:
        state.dry_run = dry_run
    state.updated_at = datetime.now(tz=UTC)
    store.save_control_state(state)
    oracle_store.save_print_control(state)
    return state


def generate_dry_run_sheet(settings: GuiSettings, *, spool_root: Path | None = None, symbol_root: Path | None = None) -> dict[str, Path]:
    output_root = spool_root or PlotterSettings().spool_root
    ensure_dir(output_root)
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        raise FileNotFoundError("No symbols available for dry-run sheet generation")
    capacity = layout_capacity(settings)
    count = capacity
    placements = build_sheet_layout(
        count,
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
    )
    items = [
        SheetItem(
            source_kind="placeholder",
            session_id=f"gui_dry_run_{index + 1:03d}",
            title=symbols[index % len(symbols)].stem,
            svg_path=symbols[index % len(symbols)],
        )
        for index in range(len(placements))
    ]
    sheet_id = datetime.now(tz=UTC).strftime("gui_sheet_%Y%m%d_%H%M%S")
    gcode = generate_sheet_gcode(
        items,
        placements,
        sample_step_mm=PlotterSettings().sample_step_mm,
        cell_diameter_mm=settings.cell_diameter_mm,
        travel_rate=PlotterSettings().travel_rate,
        draw_rate=PlotterSettings().draw_rate,
        pen_up_command=PlotterSettings().pen_up_command,
        pen_down_command=PlotterSettings().pen_down_command,
        include_rings=settings.include_rings,
        use_z_servo=PlotterSettings().use_z_servo,
        z_down_mm=PlotterSettings().z_down_mm,
        z_up_mm=PlotterSettings().z_up_mm,
        z_feed_mm_min=PlotterSettings().z_feed_mm_min,
    )
    gcode_path = output_root / f"{sheet_id}.gcode"
    manifest_path = output_root / f"{sheet_id}.json"
    gcode_path.write_text(gcode, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "sheet_id": sheet_id,
                "generated_by": "neje-gui",
                "layout_mode": settings.layout_mode,
                "cell_diameter_mm": settings.cell_diameter_mm,
                "gap_mm": settings.gap_mm,
                "symbol_fit_ratio": SYMBOL_FIT_RATIO,
                "items": [
                    {
                        "session_id": item.session_id,
                        "source_kind": item.source_kind,
                        "svg_path": str(item.svg_path),
                        "sheet_index": index,
                        "center_x_mm": placements[index].center_x_mm,
                        "center_y_mm": placements[index].center_y_mm,
                        "cell_diameter_mm": placements[index].diameter_mm,
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


def _preview_scale(settings: GuiSettings) -> float:
    longest = max(settings.sheet_width_mm, settings.sheet_height_mm, 1.0)
    return min(900.0 / longest, 1.2)


def _empty_preview_svg(settings: GuiSettings, message: str) -> str:
    scale = _preview_scale(settings)
    width = max(settings.sheet_width_mm * scale, 300)
    height = max(settings.sheet_height_mm * scale, 200)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<text x="{width / 2:.2f}" y="{height / 2:.2f}" text-anchor="middle" '
        f'font-size="18" fill="#8f4f2b">{message}</text></svg>'
    )
