from __future__ import annotations

import os
import subprocess
from typing import Any

from nicegui import ui

from .gui_modes import mode_policy
from .gui_ui import (
    danger_action_button,
    log_viewer,
    number_control,
    primary_action_button,
    safe_action_button,
    status_pill,
    update_status_pill,
    warning_banner,
)
from .models import ComponentStatus, PreflightLevel, SystemMode
from .gui_support import (
    GUI_DEFAULTS,
    build_preview_svg,
    confirm_plotter_reload,
    create_user_sessions_from_gui,
    effective_randomness,
    generate_dry_run_sheet,
    gui_settings_to_plotter_config,
    layout_capacity,
    list_base_symbols,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
    read_queue_status,
    save_gui_settings,
    save_oracle_plotter_config,
    save_symbol_scales,
)
from .oracle_logging import read_logs
from .supervisor import SupervisorService


def build_page() -> None:
    settings = load_gui_settings()
    scales = load_symbol_scales()
    symbols = list_base_symbols()

    fields: dict[str, Any] = {}
    plotter_labels: dict[str, Any] = {}
    queue_labels: dict[str, Any] = {}
    fluidnc_labels: dict[str, Any] = {}
    ready_labels: dict[str, Any] = {}
    node_pills: dict[str, Any] = {}
    cycle_state = {"index": 0}
    supervisor = SupervisorService()
    valid_workspaces = {"connection", "calibration", "tests", "work", "exhibition"}
    saved_workspace = str(supervisor.runtime_store.load_json("gui_workspace", {"tab": "connection"}).get("tab", "connection"))
    active_workspace = {"value": saved_workspace if saved_workspace in valid_workspaces else "connection"}

    ui.colors(primary="#1f1a17", secondary="#9a5b24", accent="#c7a45a")
    ui.add_head_html(
        """
        <style>
          body { background: #f7f1e7; color: #1f1a17; overflow: hidden; }
          .q-field__control { min-height: 40px !important; }
          .q-field__label { font-size: 12px; }
          .oracle-shell { height: 100vh; max-height: 100vh; overflow: hidden; }
          .oracle-card {
            background: rgba(255, 252, 245, 0.94);
            border: 1px solid #dac9ad;
            border-radius: 14px;
            box-shadow: 0 8px 22px rgba(31, 26, 23, 0.07);
          }
          .oracle-title { letter-spacing: 0.16em; color: #8f4f2b; }
          .compact-card { padding: 10px 12px !important; }
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
          .workspace-panel { height: calc(100vh - 104px); overflow: hidden; }
          .workspace-scroll {
            max-height: calc(100vh - 120px);
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 8px;
            box-sizing: border-box;
          }
          .preview-frame svg { width: 100%; height: auto; max-height: calc(100vh - 182px); }
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
        </style>
        """
    )

    def pull_settings_from_fields() -> None:
        settings.apply_system_mode()
        settings.layout_mode = str(fields["layout_mode"].value)
        settings.cell_diameter_mm = float(fields["cell_diameter_mm"].value or 1)
        settings.gap_mm = float(fields["gap_mm"].value or 0)
        settings.randomness = float(fields["randomness"].value or 0)
        settings.randomness_fine = float(fields["randomness_fine"].value or 0)
        settings.live_interval_seconds = float(fields["live_interval_seconds"].value or 1)
        settings.selected_symbol = str(fields["selected_symbol"].value)
        settings.include_rings = bool(fields["include_rings"].value)
        settings.sheet_width_mm = float(fields["sheet_width_mm"].value or 1)
        settings.sheet_height_mm = float(fields["sheet_height_mm"].value or 1)
        settings.sheet_margin_mm = float(fields["sheet_margin_mm"].value or 0)
        settings.global_scale = float(fields["global_scale"].value or 1)
        settings.travel_rate = float(fields["travel_rate"].value or 1)
        settings.draw_rate = float(fields["draw_rate"].value or 1)
        settings.z_down_mm = float(fields["z_down_mm"].value or 0)
        settings.z_up_mm = float(fields["z_up_mm"].value or 0)
        settings.z_feed_mm_min = float(fields["z_feed_mm_min"].value or 1)

    def persist_and_refresh() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        preview.content = build_preview_svg(settings)
        preview.update()
        capacity_label.set_text(f"{layout_capacity(settings)} cells")
        policy = mode_policy(settings.mode)
        real_warning.visible = policy.real_fluidnc_required
        real_warning.update()
        if policy.real_fluidnc_required:
            arm_button.enable()
            if supervisor.runtime_store.load_real_fluidnc_armed():
                start_print_button.enable()
            else:
                start_print_button.disable()
        else:
            arm_button.disable()
            start_print_button.enable()
            supervisor.runtime_store.save_real_fluidnc_armed(False)
        live_timer.interval = max(settings.live_interval_seconds, 1.0)
        refresh_status()
        refresh_component_status()

    def update_scales_from_fields() -> None:
        pull_settings_from_fields()
        for symbol in symbols:
            scales[symbol.name] = float(fields[f"scale:{symbol.name}"].value or 1.0)
        save_gui_settings(settings)
        save_symbol_scales(scales)
        preview.content = build_preview_svg(settings)
        preview.update()

    def generate_user_sessions() -> None:
        pull_settings_from_fields()
        settings.user_count = 1
        paths = create_user_sessions_from_gui(settings, start_index=cycle_state["index"])
        cycle_state["index"] += len(paths)
        save_gui_settings(settings)
        ui.notify("Generated 1 test session", color="positive")
        last_user_output.set_text(str(paths[-1]) if paths else "-")

    def generate_dry_run() -> None:
        pull_settings_from_fields()
        try:
            output = generate_dry_run_sheet(settings)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"G-code generation failed: {exc}", color="negative")
            return
        ui.notify(f"G-code file: {output['gcode']}", color="positive")
        refresh_status()

    def refresh_status() -> None:
        status = read_plotter_status()
        queue = read_queue_status()
        total = int(status.get("processed_symbols", 0) or 0)
        progress_percent = float(status.get("sheet_progress_percent", status.get("gcode_progress_percent", 0.0)) or 0.0)
        current_row = int(status.get("current_row_index", 0) or 0)
        current_cell = int(status.get("current_cell_index", 0) or 0)
        current_cell_in_row = int(status.get("current_cell_in_row", 0) or 0)
        row_cell_count = int(status.get("row_cell_count", 0) or 0)
        preview.content = build_preview_svg(
            settings,
            highlighted_row_index=current_row if current_row > 0 else None,
            highlighted_cell_index=current_cell if current_cell > 0 else None,
        )
        preview.update()
        progress.value = min(max(progress_percent / 100.0, 0.0), 1.0)
        print_enabled = bool(status.get("print_enabled"))
        pending_reload = bool(status.get("pending_reload"))
        dry_run = bool(status.get("dry_run"))
        run_mode = str(status.get("run_mode", "-") or "-")
        status_text = str(status.get("status", "-") or "-").replace("_", " ")
        transport_text = "G-CODE ONLY" if dry_run else "FLUIDNC MOTION"
        print_text = "READY" if print_enabled else "STOPPED"
        if pending_reload:
            print_text = "WAITING FOR RELOAD"
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
            queue_labels["pending"].set_text(str(queue.get("pendingAfterBaseline", 0)))
            queue_labels["active"].set_text(str(active))
            queue_labels["failed"].set_text(f"{queue.get('failed', 0)} / {queue.get('skipped', 0)}")
            queue_labels["message"].set_text(str(queue.get("message", "-") or "-"))
        readiness = supervisor.runtime_store.load_plotter_readiness()
        if ready_labels:
            ready_labels["zero"].set_text("SET" if readiness.work_zero_set else "NOT SET")
            ready_labels["state"].set_text("READY" if readiness.plotter_ready else "NOT READY")
            ready_labels["message"].set_text(readiness.message)
        preview_progress_label.set_text(
            f"{status.get('status', '-')} | {progress_percent:.1f}% | "
            f"row {current_row}/{status.get('row_count', 0)} | cell {current_cell_in_row}/{row_cell_count} | "
            f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} G-code lines | "
            f"{total}/{layout_capacity(settings)} cells in last sheet"
        )
        if status.get("pending_reload"):
            reload_button.enable()
        else:
            reload_button.disable()
        refresh_component_status()

    def refresh_component_status() -> None:
        states = supervisor.refresh_all_status()
        if node_pills:
            update_status_pill(node_pills["fluidnc"], states.get("fluidnc"), "Plotter")
            update_status_pill(node_pills["macmini"], states.get("macmini_uploader"), "Mac mini")
            update_status_pill(node_pills["firebase"], states.get("firebase"), "Firebase")
            update_status_pill(node_pills["queue"], states.get("queue"), "Queue")
            update_status_pill(node_pills["print"], states.get("print"), "Print")

    def start_system() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        supervisor.start_system(gui_settings_to_plotter_config(settings))
        ui.notify("System supervisor started in safe mode", color="positive")
        refresh_status()

    def stop_system() -> None:
        supervisor.stop_system()
        ui.notify("System stopped safely", color="warning")
        refresh_status()

    def reset_baseline() -> None:
        state = supervisor.reset_run_baseline()
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        refresh_status()

    def set_system_mode(mode: SystemMode, *, notify: bool = True) -> None:
        settings.system_mode = mode.value
        settings.apply_system_mode()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        supervisor.set_system_mode(settings.mode)
        if notify:
            ui.notify(f"Mode set to {mode_policy(settings.mode).label}. REAL FluidNC disarmed.", color="warning")
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
            set_system_mode(SystemMode.EXHIBITION_DRY, notify=False)

    def restore_workspace() -> None:
        workspace_tabs.value = active_workspace["value"]
        workspace_tabs.update()

    def run_system_check(*, notify_success: bool = False) -> bool:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        result = supervisor.run_preflight(settings)
        refresh_system_check_result()
        refresh_component_status()
        refresh_logs()
        if result.has_critical:
            first_critical = next((check for check in result.checks if check.level == PreflightLevel.CRITICAL), None)
            message = first_critical.message if first_critical is not None else "System is not ready"
            ui.notify(f"Cannot start: {message}", color="negative")
            return False
        if notify_success:
            ui.notify("System check passed", color="positive" if result.status == PreflightLevel.OK else "warning")
        return True

    def refresh_system_check_result() -> None:
        result = supervisor.runtime_store.load_preflight_result()
        if not result:
            system_check_label.set_text("System check: not run")
            return
        critical = sum(1 for check in result.checks if check.level == PreflightLevel.CRITICAL)
        warnings = sum(1 for check in result.checks if check.level == PreflightLevel.WARNING)
        ok_count = sum(1 for check in result.checks if check.level == PreflightLevel.OK)
        system_check_label.set_text(f"System check: {critical} blocked · {warnings} warnings · {ok_count} ok")

    def arm_real_fluidnc() -> None:
        settings.system_mode = SystemMode.EXHIBITION_REAL.value
        settings.apply_system_mode()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        supervisor.set_system_mode(settings.mode)
        state = supervisor.arm_real_fluidnc(settings.mode)
        persist_and_refresh()
        color = "positive" if supervisor.runtime_store.load_real_fluidnc_armed() else "warning"
        ui.notify(state.message, color=color)

    def confirm_reload() -> None:
        if confirm_plotter_reload():
            ui.notify("Reload confirmed", color="positive")
        else:
            ui.notify("No reload confirmation is pending")
        refresh_status()

    def start_print() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        if not run_system_check():
            refresh_status()
            return
        plotter_state = supervisor.start_plotter(gui_settings_to_plotter_config(settings))
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start: {plotter_state.last_error or plotter_state.message}", color="negative")
            refresh_status()
            refresh_logs()
            return
        state = supervisor.start_print(settings.mode)
        color = "positive" if state.status == ComponentStatus.RUNNING else "warning"
        ui.notify(state.message, color=color)
        refresh_status()

    def start_test_print() -> None:
        set_system_mode(SystemMode.TEST, notify=False)
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        if not run_system_check():
            return
        plotter_state = supervisor.start_plotter(gui_settings_to_plotter_config(settings))
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start test print: {plotter_state.last_error or plotter_state.message}", color="negative")
            refresh_status()
            refresh_logs()
            return
        state = supervisor.start_print(settings.mode)
        color = "positive" if state.status == ComponentStatus.RUNNING else "warning"
        ui.notify(f"TEST PRINT: {state.message}", color=color)
        refresh_status()
        refresh_logs()

    def stop_print() -> None:
        state = supervisor.stop_print()
        ui.notify(state.message, color="warning")
        refresh_status()

    def set_work_zero() -> None:
        confirm_action(
            "SET WORK ZERO",
            "Current position becomes G54 X0 Y0 Z0. Use only after placing the tool at the upper-left work origin.",
            lambda: fluidnc_action("set work zero", supervisor.set_work_zero),
        )

    def ready_check() -> None:
        confirm_action(
            "READY CHECK",
            "Raises Z, homes X/Y, returns to X0 Y0, then checks FluidNC Idle. Confirm only when the machine is clear.",
            lambda: fluidnc_action("ready check", supervisor.ready_check),
        )

    def check_fluidnc() -> None:
        probe = supervisor.probe_fluidnc()
        supervisor.check_fluidnc()
        result = {**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port}
        color = "positive" if probe.online else "negative"
        update_fluidnc_labels(result)
        ui.notify(probe.message, color=color)
        refresh_logs()
        restore_workspace()

    def update_fluidnc_labels(result: dict[str, Any]) -> None:
        fluidnc_labels["webui"].set_text("online" if result.get("http_online") else "offline")
        fluidnc_labels["telnet"].set_text("online" if result.get("telnet_online") else "offline")
        fluidnc_labels["state"].set_text(str(result.get("controller_state") or "Unknown"))
        fluidnc_labels["mpos"].set_text(_format_gui_tuple(result.get("machine_position")))
        if "pins" in fluidnc_labels:
            fluidnc_labels["pins"].set_text(str(result.get("pins") or "none"))
        fluidnc_labels["modal"].set_text(str(result.get("modal_state") or "-").replace("\n", " | "))
        fluidnc_labels["target"].set_text(f"{result.get('http_url') or '-'} · {result.get('host')}:{result.get('port')}")
        fluidnc_labels["message"].set_text(str(result.get("message") or result.get("last_error") or "-"))

    def confirm_action(title: str, message: str, action: Any) -> None:
        with ui.dialog() as dialog, ui.card().classes("oracle-card"):
            ui.label(title).classes("text-sm font-bold")
            ui.label(message).classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("dense flat")
                ui.button("Confirm", on_click=lambda: (dialog.close(), action())).props("dense color=warning")
        dialog.open()

    def fluidnc_action(label: str, action: Any, *, refresh_probe: bool = True) -> None:
        state = action()
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        if refresh_probe:
            check_fluidnc()
        refresh_status()
        refresh_logs()
        restore_workspace()

    def home_all() -> None:
        confirm_action("HOME ALL", "The plotter will run FluidNC homing command $H. Confirm only if the machine is physically clear.", lambda: fluidnc_action("home", lambda: supervisor.home_fluidnc(), refresh_probe=False))

    def home_axis(axis: str) -> None:
        confirm_action(f"HOME {axis}", f"Single-axis homing sends $H={axis}. Use only if this FluidNC config supports it.", lambda: fluidnc_action(f"home {axis}", lambda: supervisor.home_fluidnc(axis), refresh_probe=False))

    def jog(axis: str, sign: float) -> None:
        distance = sign * float(fields["jog_step"].value or 1)
        feed = float(fields["jog_feed"].value or 1000)
        fluidnc_action(f"jog {axis}", lambda: supervisor.jog_fluidnc(axis, distance, feed))

    def unlock_alarm() -> None:
        confirm_action("UNLOCK ALARM", "This sends $X. It clears FluidNC alarm state without moving the machine.", lambda: fluidnc_action("unlock", supervisor.unlock_fluidnc_alarm))

    def emergency_stop() -> None:
        state = supervisor.emergency_stop_fluidnc()
        ui.notify(state.message, color="negative")
        refresh_status()
        refresh_logs()

    def resume_after_hold() -> None:
        confirm_action("RESUME AFTER HOLD", "This sends realtime cycle start ~. Confirm only if the machine is safe to resume.", lambda: fluidnc_action("resume", supervisor.resume_fluidnc))

    def soft_reset() -> None:
        confirm_action("SOFT RESET / ABORT", "This sends Ctrl-X and disables print. Use only to abort/reset FluidNC.", lambda: fluidnc_action("soft reset", supervisor.soft_reset_fluidnc))

    def toggle_live() -> None:
        pull_settings_from_fields()
        live_timer.interval = max(settings.live_interval_seconds, 1.0)
        if live_toggle.value:
            live_timer.activate()
            ui.notify(f"Generator started: 1 symbol every {live_timer.interval:g}s", color="positive")
        else:
            live_timer.deactivate()
            ui.notify("Generator stopped")

    def live_interval_changed() -> None:
        pull_settings_from_fields()
        live_timer.interval = max(settings.live_interval_seconds, 1.0)
        save_gui_settings(settings)

    def start_macmini() -> None:
        supervisor.start_macmini_uploader()
        refresh_component_status()

    def stop_macmini() -> None:
        supervisor.stop_macmini_uploader()
        refresh_component_status()

    def restart_macmini() -> None:
        supervisor.restart_macmini_uploader()
        refresh_component_status()

    def scan_macmini() -> None:
        supervisor.scan_macmini_once()
        refresh_component_status()

    def refresh_logs() -> None:
        selected = str(fields["log_filter"].value or "all") if "log_filter" in fields else "all"
        log_lines = read_logs(category_filter=selected, limit=100)
        logs_view.value = "\n".join(log_lines)
        logs_view.update()

    def open_logs() -> None:
        subprocess.run(["open", str(supervisor.settings.logs_root)], check=False)

    def calibration_slider_row(
        label: str,
        key: str,
        *,
        value: float,
        default: float,
        min_value: float,
        max_value: float,
        step: float,
        on_change: Any,
    ) -> Any:
        with ui.grid(columns="135px 1fr 74px 28px 28px").classes("w-full items-center gap-2"):
            ui.label(label).classes("text-xs text-[#8f4f2b]")
            control = ui.slider(min=min_value, max=max_value, step=step, value=value).props("dense").classes("w-full tight-slider")
            number = ui.number(value=value, min=min_value, max=max_value, step=step).props("dense outlined").classes("w-full")

            def sync_from_slider() -> None:
                number.value = control.value
                number.update()
                on_change()

            def sync_from_number() -> None:
                control.value = number.value
                control.update()
                on_change()

            def nudge(delta: float) -> None:
                current = float(number.value or 0)
                next_value = max(min_value, min(max_value, current + delta))
                control.value = next_value
                number.value = next_value
                control.update()
                number.update()
                on_change()

            def reset() -> None:
                control.value = default
                number.value = default
                control.update()
                number.update()
                on_change()

            control.on_value_change(sync_from_slider)
            control.on("dblclick", lambda _: reset())
            number.on_value_change(sync_from_number)
            number.on("dblclick", lambda _: reset())
            ui.button("-", on_click=lambda: nudge(-step)).props("dense flat").classes("w-full")
            ui.button("+", on_click=lambda: nudge(step)).props("dense flat").classes("w-full")
            fields[key] = control
            return control

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

        real_warning = warning_banner("Real plotter output starts only after zero is set, readiness is checked, and real output is enabled.")

        with ui.grid(columns="360px minmax(420px, 0.9fr) 460px").classes("w-full gap-2 min-h-0 workspace-panel"):
            with ui.tab_panels(workspace_tabs, value=active_workspace["value"]).classes("w-full h-full"):
                with ui.tab_panel(connection_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Connection").classes("text-sm font-bold")
                            ui.label("Network/controller checks only. No motion except emergency, unlock, resume and reset.").classes("text-xs text-[#8f4f2b]")
                            with ui.row().classes("gap-2"):
                                ui.button("CONNECT", on_click=check_fluidnc).props("dense color=positive")
                                ui.button("Emergency Stop", on_click=emergency_stop).props("dense color=negative")
                            with ui.grid(columns=2).classes("w-full gap-1"):
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("WebUI").classes("label")
                                    fluidnc_labels["webui"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Telnet").classes("label")
                                    fluidnc_labels["telnet"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("State").classes("label")
                                    fluidnc_labels["state"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("MPos").classes("label")
                                    fluidnc_labels["mpos"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Inputs").classes("label")
                                    fluidnc_labels["pins"] = ui.label("-").classes("value")
                            fluidnc_labels["message"] = ui.label("Not connected").classes("path-label text-xs font-bold")
                            fluidnc_labels["target"] = ui.label("-").classes("path-label text-[10px] text-[#8f4f2b]")
                            fluidnc_labels["modal"] = ui.label("-").classes("path-label text-[10px] text-[#8f4f2b]")
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Controller recovery").classes("text-sm font-bold")
                            with ui.row().classes("gap-2"):
                                ui.button("Unlock", on_click=unlock_alarm).props("dense color=warning")
                                ui.button("Resume", on_click=resume_after_hold).props("dense flat")
                                ui.button("Reset", on_click=soft_reset).props("dense color=negative")

                with ui.tab_panel(calibration_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Manual motion").classes("text-sm font-bold")
                            ui.label("Jog and homing for setup. Manual movement is blocked while G-code streams.").classes("text-xs text-[#8f4f2b]")
                            with ui.row().classes("gap-2 items-end"):
                                fields["jog_step"] = ui.select(
                                    {1.0: "1", 5.0: "5", 10.0: "10", 25.0: "25", 50.0: "50", 100.0: "100"},
                                    value=1.0,
                                    label="Step mm",
                                ).props("dense outlined").classes("w-24")
                                fields["jog_feed"] = ui.number("Feed", value=1000, min=1, step=100).props("dense outlined").classes("w-24")
                                ui.button("Home", on_click=home_all).props("dense color=warning")
                            with ui.grid(columns=3).classes("w-full gap-1 jog-pad"):
                                ui.label("")
                                ui.button("Y+", on_click=lambda: jog("Y", 1)).props("dense")
                                ui.label("")
                                ui.button("X-", on_click=lambda: jog("X", -1)).props("dense")
                                ui.button("Y-", on_click=lambda: jog("Y", -1)).props("dense")
                                ui.button("X+", on_click=lambda: jog("X", 1)).props("dense")
                            with ui.row().classes("gap-1"):
                                ui.button("Z+", on_click=lambda: jog("Z", 1)).props("dense flat")
                                ui.button("Z-", on_click=lambda: jog("Z", -1)).props("dense flat")
                                ui.button("Home X", on_click=lambda: home_axis("X")).props("dense flat")
                                ui.button("Home Y", on_click=lambda: home_axis("Y")).props("dense flat")
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Motion quality").classes("text-sm font-bold")
                            ui.label("Speed values are G-code feed rates in mm/min. Z servo PWM stays inside the FluidNC firmware config.").classes("text-xs text-[#8f4f2b]")
                            with ui.grid(columns=2).classes("w-full gap-2"):
                                number_control(fields, "travel_rate", label="Travel mm/min", value=settings.travel_rate, default=5000, min_value=1, width_class="w-full", tooltip="Pen-up movement speed. Saved directly to G-code F.", on_change=persist_and_refresh)
                                number_control(fields, "draw_rate", label="Draw mm/min", value=settings.draw_rate, default=1800, min_value=1, width_class="w-full", tooltip="Drawing movement speed. Saved directly to G-code F.", on_change=persist_and_refresh)
                                number_control(fields, "z_up_mm", label="Z up", value=settings.z_up_mm, default=25, min_value=0, width_class="w-full", tooltip="Safe raised Z position.", on_change=persist_and_refresh)
                                number_control(fields, "z_down_mm", label="Z down", value=settings.z_down_mm, default=0, min_value=-25, width_class="w-full", tooltip="Drawing/contact Z position.", on_change=persist_and_refresh)
                                number_control(fields, "z_feed_mm_min", label="Z mm/min", value=settings.z_feed_mm_min, default=1000, min_value=1, width_class="w-full", tooltip="Z movement speed. Saved directly to G-code F. Servo PWM is configured in FluidNC.", on_change=persist_and_refresh)
                with ui.tab_panel(tests_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2") as test_panel:
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("System nodes").classes("text-sm font-bold")
                            ui.label("Green = ready/running, yellow = warning, gray = offline/stopped, red = error.").classes("text-xs text-[#8f4f2b]")
                            with ui.row().classes("gap-2 flex-wrap"):
                                node_pills["fluidnc"] = status_pill("Plotter")
                                node_pills["macmini"] = status_pill("Mac mini")
                                node_pills["firebase"] = status_pill("Firebase")
                                node_pills["queue"] = status_pill("Queue")
                                node_pills["print"] = status_pill("Print")
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Test Generator").classes("text-sm font-bold")
                            ui.label("Creates one fake session at a time. Use it to test uploader, Firebase queue, and plotter flow.").classes("text-xs text-[#8f4f2b]")
                            symbol_options = {
                                "__cycle__": "All in order",
                                "__random__": "All random",
                            }
                            symbol_options.update({symbol.name: f"{index + 1}. {symbol.stem}" for index, symbol in enumerate(symbols)})
                            fields["selected_symbol"] = ui.select(
                                symbol_options,
                                value=settings.selected_symbol,
                                label="Symbol source",
                            ).props("dense outlined").classes("w-full")
                            with ui.row().classes("items-end gap-2"):
                                fields["live_interval_seconds"] = ui.number(
                                    "Interval sec",
                                    value=settings.live_interval_seconds,
                                    min=1,
                                ).props("dense outlined").classes("w-32").on_value_change(live_interval_changed)
                            with ui.row().classes("items-center gap-2"):
                                live_toggle = ui.switch("START GENERATOR", value=False, on_change=toggle_live)
                                ui.button("Generate G-code only", on_click=generate_dry_run).props("dense")
                                ui.button("START TEST PRINT", on_click=start_test_print).props("dense color=positive")
                            last_user_output = ui.label("-").classes("path-label text-xs")

                with ui.tab_panel(work_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("System run").classes("text-sm font-bold")
                            ui.label("Start the supervised local services, reset the Firebase baseline for this run, or stop safely before the next sheet.").classes("text-xs text-[#8f4f2b]")
                            with ui.row().classes("gap-2"):
                                primary_action_button("START SYSTEM", start_system)
                                safe_action_button("NEW RUN", reset_baseline)
                                danger_action_button("STOP SYSTEM", stop_system)
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Mac mini uploader").classes("text-sm font-bold")
                            with ui.row().classes("gap-2"):
                                ui.button("Start", on_click=start_macmini).props("dense")
                                ui.button("Stop", on_click=stop_macmini).props("dense")
                                ui.button("Scan", on_click=scan_macmini).props("dense")
                                ui.button("Restart", on_click=restart_macmini).props("dense")
                            ui.label("Controlled through NEJE_MACMINI_AGENT_URL").classes("text-xs text-[#8f4f2b]")
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Ready workflow").classes("text-sm font-bold")
                            ui.label("Before Set Zero: fix paper, jog to upper-left work origin, lower Z manually, set pen pressure/contact, then confirm. Software cannot verify pen pressure.").classes("text-xs text-[#8f4f2b]")
                            with ui.row().classes("gap-2"):
                                ui.button("Set Zero", on_click=set_work_zero).props("dense color=warning")
                                ui.button("Check Ready", on_click=ready_check).props("dense color=positive")
                            with ui.grid(columns=2).classes("w-full gap-1"):
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Zero").classes("label")
                                    ready_labels["zero"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Ready").classes("label")
                                    ready_labels["state"] = ui.label("-").classes("value")
                            ready_labels["message"] = ui.label("-").classes("path-label text-xs")
                            ui.separator()
                            with ui.row().classes("gap-2"):
                                arm_button = danger_action_button("Enable Real Output", arm_real_fluidnc)
                            system_check_label = ui.label("System check runs automatically when print starts.").classes("text-xs text-[#8f4f2b]")

                with ui.tab_panel(exhibition_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Exhibition controls").classes("text-sm font-bold")
                            ui.label("Minimal live-print controls. No layout, jog, scale or test generation here.").classes("text-xs text-[#8f4f2b]")
                            with ui.column().classes("gap-2"):
                                start_print_button = ui.button("START PRINT", on_click=start_print).props("dense color=positive").classes("w-full")
                                ui.button("STOP AFTER SHEET", on_click=stop_print).props("dense color=warning").classes("w-full")
                                reload_button = ui.button("RELOAD OK", on_click=confirm_reload).props("dense").classes("w-full")
                                ui.button("EMERGENCY STOP", on_click=emergency_stop).props("dense color=negative").classes("w-full")

            with ui.card().classes("oracle-card compact-card w-full min-h-0 h-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Sheet Preview").classes("text-sm font-bold")
                preview_progress_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
                preview = ui.html().classes("preview-frame w-full")

            with ui.tab_panels(workspace_tabs, value=active_workspace["value"]).classes("w-full h-full"):
                with ui.tab_panel(connection_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Connection details").classes("text-sm font-bold")
                            ui.label("Operator order: connect to the plotter Wi-Fi, press CONNECT, verify Idle state, then move to Calibration.").classes("text-xs text-[#8f4f2b]")
                            ui.label("WebUI only proves the controller page is reachable; Telnet + ok/error protocol is required for printing.").classes("text-xs text-[#8f4f2b]")

                with ui.tab_panel(calibration_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.label("Layout").classes("text-sm font-bold")
                                capacity_label = ui.label("-").classes("status-pill text-xs font-bold")
                            with ui.row().classes("items-end gap-2"):
                                fields["layout_mode"] = ui.select(["hex", "grid"], value=settings.layout_mode, label="Layout").props("dense outlined").classes("w-28").on_value_change(persist_and_refresh)
                                fields["include_rings"] = ui.switch("Rings", value=settings.include_rings).on_value_change(persist_and_refresh)
                            with ui.grid(columns=2).classes("w-full gap-2"):
                                number_control(fields, "sheet_width_mm", label="Field W", value=settings.sheet_width_mm, default=GUI_DEFAULTS["sheet_width_mm"], min_value=1, width_class="w-full", tooltip="Printable field width in mm.", on_change=persist_and_refresh)
                                number_control(fields, "sheet_height_mm", label="Field H", value=settings.sheet_height_mm, default=GUI_DEFAULTS["sheet_height_mm"], min_value=1, width_class="w-full", tooltip="Printable field height in mm.", on_change=persist_and_refresh)
                                number_control(fields, "cell_diameter_mm", label="Cell", value=settings.cell_diameter_mm, default=GUI_DEFAULTS["cell_diameter_mm"], min_value=1, width_class="w-full", tooltip="Packing cell diameter and grid step base.", on_change=persist_and_refresh)
                                number_control(fields, "gap_mm", label="Gap", value=settings.gap_mm, default=GUI_DEFAULTS["gap_mm"], min_value=0, width_class="w-full", tooltip="Distance between neighboring cell diameters.", on_change=persist_and_refresh)
                                number_control(fields, "sheet_margin_mm", label="Margin", value=settings.sheet_margin_mm, default=GUI_DEFAULTS["sheet_margin_mm"], min_value=0, width_class="w-full", tooltip="Safe border inside printable field.", on_change=persist_and_refresh)
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Symbol scale correction").classes("text-sm font-bold")
                            ui.label("These controls define how generated symbols will look before test generation and printing.").classes("text-xs text-[#8f4f2b]")
                            calibration_slider_row("Random coarse", "randomness", value=settings.randomness, default=GUI_DEFAULTS["randomness"], min_value=0, max_value=100, step=1, on_change=persist_and_refresh)
                            calibration_slider_row("Random fine", "randomness_fine", value=settings.randomness_fine, default=GUI_DEFAULTS["randomness_fine"], min_value=-10, max_value=10, step=0.1, on_change=persist_and_refresh)
                            calibration_slider_row("Global scale", "global_scale", value=settings.global_scale, default=GUI_DEFAULTS["global_scale"], min_value=0.3, max_value=3.0, step=0.01, on_change=persist_and_refresh)
                            ui.label("Double-click any scale slider to reset it to 1.0. Scale changes are applied and saved immediately.").classes("text-xs text-[#8f4f2b]")
                            with ui.column().classes("w-full gap-0"):
                                for symbol in symbols:
                                    calibration_slider_row(
                                        symbol.stem[:20],
                                        f"scale:{symbol.name}",
                                        value=scales.get(symbol.name, 1.0),
                                        default=1.0,
                                        min_value=0.3,
                                        max_value=5.0,
                                        step=0.01,
                                        on_change=update_scales_from_fields,
                                    )

                with ui.tab_panel(work_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Queue").classes("text-sm font-bold")
                            with ui.grid(columns=4).classes("w-full gap-1"):
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Queue").classes("label")
                                    queue_labels["state"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Pending").classes("label")
                                    queue_labels["pending"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Active").classes("label")
                                    queue_labels["active"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Fail/Skip").classes("label")
                                    queue_labels["failed"] = ui.label("-").classes("value")
                            queue_labels["message"] = ui.label("-").classes("path-label text-[10px]")
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Logs").classes("text-sm font-bold")
                            fields["log_filter"] = ui.select(
                                {"all": "all", "errors": "errors", "system": "system", "plotter": "plotter", "uploader": "uploader", "preflight": "checks"},
                                value="all",
                                label="Filter",
                            ).props("dense outlined").classes("w-full").on_value_change(refresh_logs)
                            with ui.row().classes("gap-2"):
                                safe_action_button("Refresh", refresh_logs)
                                safe_action_button("Open logs", open_logs)
                            logs_view = log_viewer([])

                with ui.tab_panel(exhibition_tab).classes("p-0"):
                    with ui.column().classes("workspace-scroll gap-2"):
                        with ui.card().classes("oracle-card compact-card w-full"):
                            ui.label("Live print state").classes("text-sm font-bold")
                            with ui.grid(columns=2).classes("w-full gap-1"):
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Print").classes("label")
                                    plotter_labels["state"] = ui.label("-").classes("value")
                                with ui.element("div").classes("mini-metric"):
                                    ui.label("Mode").classes("label")
                                    plotter_labels["mode"] = ui.label("-").classes("value")
                            plotter_labels["sheet"] = ui.label("no sheet yet").classes("path-label text-xs font-bold")
                            plotter_labels["cells"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
                            progress = ui.linear_progress(value=0).classes("w-full")
                            plotter_labels["progress"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
                            plotter_labels["message"] = ui.label("-").classes("path-label text-xs")

    live_timer = ui.timer(settings.live_interval_seconds, generate_user_sessions, active=False)
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
    ui.page("/")(build_page)
    host = os.getenv("NEJE_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("NEJE_GUI_PORT", "8787"))
    ui.run(host=host, port=port, reload=False, title="Oracle Operator")


if __name__ == "__main__":
    main()
