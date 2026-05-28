from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from nicegui import run, ui

from .modes import mode_policy
from .workspaces.connection import build_connection_notes, build_connection_workspace
from .workspaces.calibration import (
    build_calibration_motion_workspace,
    build_calibration_workspace,
)
from .workspaces.tests import build_tests_notes, build_tests_workspace
from .workspaces.work import build_work_status_workspace, build_work_workspace
from .workspaces.exhibition import (
    build_exhibition_status_workspace,
    build_exhibition_workspace,
)
from .ui import update_status_pill, warning_banner
from ...shared.models import ComponentStatus, SystemCheckLevel, SystemMode
from .support import (
    GUI_DEFAULTS,
    build_preview_svg,
    build_realtime_preview_svg,
    compute_effective_sample_step,
    effective_randomness,
    generate_dry_run_sheet,
    gui_settings_to_plotter_config,
    layout_capacity,
    list_base_symbols,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
    read_queue_status,
    read_upload_event_payload,
    save_gui_settings,
    save_oracle_plotter_config,
    save_symbol_scales,
)
from ...shared.logging import read_logs
from ...shared.origin_markers import ALL_ORIGINS, ORIGIN_LABELS, ORIGIN_MARKER_POSITIONS, ORIGIN_PREVIEW_COLORS
from ...app.supervisor import SupervisorService


