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
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from nicegui import run, ui

from ...app.supervisor import SupervisorService
from ...shared.models import ComponentStatus, SystemCheckLevel, SystemMode
from ...shared.origin_markers import ALL_ORIGINS
from .modes import mode_policy
from .support import (
    GUI_DEFAULTS,
    _field_or_default,
    build_preview_svg,
    build_realtime_preview_svg,
    compute_effective_sample_step,
    generate_dry_run_sheet,
    generate_pen_cal_sheet,
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
from .ui import helper_text, notify_if_connected

# The three screens. Anything else -- including the seven module-named tabs these replaced --
# falls back to PRINT, which is where an operator should land anyway.
VALID_WORKSPACES = {"print", "create", "setup"}


_T = TypeVar("_T")


class GuiContext:
    """Owns shared GUI state and every page-level handler."""

    async def _blocking(self, func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        """Run a blocking call off the event loop and require a result.

        nicegui's ``run.io_bound`` is typed Optional because it yields None when the
        task is cancelled (client disconnect, shutdown). Callers that consume the
        result would otherwise raise ``AttributeError: 'NoneType' has no attribute
        'status'`` deep inside a handler, losing the print outcome silently. Narrow it
        once here. Fire-and-forget calls keep using ``run.io_bound`` directly, since
        cancellation is harmless there.
        """
        result = await run.io_bound(func, *args, **kwargs)
        if result is None:
            name = getattr(func, "__name__", repr(func))
            raise RuntimeError(f"{name} was cancelled before returning a result")
        return result

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
        self.uploaded_svg: dict[str, Any] = {"name": "", "bytes": b""}
        self.run_profile_select: Any = None
        # What the machine rail's primary button will do when pressed, kept in step with
        # the readiness state machine in refresh_status().
        self.next_action_key = "watch"
        self.next_action_button: Any = None
        self.next_action_hint: Any = None
        self.blockers_label: Any = None
        self.position_label: Any = None

        store = self.supervisor.runtime_store
        saved_workspace = str(store.load_json("gui_workspace", {"tab": "print"}).get("tab", "print"))
        self.active_workspace = {"value": saved_workspace if saved_workspace in VALID_WORKSPACES else "print"}
        self.preview_mode = {"value": "preview"}

        # Dedup state for the FluidNC offline toast: only notify once per offline
        # transition instead of on every status check (CONNECT click, periodic
        # probe after another action, etc). The live-strip "Now" metric stays as
        # the persistent indicator while this stays quiet in between transitions.
        self._fluidnc_offline_notified = False

        # Element handles assigned during layout / workspace build.
        self.preview: Any = None
        self.preview_progress_label: Any = None
        self.progress: Any = None
        self.capacity_label: Any = None
        self.system_check_label: Any = None
        self.logs_view: Any = None
        self.uploaded_svg_label: Any = None
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
        # Guarded, unlike the calibration fields above: the generative workspace is not
        # always built (tests render subsets), so these two may legitimately be absent.
        if (stream_switch := fields.get("stream_enabled")) is not None:
            settings.stream_enabled = bool(stream_switch.value)
        if (stream_interval := fields.get("stream_interval_seconds")) is not None:
            settings.stream_interval_seconds = float(stream_interval.value or GUI_DEFAULTS["stream_interval_seconds"])
        settings.marker_diameter_mm = _field_or_default(fields, "marker_diameter_mm")
        settings.sample_step_mm = _field_or_default(fields, "sample_step_mm")
        settings.sample_density_exponent = _field_or_default(fields, "sample_density_exponent")
        settings.sample_min_step_mm = _field_or_default(fields, "sample_min_step_mm")
        settings.sample_max_step_mm = _field_or_default(fields, "sample_max_step_mm")
        settings.streaming_mode = str(fields["streaming_mode"].value or GUI_DEFAULTS["streaming_mode"])
        settings.show_origins = [
            origin
            for origin in ALL_ORIGINS
            if bool(fields.get(f"show_origin:{origin}") and fields[f"show_origin:{origin}"].value)
        ] or list(ALL_ORIGINS)
        settings.print_origins = [
            origin
            for origin in ALL_ORIGINS
            if bool(fields.get(f"print_origin:{origin}") and fields[f"print_origin:{origin}"].value)
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
        # Pen profile fields. pen_width_mm existed on GuiSettings long before it was
        # pulled here, which is why it had no working GUI control: a widget missing from
        # this method silently never persists.
        settings.pen_width_mm = _field_or_default(fields, "pen_width_mm")
        settings.pen_down_dwell_ms = _field_or_default(fields, "pen_down_dwell_ms")
        settings.direct_svg_origin_x_mm = _field_or_default(fields, "direct_svg_origin_x_mm")
        settings.direct_svg_origin_y_mm = _field_or_default(fields, "direct_svg_origin_y_mm")
        # Image workspace. Guarded like the stream pair above, and for the same reason: this
        # tab is not always built. image_quality is absent on purpose — its widget is a preset
        # index, so image.py mirrors the name straight onto settings instead.
        if (control := fields.get("image_mode")) is not None:
            settings.image_mode = str(control.value)
        if (control := fields.get("image_source")) is not None:
            settings.image_source = str(control.value)
        if (control := fields.get("image_width_mm")) is not None:
            settings.image_width_mm = float(control.value or GUI_DEFAULTS["image_width_mm"])
        if (control := fields.get("image_height_mm")) is not None:
            settings.image_height_mm = float(control.value or GUI_DEFAULTS["image_height_mm"])
        if (control := fields.get("image_cell_mm")) is not None:
            settings.image_cell_mm = float(control.value or GUI_DEFAULTS["image_cell_mm"])
        if (control := fields.get("image_detail")) is not None:
            settings.image_detail = float(control.value or GUI_DEFAULTS["image_detail"])
        if (control := fields.get("image_gamma")) is not None:
            settings.image_gamma = float(control.value or GUI_DEFAULTS["image_gamma"])
        if (control := fields.get("image_invert")) is not None:
            settings.image_invert = bool(control.value)
        if (control := fields.get("image_show_travel")) is not None:
            settings.image_show_travel = bool(control.value)
        if (control := fields.get("sheet_cell_width_mm")) is not None:
            settings.sheet_cell_width_mm = float(control.value or GUI_DEFAULTS["sheet_cell_width_mm"])
        if (control := fields.get("sheet_cell_height_mm")) is not None:
            settings.sheet_cell_height_mm = float(control.value or GUI_DEFAULTS["sheet_cell_height_mm"])
        if (control := fields.get("sheet_gap_mm")) is not None:
            # `or` would turn a deliberate 0 into the default, and 0 is the setting that butts
            # the cells together — the whole point of the control.
            settings.sheet_gap_mm = float(control.value if control.value is not None else GUI_DEFAULTS["sheet_gap_mm"])
        if (control := fields.get("sheet_padding_mm")) is not None:
            settings.sheet_padding_mm = float(
                control.value if control.value is not None else GUI_DEFAULTS["sheet_padding_mm"]
            )
        if (control := fields.get("sheet_shape")) is not None:
            settings.sheet_shape = str(control.value)
        if (control := fields.get("motif_mode")) is not None:
            settings.motif_mode = str(control.value)
        if (control := fields.get("motif_cell_mm")) is not None:
            settings.motif_cell_mm = float(control.value or GUI_DEFAULTS["motif_cell_mm"])
        if (control := fields.get("motif_gamma")) is not None:
            settings.motif_gamma = float(control.value or GUI_DEFAULTS["motif_gamma"])
        if (control := fields.get("motif_autocontrast")) is not None:
            settings.motif_autocontrast = bool(control.value)
        if (control := fields.get("motif_invert")) is not None:
            settings.motif_invert = bool(control.value)
        if (control := fields.get("motif_despeckle_mm")) is not None:
            # Same zero-is-meaningful case: 0 mm is "keep every speck".
            settings.motif_despeckle_mm = float(
                control.value if control.value is not None else GUI_DEFAULTS["motif_despeckle_mm"]
            )
        if (control := fields.get("motif_simplify_mm")) is not None:
            settings.motif_simplify_mm = float(
                control.value if control.value is not None else GUI_DEFAULTS["motif_simplify_mm"]
            )

    def _save_settings(self) -> None:
        save_gui_settings(self.settings)
        save_oracle_plotter_config(self.settings)

    def save_settings(self) -> None:
        """Persist without re-reading every widget.

        pull_settings_from_fields() indexes the calibration fields directly, so it only
        works once that workspace has been built. Controls that already hold their own
        value save through here instead of depending on an unrelated tab existing.
        """
        self._save_settings()

    def persist_and_refresh(self) -> None:
        self.pull_settings_from_fields()
        self._save_settings()
        self.update_preview()
        if self.capacity_label is not None:
            self.capacity_label.set_text(f"{layout_capacity(self.settings)} cells")
        self.update_gcode_detail_labels()
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
        state = await self._blocking(
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
            ui.notify(
                state.last_error or state.message,
                color="negative" if state.status == ComponentStatus.ERROR else "warning",
            )
        self.refresh_status()
        self.refresh_logs()

    async def print_svg_payload(self, svg_bytes: bytes, name: str) -> bool:
        """Print an SVG built in-process (line text, image conversion). Returns success."""
        if not svg_bytes:
            ui.notify("Nothing to print yet", color="warning")
            return False
        self.pull_settings_from_fields()
        self._save_settings()
        ui.notify("Printing SVG...", color="info")
        state = await self._blocking(
            self.supervisor.print_uploaded_svg,
            self.settings,
            svg_bytes=svg_bytes,
            original_name=name,
        )
        ok = state.status == ComponentStatus.STOPPED
        if ok:
            ui.notify(state.message, color="positive")
        else:
            ui.notify(
                state.last_error or state.message,
                color="negative" if state.status == ComponentStatus.ERROR else "warning",
            )
        self.refresh_status()
        self.refresh_logs()
        return ok

    async def generate_dry_run(self) -> None:
        self.pull_settings_from_fields()
        try:
            output = await self._blocking(generate_dry_run_sheet, self.settings)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"G-code generation failed: {exc}", color="negative")
            return
        ui.notify(f"G-code file: {output['gcode']}", color="positive")
        self.refresh_status()

    async def generate_pen_cal(self) -> None:
        """Write the pen calibration sheet for the fitted pen."""
        self.pull_settings_from_fields()
        try:
            output = await self._blocking(generate_pen_cal_sheet, self.settings)
        except Exception as exc:  # noqa: BLE001
            # A sheet that will not fit the bed raises rather than being clipped, and
            # that is a normal outcome when the ladders are widened.
            ui.notify(f"Pen calibration sheet failed: {exc}", color="negative")
            return
        ui.notify(f"Pen calibration G-code: {output['gcode']}", color="positive")
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
            # Real sheets are mostly filler, and filler cells are drawn with a second ring
            # (svg_gcode.ring_radii_mm). Asking for a sheet of nothing but user cells drew
            # one ring per cell on screen while the pen put two on the paper, and stamped
            # every origin dot in the user corner. Ask for the mix the daemon will claim.
            queue = queue if queue is not None else read_queue_status(ttl_seconds=30.0)
            capacity = layout_capacity(self.settings)
            pending = int(queue.get("pendingUserAfterBaseline", queue.get("pendingAfterBaseline", 0)) or 0)
            user_count = max(0, min(pending, capacity))
            self.preview.content = build_preview_svg(
                self.settings,
                user_count=user_count,
                idle_count=capacity - user_count,
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
        status_text = str(status.get("status", "-") or "-").replace("_", " ")
        if self.plotter_labels:
            self.plotter_labels["sheet"].set_text(str(status.get("current_sheet_id") or "no sheet yet"))
            self.plotter_labels["cells"].set_text(
                f"{total}/{layout_capacity(self.settings)} cells · "
                f"user {status.get('user_count', 0)} · idle {status.get('idle_count', 0)}"
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
        if self.run_profile_select is not None and self.run_profile_select.value != self.settings.system_mode:
            # START TEST PRINT switches the profile on the operator's behalf; the selector
            # is the only place that says so, so it has to follow.
            self.run_profile_select.value = self.settings.system_mode
        # Computed whether or not anything is rendered: the machine rail's primary button
        # reads it, and the rail exists independently of the live strip.
        if not readiness.work_zero_set:
            next_action, self.next_action_key = "Set work zero", "work_zero"
        elif not print_enabled:
            next_action, self.next_action_key = "Start print", "start_print"
        elif pending_users:
            next_action, self.next_action_key = "Print queued sessions", "start_print"
        else:
            next_action, self.next_action_key = "Watch next sheet", "watch"
        if self.live_labels:
            self._set_state_chip(status_text)
            self.live_labels["zero"].set_text("SET" if readiness.work_zero_set else "NOT SET")
            # The firebase tile has one writer: refresh_component_status (called below)
            # shows whether Firebase is UP; whether it is *required* lives in the
            # run-profile select, not here.
            self.live_labels["queue"].set_text("ONLINE" if queue_online else "OFFLINE")
            self.live_labels["sheet"].set_text(current_sheet)
        if self.blockers_label is not None:
            self.blockers_label.set_text(f"blockers: {' · '.join(blockers)}" if blockers else "nothing blocking")
        if self.next_action_button is not None:
            # The button renders only when starting a print, which is the one action whose
            # home is this button. For "set work zero" the hint points at the rail's own
            # SET WORK ZERO control instead of duplicating it -- the audit found that pair
            # rendered two identical buttons two cards apart in the same rail.
            if self.next_action_key == "start_print":
                self.next_action_button.set_text(next_action.upper())
                self.next_action_button.set_visibility(True)
                hint = ""
            elif self.next_action_key == "work_zero":
                self.next_action_button.set_visibility(False)
                hint = "Jog to the paper origin, then SET WORK ZERO below."
            else:
                self.next_action_button.set_visibility(False)
                hint = "Sheet is drawing."
            if self.next_action_hint is not None:
                self.next_action_hint.set_text(hint)
                self.next_action_hint.set_visibility(bool(hint))
        if self.ready_labels:
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
                # Say what this actually is. Geometry, ring counts and the user/filler mix
                # are now the real ones; which symbol lands in which cell is still decided
                # when the sheet is built, so the caption promises layout and nothing more.
                capacity = layout_capacity(self.settings)
                filler = max(0, capacity - min(pending_users, capacity))
                self.preview_progress_label.set_text(
                    f"layout preview | {capacity} cells | "
                    f"{min(pending_users, capacity)} queued, {filler} filler | "
                    "symbols picked at print time"
                )
        self.refresh_component_status()

    def refresh_component_status(self) -> None:
        states = self.supervisor.refresh_all_status()
        if self.live_labels:
            firebase_state = states.get("firebase")
            if firebase_state is not None:
                self.live_labels["firebase"].set_text(firebase_state.status.value.upper())

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
        state = await self._blocking(self.supervisor.reset_run_baseline)
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

    def run_profile_changed(self, value: Any) -> None:
        """The operator's explicit choice of run profile, replacing the tab-name coupling."""
        mode = SystemMode(str(value))
        if mode != self.settings.mode:
            self.set_system_mode(mode)

    def workspace_changed(self, value: Any) -> None:
        """Record which workspace is open. Navigation changes nothing else.

        This used to derive the system mode from the tab name -- TEST for tests/generative/
        image, EXHIBITION for everything else -- so merely opening a tab to look at it
        silently rewrote Firebase and test-tool policy, and persisted that. The guard added
        for the mid-print case only narrowed the blast radius; the coupling itself was the
        bug. Mode is an operator decision, made in the run-profile selector in service.py.
        """
        workspace = _workspace_name(value)
        if workspace in VALID_WORKSPACES:
            self.active_workspace["value"] = workspace
            self.supervisor.runtime_store.save_json("gui_workspace", {"tab": workspace})

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
        result = await self._blocking(self.supervisor.run_system_check, self.settings)
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
        plotter_state = await self._blocking(
            self.supervisor.start_plotter, gui_settings_to_plotter_config(self.settings)
        )
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start: {plotter_state.last_error or plotter_state.message}", color="negative")
            self.refresh_status()
            self.refresh_logs()
            return
        state = await self._blocking(self.supervisor.start_print, self.settings)
        ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        self.refresh_status()

    async def start_test_print(self) -> None:
        self.set_system_mode(SystemMode.TEST, notify=False)
        self.pull_settings_from_fields()
        self._save_settings()
        ui.notify("Checking FluidNC before TEST PRINT...", color="info")
        probe = await self._blocking(self.supervisor.probe_fluidnc, scan=False)
        if probe is None:
            ui.notify("FluidNC must be connected and Idle before START TEST PRINT.", color="warning")
            self.refresh_status()
            self.refresh_logs()
            return
        self.update_fluidnc_labels(
            {**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port}
        )
        self.supervisor.check_fluidnc(probe)
        if not (probe.online and probe.controller.is_idle):
            ui.notify("FluidNC must be connected and Idle before START TEST PRINT.", color="warning")
            self.refresh_status()
            self.refresh_logs()
            return
        if not await self.run_system_check():
            return
        plotter_state = await self._blocking(
            self.supervisor.start_plotter, gui_settings_to_plotter_config(self.settings)
        )
        if plotter_state.status == ComponentStatus.ERROR:
            ui.notify(f"Cannot start test print: {plotter_state.last_error or plotter_state.message}", color="negative")
            self.refresh_status()
            self.refresh_logs()
            return
        state = await self._blocking(self.supervisor.start_print, self.settings)
        ui.notify(
            f"TEST PRINT: {state.message}", color="positive" if state.status == ComponentStatus.RUNNING else "warning"
        )
        self.refresh_status()
        self.refresh_logs()

    # ---- FluidNC / motion (one copy, shared by connection + calibration) ------

    # Glyph first, colour second. ISA-101 and the high-performance-HMI literature both
    # insist state is never encoded by colour alone -- an operator glancing across a room,
    # or one of the ~8% of men with a colour vision deficiency, has to read it either way.
    _STATE_MARKS = (
        ("alarm", "\u25b2", "state-danger"),
        ("error", "\u25b2", "state-danger"),
        ("hold", "\u25ae\u25ae", "state-warn"),
        ("paus", "\u25ae\u25ae", "state-warn"),
        ("run", "\u25b6", "state-run"),
        ("jog", "\u25b6", "state-run"),
        ("idle", "\u25cf", "state-ok"),
    )

    def _set_state_chip(self, status_text: str) -> None:
        chip = self.live_labels.get("fluidnc")
        if chip is None:
            return
        lowered = status_text.lower()
        glyph, tone = "\u2715", "state-offline"
        for needle, mark, css in self._STATE_MARKS:
            if needle in lowered:
                glyph, tone = mark, css
                break
        chip.set_text(f"{glyph}  {status_text.upper()}")
        chip.classes(replace=f"state-chip {tone}")

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
        if self.position_label is not None:
            # The position readout belongs in the persistent bar, not buried in the
            # connection details: knowing where the head is matters most while jogging,
            # which happens from every screen.
            position = result.get("machine_position")
            self.position_label.set_text(
                f"X {position[0]:.1f} · Y {position[1]:.1f}"
                if isinstance(position, (list, tuple)) and len(position) >= 2
                else "X — · Y —"
            )
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
            helper_text(message)

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

    def _notify_fluidnc_offline(self, detail: str) -> None:
        """Show one friendly, dismissible offline notice per offline transition.

        The raw technical detail (host:port, timeout kind) is demoted to a
        secondary caption here and is also already routed to the logs view via
        supervisor.check_fluidnc()/refresh_logs(). Repeated checks while still
        offline (CONNECT re-clicks, incidental probes after other FluidNC
        actions) are suppressed until the state flips back online.
        """
        if self._fluidnc_offline_notified:
            return
        self._fluidnc_offline_notified = True
        ui.notify(
            "Plotter offline — check power and WiFi, then press CONNECT on SETUP.",
            caption=detail,
            type="negative",
            close_button="DISMISS",
            timeout=0,
        )

    async def fluidnc_action(
        self, label: str, action: Any, *, refresh_probe: bool = True, success_message: str | None = None
    ) -> None:
        ui.notify(f"Sending {label}...", color="info")
        try:
            state = await self._blocking(action)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"{label} failed: {exc}", color="negative")
            self.refresh_status()
            self.refresh_logs()
            self.restore_workspace()
            return
        if state.status == ComponentStatus.RUNNING and success_message:
            ui.notify(success_message, color="positive")
        else:
            ui.notify(state.message, color="positive" if state.status == ComponentStatus.RUNNING else "warning")
        if refresh_probe:
            await self.check_fluidnc(scan=False)
        self.refresh_status()
        self.refresh_logs()
        self.restore_workspace()

    async def check_fluidnc(self, *, scan: bool = False) -> None:
        notify_if_connected("Checking FluidNC...", color="info")
        try:
            probe = await self._blocking(self.supervisor.probe_fluidnc, scan=scan)
        except Exception as exc:  # noqa: BLE001
            notify_if_connected(f"FluidNC check failed: {exc}", color="negative")
            self.refresh_logs()
            self.restore_workspace()
            return
        if probe is None:  # ponytail: no configured endpoint yet — offline, not an error
            self.update_fluidnc_labels({"controller_state": "Offline", "message": "No FluidNC endpoint configured"})
            self._notify_fluidnc_offline("No FluidNC endpoint configured yet.")
            self.refresh_logs()
            self.restore_workspace()
            return
        self.supervisor.check_fluidnc(probe)
        result = {**probe.to_dict(), "online": probe.online, "host": probe.telnet_host, "port": probe.telnet_port}
        self.update_fluidnc_labels(result)
        if probe.online:
            self._fluidnc_offline_notified = False
            notify_if_connected(probe.message, color="positive")
        else:
            self._notify_fluidnc_offline(probe.message)
        self.refresh_logs()
        self.restore_workspace()

    async def scan_fluidnc(self) -> None:
        await self.check_fluidnc(scan=True)

    def set_work_zero(self) -> None:
        self.confirm_action(
            "SET WORK ZERO",
            "Current XY becomes G54 X0 Y0. Z is not zeroed; Z moves use absolute configured values. Use after placing the tool at the upper-left origin.",
            lambda: self.fluidnc_action(
                "set work zero", self.supervisor.set_work_zero, success_message="Work zero set"
            ),
        )

    def home_xy(self) -> None:
        self.confirm_action(
            "HOME ALL",
            "The plotter will run FluidNC homing command $H. Use this when FluidNC rejects single-axis homing.",
            lambda: self.fluidnc_action(
                "home all", self.supervisor.home_xy_fluidnc, refresh_probe=False, success_message="Homed all axes"
            ),
        )

    def home_axis(self, axis: str) -> None:
        self.confirm_action(
            f"HOME {axis}",
            f"Single-axis homing sends $H={axis}. Use only if this FluidNC config supports it.",
            lambda: self.fluidnc_action(
                f"home {axis}",
                lambda: self.supervisor.home_fluidnc(axis),
                refresh_probe=False,
                success_message=f"Homed {axis}",
            ),
        )

    async def jog(self, axis: str, sign: float) -> None:
        distance = sign * float(self.fields["jog_step"].value or 1)
        feed = float(self.fields["jog_feed"].value or 1000)
        await self.fluidnc_action(
            f"jog {axis}",
            lambda: self.supervisor.jog_fluidnc(axis, distance, feed),
            refresh_probe=False,
            success_message=f"Jogged {axis} {distance:+g}mm",
        )

    async def jog_x_negative(self) -> None:
        await self.jog("X", -1)

    async def jog_x_positive(self) -> None:
        await self.jog("X", 1)

    async def jog_y_negative(self) -> None:
        await self.jog("Y", -1)

    async def jog_y_positive(self) -> None:
        await self.jog("Y", 1)

    async def pen_up(self) -> None:
        await self.fluidnc_action(
            "pen up", self.supervisor.pen_up_fluidnc, refresh_probe=False, success_message="Pen up"
        )

    async def pen_down(self) -> None:
        await self.fluidnc_action(
            "pen down", self.supervisor.pen_down_fluidnc, refresh_probe=False, success_message="Pen down"
        )

    def unlock_alarm(self) -> None:
        self.confirm_action(
            "UNLOCK ALARM",
            "This sends $X. It clears FluidNC alarm state without moving the machine.",
            lambda: self.fluidnc_action("unlock", self.supervisor.unlock_fluidnc_alarm),
        )

    async def stop_print(self) -> None:
        state = await self._blocking(self.supervisor.stop_print)
        ui.notify(state.message, color="warning")
        self.refresh_status()
        self.refresh_logs()

    async def emergency_stop(self) -> None:
        state = await self._blocking(self.supervisor.emergency_stop_fluidnc)
        ui.notify(state.message, color="negative")
        self.refresh_status()
        self.refresh_logs()

    def resume_after_hold(self) -> None:
        self.confirm_action(
            "RESUME AFTER HOLD",
            "This sends realtime cycle start ~. Confirm only if the machine is safe to resume.",
            lambda: self.fluidnc_action("resume", self.supervisor.resume_fluidnc),
        )

    def soft_reset(self) -> None:
        self.confirm_action(
            "SOFT RESET / ABORT",
            "This sends Ctrl-X and disables print. Use only to abort/reset FluidNC.",
            lambda: self.fluidnc_action("soft reset", self.supervisor.soft_reset_fluidnc),
        )

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
        ok, output = await self._blocking(self.supervisor.thermal_status, esp32_url=url)
        self._update_thermal_label(output)
        ui.notify(
            "Thermal printer status updated" if ok else "Thermal printer offline", color="positive" if ok else "warning"
        )

    async def thermal_printer_connect(self) -> None:
        url = self._thermal_url()
        ok, output = await self._blocking(self.supervisor.thermal_connect, esp32_url=url)
        self._update_thermal_label(output)
        ui.notify(
            "Thermal printer connected" if ok else "Thermal printer connection failed",
            color="positive" if ok else "warning",
        )

    async def thermal_printer_test_receipt(self) -> None:
        url = self._thermal_url()
        ok, output = await self._blocking(self.supervisor.thermal_test, message="ORACLE THERMAL TEST", esp32_url=url)
        self._update_thermal_label(output)
        ui.notify("Thermal test sent" if ok else "Thermal test failed", color="positive" if ok else "warning")

    async def _thermal_print_session(self, session_dir: Path | None) -> None:
        if session_dir is None or not session_dir.exists():
            ui.notify("No receipt session folder found", color="warning")
            return
        url = self._thermal_url()
        ok, output = await self._blocking(self.supervisor.thermal_print_receipt, session_dir, esp32_url=url)
        self._update_thermal_label(output)
        ui.notify(
            f"Thermal receipt sent: {session_dir.name}" if ok else "Thermal receipt failed",
            color="positive" if ok else "warning",
        )

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
