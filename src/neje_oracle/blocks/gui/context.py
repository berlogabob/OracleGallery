"""Single controller for the Oracle operator GUI.

`GuiContext` holds the shared mutable UI state (field/label dicts, element handles)
and every page-level handler as a method. Workspaces receive one `ctx` instead of a
long list of threaded callbacks, and the FluidNC/motion handlers live here exactly
once instead of being copied across service.py, connection, and calibration.

ponytail: one context object beats ~30 threaded callbacks — this is a plain
state+supervisor bundle, not a DI framework.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from nicegui import run, ui

from .modes import mode_policy
from .support import (
    GUI_DEFAULTS,
    _field_or_default,
    build_preview_svg,
    build_realtime_preview_svg,
    compute_effective_sample_step,
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
from ...shared.models import ComponentStatus, SystemCheckLevel, SystemMode
from ...shared.origin_markers import ALL_ORIGINS
from ...app.supervisor import SupervisorService


VALID_WORKSPACES = {"connection", "calibration", "tests", "work", "exhibition"}


class GuiContext:
    """Owns shared GUI state and every page-level handler."""

    def __init__(self) -> None:
        self.supervisor = SupervisorService()
        self.settings = load_gui_settings()
        self.scales = load_symbol_scales()
        self.symbols = list_base_symbols()

        # Shared mutable UI state, populated as workspaces render.
        self.fields: dict[str, Any] = {}
        self.plotter_labels: dict[str, Any] = {}
        self.queue_labels: dict[str, Any] = {}
        self.thermal_printer_labels: dict[str, Any] = {}
        self.fluidnc_labels: dict[str, Any] = {}
        self.gcode_labels: dict[str, Any] = {}
        self.ready_labels: dict[str, Any] = {}
        self.live_labels: dict[str, Any] = {}
        self.node_pills: dict[str, Any] = {}
        self.uploaded_svg: dict[str, Any] = {"name": "", "bytes": b""}

        store = self.supervisor.runtime_store
        saved_workspace = str(store.load_json("gui_workspace", {"tab": "connection"}).get("tab", "connection"))
        self.active_workspace = {"value": saved_workspace if saved_workspace in VALID_WORKSPACES else "connection"}
        saved_preview_mode = str(store.load_json("gui_preview_mode", {"mode": "preview"}).get("mode", "preview"))
        self.preview_mode = {"value": saved_preview_mode if saved_preview_mode in {"preview", "printing"} else "preview"}

        # Element handles assigned during layout / workspace build.
        self.preview: Any = None
        self.preview_progress_label: Any = None
        self.progress: Any = None
        self.capacity_label: Any = None
        self.system_check_label: Any = None
        self.logs_view: Any = None
        self.uploaded_svg_label: Any = None
        self.start_print_button: Any = None
        self.workspace_tabs: Any = None

    # ---- settings persistence -------------------------------------------------

    def pull_settings_from_fields(self) -> None:
        settings, fields = self.settings, self.fields
        settings.apply_system_mode()
        settings.layout_mode = str(fields["layout_mode"].value)
        settings.cell_diameter_mm = _field_or_default(fields, "cell_diameter_mm")
        settings.gap_mm = _field_or_default(fields, "gap_mm")
        settings.organic_enabled = bool(fields["organic_enabled"].value)
        settings.organic_cell_size_mm = _field_or_default(fields, "organic_cell_size_mm")
        settings.organic_rotation_ramp = _field_or_default(fields, "organic_rotation_ramp")
        settings.organic_scale_ramp = _field_or_default(fields, "organic_scale_ramp")
        settings.organic_seed = int(_field_or_default(fields, "organic_seed"))
        settings.randomness = _field_or_default(fields, "randomness")
        settings.randomness_fine = _field_or_default(fields, "randomness_fine")
        settings.include_rings = bool(fields["include_rings"].value)
        settings.include_markers = bool(fields["include_markers"].value)
        settings.marker_diameter_mm = _field_or_default(fields, "marker_diameter_mm")
        settings.sample_step_mm = _field_or_default(fields, "sample_step_mm")
        settings.sample_density_exponent = _field_or_default(fields, "sample_density_exponent")
        settings.sample_min_step_mm = _field_or_default(fields, "sample_min_step_mm")
        settings.sample_max_step_mm = _field_or_default(fields, "sample_max_step_mm")
        settings.streaming_mode = str(fields["streaming_mode"].value or GUI_DEFAULTS["streaming_mode"])
        settings.show_origins = [
            origin for origin in ALL_ORIGINS if bool(fields.get(f"show_origin:{origin}") and fields[f"show_origin:{origin}"].value)
        ] or list(ALL_ORIGINS)
        settings.print_origins = [
            origin for origin in ALL_ORIGINS if bool(fields.get(f"print_origin:{origin}") and fields[f"print_origin:{origin}"].value)
        ] or list(ALL_ORIGINS)
        settings.sheet_width_mm = _field_or_default(fields, "sheet_width_mm")
        settings.sheet_height_mm = _field_or_default(fields, "sheet_height_mm")
        settings.sheet_margin_mm = _field_or_default(fields, "sheet_margin_mm")
        settings.global_scale = _field_or_default(fields, "global_scale")
        settings.travel_rate = _field_or_default(fields, "travel_rate")
        settings.draw_rate = _field_or_default(fields, "draw_rate")
        settings.xy_acceleration_mm_s2 = _field_or_default(fields, "xy_acceleration_mm_s2")
        settings.z_down_mm = _field_or_default(fields, "z_down_mm")
        settings.z_up_mm = _field_or_default(fields, "z_up_mm")
        settings.z_feed_mm_min = _field_or_default(fields, "z_feed_mm_min")
        settings.direct_svg_origin_x_mm = _field_or_default(fields, "direct_svg_origin_x_mm")
        settings.direct_svg_origin_y_mm = _field_or_default(fields, "direct_svg_origin_y_mm")

    def _save_settings(self) -> None:
        save_gui_settings(self.settings)
        save_oracle_plotter_config(self.settings)

    def persist_and_refresh(self) -> None:
        self.pull_settings_from_fields()
        self._save_settings()
        self.update_preview()
        if self.capacity_label is not None:
            self.capacity_label.set_text(f"{layout_capacity(self.settings)} cells")
        self.update_gcode_detail_labels()
        if self.start_print_button is not None:
            self.start_print_button.enable()
        self.refresh_status()
        self.refresh_component_status()

    def update_gcode_detail_labels(self) -> None:
        if not self.gcode_labels:
            return
        settings = self.settings
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
        self.gcode_labels["effective"].set_text(f"{effective_step:.2f} mm")
        self.gcode_labels["points"].set_text(f"{points_per_100mm:.0f} pts / 100 mm")
        self.gcode_labels["load"].set_text(load)
        self.gcode_labels["limits"].set_text(f"{settings.sample_min_step_mm:g} to {settings.sample_max_step_mm:g} mm")

    def update_scales_from_fields(self) -> None:
        self.pull_settings_from_fields()
        for symbol in self.symbols:
            self.scales[symbol.name] = float(self.fields[f"scale:{symbol.name}"].value or 1.0)
        self._save_settings()
        save_symbol_scales(self.scales)
        self.update_preview()

    # ---- SVG upload / print ---------------------------------------------------

    async def handle_svg_upload(self, event: Any) -> None:
        try:
            name, data = await read_upload_event_payload(event)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"SVG upload failed: {exc}", color="negative")
            return
        if not data:
            ui.notify("SVG upload failed: uploaded file is empty", color="negative")
            return
        self.uploaded_svg["name"] = name
        self.uploaded_svg["bytes"] = data
        self.uploaded_svg_label.set_text(f"Selected: {name}")
        ui.notify(f"Selected SVG: {name}", color="positive")

    async def print_uploaded_svg(self) -> None:
        if not self.uploaded_svg["bytes"]:
            ui.notify("Choose an SVG file first", color="warning")
            return
        self.pull_settings_from_fields()
        self._save_settings()
        ui.notify("Printing SVG...", color="info")
        state = await run.io_bound(
            self.supervisor.print_uploaded_svg,
            self.settings,
            svg_bytes=self.uploaded_svg["bytes"],
            original_name=str(self.uploaded_svg["name"] or "uploaded.svg"),
        )
        if state.status == ComponentStatus.STOPPED:
            self.uploaded_svg["bytes"] = b""
            self.uploaded_svg["name"] = ""
            self.uploaded_svg_label.set_text("No SVG selected")
            ui.notify(state.message, color="positive")
        else:
            ui.notify(state.last_error or state.message, color="negative" if state.status == ComponentStatus.ERROR else "warning")
        self.refresh_status()
        self.refresh_logs()

    async def generate_dry_run(self) -> None:
        self.pull_settings_from_fields()
        try:
            output = await run.io_bound(generate_dry_run_sheet, self.settings)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"G-code generation failed: {exc}", color="negative")
            return
        ui.notify(f"G-code file: {output['gcode']}", color="positive")
        self.refresh_status()

    # ---- preview & status -----------------------------------------------------

    def update_preview(self, status: dict[str, Any] | None = None, queue: dict[str, Any] | None = None) -> None:
        if self.preview is None:
            return
        if self.preview_mode["value"] == "printing":
            status = status if status is not None else read_plotter_status()
            queue = queue if queue is not None else read_queue_status(ttl_seconds=30.0)
            self.preview.content = build_realtime_preview_svg(self.settings, status, queue)
        else:
            self.preview.content = build_preview_svg(
                self.settings,
                user_count=layout_capacity(self.settings),
                idle_count=0,
                randomize_symbols=True,
            )
        self.preview.update()

    def refresh_status(self) -> None:
        status = read_plotter_status()
        queue = read_queue_status(ttl_seconds=30.0)
        total = int(status.get("processed_symbols", 0) or 0)
        pending_users = int(queue.get("pendingUserAfterBaseline", queue.get("pendingAfterBaseline", 0)) or 0)
        progress_percent = float(status.get("sheet_progress_percent", status.get("gcode_progress_percent", 0.0)) or 0.0)
        current_row = int(status.get("current_row_index", 0) or 0)
        current_cell_in_row = int(status.get("current_cell_in_row", 0) or 0)
        row_cell_count = int(status.get("row_cell_count", 0) or 0)
        self.update_preview(status, queue)
        if self.progress is not None:
            self.progress.value = min(max(progress_percent / 100.0, 0.0), 1.0)
        print_enabled = bool(status.get("print_enabled"))
        dry_run = bool(status.get("dry_run"))
        run_mode = str(status.get("run_mode", "-") or "-")
        status_text = str(status.get("status", "-") or "-").replace("_", " ")
        transport_text = "G-CODE ONLY" if dry_run else "FLUIDNC MOTION"
        print_text = "READY" if print_enabled else "STOPPED"
        if self.plotter_labels:
            self.plotter_labels["state"].set_text(f"{status_text.upper()} · {print_text}")
            self.plotter_labels["mode"].set_text(f"{run_mode.upper()} · {transport_text}")
            self.plotter_labels["sheet"].set_text(str(status.get("current_sheet_id") or "no sheet yet"))
            self.plotter_labels["cells"].set_text(
                f"{total}/{layout_capacity(self.settings)} cells · "
                f"user {status.get('user_count', 0)} · idle {status.get('idle_count', 0)}"
            )
            self.plotter_labels["progress"].set_text(
                f"{progress_percent:.0f}% · row {current_row}/{status.get('row_count', 0)} · "
                f"cell {current_cell_in_row}/{row_cell_count} · "
                f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} lines"
            )
            self.plotter_labels["message"].set_text(str(status.get("message", "-") or "-"))
        if self.queue_labels:
            active = int(queue.get("leased", 0) or 0) + int(queue.get("plotting", 0) or 0)
            self.queue_labels["state"].set_text("ONLINE" if queue.get("online") else "OFFLINE")
            self.queue_labels["pending"].set_text(str(pending_users))
            self.queue_labels["active"].set_text(str(active))
            self.queue_labels["failed"].set_text(f"{queue.get('failed', 0)} / {queue.get('skipped', 0)}")
            self.queue_labels["message"].set_text(str(queue.get("message", "-") or "-"))
        readiness = self.supervisor.runtime_store.load_plotter_readiness()
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
        if self.live_labels:
            self.live_labels["fluidnc"].set_text(status_text.upper())
            self.live_labels["zero"].set_text("SET" if readiness.work_zero_set else "NOT SET")
            self.live_labels["firebase"].set_text("REQUIRED" if mode_policy(self.settings.mode).firebase_required else "TEST BYPASS")
            self.live_labels["queue"].set_text("ONLINE" if queue_online else "OFFLINE")
            self.live_labels["sheet"].set_text(current_sheet)
            if not readiness.work_zero_set:
                next_action = "Set work zero"
            elif not print_enabled:
                next_action = "Start print"
            elif pending_users:
                next_action = "Print queued sessions"
            else:
                next_action = "Watch next sheet"
            self.live_labels["next"].set_text(next_action)
            self.live_labels["blockers"].set_text(" · ".join(blockers) if blockers else "none")
        if self.ready_labels:
            self.ready_labels["zero"].set_text("SET" if readiness.work_zero_set else "NOT SET")
            self.ready_labels["message"].set_text(readiness.message)
        if self.preview_progress_label is not None:
            if self.preview_mode["value"] == "printing":
                self.preview_progress_label.set_text(
                    f"{status.get('status', '-')} | {progress_percent:.1f}% | "
                    f"pending real {pending_users} | "
                    f"row {current_row}/{status.get('row_count', 0)} | cell {current_cell_in_row}/{row_cell_count} | "
                    f"{status.get('gcode_lines_sent', 0)}/{status.get('gcode_lines_total', 0)} G-code lines | "
                    f"{total}/{layout_capacity(self.settings)} cells in last sheet"
                )
            else:
                self.preview_progress_label.set_text(f"preview tuning | random symbols | {layout_capacity(self.settings)} cells")
        self.refresh_component_status()

    def refresh_component_status(self) -> None:
        states = self.supervisor.refresh_all_status()
        if self.live_labels:
            firebase_state = states.get("firebase")
            if firebase_state is not None:
                self.live_labels["firebase"].set_text(firebase_state.status.value.upper())
        if self.node_pills:
            from .ui import update_status_pill

            update_status_pill(self.node_pills["fluidnc"], states.get("fluidnc"), "Plotter")
            update_status_pill(self.node_pills["macmini"], states.get("macmini_uploader"), "Mac mini")
            update_status_pill(self.node_pills["firebase"], states.get("firebase"), "Firebase")
            update_status_pill(self.node_pills["queue"], states.get("queue"), "Queue")
            update_status_pill(self.node_pills["print"], states.get("print"), "Print")

    def refresh_logs(self) -> None:
        from ...shared.logging import read_logs

        if self.logs_view is None:
            return
        selected = str(self.fields["log_filter"].value or "all") if "log_filter" in self.fields else "all"
        self.logs_view.value = "\n".join(read_logs(category_filter=selected, limit=100))
        self.logs_view.update()

    def open_logs(self) -> None:
        subprocess.run(["open", str(self.supervisor.settings.logs_root)], check=False)

    # ---- system lifecycle -----------------------------------------------------

    async def start_system(self) -> None:
        self.pull_settings_from_fields()
        self._save_settings()
        await run.io_bound(self.supervisor.start_system, gui_settings_to_plotter_config(self.settings))
        ui.notify("System supervisor started in safe mode", color="positive")
        self.refresh_status()

    async def stop_system(self) -> None:
        await run.io_bound(self.supervisor.stop_system)
        ui.notify("System stopped safely", color="warning")
        self.refresh_status()

    async def reset_baseline(self) -> None:
        state = await run.io_bound(self.supervisor.reset_run_baseline)
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        self.refresh_status()

    def set_system_mode(self, mode: SystemMode, *, notify: bool = True) -> None:
        self.settings.system_mode = mode.value
        self.settings.apply_system_mode()
        self._save_settings()
        self.supervisor.set_system_mode(self.settings.mode)
        if notify:
            ui.notify(f"Mode set to {mode_policy(self.settings.mode).label}.", color="warning")
        self.refresh_status()

    def workspace_changed(self, value: Any) -> None:
        workspace = _workspace_name(value)
        if workspace in VALID_WORKSPACES:
            self.active_workspace["value"] = workspace
            self.supervisor.runtime_store.save_json("gui_workspace", {"tab": workspace})
        if workspace == "tests":
            if self.settings.mode != SystemMode.TEST:
                self.set_system_mode(SystemMode.TEST, notify=False)
            return
        if self.settings.mode == SystemMode.TEST:
            self.set_system_mode(SystemMode.EXHIBITION, notify=False)

    def preview_mode_changed(self, value: Any) -> None:
        mode = str(value or "preview")
        self.preview_mode["value"] = mode if mode in {"preview", "printing"} else "preview"
        self.supervisor.runtime_store.save_json("gui_preview_mode", {"mode": self.preview_mode["value"]})
        self.update_preview()

    def restore_workspace(self) -> None:
        if self.workspace_tabs is None:
            return
        self.workspace_tabs.value = self.active_workspace["value"]
        self.workspace_tabs.update()

    async def run_system_check(self, *, notify_success: bool = False) -> bool:
        self.pull_settings_from_fields()
        self._save_settings()
        result = await run.io_bound(self.supervisor.run_system_check, self.settings)
        self.refresh_system_check_result()
        self.refresh_component_status()
        self.refresh_logs()
        if result.has_critical:
            first_critical = next((check for check in result.checks if check.level == SystemCheckLevel.CRITICAL), None)
            message = first_critical.message if first_critical is not None else "System is not ready"
            ui.notify(f"Cannot start: {message}", color="negative")
            return False
        if notify_success:
            ui.notify("System check passed", color="positive" if result.status == SystemCheckLevel.OK else "warning")
        return True

    def refresh_system_check_result(self) -> None:
        if self.system_check_label is None:
            return
        result = self.supervisor.runtime_store.load_system_check_result()
        if not result:
            self.system_check_label.set_text("System check: not run")
            return
        critical = sum(1 for check in result.checks if check.level == SystemCheckLevel.CRITICAL)
        warnings = sum(1 for check in result.checks if check.level == SystemCheckLevel.WARNING)
        ok_count = sum(1 for check in result.checks if check.level == SystemCheckLevel.OK)
        self.system_check_label.set_text(f"System check: {critical} blocked · {warnings} warnings · {ok_count} ok")

    async def start_print(self) -> None:
        self.pull_settings_from_fields()
        self._save_settings()
        ui.notify("Checking plotter before START PRINT...", color="info")
        if not await self.run_system_check():
            self.refresh_status()
            return
        plotter_state = await run.io_bound(self.supervisor.start_plotter, gui_settings_to_plotter_config(self.settings))
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start: {plotter_state.last_error or plotter_state.message}", color="negative")
            self.refresh_status()
            self.refresh_logs()
            return
        state = await run.io_bound(self.supervisor.start_print, self.settings)
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        self.refresh_status()

    async def start_test_print(self) -> None:
        self.set_system_mode(SystemMode.TEST, notify=False)
        self.pull_settings_from_fields()
        self._save_settings()
        ui.notify("Checking FluidNC before TEST PRINT...", color="info")
        probe = await run.io_bound(self.supervisor.probe_fluidnc, scan=False)
        if probe is None:
            ui.notify("FluidNC must be connected and Idle before START TEST PRINT.", color="warning")
            self.refresh_status()
            self.refresh_logs()
            return
        self.update_fluidnc_labels({**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port})
        self.supervisor.check_fluidnc(probe)
        if not (probe.online and probe.controller.is_idle):
            ui.notify("FluidNC must be connected and Idle before START TEST PRINT.", color="warning")
            self.refresh_status()
            self.refresh_logs()
            return
        if not await self.run_system_check():
            return
        plotter_state = await run.io_bound(self.supervisor.start_plotter, gui_settings_to_plotter_config(self.settings))
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start test print: {plotter_state.last_error or plotter_state.message}", color="negative")
            self.refresh_status()
            self.refresh_logs()
            return
        state = await run.io_bound(self.supervisor.start_print, self.settings)
        ui.notify(f"TEST PRINT: {state.message}", color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        self.refresh_status()
        self.refresh_logs()

    # ---- FluidNC / motion (one copy, shared by connection + calibration) ------

    def update_fluidnc_labels(self, result: dict[str, Any]) -> None:
        labels = self.fluidnc_labels
        if "webui" in labels:
            labels["webui"].set_text("online" if result.get("http_online") else "offline")
        if "telnet" in labels:
            labels["telnet"].set_text("online" if result.get("telnet_online") else "offline")
        if "state" in labels:
            labels["state"].set_text(str(result.get("controller_state") or "Unknown"))
        if "mpos" in labels:
            labels["mpos"].set_text(_format_gui_tuple(result.get("machine_position")))
        if "pins" in labels:
            labels["pins"].set_text(str(result.get("pins") or "none"))
        if "modal" in labels:
            labels["modal"].set_text(str(result.get("modal_state") or "-").replace("\n", " | "))
        if "target" in labels:
            labels["target"].set_text(f"{result.get('http_url') or '-'} · {result.get('host')}:{result.get('port')}")
        if "message" in labels:
            labels["message"].set_text(str(result.get("message") or result.get("last_error") or "-"))

    def confirm_action(self, title: str, message: str, action: Any) -> None:
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
                    self.refresh_status()
                    self.refresh_logs()

            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("dense flat")
                ui.button("Confirm", on_click=confirmed).props("dense color=warning")
        dialog.open()

    async def fluidnc_action(self, label: str, action: Any, *, refresh_probe: bool = True) -> None:
        ui.notify(f"Sending {label}...", color="info")
        try:
            state = await run.io_bound(action)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"{label} failed: {exc}", color="negative")
            self.refresh_status()
            self.refresh_logs()
            self.restore_workspace()
            return
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        if refresh_probe:
            await self.check_fluidnc(scan=False)
        self.refresh_status()
        self.refresh_logs()
        self.restore_workspace()

    async def check_fluidnc(self, *, scan: bool = False) -> None:
        ui.notify("Checking FluidNC...", color="info")
        try:
            probe = await run.io_bound(self.supervisor.probe_fluidnc, scan=scan)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"FluidNC check failed: {exc}", color="negative")
            self.refresh_logs()
            self.restore_workspace()
            return
        if probe is None:  # ponytail: no configured endpoint yet — offline, not an error
            self.update_fluidnc_labels({"controller_state": "Offline", "message": "No FluidNC endpoint configured"})
            self.restore_workspace()
            return
        self.supervisor.check_fluidnc(probe)
        result = {**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port}
        self.update_fluidnc_labels(result)
        ui.notify(probe.message, color="positive" if probe.online else "negative")
        self.refresh_logs()
        self.restore_workspace()

    async def scan_fluidnc(self) -> None:
        await self.check_fluidnc(scan=True)

    def set_work_zero(self) -> None:
        self.confirm_action(
            "SET WORK ZERO",
            "Current XY becomes G54 X0 Y0. Z is not zeroed; Z moves use absolute configured values. Use after placing the tool at the upper-left origin.",
            lambda: self.fluidnc_action("set work zero", self.supervisor.set_work_zero),
        )

    def home_xy(self) -> None:
        self.confirm_action(
            "HOME ALL",
            "The plotter will run FluidNC homing command $H. Use this when FluidNC rejects single-axis homing.",
            lambda: self.fluidnc_action("home all", self.supervisor.home_xy_fluidnc, refresh_probe=False),
        )

    def home_axis(self, axis: str) -> None:
        self.confirm_action(
            f"HOME {axis}",
            f"Single-axis homing sends $H={axis}. Use only if this FluidNC config supports it.",
            lambda: self.fluidnc_action(f"home {axis}", lambda: self.supervisor.home_fluidnc(axis), refresh_probe=False),
        )

    async def jog(self, axis: str, sign: float) -> None:
        distance = sign * float(self.fields["jog_step"].value or 1)
        feed = float(self.fields["jog_feed"].value or 1000)
        await self.fluidnc_action(f"jog {axis}", lambda: self.supervisor.jog_fluidnc(axis, distance, feed), refresh_probe=False)

    async def jog_x_negative(self) -> None:
        await self.jog("X", -1)

    async def jog_x_positive(self) -> None:
        await self.jog("X", 1)

    async def jog_y_negative(self) -> None:
        await self.jog("Y", -1)

    async def jog_y_positive(self) -> None:
        await self.jog("Y", 1)

    async def pen_up(self) -> None:
        await self.fluidnc_action("pen up", self.supervisor.pen_up_fluidnc, refresh_probe=False)

    async def pen_down(self) -> None:
        await self.fluidnc_action("pen down", self.supervisor.pen_down_fluidnc, refresh_probe=False)

    def unlock_alarm(self) -> None:
        self.confirm_action("UNLOCK ALARM", "This sends $X. It clears FluidNC alarm state without moving the machine.", lambda: self.fluidnc_action("unlock", self.supervisor.unlock_fluidnc_alarm))

    async def emergency_stop(self) -> None:
        state = await run.io_bound(self.supervisor.emergency_stop_fluidnc)
        ui.notify(state.message, color="negative")
        self.refresh_status()
        self.refresh_logs()

    def resume_after_hold(self) -> None:
        self.confirm_action("RESUME AFTER HOLD", "This sends realtime cycle start ~. Confirm only if the machine is safe to resume.", lambda: self.fluidnc_action("resume", self.supervisor.resume_fluidnc))

    def soft_reset(self) -> None:
        self.confirm_action("SOFT RESET / ABORT", "This sends Ctrl-X and disables print. Use only to abort/reset FluidNC.", lambda: self.fluidnc_action("soft reset", self.supervisor.soft_reset_fluidnc))

    # ---- Mac mini uploader ----------------------------------------------------

    async def start_macmini(self) -> None:
        await run.io_bound(self.supervisor.start_macmini_uploader)
        self.refresh_component_status()

    async def stop_macmini(self) -> None:
        await run.io_bound(self.supervisor.stop_macmini_uploader)
        self.refresh_component_status()

    async def restart_macmini(self) -> None:
        await run.io_bound(self.supervisor.restart_macmini_uploader)
        self.refresh_component_status()

    async def scan_macmini(self) -> None:
        await run.io_bound(self.supervisor.scan_macmini_once)
        self.refresh_component_status()

    # ---- thermal printer (through the supervisor facade) ----------------------

    def _thermal_url(self) -> str:
        url = str(self.fields["thermal_printer_url"].value or "").strip()
        self.supervisor.save_thermal_printer_url(url)
        return url

    def _update_thermal_label(self, message: str) -> None:
        if self.thermal_printer_labels:
            self.thermal_printer_labels["message"].set_text(message[:220] or "-")

    def latest_receipt_session_dir(self) -> Path | None:
        return self.supervisor.latest_receipt_session_dir()

    async def thermal_printer_status(self) -> None:
        url = self._thermal_url()
        ok, output = await run.io_bound(self.supervisor.thermal_status, esp32_url=url)
        self._update_thermal_label(output)
        ui.notify("Thermal printer status updated" if ok else "Thermal printer offline", color="positive" if ok else "warning")

    async def thermal_printer_connect(self) -> None:
        url = self._thermal_url()
        ok, output = await run.io_bound(self.supervisor.thermal_connect, esp32_url=url)
        self._update_thermal_label(output)
        ui.notify("Thermal printer connected" if ok else "Thermal printer connection failed", color="positive" if ok else "warning")

    async def thermal_printer_test_receipt(self) -> None:
        url = self._thermal_url()
        ok, output = await run.io_bound(self.supervisor.thermal_test, message="ORACLE THERMAL TEST", esp32_url=url)
        self._update_thermal_label(output)
        ui.notify("Thermal test sent" if ok else "Thermal test failed", color="positive" if ok else "warning")

    async def _thermal_print_session(self, session_dir: Path | None) -> None:
        if session_dir is None or not session_dir.exists():
            ui.notify("No receipt session folder found", color="warning")
            return
        url = self._thermal_url()
        ok, output = await run.io_bound(self.supervisor.thermal_print_receipt, session_dir, esp32_url=url)
        self._update_thermal_label(output)
        ui.notify(f"Thermal receipt sent: {session_dir.name}" if ok else "Thermal receipt failed", color="positive" if ok else "warning")

    async def thermal_printer_print_latest(self) -> None:
        await self._thermal_print_session(self.latest_receipt_session_dir())

    async def thermal_printer_print_selected(self) -> None:
        raw = str(self.fields["thermal_session_dir"].value or "").strip()
        await self._thermal_print_session(Path(raw).expanduser() if raw else self.latest_receipt_session_dir())


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
