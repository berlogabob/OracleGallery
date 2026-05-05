from __future__ import annotations

import os
import subprocess
from base64 import b64encode
from typing import Any

from nicegui import ui

from .config import PlotterSettings
from .gui_modes import MODE_LABELS, mode_policy
from .gui_ui import (
    danger_action_button,
    log_viewer,
    mode_badge,
    number_control,
    primary_action_button,
    safe_action_button,
    slider_control,
    warning_banner,
)
from .models import ComponentStatus, PreflightLevel, SystemMode
from .gui_support import (
    GUI_DEFAULTS,
    build_preview_svg,
    build_symbol_preview_svg,
    check_fluidnc_connection,
    confirm_plotter_reload,
    create_idle_bank_from_gui,
    create_user_sessions_from_gui,
    default_idle_root,
    default_scale_config_path,
    effective_randomness,
    generate_dry_run_sheet,
    gui_settings_to_plotter_config,
    layout_capacity,
    list_base_symbols,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
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
    status_labels: dict[str, Any] = {}
    symbol_previews: dict[str, Any] = {}
    control_labels: dict[str, Any] = {}
    plotter_labels: dict[str, Any] = {}
    fluidnc_labels: dict[str, Any] = {}
    cycle_state = {"index": 0}
    supervisor = SupervisorService()

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
          .preview-frame svg { width: 100%; height: auto; max-height: 68vh; }
          .symbol-preview svg { width: 58px; height: 58px; }
          .path-label { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .tight-slider .q-slider { min-height: 28px; }
          .status-pill { border: 1px solid #dac9ad; border-radius: 999px; padding: 3px 8px; font-size: 11px; white-space: nowrap; }
          .mode-badge { border: 1px solid #9a5b24; border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 700; color: #8f4f2b; }
          .warning-banner { background: #fff4df; border: 1px solid #c99743; border-radius: 10px; color: #8f4f2b; padding: 6px 8px; font-size: 12px; }
          .log-viewer textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.35; }
          .plotter-console .q-btn { min-height: 28px; padding: 3px 8px; }
          .mini-metric { border: 1px solid #e1d3ba; border-radius: 10px; padding: 5px 7px; background: rgba(255,255,255,0.45); }
          .mini-metric .label { font-size: 9px; letter-spacing: 0.16em; color: #8f4f2b; text-transform: uppercase; }
          .mini-metric .value { font-size: 12px; font-weight: 700; color: #1f1a17; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .jog-pad .q-btn { width: 54px; }
        </style>
        """
    )

    def pull_settings_from_fields() -> None:
        settings.system_mode = str(fields["system_mode"].value)
        settings.apply_system_mode()
        settings.layout_mode = str(fields["layout_mode"].value)
        settings.cell_diameter_mm = float(fields["cell_diameter_mm"].value or 1)
        settings.gap_mm = float(fields["gap_mm"].value or 0)
        settings.randomness = float(fields["randomness"].value or 0)
        settings.randomness_fine = float(fields["randomness_fine"].value or 0)
        settings.user_count = int(fields["user_count"].value or 1)
        settings.live_interval_seconds = float(fields["live_interval_seconds"].value or 1)
        settings.selected_symbol = str(fields["selected_symbol"].value)
        settings.idle_variations_per_symbol = int(fields["idle_variations_per_symbol"].value or 1)
        settings.idle_count = max(len(symbols) * settings.idle_variations_per_symbol, 1)
        settings.include_rings = bool(fields["include_rings"].value)
        settings.sheet_width_mm = float(fields["sheet_width_mm"].value or 1)
        settings.sheet_height_mm = float(fields["sheet_height_mm"].value or 1)
        settings.sheet_margin_mm = float(fields["sheet_margin_mm"].value or 0)
        settings.global_scale = float(fields["global_scale"].value or 1)

    def persist_and_refresh() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        preview.content = build_preview_svg(settings)
        preview.update()
        capacity_label.set_text(f"{layout_capacity(settings)} cells")
        policy = mode_policy(settings.mode)
        mode_label.set_text(policy.label)
        transport_label.set_text("DRY RUN" if policy.dry_run else "REAL FLUIDNC")
        test_panel.visible = policy.test_tools_enabled
        test_panel.update()
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
        refresh_symbol_previews()
        refresh_status()
        refresh_component_status()

    def refresh_symbol_previews() -> None:
        for symbol in symbols:
            scale = scales.get(symbol.name, 1.0) * settings.global_scale
            svg = build_symbol_preview_svg(
                symbol,
                marker_kind="user",
                scale=scale,
                include_rings=settings.include_rings,
                randomness=effective_randomness(settings),
            )
            encoded = b64encode(svg.encode("utf-8")).decode("ascii")
            symbol_previews[symbol.name].content = (
                f'<img src="data:image/svg+xml;base64,{encoded}" '
                f'alt="{symbol.stem}" style="width:58px;height:58px;object-fit:contain;" />'
            )
            symbol_previews[symbol.name].update()

    def update_scales_from_fields() -> None:
        pull_settings_from_fields()
        for symbol in symbols:
            scales[symbol.name] = float(fields[f"scale:{symbol.name}"].value or 1.0)
        save_gui_settings(settings)
        save_symbol_scales(scales)
        refresh_symbol_previews()
        preview.content = build_preview_svg(settings)
        preview.update()

    def save_scales_from_fields() -> None:
        update_scales_from_fields()
        ui.notify("Symbol scales saved", color="positive")

    def generate_user_sessions() -> None:
        pull_settings_from_fields()
        paths = create_user_sessions_from_gui(settings, start_index=cycle_state["index"])
        cycle_state["index"] += len(paths)
        save_gui_settings(settings)
        ui.notify(f"Generated {len(paths)} user session(s)", color="positive")
        last_user_output.set_text(str(paths[-1]) if paths else "-")

    def generate_all_user_symbols() -> None:
        pull_settings_from_fields()
        original_count = settings.user_count
        original_symbol = settings.selected_symbol
        settings.user_count = len(symbols)
        settings.selected_symbol = "__cycle__"
        paths = create_user_sessions_from_gui(settings, start_index=0)
        settings.user_count = original_count
        settings.selected_symbol = original_symbol
        cycle_state["index"] = len(symbols)
        save_gui_settings(settings)
        ui.notify(f"Generated all {len(paths)} base symbols", color="positive")
        last_user_output.set_text(str(paths[-1]) if paths else "-")

    def generate_idle_bank() -> None:
        pull_settings_from_fields()
        paths = create_idle_bank_from_gui(settings)
        save_gui_settings(settings)
        ui.notify(f"Generated {len(paths)} idle variation(s)", color="positive")
        idle_output.set_text(f"{len(paths)} files -> {default_idle_root()}")

    def generate_dry_run() -> None:
        pull_settings_from_fields()
        try:
            output = generate_dry_run_sheet(settings)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Dry-run failed: {exc}", color="negative")
            return
        ui.notify(f"Dry-run G-code: {output['gcode']}", color="positive")
        refresh_status()

    def refresh_status() -> None:
        status = read_plotter_status()
        for key, label in status_labels.items():
            label.set_text(str(status.get(key, "-") or "-"))
        for key, label in control_labels.items():
            label.set_text(str(status.get(key, "-") or "-"))
        total = int(status.get("processed_symbols", 0) or 0)
        progress_percent = float(status.get("sheet_progress_percent", status.get("gcode_progress_percent", 0.0)) or 0.0)
        progress.value = min(max(progress_percent / 100.0, 0.0), 1.0)
        print_enabled = bool(status.get("print_enabled"))
        pending_reload = bool(status.get("pending_reload"))
        dry_run = bool(status.get("dry_run"))
        run_mode = str(status.get("run_mode", "-") or "-")
        status_text = str(status.get("status", "-") or "-").replace("_", " ")
        transport_text = "DRY RUN" if dry_run else "REAL FLUIDNC"
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
            f"{progress_percent:.0f}% · row {status.get('current_row_index', 0)}/{status.get('row_count', 0)} · "
            f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} lines"
        )
        plotter_labels["message"].set_text(str(status.get("message", "-") or "-"))
        preview_progress_label.set_text(
            f"{status.get('status', '-')} | {progress_percent:.1f}% | "
            f"row {status.get('current_row_index', 0)}/{status.get('row_count', 0)} | "
            f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} G-code lines | "
            f"{total}/{layout_capacity(settings)} cells in last sheet"
        )
        if status.get("pending_reload"):
            reload_button.enable()
        else:
            reload_button.disable()
        refresh_component_status()

    def refresh_component_status() -> None:
        supervisor.refresh_all_status()

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

    def check_system() -> None:
        supervisor.check_firebase()
        supervisor.check_fluidnc()
        supervisor.check_macmini_agent()
        refresh_component_status()
        ui.notify("System checks refreshed")

    def set_system_mode() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        supervisor.set_system_mode(settings.mode)
        ui.notify(f"Mode set to {mode_policy(settings.mode).label}. REAL FluidNC disarmed.", color="warning")
        refresh_status()

    def run_preflight() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        save_oracle_plotter_config(settings)
        result = supervisor.run_preflight(settings)
        refresh_preflight_result()
        refresh_component_status()
        refresh_logs()
        color = "positive" if result.status == PreflightLevel.OK else "warning"
        if result.status == PreflightLevel.CRITICAL:
            color = "negative"
        ui.notify(f"Preflight {result.status.value}: {len(result.checks)} checks", color=color)

    def refresh_preflight_result() -> None:
        result = supervisor.runtime_store.load_preflight_result()
        if not result:
            preflight_label.set_text("Preflight: not run")
            return
        critical = sum(1 for check in result.checks if check.level == PreflightLevel.CRITICAL)
        warnings = sum(1 for check in result.checks if check.level == PreflightLevel.WARNING)
        preflight_label.set_text(f"Preflight: {result.status.value} · critical {critical} · warnings {warnings}")

    def arm_real_fluidnc() -> None:
        pull_settings_from_fields()
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
        save_oracle_plotter_config(settings)
        state = supervisor.start_print(settings.mode)
        color = "positive" if state.status == ComponentStatus.RUNNING else "warning"
        ui.notify(state.message, color=color)
        refresh_status()

    def stop_print() -> None:
        state = supervisor.stop_print()
        ui.notify(state.message, color="warning")
        refresh_status()

    def open_spool() -> None:
        subprocess.run(["open", str(PlotterSettings().spool_root)], check=False)

    def check_fluidnc() -> None:
        result = check_fluidnc_connection()
        supervisor.check_fluidnc()
        color = "positive" if result["online"] else "negative"
        update_fluidnc_labels(result)
        ui.notify(result["message"], color=color)
        refresh_logs()

    def update_fluidnc_labels(result: dict[str, Any]) -> None:
        if "top_status" in fluidnc_labels:
            fluidnc_labels["top_status"].set_text(
                f"Plotter: {result.get('message') or '-'}"
            )
        fluidnc_labels["webui"].set_text("online" if result.get("http_online") else "offline")
        fluidnc_labels["telnet"].set_text("online" if result.get("telnet_online") else "offline")
        fluidnc_labels["state"].set_text(str(result.get("controller_state") or "Unknown"))
        fluidnc_labels["mpos"].set_text(_format_gui_tuple(result.get("machine_position")))
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

    def home_all() -> None:
        confirm_action("HOME ALL", "The plotter will run FluidNC homing command $H. Confirm only if the machine is physically clear.", lambda: fluidnc_action("home", lambda: supervisor.home_fluidnc()))

    def home_axis(axis: str) -> None:
        confirm_action(f"HOME {axis}", f"Single-axis homing sends $H={axis}. Use only if this FluidNC config supports it.", lambda: fluidnc_action(f"home {axis}", lambda: supervisor.home_fluidnc(axis)))

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
            ui.notify(f"Live generation every {live_timer.interval:g}s", color="positive")
        else:
            live_timer.deactivate()
            ui.notify("Live generation stopped")

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

    with ui.column().classes("oracle-shell w-full gap-2 p-3"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("THE ORACLE OPERATOR").classes("oracle-title text-lg")
            with ui.row().classes("items-center gap-2"):
                mode_label = mode_badge()
                transport_label = ui.label("-").classes("text-xs font-bold")
                primary_action_button("START SYSTEM", start_system)
                danger_action_button("STOP SYSTEM", stop_system)
                ui.label("capacity").classes("text-xs text-[#8f4f2b]")
                capacity_label = ui.label("-").classes("text-sm font-bold")

        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("w-full items-end gap-2"):
                fields["system_mode"] = ui.select(
                    {mode.value: MODE_LABELS[mode] for mode in SystemMode},
                    value=settings.system_mode,
                    label="Mode",
                ).props("dense outlined").classes("w-48").on_value_change(set_system_mode)
                fields["layout_mode"] = ui.select(["hex", "grid"], value=settings.layout_mode, label="Layout").props("dense outlined").classes("w-28").on_value_change(persist_and_refresh)
                number_control(fields, "sheet_width_mm", label="Field W", value=settings.sheet_width_mm, default=GUI_DEFAULTS["sheet_width_mm"], min_value=1, width_class="w-24", tooltip="Printable field width in mm.", on_change=persist_and_refresh)
                number_control(fields, "sheet_height_mm", label="Field H", value=settings.sheet_height_mm, default=GUI_DEFAULTS["sheet_height_mm"], min_value=1, width_class="w-24", tooltip="Printable field height in mm.", on_change=persist_and_refresh)
                number_control(fields, "cell_diameter_mm", label="Cell", value=settings.cell_diameter_mm, default=GUI_DEFAULTS["cell_diameter_mm"], min_value=1, width_class="w-24", tooltip="Packing cell diameter and grid step base.", on_change=persist_and_refresh)
                number_control(fields, "gap_mm", label="Gap", value=settings.gap_mm, default=GUI_DEFAULTS["gap_mm"], min_value=0, width_class="w-20", tooltip="Distance between neighboring cell diameters.", on_change=persist_and_refresh)
                number_control(fields, "sheet_margin_mm", label="Margin", value=settings.sheet_margin_mm, default=GUI_DEFAULTS["sheet_margin_mm"], min_value=0, width_class="w-24", tooltip="Safe border inside printable field.", on_change=persist_and_refresh)
                fields["include_rings"] = ui.switch("Rings", value=settings.include_rings).on_value_change(persist_and_refresh)
            real_warning = warning_banner("REAL mode is locked until preflight passes and ARM REAL FLUIDNC is pressed.")
            preflight_label = ui.label("Preflight: not run").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("precision_manufacturing").classes("text-[#8f4f2b]")
                fluidnc_labels["top_status"] = ui.label("Plotter: not connected. Use Plotter Console -> Connect.").classes("text-xs font-bold")

        with ui.grid(columns="300px 1fr 360px").classes("w-full gap-2 min-h-0"):
            with ui.column().classes("gap-2 min-h-0"):
                with ui.column().classes("gap-2 w-full") as test_panel:
                    with ui.card().classes("oracle-card compact-card w-full"):
                        with ui.expansion("Test Generator", icon="science", group="left-column", value=False).classes("w-full"):
                            symbol_options = {"__cycle__": "ALL 8 / cycle one-by-one"}
                            symbol_options.update({symbol.name: symbol.stem for symbol in symbols})
                            fields["selected_symbol"] = ui.select(
                                symbol_options,
                                value=settings.selected_symbol,
                                label="Base symbol mode",
                            ).props("dense outlined").classes("w-full")
                            with ui.row().classes("items-end gap-2"):
                                fields["user_count"] = ui.number("Count", value=settings.user_count, min=1, step=1).props("dense outlined").classes("w-20")
                                fields["live_interval_seconds"] = ui.number("Live sec", value=settings.live_interval_seconds, min=1).props("dense outlined").classes("w-24").on_value_change(live_interval_changed)
                            with ui.row().classes("items-center gap-2"):
                                slider_control(fields, "randomness", label="Random", value=settings.randomness, default=GUI_DEFAULTS["randomness"], min_value=0, max_value=100, step=1, on_change=persist_and_refresh).classes("w-56")
                            with ui.row().classes("items-center gap-2"):
                                slider_control(fields, "randomness_fine", label="Fine", value=settings.randomness_fine, default=GUI_DEFAULTS["randomness_fine"], min_value=-10, max_value=10, step=0.1, on_change=persist_and_refresh).classes("w-44")
                            with ui.row().classes("items-center gap-2"):
                                ui.button("Generate", on_click=generate_user_sessions).props("dense")
                                ui.button("All 8", on_click=generate_all_user_symbols).props("dense")
                                live_toggle = ui.switch("Live", value=False, on_change=toggle_live)
                            last_user_output = ui.label("-").classes("path-label text-xs")

                    with ui.card().classes("oracle-card compact-card w-full"):
                        with ui.expansion("Idle filler bank", icon="inventory_2", group="left-column", value=False).classes("w-full"):
                            ui.label("Creates local idle symbols for empty sheet cells. Usually run once after scale changes.").classes("text-xs text-[#8f4f2b]")
                            with ui.row().classes("items-end gap-2"):
                                fields["idle_variations_per_symbol"] = ui.number(
                                    "Variations/base",
                                    value=settings.idle_variations_per_symbol,
                                    min=1,
                                    step=1,
                                ).props("dense outlined").classes("w-32")
                                ui.button("Generate filler", on_click=generate_idle_bank).props("dense")
                            idle_output = ui.label(str(default_idle_root())).classes("path-label text-xs")

                with ui.card().classes("oracle-card compact-card w-full"):
                    with ui.expansion("Mac mini uploader", icon="cloud_upload", group="left-column", value=False).classes("w-full"):
                        with ui.row().classes("gap-1"):
                            ui.button("Start", on_click=start_macmini).props("dense")
                            ui.button("Stop", on_click=stop_macmini).props("dense")
                            ui.button("Scan", on_click=scan_macmini).props("dense")
                            ui.button("Restart", on_click=restart_macmini).props("dense")
                        ui.label("Controlled through NEJE_MACMINI_AGENT_URL").classes("text-xs text-[#8f4f2b]")

                with ui.card().classes("oracle-card compact-card w-full"):
                    with ui.expansion("Plotter Console", icon="precision_manufacturing", group="left-column", value=True).classes("w-full plotter-console"):
                        ui.label("1. Connect").classes("text-[10px] tracking-[0.2em] text-[#8f4f2b]")
                        with ui.row().classes("gap-1"):
                            ui.button("Connect / Probe", on_click=check_fluidnc).props("dense color=positive")
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
                        fluidnc_labels["message"] = ui.label("Not connected").classes("path-label text-xs font-bold")
                        fluidnc_labels["target"] = ui.label("-").classes("path-label text-[10px] text-[#8f4f2b]")
                        fluidnc_labels["modal"] = ui.label("-").classes("hidden")
                        ui.separator()
                        ui.label("2. Manual control").classes("text-[10px] tracking-[0.2em] text-[#8f4f2b]")
                        ui.label("Manual commands pause print before moving. They are blocked while G-code is streaming.").classes("text-[10px] text-[#8f4f2b]")
                        with ui.row().classes("gap-1 items-end"):
                            fields["jog_step"] = ui.select(
                                {1.0: "1", 5.0: "5", 10.0: "10", 25.0: "25", 50.0: "50", 100.0: "100"},
                                value=1.0,
                                label="Step mm",
                            ).props("dense outlined").classes("w-20")
                            fields["jog_feed"] = ui.number("Feed", value=1000, min=1, step=100).props("dense outlined").classes("w-20")
                            ui.button("Home", on_click=home_all).props("dense color=warning")
                        with ui.grid(columns=3).classes("w-full gap-1 jog-pad"):
                            ui.label("")
                            ui.button("Y+", on_click=lambda: jog("Y", 1)).props("dense")
                            ui.label("")
                            ui.button("X-", on_click=lambda: jog("X", -1)).props("dense")
                            ui.button("Y-", on_click=lambda: jog("Y", -1)).props("dense")
                            ui.button("X+", on_click=lambda: jog("X", 1)).props("dense")
                        with ui.row().classes("gap-1"):
                            ui.button("Home X", on_click=lambda: home_axis("X")).props("dense flat")
                            ui.button("Home Y", on_click=lambda: home_axis("Y")).props("dense flat")
                            ui.button("Unlock", on_click=unlock_alarm).props("dense color=warning")
                            ui.button("Resume", on_click=resume_after_hold).props("dense flat")
                            ui.button("Reset", on_click=soft_reset).props("dense color=negative")
                        ui.separator()
                        ui.label("3. Print").classes("text-[10px] tracking-[0.2em] text-[#8f4f2b]")
                        with ui.row().classes("gap-1"):
                            safe_action_button("Preflight", run_preflight)
                            arm_button = danger_action_button("Arm Real", arm_real_fluidnc)
                        with ui.row().classes("gap-1"):
                            start_print_button = ui.button("Start Print", on_click=start_print).props("dense color=positive")
                            ui.button("Stop After Sheet", on_click=stop_print).props("dense color=warning")
                            reload_button = ui.button("Reload OK", on_click=confirm_reload).props("dense")
                        with ui.row().classes("gap-1"):
                            ui.button("Dry-run Sheet", on_click=generate_dry_run).props("dense")
                            ui.button("Spool", on_click=open_spool).props("dense flat")
                            ui.button("Refresh", on_click=refresh_status).props("dense flat")
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
                        status_labels["pending_reload"] = ui.label("-").classes("hidden")
                        status_labels["latest_manifest"] = ui.label("-").classes("hidden")
                        status_labels["last_sheet_path"] = ui.label("-").classes("hidden")

                with ui.card().classes("oracle-card compact-card w-full"):
                    with ui.expansion("Logs", icon="receipt_long", group="left-column", value=False).classes("w-full"):
                        fields["log_filter"] = ui.select(
                            {"all": "all", "errors": "errors", "system": "system", "plotter": "plotter", "uploader": "uploader", "preflight": "preflight"},
                            value="all",
                            label="Filter",
                        ).props("dense outlined").classes("w-full").on_value_change(refresh_logs)
                        with ui.row().classes("gap-1"):
                            safe_action_button("Refresh", refresh_logs)
                            safe_action_button("Open logs", open_logs)
                        logs_view = log_viewer([])

            with ui.card().classes("oracle-card compact-card w-full min-h-0"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Sheet Preview").classes("text-sm font-bold")
                preview_progress_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
                preview = ui.html().classes("preview-frame w-full")

            with ui.card().classes("oracle-card compact-card w-full"):
                with ui.expansion("Symbol scale correction", icon="graphic_eq", value=True).classes("w-full"):
                    slider_control(fields, "global_scale", label="Global scale", value=settings.global_scale, default=GUI_DEFAULTS["global_scale"], min_value=0.3, max_value=5.0, step=0.01, on_change=persist_and_refresh)
                    ui.label(f"Config: {default_scale_config_path()}").classes("path-label text-xs")
                    ui.label("Double-click any scale slider to reset it to 1.0. Scale changes are applied and saved immediately.").classes("text-xs text-[#8f4f2b]")
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        for symbol in symbols:
                            with ui.column().classes("gap-0"):
                                symbol_previews[symbol.name] = ui.html().classes("symbol-preview")
                                ui.label(symbol.stem[:22]).classes("text-[10px]")
                                slider_control(
                                    fields,
                                    f"scale:{symbol.name}",
                                    label="",
                                    value=scales.get(symbol.name, 1.0),
                                    default=1.0,
                                    min_value=0.3,
                                    max_value=5.0,
                                    step=0.01,
                                    on_change=update_scales_from_fields,
                                )
                    ui.button("Save scales", on_click=save_scales_from_fields).props("dense")

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


def main() -> None:
    ui.page("/")(build_page)
    host = os.getenv("NEJE_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("NEJE_GUI_PORT", "8787"))
    ui.run(host=host, port=port, reload=False, title="Oracle Operator")


if __name__ == "__main__":
    main()