def build_page() -> None:
    settings = load_gui_settings()
    scales = load_symbol_scales()
    symbols = list_base_symbols()

    fields: dict[str, Any] = {}
    plotter_labels: dict[str, Any] = {}
    queue_labels: dict[str, Any] = {}
    thermal_printer_labels: dict[str, Any] = {}
    fluidnc_labels: dict[str, Any] = {}
    gcode_labels: dict[str, Any] = {}
    ready_labels: dict[str, Any] = {}
    live_labels: dict[str, Any] = {}
    node_pills: dict[str, Any] = {}
    uploaded_svg: dict[str, Any] = {"name": "", "bytes": b""}
    supervisor = SupervisorService()
    valid_workspaces = {"connection", "calibration", "tests", "work", "exhibition"}
    saved_workspace = str(supervisor.runtime_store.load_json("gui_workspace", {"tab": "connection"}).get("tab", "connection"))
    active_workspace = {"value": saved_workspace if saved_workspace in valid_workspaces else "connection"}
    saved_preview_mode = str(supervisor.runtime_store.load_json("gui_preview_mode", {"mode": "preview"}).get("mode", "preview"))
    preview_mode = {"value": saved_preview_mode if saved_preview_mode in {"preview", "printing"} else "preview"}
    repo_root = Path(__file__).resolve().parents[4]
    printer_connect_script = repo_root / "ESP32-BTN_Printer" / "tools" / "printer_connect.py"

    ui.colors(primary="#1f1a17", secondary="#9a5b24", accent="#c7a45a")
    ui.add_head_html(
        """
        <style>
          body { background: #f7f1e7; color: #1f1a17; overflow: auto; }
          .q-field__control { min-height: 40px !important; }
          .q-field__label { font-size: 12px; }
          .oracle-shell { min-height: 100vh; overflow: visible; }
          .oracle-card {
            background: rgba(255, 252, 245, 0.94);
            border: 1px solid #dac9ad;
            border-radius: 14px;
            box-shadow: 0 8px 22px rgba(31, 26, 23, 0.07);
          }
          .oracle-title { letter-spacing: 0.16em; color: #8f4f2b; }
          .compact-card { padding: 10px 12px !important; }
          .live-strip {
            display: grid;
            grid-template-columns: repeat(6, minmax(110px, 1fr));
            gap: 6px;
            align-items: stretch;
          }
          .live-strip .mini-metric {
            background: rgba(255, 252, 245, 0.9);
          }
          .live-strip .next-action {
            border-color: #9a5b24;
            background: #fff6df;
          }
          .mobile-operator-warning {
            display: none;
            background: #fff4df;
            border: 1px solid #c99743;
            border-radius: 10px;
            color: #8f4f2b;
            padding: 8px 10px;
            font-size: 12px;
            font-weight: 700;
          }
          .workspace-tabs {
            background: rgba(255, 252, 245, 0.84);
            border: 1px solid #dac9ad;
            border-radius: 14px;
            min-height: 44px;
            flex: 1 1 auto;
          }
          .workspace-tabs .q-tab {
            min-height: 42px;
            padding: 0 12px;
            letter-spacing: 0.08em;
            font-weight: 700;
          }
          .workspace-tabs .q-tab--active { color: #8f4f2b; }
          .workspace-panel { min-height: calc(100vh - 104px); }
          .workspace-scroll {
            max-height: calc(100vh - 120px);
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 8px;
            box-sizing: border-box;
          }
          .preview-frame {
            max-height: calc(100vh - 210px);
            overflow: auto;
            width: 100%;
          }
          .preview-frame svg {
            display: block;
            width: auto;
            height: auto;
            max-width: none;
            max-height: none;
          }
          .symbol-preview svg { width: 58px; height: 58px; }
          .path-label { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .tight-slider .q-slider { min-height: 28px; }
          .status-pill { border: 1px solid #dac9ad; border-radius: 999px; padding: 3px 8px; font-size: 11px; white-space: nowrap; }
          .mode-badge { border: 1px solid #9a5b24; border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 700; color: #8f4f2b; }
          .warning-banner { background: #fff4df; border: 1px solid #c99743; border-radius: 10px; color: #8f4f2b; padding: 6px 8px; font-size: 12px; }
          .log-viewer textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.35; }
          .q-btn { min-height: 30px; }
          .mini-metric { border: 1px solid #e1d3ba; border-radius: 10px; padding: 5px 7px; background: rgba(255,255,255,0.45); }
          .mini-metric .label { font-size: 9px; letter-spacing: 0.16em; color: #8f4f2b; text-transform: uppercase; }
          .mini-metric .value { font-size: 12px; font-weight: 700; color: #1f1a17; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .jog-pad .q-btn { width: 54px; }
          .preview-legend { border-top: 1px solid #e1d3ba; padding-top: 6px; }
          .legend-chip { display: flex; align-items: center; gap: 5px; font-size: 10px; color: #1f1a17; white-space: nowrap; }
          .legend-dot { width: 9px; height: 9px; border-radius: 999px; border: 1px solid #1f1a17; display: inline-block; flex: 0 0 auto; }
          .legend-ring { width: 15px; height: 15px; border-radius: 999px; border: 1.5px solid #1f1a17; display: inline-block; flex: 0 0 auto; }
          .legend-double-ring { box-shadow: inset 0 0 0 3px #fbf7ef, inset 0 0 0 4.4px #1f1a17; }
          @media (min-width: 1200px) {
            body { overflow: hidden; }
            .oracle-shell { height: 100vh; max-height: 100vh; overflow: hidden; }
            .workspace-panel { height: calc(100vh - 104px); overflow: hidden; }
          }
          @media (max-width: 1199px) {
            .workspace-grid { grid-template-columns: 1fr !important; height: auto !important; overflow: visible !important; }
            .workspace-scroll { max-height: none; overflow: visible; padding-right: 0; }
            .preview-frame { max-height: 70vh; }
            .path-label { max-width: 100%; white-space: normal; }
            .live-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }
          @media (max-width: 760px) {
            .oracle-shell { min-width: 560px; }
            .mobile-operator-warning { display: block; }
            .workspace-tabs { overflow-x: auto; }
          }
        </style>
        """
    )

    def pull_settings_from_fields() -> None:
        settings.apply_system_mode()
        settings.layout_mode = str(fields["layout_mode"].value)
        settings.cell_diameter_mm = float(fields["cell_diameter_mm"].value or 1)
        settings.gap_mm = float(fields["gap_mm"].value or 0)
        settings.organic_enabled = bool(fields["organic_enabled"].value)
        settings.organic_cell_size_mm = float(fields["organic_cell_size_mm"].value or 0)
        settings.organic_rotation_ramp = float(fields["organic_rotation_ramp"].value or 0)
        settings.organic_scale_ramp = float(fields["organic_scale_ramp"].value or 0)
        settings.organic_seed = int(float(fields["organic_seed"].value or cast(float, GUI_DEFAULTS["organic_seed"])))
        settings.randomness = float(fields["randomness"].value or 0)
        settings.randomness_fine = float(fields["randomness_fine"].value or 0)
        settings.include_rings = bool(fields["include_rings"].value)
        settings.include_markers = bool(fields["include_markers"].value)
        settings.marker_diameter_mm = float(fields["marker_diameter_mm"].value or 1.5)
        settings.sample_step_mm = float(fields["sample_step_mm"].value or cast(float, GUI_DEFAULTS["sample_step_mm"]))
        settings.sample_density_exponent = float(fields["sample_density_exponent"].value or cast(float, GUI_DEFAULTS["sample_density_exponent"]))
        settings.sample_min_step_mm = float(fields["sample_min_step_mm"].value or cast(float, GUI_DEFAULTS["sample_min_step_mm"]))
        settings.sample_max_step_mm = float(fields["sample_max_step_mm"].value or cast(float, GUI_DEFAULTS["sample_max_step_mm"]))
        settings.streaming_mode = str(fields["streaming_mode"].value or GUI_DEFAULTS["streaming_mode"])
        settings.show_origins = [
            origin for origin in ALL_ORIGINS if bool(fields.get(f"show_origin:{origin}") and fields[f"show_origin:{origin}"].value)
        ] or list(ALL_ORIGINS)
        settings.print_origins = [
            origin for origin in ALL_ORIGINS if bool(fields.get(f"print_origin:{origin}") and fields[f"print_origin:{origin}"].value)
        ] or list(ALL_ORIGINS)
        settings.sheet_width_mm = float(fields["sheet_width_mm"].value or 1)
        settings.sheet_height_mm = float(fields["sheet_height_mm"].value or 1)
        settings.sheet_margin_mm = float(fields["sheet_margin_mm"].value or 0)
        settings.global_scale = float(fields["global_scale"].value or 1)
        settings.travel_rate = float(fields["travel_rate"].value or 1)
        settings.draw_rate = float(fields["draw_rate"].value or 1)
        settings.xy_acceleration_mm_s2 = float(fields["xy_acceleration_mm_s2"].value or 0)
        settings.z_down_mm = float(fields["z_down_mm"].value or 0)
        settings.z_up_mm = float(fields["z_up_mm"].value or 0)
        settings.z_feed_mm_min = float(fields["z_feed_mm_min"].value or 1)
        settings.direct_svg_origin_x_mm = float(fields["direct_svg_origin_x_mm"].value or 0)
        settings.direct_svg_origin_y_mm = float(fields["direct_svg_origin_y_mm"].value or 0)

    def persist_and_refresh() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        update_preview()
        capacity_label.set_text(f"{layout_capacity(settings)} cells")
        update_gcode_detail_labels()
        start_print_button.enable()
        refresh_status()
        refresh_component_status()

    def update_gcode_detail_labels() -> None:
        if not gcode_labels:
            return
        effective_step = compute_effective_sample_step(
            sample_step_mm=settings.sample_step_mm,
            cell_diameter_mm=settings.cell_diameter_mm,
            sample_reference_cell_mm=settings.sample_reference_cell_mm,
            sample_density_exponent=settings.sample_density_exponent,
            sample_min_step_mm=settings.sample_min_step_mm,
            sample_max_step_mm=settings.sample_max_step_mm,
        )
        points_per_100mm = 100.0 / max(effective_step, 0.001)
        if effective_step <= 0.25:
            load = "VERY FINE"
        elif effective_step <= 0.75:
            load = "FINE"
        elif effective_step <= 1.5:
            load = "NORMAL"
        else:
            load = "LIGHT"
        gcode_labels["effective"].set_text(f"{effective_step:.2f} mm")
        gcode_labels["points"].set_text(f"{points_per_100mm:.0f} pts / 100 mm")
        gcode_labels["load"].set_text(load)
        gcode_labels["limits"].set_text(f"{settings.sample_min_step_mm:g} to {settings.sample_max_step_mm:g} mm")

    def update_scales_from_fields() -> None:
        pull_settings_from_fields()
        for symbol in symbols:
            scales[symbol.name] = float(fields[f"scale:{symbol.name}"].value or 1.0)
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        save_symbol_scales(scales)
        update_preview()

    async def handle_svg_upload(event: Any) -> None:
        try:
            name, data = await read_upload_event_payload(event)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"SVG upload failed: {exc}", color="negative")
            return
        if not data:
            ui.notify("SVG upload failed: uploaded file is empty", color="negative")
            return
        uploaded_svg["name"] = name
        uploaded_svg["bytes"] = data
        uploaded_svg_label.set_text(f"Selected: {name}")
        ui.notify(f"Selected SVG: {name}", color="positive")

    async def print_uploaded_svg() -> None:
        if not uploaded_svg["bytes"]:
            ui.notify("Choose an SVG file first", color="warning")
            return
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        ui.notify("Printing SVG...", color="info")
        state = await run.io_bound(
            supervisor.print_uploaded_svg,
            settings,
            svg_bytes=uploaded_svg["bytes"],
            original_name=str(uploaded_svg["name"] or "uploaded.svg"),
        )
        if state.status == ComponentStatus.STOPPED:
            uploaded_svg["bytes"] = b""
            uploaded_svg["name"] = ""
            uploaded_svg_label.set_text("No SVG selected")
            ui.notify(state.message, color="positive")
        else:
            ui.notify(state.last_error or state.message, color="negative" if state.status == ComponentStatus.ERROR else "warning")
        refresh_status()
        refresh_logs()

    async def generate_dry_run() -> None:
        pull_settings_from_fields()
        try:
            output = await run.io_bound(generate_dry_run_sheet, settings)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"G-code generation failed: {exc}", color="negative")
            return
        ui.notify(f"G-code file: {output['gcode']}", color="positive")
        refresh_status()

    def update_preview(status: dict[str, Any] | None = None, queue: dict[str, Any] | None = None) -> None:
        if preview_mode["value"] == "printing":
            status = status if status is not None else read_plotter_status()
            queue = queue if queue is not None else read_queue_status(ttl_seconds=30.0)
            preview.content = build_realtime_preview_svg(settings, status, queue)
        else:
            preview.content = build_preview_svg(
                settings,
                user_count=layout_capacity(settings),
                idle_count=0,
                randomize_symbols=True,
            )
        preview.update()

    def refresh_status() -> None:
        status = read_plotter_status()
        queue = read_queue_status(ttl_seconds=30.0)
        total = int(status.get("processed_symbols", 0) or 0)
        pending_users = int(queue.get("pendingUserAfterBaseline", queue.get("pendingAfterBaseline", 0)) or 0)
        progress_percent = float(status.get("sheet_progress_percent", status.get("gcode_progress_percent", 0.0)) or 0.0)
        current_row = int(status.get("current_row_index", 0) or 0)
        current_cell_in_row = int(status.get("current_cell_in_row", 0) or 0)
        row_cell_count = int(status.get("row_cell_count", 0) or 0)
        update_preview(status, queue)
        progress.value = min(max(progress_percent / 100.0, 0.0), 1.0)
        print_enabled = bool(status.get("print_enabled"))
        dry_run = bool(status.get("dry_run"))
        run_mode = str(status.get("run_mode", "-") or "-")
        status_text = str(status.get("status", "-") or "-").replace("_", " ")
        transport_text = "G-CODE ONLY" if dry_run else "FLUIDNC MOTION"
        print_text = "READY" if print_enabled else "STOPPED"
        plotter_labels["state"].set_text(f"{status_text.upper()} · {print_text}")
        plotter_labels["mode"].set_text(f"{run_mode.upper()} · {transport_text}")
        plotter_labels["sheet"].set_text(str(status.get("current_sheet_id") or "no sheet yet"))
        plotter_labels["cells"].set_text(
            f"{total}/{layout_capacity(settings)} cells · "
            f"user {status.get('user_count', 0)} · idle {status.get('idle_count', 0)}"
        )
        plotter_labels["progress"].set_text(
            f"{progress_percent:.0f}% · row {current_row}/{status.get('row_count', 0)} · "
            f"cell {current_cell_in_row}/{row_cell_count} · "
            f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} lines"
        )
        plotter_labels["message"].set_text(str(status.get("message", "-") or "-"))
        if queue_labels:
            active = int(queue.get("leased", 0) or 0) + int(queue.get("plotting", 0) or 0)
            queue_labels["state"].set_text("ONLINE" if queue.get("online") else "OFFLINE")
            queue_labels["pending"].set_text(str(pending_users))
            queue_labels["active"].set_text(str(active))
            queue_labels["failed"].set_text(f"{queue.get('failed', 0)} / {queue.get('skipped', 0)}")
            queue_labels["message"].set_text(str(queue.get("message", "-") or "-"))
        readiness = supervisor.runtime_store.load_plotter_readiness()
        queue_online = bool(queue.get("online"))
        current_sheet = str(status.get("current_sheet_id") or "no sheet yet")
        blockers: list[str] = []
        if not readiness.work_zero_set:
            blockers.append("work zero")
        if not queue_online:
            blockers.append("queue")
        if "idle" not in status_text.lower() and "paused" not in status_text.lower():
            blockers.append("FluidNC")
        if not print_enabled:
            blockers.append("print paused")
        if live_labels:
            live_labels["fluidnc"].set_text(status_text.upper())
            live_labels["zero"].set_text("SET" if readiness.work_zero_set else "NOT SET")
            live_labels["firebase"].set_text("REQUIRED" if mode_policy(settings.mode).firebase_required else "TEST BYPASS")
            live_labels["queue"].set_text("ONLINE" if queue_online else "OFFLINE")
            live_labels["sheet"].set_text(current_sheet)
            if not readiness.work_zero_set:
                next_action = "Set work zero"
            elif not print_enabled:
                next_action = "Start print"
            elif pending_users:
                next_action = "Print queued sessions"
            else:
                next_action = "Watch next sheet"
            live_labels["next"].set_text(next_action)
            live_labels["blockers"].set_text(" · ".join(blockers) if blockers else "none")
        if ready_labels:
            ready_labels["zero"].set_text("SET" if readiness.work_zero_set else "NOT SET")
            ready_labels["message"].set_text(readiness.message)
        if preview_mode["value"] == "printing":
            preview_progress_label.set_text(
                f"{status.get('status', '-')} | {progress_percent:.1f}% | "
                f"pending real {pending_users} | "
                f"row {current_row}/{status.get('row_count', 0)} | cell {current_cell_in_row}/{row_cell_count} | "
                f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} G-code lines | "
                f"{total}/{layout_capacity(settings)} cells in last sheet"
            )
        else:
            preview_progress_label.set_text(f"preview tuning | random symbols | {layout_capacity(settings)} cells")
        refresh_component_status()

    def refresh_component_status() -> None:
        states = supervisor.refresh_all_status()
        if live_labels:
            firebase_state = states.get("firebase")
            if firebase_state is not None:
                live_labels["firebase"].set_text(firebase_state.status.value.upper())
        if node_pills:
            update_status_pill(node_pills["fluidnc"], states.get("fluidnc"), "Plotter")
            update_status_pill(node_pills["macmini"], states.get("macmini_uploader"), "Mac mini")
            update_status_pill(node_pills["firebase"], states.get("firebase"), "Firebase")
            update_status_pill(node_pills["queue"], states.get("queue"), "Queue")
            update_status_pill(node_pills["print"], states.get("print"), "Print")

    async def start_system() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        await run.io_bound(supervisor.start_system, gui_settings_to_plotter_config(settings))
        ui.notify("System supervisor started in safe mode", color="positive")
        refresh_status()

    async def stop_system() -> None:
        await run.io_bound(supervisor.stop_system)
        ui.notify("System stopped safely", color="warning")
        refresh_status()

    async def reset_baseline() -> None:
        state = await run.io_bound(supervisor.reset_run_baseline)
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        refresh_status()

    def set_system_mode(mode: SystemMode, *, notify: bool = True) -> None:
        settings.system_mode = mode.value
        settings.apply_system_mode()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        supervisor.set_system_mode(settings.mode)
        if notify:
            ui.notify(f"Mode set to {mode_policy(settings.mode).label}.", color="warning")
        refresh_status()

    def workspace_changed(value: Any) -> None:
        workspace = _workspace_name(value)
        if workspace in valid_workspaces:
            active_workspace["value"] = workspace
            supervisor.runtime_store.save_json("gui_workspace", {"tab": workspace})
        if workspace == "tests":
            if settings.mode != SystemMode.TEST:
                set_system_mode(SystemMode.TEST, notify=False)
            return
        if settings.mode == SystemMode.TEST:
            set_system_mode(SystemMode.EXHIBITION, notify=False)

    def preview_mode_changed(value: Any) -> None:
        mode = str(value or "preview")
        preview_mode["value"] = mode if mode in {"preview", "printing"} else "preview"
        supervisor.runtime_store.save_json("gui_preview_mode", {"mode": preview_mode["value"]})
        update_preview()

    def restore_workspace() -> None:
        workspace_tabs.value = active_workspace["value"]
        workspace_tabs.update()

    async def run_system_check(*, notify_success: bool = False) -> bool:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        result = await run.io_bound(supervisor.run_system_check, settings)
        refresh_system_check_result()
        refresh_component_status()
        refresh_logs()
        if result.has_critical:
            first_critical = next((check for check in result.checks if check.level == SystemCheckLevel.CRITICAL), None)
            message = first_critical.message if first_critical is not None else "System is not ready"
            ui.notify(f"Cannot start: {message}", color="negative")
            return False
        if notify_success:
            ui.notify("System check passed", color="positive" if result.status == SystemCheckLevel.OK else "warning")
        return True

    def refresh_system_check_result() -> None:
        result = supervisor.runtime_store.load_system_check_result()
        if not result:
            system_check_label.set_text("System check: not run")
            return
        critical = sum(1 for check in result.checks if check.level == SystemCheckLevel.CRITICAL)
        warnings = sum(1 for check in result.checks if check.level == SystemCheckLevel.WARNING)
        ok_count = sum(1 for check in result.checks if check.level == SystemCheckLevel.OK)
        system_check_label.set_text(f"System check: {critical} blocked · {warnings} warnings · {ok_count} ok")

    async def start_print() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        ui.notify("Checking plotter before START PRINT...", color="info")
        if not await run_system_check():
            refresh_status()
            return
        plotter_state = await run.io_bound(supervisor.start_plotter, gui_settings_to_plotter_config(settings))
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start: {plotter_state.last_error or plotter_state.message}", color="negative")
            refresh_status()
            refresh_logs()
            return
        state = await run.io_bound(supervisor.start_print, settings)
        color = "positive" if state.status == ComponentStatus.RUNNING else "warning"
        ui.notify(state.message, color=color)
        refresh_status()

    async def start_test_print() -> None:
        set_system_mode(SystemMode.TEST, notify=False)
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        ui.notify("Checking FluidNC before TEST PRINT...", color="info")
        probe = await run.io_bound(supervisor.probe_fluidnc, scan=False)
        update_fluidnc_labels({**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port})
        supervisor.check_fluidnc(probe)
        if not (probe.online and probe.controller.is_idle):
            ui.notify("FluidNC must be connected and Idle before START TEST PRINT.", color="warning")
            refresh_status()
            refresh_logs()
            return
        if not await run_system_check():
            return
        plotter_state = await run.io_bound(supervisor.start_plotter, gui_settings_to_plotter_config(settings))
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start test print: {plotter_state.last_error or plotter_state.message}", color="negative")
            refresh_status()
            refresh_logs()
            return
        state = await run.io_bound(supervisor.start_print, settings)
        color = "positive" if state.status == ComponentStatus.RUNNING else "warning"
        ui.notify(f"TEST PRINT: {state.message}", color=color)
        refresh_status()
        refresh_logs()

    def set_work_zero() -> None:
        confirm_action(
            "SET WORK ZERO",
            "Current XY becomes G54 X0 Y0. Z is not zeroed; Z moves use absolute configured values. Use after placing the tool at the upper-left origin.",
            lambda: fluidnc_action("set work zero", supervisor.set_work_zero),
        )

    async def check_fluidnc(*, scan: bool = False) -> None:
        ui.notify("Checking FluidNC...", color="info")
        try:
            probe = await run.io_bound(supervisor.probe_fluidnc, scan=scan)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"FluidNC check failed: {exc}", color="negative")
            refresh_logs()
            restore_workspace()
            return
        supervisor.check_fluidnc(probe)
        result = {**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port}
        color = "positive" if probe.online else "negative"
        update_fluidnc_labels(result)
        ui.notify(probe.message, color=color)
        refresh_logs()
        restore_workspace()

    async def scan_fluidnc() -> None:
        await check_fluidnc(scan=True)

    def update_fluidnc_labels(result: dict[str, Any]) -> None:
        if "webui" in fluidnc_labels:
            fluidnc_labels["webui"].set_text("online" if result.get("http_online") else "offline")
        if "telnet" in fluidnc_labels:
            fluidnc_labels["telnet"].set_text("online" if result.get("telnet_online") else "offline")
        if "state" in fluidnc_labels:
            fluidnc_labels["state"].set_text(str(result.get("controller_state") or "Unknown"))
        if "mpos" in fluidnc_labels:
            fluidnc_labels["mpos"].set_text(_format_gui_tuple(result.get("machine_position")))
        if "pins" in fluidnc_labels:
            fluidnc_labels["pins"].set_text(str(result.get("pins") or "none"))
        if "modal" in fluidnc_labels:
            fluidnc_labels["modal"].set_text(str(result.get("modal_state") or "-").replace("\n", " | "))
        if "target" in fluidnc_labels:
            fluidnc_labels["target"].set_text(f"{result.get('http_url') or '-'} · {result.get('host')}:{result.get('port')}")
        if "message" in fluidnc_labels:
            fluidnc_labels["message"].set_text(str(result.get("message") or result.get("last_error") or "-"))

    def confirm_action(title: str, message: str, action: Any) -> None:
        with ui.dialog() as dialog, ui.card().classes("oracle-card"):
            ui.label(title).classes("text-sm font-bold")
            ui.label(message).classes("text-xs text-[#8f4f2b]")

            async def confirmed() -> None:
                dialog.close()
                try:
                    result = action()
                    if hasattr(result, "__await__"):
                        await result
                except Exception as exc:  # noqa: BLE001
                    ui.notify(f"{title} failed: {exc}", color="negative")
                    refresh_status()
                    refresh_logs()

            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("dense flat")
                ui.button("Confirm", on_click=confirmed).props("dense color=warning")
        dialog.open()

    async def fluidnc_action(label: str, action: Any, *, refresh_probe: bool = True) -> None:
        ui.notify(f"Sending {label}...", color="info")
        try:
            state = await run.io_bound(action)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"{label} failed: {exc}", color="negative")
            refresh_status()
            refresh_logs()
            restore_workspace()
            return
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        if refresh_probe:
            await check_fluidnc(scan=False)
        refresh_status()
        refresh_logs()
        restore_workspace()

    def home_xy() -> None:
        confirm_action("HOME ALL", "The plotter will run FluidNC homing command $H. Use this when FluidNC rejects single-axis homing.", lambda: fluidnc_action("home all", supervisor.home_xy_fluidnc, refresh_probe=False))

    def home_axis(axis: str) -> None:
        confirm_action(f"HOME {axis}", f"Single-axis homing sends $H={axis}. Use only if this FluidNC config supports it.", lambda: fluidnc_action(f"home {axis}", lambda: supervisor.home_fluidnc(axis), refresh_probe=False))

    async def jog(axis: str, sign: float) -> None:
        distance = sign * float(fields["jog_step"].value or 1)
        feed = float(fields["jog_feed"].value or 1000)
        await fluidnc_action(f"jog {axis}", lambda: supervisor.jog_fluidnc(axis, distance, feed), refresh_probe=False)

    async def jog_x_negative() -> None:
        await jog("X", -1)

    async def jog_x_positive() -> None:
        await jog("X", 1)

    async def jog_y_negative() -> None:
        await jog("Y", -1)

    async def jog_y_positive() -> None:
        await jog("Y", 1)

    async def pen_up() -> None:
        await fluidnc_action("pen up", supervisor.pen_up_fluidnc, refresh_probe=False)

    async def pen_down() -> None:
        await fluidnc_action("pen down", supervisor.pen_down_fluidnc, refresh_probe=False)

    def unlock_alarm() -> None:
        confirm_action("UNLOCK ALARM", "This sends $X. It clears FluidNC alarm state without moving the machine.", lambda: fluidnc_action("unlock", supervisor.unlock_fluidnc_alarm))

    async def emergency_stop() -> None:
        state = await run.io_bound(supervisor.emergency_stop_fluidnc)
        ui.notify(state.message, color="negative")
        refresh_status()
        refresh_logs()

    def resume_after_hold() -> None:
        confirm_action("RESUME AFTER HOLD", "This sends realtime cycle start ~. Confirm only if the machine is safe to resume.", lambda: fluidnc_action("resume", supervisor.resume_fluidnc))

    def soft_reset() -> None:
        confirm_action("SOFT RESET / ABORT", "This sends Ctrl-X and disables print. Use only to abort/reset FluidNC.", lambda: fluidnc_action("soft reset", supervisor.soft_reset_fluidnc))

    async def start_macmini() -> None:
        await run.io_bound(supervisor.start_macmini_uploader)
        refresh_component_status()

    async def stop_macmini() -> None:
        await run.io_bound(supervisor.stop_macmini_uploader)
        refresh_component_status()

    async def restart_macmini() -> None:
        await run.io_bound(supervisor.restart_macmini_uploader)
        refresh_component_status()

    async def scan_macmini() -> None:
        await run.io_bound(supervisor.scan_macmini_once)
        refresh_component_status()

    def latest_receipt_session_dir() -> Path | None:
        session_root = repo_root / "assets" / "sessions"
        candidates = [
            path
            for path in session_root.iterdir()
            if path.is_dir() and any(path.glob("*_receipt.txt"))
        ] if session_root.exists() else []
        return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None

    def run_thermal_printer_command(args: list[str], *, timeout: float = 90.0) -> tuple[bool, str]:
        command = [sys.executable, str(printer_connect_script), *args]
        try:
            result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, timeout=timeout, check=False)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        output = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode == 0, output

    def printer_url_args() -> list[str]:
        url = str(fields["thermal_printer_url"].value or "").strip()
        supervisor.runtime_store.save_json("thermal_printer", {"url": url})
        return ["--esp32", url] if url else []

    def update_thermal_printer_label(message: str) -> None:
        if thermal_printer_labels:
            thermal_printer_labels["message"].set_text(message[:220] or "-")

    async def thermal_printer_status() -> None:
        ok, output = await run.io_bound(run_thermal_printer_command, ["status", *printer_url_args()], timeout=20.0)
        update_thermal_printer_label(output)
        ui.notify("Thermal printer status updated" if ok else "Thermal printer offline", color="positive" if ok else "warning")

    async def thermal_printer_connect() -> None:
        ok, output = await run.io_bound(run_thermal_printer_command, ["connect", *printer_url_args()], timeout=45.0)
        update_thermal_printer_label(output)
        ui.notify("Thermal printer connected" if ok else "Thermal printer connection failed", color="positive" if ok else "warning")

    async def thermal_printer_test_receipt() -> None:
        ok, output = await run.io_bound(run_thermal_printer_command, ["test", "--message", "ORACLE THERMAL TEST", *printer_url_args()], timeout=60.0)
        update_thermal_printer_label(output)
        ui.notify("Thermal test sent" if ok else "Thermal test failed", color="positive" if ok else "warning")

    async def thermal_printer_print_session(session_dir: Path | None) -> None:
        if session_dir is None or not session_dir.exists():
            ui.notify("No receipt session folder found", color="warning")
            return
        preview_path = repo_root / "reports" / f"{session_dir.name}_thermal_preview.png"
        args = [
            "receipt",
            str(session_dir),
            "--preview-png",
            str(preview_path),
            *printer_url_args(),
        ]
        ok, output = await run.io_bound(run_thermal_printer_command, args, timeout=120.0)
        update_thermal_printer_label(output)
        ui.notify(f"Thermal receipt sent: {session_dir.name}" if ok else "Thermal receipt failed", color="positive" if ok else "warning")

    async def thermal_printer_print_latest() -> None:
        await thermal_printer_print_session(latest_receipt_session_dir())

    async def thermal_printer_print_selected() -> None:
        raw = str(fields["thermal_session_dir"].value or "").strip()
        await thermal_printer_print_session(Path(raw).expanduser() if raw else latest_receipt_session_dir())

    def refresh_logs() -> None:
        selected = str(fields["log_filter"].value or "all") if "log_filter" in fields else "all"
        log_lines = read_logs(category_filter=selected, limit=100)
        logs_view.value = "\n".join(log_lines)
        logs_view.update()

    def preview_legend() -> None:
        with ui.column().classes("preview-legend w-full gap-1"):
            with ui.row().classes("items-center gap-3 flex-wrap"):
                with ui.element("div").classes("legend-chip"):
                    ui.element("span").classes("legend-ring")
                    ui.label("outer ring: real/user cell").classes("text-[10px]")
                with ui.element("div").classes("legend-chip"):
                    ui.element("span").classes("legend-ring legend-double-ring")
                    ui.label("double ring: filler/local cell").classes("text-[10px]")
                with ui.element("div").classes("legend-chip"):
                    ui.element("span").classes("legend-dot").style("background:#8f8980; border-color:#8f8980; opacity:0.45;")
                    ui.label("gray: next in line").classes("text-[10px]")
            with ui.row().classes("items-center gap-3 flex-wrap"):
                for origin in ALL_ORIGINS:
                    position = ORIGIN_MARKER_POSITIONS.get(origin, "right").replace("-", " ")
                    color = ORIGIN_PREVIEW_COLORS.get(origin, "#77706a")
                    with ui.element("div").classes("legend-chip"):
                        ui.element("span").classes("legend-dot").style(f"background:{color}; border-color:{color};")
                        ui.label(f"{ORIGIN_LABELS[origin]} dot: {position}").classes("text-[10px]")

    def live_metric(key: str, label: str, *, important: bool = False) -> None:
        with ui.element("div").classes("mini-metric next-action" if important else "mini-metric"):
            ui.label(label).classes("label")
            live_labels[key] = ui.label("-").classes("value")

    def open_logs() -> None:
        subprocess.run(["open", str(supervisor.settings.logs_root)], check=False)

    with ui.column().classes("oracle-shell w-full gap-2 p-3"):
        with ui.row().classes("w-full items-center gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.label("THE ORACLE OPERATOR").classes("oracle-title text-lg")
            with ui.tabs(on_change=lambda event: workspace_changed(event.value)).classes("workspace-tabs") as workspace_tabs:
                connection_tab = ui.tab("connection", label="1 CONNECTION")
                calibration_tab = ui.tab("calibration", label="2 CALIBRATION")
                tests_tab = ui.tab("tests", label="3 TESTS")
                work_tab = ui.tab("work", label="4 WORK")
                exhibition_tab = ui.tab("exhibition", label="5 EXHIBITION")
            workspace_tabs.value = active_workspace["value"]
            with ui.row().classes("items-center gap-2"):
                ui.button("EMERGENCY STOP", on_click=emergency_stop).props("dense color=negative")

        real_warning = warning_banner("Plotter output starts only after system checks pass, work zero is set, and FluidNC is Idle.")
        ui.label("Operator GUI is designed for MacBook/tablet width. Use the MacBook operator station for exhibition control.").classes("mobile-operator-warning")
        with ui.element("div").classes("live-strip w-full"):
            live_metric("fluidnc", "Now")
            live_metric("zero", "Work zero")
            live_metric("firebase", "Firebase")
            live_metric("queue", "Queue")
            live_metric("sheet", "Sheet")
            live_metric("next", "Next action", important=True)
            with ui.element("div").classes("mini-metric").style("grid-column: 1 / -1"):
                ui.label("Blockers").classes("label")
                live_labels["blockers"] = ui.label("-").classes("value")

        with ui.grid(columns="360px minmax(420px, 0.9fr) 460px").classes("w-full gap-2 min-h-0 workspace-panel workspace-grid"):
            with ui.tab_panels(workspace_tabs, value=active_workspace["value"]).classes("w-full h-full"):
                with ui.tab_panel(connection_tab).classes("p-0"):
                    build_connection_workspace(supervisor)

                with ui.tab_panel(calibration_tab).classes("p-0"):
                    build_calibration_motion_workspace(
                        settings,
                        fields,
                        persist_and_refresh=persist_and_refresh,
                        home_xy=home_xy,
                        jog_y_positive=jog_y_positive,
                        jog_x_negative=jog_x_negative,
                        jog_y_negative=jog_y_negative,
                        jog_x_positive=jog_x_positive,
                        pen_up=pen_up,
                        pen_down=pen_down,
                        home_axis=home_axis,
                    )
                with ui.tab_panel(tests_tab).classes("p-0"):
                    uploaded_svg_label = build_tests_workspace(
                        settings,
                        fields,
                        node_pills,
                        generate_dry_run=generate_dry_run,
                        start_test_print=start_test_print,
                        handle_svg_upload=handle_svg_upload,
                        print_uploaded_svg=print_uploaded_svg,
                        persist_and_refresh=persist_and_refresh,
                    )

                with ui.tab_panel(work_tab).classes("p-0"):
                    system_check_label = build_work_workspace(
                        supervisor,
                        fields,
                        ready_labels,
                        thermal_printer_labels,
                        start_system=start_system,
                        reset_baseline=reset_baseline,
                        stop_system=stop_system,
                        start_macmini=start_macmini,
                        stop_macmini=stop_macmini,
                        scan_macmini=scan_macmini,
                        restart_macmini=restart_macmini,
                        latest_receipt_session_dir=latest_receipt_session_dir,
                        thermal_printer_status=thermal_printer_status,
                        thermal_printer_connect=thermal_printer_connect,
                        thermal_printer_print_latest=thermal_printer_print_latest,
                        thermal_printer_print_selected=thermal_printer_print_selected,
                        thermal_printer_test_receipt=thermal_printer_test_receipt,
                        set_work_zero=set_work_zero,
                    )

                with ui.tab_panel(exhibition_tab).classes("p-0"):
                    start_print_button = build_exhibition_workspace(start_print=start_print)

            with ui.card().classes("oracle-card compact-card w-full min-h-0 h-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Sheet Preview").classes("text-sm font-bold")
                preview_progress_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
                preview_legend()
                preview = ui.html().classes("preview-frame w-full")

            with ui.tab_panels(workspace_tabs, value=active_workspace["value"]).classes("w-full h-full"):
                with ui.tab_panel(connection_tab).classes("p-0"):
                    build_connection_notes()

                with ui.tab_panel(calibration_tab).classes("p-0"):
                    capacity_label = build_calibration_workspace(
                        settings,
                        scales,
                        preview_mode,
                        fields,
                        gcode_labels,
                        persist_and_refresh=persist_and_refresh,
                        preview_mode_changed=preview_mode_changed,
                        update_scales_from_fields=update_scales_from_fields,
                        update_gcode_detail_labels=update_gcode_detail_labels,
                    )

                with ui.tab_panel(work_tab).classes("p-0"):
                    logs_view = build_work_status_workspace(
                        queue_labels,
                        fields,
                        refresh_logs=refresh_logs,
                        open_logs=open_logs,
                    )

                with ui.tab_panel(exhibition_tab).classes("p-0"):
                    progress = build_exhibition_status_workspace(plotter_labels)

                with ui.tab_panel(tests_tab).classes("p-0"):
                    build_tests_notes()

    ui.timer(2.0, refresh_status)
    persist_and_refresh()


def _format_gui_tuple(value: Any) -> str:
    if not value:
        return "-"
    try:
        return ",".join(f"{float(item):.3f}" for item in value)
    except Exception:  # noqa: BLE001
        return str(value)


def _workspace_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    for attribute in ("name", "value"):
        resolved = getattr(value, attribute, None)
        if isinstance(resolved, str):
            return resolved
    return str(value)


def main() -> None:
    # Role-based access control: prevent GUI from running on wrong machines
    allowed_roles = os.getenv("NEJE_ALLOWED_ROLES", "gui_only").split(",")
    if "gui_only" not in allowed_roles:
        print("\n" + "="*70)
        print("ERROR: GUI not allowed on this machine")
        print("="*70)
        print()
        print("This error occurs when:")
        print("  1. You're on Mac mini (should only run: nje-uploader-agent)")
        print("  2. You set NEJE_ALLOWED_ROLES to restrict this machine")
        print()
        print("To fix:")
        print("  - On MacBook: Use launcher: start_oracle_gui.command")
        print("  - On MacBook: Or run: uv run nje-gui")
        print("  - On Mac mini: Use launcher: start_uploader_agent.command")
        print()
        print("For documentation, see: README.md 'Entry Points & Launchers' section")
        print("="*70 + "\n")
        sys.exit(1)

    ui.page("/")(build_page)
    host = os.getenv("NEJE_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("NEJE_GUI_PORT", "8787"))
    ui.run(host=host, port=port, reload=False, title="Oracle Operator")


if __name__ == "__main__":
    main()
