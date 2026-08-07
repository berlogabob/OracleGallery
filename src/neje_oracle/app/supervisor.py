from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..blocks.firebase.repository import FirebaseRemoteRepository
from ..blocks.fluidnc.transport import FluidNCTransport, discover_fluidnc, settings_for_fluidnc_host
from ..blocks.gcode.direct_svg import create_direct_svg_print_job_from_gui
from ..blocks.plotter.daemon import PlotterDaemon
from ..shared.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings
from ..shared.gui_settings import GuiSettings
from ..shared.logging import append_log
from ..shared.models import (
    ComponentState,
    ComponentStatus,
    FluidNCCommandResult,
    FluidNCProbeResult,
    FluidNCState,
    PlotJobLease,
    PlotStatus,
    PlotterControlState,
    PlotterReadinessState,
    PlotterRuntimeConfig,
    PlotterRuntimeState,
    RuntimeStatus,
    SystemCheckLevel,
    SystemCheckResult,
    SystemMode,
)
from ..shared.modes import mode_to_control
from ..shared.store import OracleRuntimeStore, PlotterStore
from .system_checks import SystemCheckService


class _LocalOnlyPlotterRemote(FirebaseRemoteRepository):
    def __init__(self) -> None:
        pass

    def claim_next_plot_job(
        self,
        consumer_id: str,
        *,
        run_started_at: datetime | None = None,
        allowed_origins: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> PlotJobLease | None:
        return None

    def update_plot_job(
        self,
        session_id: str,
        status: PlotStatus,
        *,
        sheet_id: str = "",
        sheet_index: int | None = None,
        error: str = "",
    ) -> None:
        return None

    def download_asset(self, storage_path: str, destination: Path) -> None:
        raise RuntimeError("Local-only plotter remote cannot download Firebase assets")


class SupervisorService:
    def __init__(
        self,
        *,
        settings: OracleSupervisorSettings | None = None,
        plotter_settings: PlotterSettings | None = None,
        uploader_settings: UploaderSettings | None = None,
        firebase_settings: FirebaseSettings | None = None,
        runtime_store: OracleRuntimeStore | None = None,
        remote_factory: Callable[[], FirebaseRemoteRepository] | None = None,
        transport_factory: Callable[[PlotterSettings], FluidNCTransport] | None = None,
    ) -> None:
        self.settings = settings or OracleSupervisorSettings()
        self.uploader_settings = uploader_settings or UploaderSettings()
        self.firebase_settings = firebase_settings or FirebaseSettings()
        self.runtime_store = runtime_store or OracleRuntimeStore(self.settings.runtime_db_path)
        self.plotter_settings = self._apply_saved_fluidnc_endpoint(plotter_settings or PlotterSettings())
        self.remote_factory = remote_factory or (lambda: FirebaseRemoteRepository(self.firebase_settings))
        self.transport_factory = transport_factory or (lambda resolved_settings: FluidNCTransport(resolved_settings))
        self._plotter_daemon: PlotterDaemon | None = None
        self._plotter_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start_system(self, config: PlotterRuntimeConfig) -> dict[str, ComponentState]:
        self.runtime_store.save_plotter_config(config)
        self.runtime_store.save_print_control(
            PlotterControlState(
                print_enabled=False, operator_paused=True, run_mode=config.run_mode, dry_run=config.dry_run
            )
        )
        append_log("system", "Start system requested", settings=self.settings)
        self.reset_run_baseline()
        self.runtime_store.set_component(
            "system", ComponentStatus.STARTING, message="Starting supervised system", started=True
        )
        firebase_state = self.check_firebase()
        macmini_state = self.check_macmini_agent()
        if macmini_state.status != ComponentStatus.OFFLINE:
            macmini_state = self.start_macmini_uploader()
        fluidnc_state = self.check_fluidnc()
        plotter_state = self.start_plotter(config)
        queue_state = self.runtime_store.load_component_state("queue")
        if queue_state.status != ComponentStatus.WARNING:
            self.runtime_store.set_component("queue", ComponentStatus.RUNNING, message="Queue transport via Firebase")
        self.runtime_store.set_component("print", ComponentStatus.STOPPED, message="Print disabled until START PRINT")
        component_states = {
            "firebase": firebase_state,
            "macmini_uploader": macmini_state,
            "fluidnc": fluidnc_state,
            "plotter": plotter_state,
        }
        if plotter_state.status == ComponentStatus.ERROR:
            self.runtime_store.set_component(
                "system",
                ComponentStatus.ERROR,
                message="Supervisor started with plotter error",
                last_error=plotter_state.last_error,
            )
        elif any(
            state.status in {ComponentStatus.ERROR, ComponentStatus.WARNING, ComponentStatus.OFFLINE}
            for state in component_states.values()
        ):
            self.runtime_store.set_component(
                "system", ComponentStatus.WARNING, message="Supervisor running with warnings", heartbeat=True
            )
        else:
            self.runtime_store.set_component(
                "system", ComponentStatus.RUNNING, message="Supervisor is running", heartbeat=True
            )
        return self.refresh_all_status()

    def stop_system(self) -> dict[str, ComponentState]:
        append_log("system", "Stop system requested", level="warning", settings=self.settings)
        self.stop_plotter()
        self.stop_macmini_uploader()
        self.runtime_store.save_print_control(PlotterControlState(print_enabled=False, operator_paused=True))
        self.runtime_store.save_plotter_readiness(PlotterReadinessState(message="System stopped"))
        self.runtime_store.set_component("live_generator", ComponentStatus.STOPPED, message="Live generation stopped")
        self.runtime_store.set_component("queue", ComponentStatus.STOPPED, message="Queue stopped with system")
        self.runtime_store.set_component("print", ComponentStatus.STOPPED, message="Print stopped by operator")
        self.runtime_store.set_component("system", ComponentStatus.STOPPED, message="System stopped by operator")
        return self.refresh_all_status()

    def reset_run_baseline(self) -> ComponentState:
        started_at = datetime.now(tz=UTC)
        self.runtime_store.save_run_started_at(started_at)
        self.runtime_store.save_plotter_readiness(PlotterReadinessState(message="New run baseline created"))
        skipped = 0
        try:
            skipped = self.remote_factory().skip_pending_before(started_at)
        except Exception as exc:  # noqa: BLE001
            append_log("queue", f"Baseline skip unavailable: {exc}", level="warning", settings=self.settings)
            return self.runtime_store.set_component(
                "queue",
                ComponentStatus.WARNING,
                message=f"Run baseline set; old Firebase jobs not skipped: {exc}",
                last_error=str(exc),
            )
        append_log(
            "queue",
            f"Run baseline set at {started_at.isoformat()}; skipped {skipped} old pending job(s)",
            settings=self.settings,
        )
        return self.runtime_store.set_component(
            "queue", ComponentStatus.RUNNING, message=f"Run baseline set; skipped {skipped} old job(s)", heartbeat=True
        )

    def set_system_mode(self, mode: SystemMode) -> ComponentState:
        mode = SystemMode(mode)
        self.runtime_store.save_system_mode(mode)
        control = mode_to_control(mode, print_enabled=False)
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        append_log("system", f"System mode changed to {mode.value}", settings=self.settings)
        return self.runtime_store.set_component("system", ComponentStatus.STOPPED, message=f"Mode set to {mode.value}")

    def run_system_check(self, gui_settings: GuiSettings) -> SystemCheckResult:
        mode = gui_settings.mode
        append_log("checks", f"System check started for {mode.value}", settings=self.settings)
        result = SystemCheckService(
            supervisor_settings=self.settings,
            plotter_settings=self.plotter_settings,
            uploader_settings=self.uploader_settings,
            firebase_settings=self.firebase_settings,
            fluidnc_checker=self._system_check_fluidnc,
            work_offset_provider=self._current_work_offset,
            board_identity_provider=self._live_board_identity,
        ).run(
            mode=mode,
            gui_settings=gui_settings,
        )
        self.runtime_store.save_system_check_result(result)
        status = ComponentStatus.RUNNING
        level = "info"
        if result.status == SystemCheckLevel.WARNING:
            status = ComponentStatus.WARNING
            level = "warning"
        elif result.status == SystemCheckLevel.CRITICAL:
            status = ComponentStatus.ERROR
            level = "error"
        critical_count = sum(1 for check in result.checks if check.level == SystemCheckLevel.CRITICAL)
        warning_count = sum(1 for check in result.checks if check.level == SystemCheckLevel.WARNING)
        ok_count = sum(1 for check in result.checks if check.level == SystemCheckLevel.OK)
        message = (
            f"System check {result.status.value}: {critical_count} critical, {warning_count} warning, {ok_count} ok"
        )
        append_log("checks", message, level=level, settings=self.settings)
        for check in result.checks:
            append_log(
                "checks",
                f"{check.level.value}: {check.name}: {check.message}",
                level=check.level.value if check.level != SystemCheckLevel.OK else "info",
                settings=self.settings,
            )
        self.runtime_store.set_component("checks", status, message=message, heartbeat=True)
        return result

    def _system_check_fluidnc(self, timeout_seconds: float) -> tuple[bool, str]:
        probe = self.transport_factory(self.plotter_settings).probe(timeout_seconds=timeout_seconds)
        message = probe.message
        if probe.online and not probe.controller.is_idle:
            message = f"{probe.message}; controller must be Idle for real print"
        return probe.online and probe.controller.is_idle, message

    def _system_check_block_message(self, result: SystemCheckResult, action: str) -> str:
        first_critical = next((check for check in result.checks if check.level == SystemCheckLevel.CRITICAL), None)
        if first_critical is None:
            return f"Resolve system checks before {action}"
        return f"Resolve system check before {action}: {first_critical.name}: {first_critical.message}"

    def start_print(self, gui_settings: GuiSettings) -> ComponentState:
        gui_settings.apply_system_mode()
        mode = gui_settings.mode
        control = mode_to_control(mode, print_enabled=True)
        system_check = self.run_system_check(gui_settings)
        if system_check.has_critical:
            message = self._system_check_block_message(system_check, "START PRINT")
            append_log("plotter", f"Start print blocked: {message}", level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message=message)
        readiness = self.runtime_store.load_plotter_readiness()
        if not readiness.work_zero_set:
            append_log("plotter", "Start print blocked: work zero is not set", level="warning", settings=self.settings)
            return self.runtime_store.set_component(
                "print", ComponentStatus.WARNING, message="Set work zero before START PRINT"
            )
        if readiness.homing_required:
            # The controller alarmed since the last home, so its position is not trustworthy
            # even if it now reports Idle -- $X clears an alarm without restoring reference.
            append_log(
                "plotter", "Start print blocked: homing required after alarm", level="warning", settings=self.settings
            )
            return self.runtime_store.set_component(
                "print",
                ComponentStatus.WARNING,
                message="Controller alarmed since the last homing cycle; HOME ALL before START PRINT",
            )
        if not control.dry_run:
            fluidnc_state = self.check_fluidnc()
            if fluidnc_state.status != ComponentStatus.RUNNING:
                append_log(
                    "plotter", "Start print blocked: FluidNC not Idle/online", level="warning", settings=self.settings
                )
                return self.runtime_store.set_component(
                    "print", ComponentStatus.WARNING, message="FluidNC must be online and Idle before plotter motion"
                )
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        append_log(
            "plotter",
            f"Print enabled in {mode.value}",
            level="warning" if not control.dry_run else "info",
            settings=self.settings,
        )
        return self.runtime_store.set_component(
            "print", ComponentStatus.RUNNING, message=f"Print enabled: {mode.value}", heartbeat=True
        )

    def stop_print(self) -> ComponentState:
        """Graceful stop: let the current cell finish, then pause before the next one.

        The daemon only re-reads print_enabled at row/cell boundaries, so the in-flight
        cell always completes -- including its trailing pen-up. Use emergency_stop_fluidnc()
        when motion must halt immediately instead.
        """
        control = self.runtime_store.load_print_control()
        control.print_enabled = False
        control.operator_paused = True
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        append_log("plotter", "Stop print requested by operator", level="warning", settings=self.settings)
        return self.runtime_store.set_component(
            "print", ComponentStatus.STOPPED, message="Stop requested; finishing the current cell, then pausing"
        )

    def print_uploaded_svg(self, gui_settings: GuiSettings, *, svg_bytes: bytes, original_name: str) -> ComponentState:
        gui_settings.apply_system_mode()
        system_check = self.run_system_check(gui_settings)
        if system_check.has_critical:
            message = self._system_check_block_message(system_check, "PRINT SVG")
            append_log("plotter", f"Uploaded SVG print blocked: {message}", level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message=message)
        readiness = self.runtime_store.load_plotter_readiness()
        if not readiness.work_zero_set:
            message = "Set work zero before PRINT SVG"
            append_log("plotter", f"Uploaded SVG print blocked: {message}", level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message=message)
        probe = self.probe_fluidnc()
        self.check_fluidnc(probe)
        if not probe.online:
            message = f"FluidNC is offline; cannot print SVG directly: {probe.message}"
            append_log("plotter", message, level="warning", settings=self.settings)
            return self.runtime_store.set_component(
                "print", ComponentStatus.WARNING, message=message, last_error=probe.last_error
            )
        if not probe.controller.is_idle:
            state = probe.controller.state.value
            message = f"FluidNC is {state}; wait for Idle before PRINT SVG"
            append_log("plotter", message, level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message=message)

        try:
            job = create_direct_svg_print_job_from_gui(
                gui_settings,
                svg_bytes=svg_bytes,
                original_name=original_name,
                output_root=self.plotter_settings.spool_root / "uploaded_svg",
                plotter_settings=self.plotter_settings,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"SVG is not printable: {exc}"
            append_log("plotter", message, level="error", settings=self.settings)
            return self.runtime_store.set_component(
                "print", ComponentStatus.ERROR, message=message, last_error=str(exc)
            )

        plotter_store = PlotterStore(self.plotter_settings.db_path)
        total_lines = len(
            [line for line in job.gcode.splitlines() if line.strip() and not line.lstrip().startswith(";")]
        )

        def record_progress(sent: int, total: int) -> None:
            percent = (sent / total * 100.0) if total else 0.0
            plotter_store.save_runtime_state(
                PlotterRuntimeState(
                    status=RuntimeStatus.PRINTING,
                    message=f"Printing uploaded SVG {job.label}: {sent}/{total} lines",
                    current_sheet_id=job.sheet_id,
                    gcode_lines_sent=sent,
                    gcode_lines_total=total,
                    gcode_progress_percent=percent,
                    current_row_index=1,
                    row_count=1,
                    current_cell_index=1,
                    current_cell_in_row=1,
                    row_cell_count=1,
                    sheet_progress_percent=percent,
                )
            )

        plotter_store.save_runtime_state(
            PlotterRuntimeState(
                status=RuntimeStatus.PRINTING,
                message=f"Printing uploaded SVG {job.label}",
                current_sheet_id=job.sheet_id,
                gcode_lines_total=total_lines,
                row_count=1,
                row_cell_count=1,
            )
        )
        self.runtime_store.set_component(
            "print", ComponentStatus.RUNNING, message=f"Printing uploaded SVG: {job.label}", heartbeat=True
        )
        try:
            gcode_path = self.transport_factory(self.plotter_settings).send(
                gcode=job.gcode,
                sheet_id=job.sheet_id,
                dry_run=False,
                progress_callback=record_progress,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"Uploaded SVG print failed: {exc}"
            plotter_store.save_runtime_state(
                PlotterRuntimeState(
                    status=RuntimeStatus.ERROR,
                    message=message,
                    current_sheet_id=job.sheet_id,
                    gcode_lines_total=total_lines,
                )
            )
            append_log("plotter", message, level="error", settings=self.settings)
            return self.runtime_store.set_component(
                "print", ComponentStatus.ERROR, message=message, last_error=str(exc)
            )

        plotter_store.save_runtime_state(
            PlotterRuntimeState(
                status=RuntimeStatus.OPERATOR_PAUSED,
                message=f"Uploaded SVG finished: {job.label}",
                current_sheet_id=job.sheet_id,
                last_sheet_path=str(gcode_path),
                gcode_lines_sent=total_lines,
                gcode_lines_total=total_lines,
                gcode_progress_percent=100.0,
                current_row_index=1,
                row_count=1,
                current_cell_index=1,
                current_cell_in_row=1,
                row_cell_count=1,
                cells_completed=1,
                rows_completed=1,
                sheet_progress_percent=100.0,
            )
        )
        append_log("plotter", f"Uploaded SVG printed directly: {job.label} -> {gcode_path}", settings=self.settings)
        return self.runtime_store.set_component(
            "print", ComponentStatus.STOPPED, message=f"Uploaded SVG printed: {job.label}"
        )

    def start_plotter(self, config: PlotterRuntimeConfig | None = None) -> ComponentState:
        with self._lock:
            if self._plotter_thread and self._plotter_thread.is_alive():
                return self.runtime_store.set_component(
                    "plotter", ComponentStatus.RUNNING, message="Plotter already running", heartbeat=True
                )
            if config is not None:
                self.runtime_store.save_plotter_config(config)
            self.runtime_store.set_component(
                "plotter", ComponentStatus.STARTING, message="Starting local plotter daemon", started=True
            )
            try:
                plotter_store = PlotterStore(self.plotter_settings.db_path)
                remote = self._create_plotter_remote(config)
                transport = self.transport_factory(self.plotter_settings)
                self._plotter_daemon = PlotterDaemon(
                    self.plotter_settings,
                    plotter_store,
                    remote,
                    transport,
                    oracle_store=self.runtime_store,
                )
                self._plotter_thread = threading.Thread(target=self._plotter_daemon.run_forever, daemon=True)
                self._plotter_thread.start()
            except Exception as exc:  # noqa: BLE001
                return self.runtime_store.set_component(
                    "plotter", ComponentStatus.ERROR, message="Plotter failed to start", last_error=str(exc)
                )
        return self.runtime_store.set_component(
            "plotter", ComponentStatus.RUNNING, message="Local plotter daemon running", heartbeat=True
        )

    def _create_plotter_remote(self, config: PlotterRuntimeConfig | None) -> FirebaseRemoteRepository:
        try:
            return self.remote_factory()
        except Exception as exc:
            local_only_allowed = config is None or config.dry_run or config.run_mode == "test"
            if not local_only_allowed:
                raise
            append_log(
                "queue",
                f"Firebase unavailable; plotter daemon will use local idle symbols only: {exc}",
                level="warning",
                settings=self.settings,
            )
            self.runtime_store.set_component(
                "queue",
                ComponentStatus.WARNING,
                message="Firebase unavailable; using local idle symbols only",
                last_error=str(exc),
                heartbeat=True,
            )
            return _LocalOnlyPlotterRemote()

    def stop_plotter(self) -> ComponentState:
        with self._lock:
            daemon = self._plotter_daemon
            thread = self._plotter_thread
            if daemon is not None:
                daemon.stop()
            if thread is not None:
                thread.join(timeout=5.0)
                if thread.is_alive():
                    return self.runtime_store.set_component(
                        "plotter",
                        ComponentStatus.WARNING,
                        message="Stop requested; daemon still finishing current motion",
                    )
            self._plotter_daemon = None
            self._plotter_thread = None
        return self.runtime_store.set_component(
            "plotter", ComponentStatus.STOPPED, message="Local plotter daemon stopped"
        )

    def check_firebase(self) -> ComponentState:
        firebase = self.firebase_settings
        if not firebase.enabled:
            append_log("system", "Firebase is not configured", level="warning", settings=self.settings)
            return self.runtime_store.set_component(
                "firebase", ComponentStatus.WARNING, message="Firebase is not configured"
            )
        append_log("system", f"Firebase configured: {firebase.project_id}", settings=self.settings)
        return self.runtime_store.set_component(
            "firebase", ComponentStatus.RUNNING, message=f"Configured: {firebase.project_id}", heartbeat=True
        )

    def _reconcile_readiness_with_controller(self, probe: FluidNCProbeResult) -> None:
        """Invalidate readiness when the controller says its position reference is gone.

        Readiness used to be latched: set once by set_work_zero() and cleared only by
        app-initiated actions. A panic, a reboot or an externally triggered alarm left the
        UI reporting "Work zero set; plotter ready" on a machine that had lost its
        reference -- observed three separate times during hardware testing on 2026-08-07.

        Alarm is the signal that the reference is gone. Hold is not: a feed hold, and a
        soft reset after it, both preserve MPos and G54, so those must stay ready.
        """
        if not probe.online or probe.controller.state != FluidNCState.ALARM:
            return
        readiness = self.runtime_store.load_plotter_readiness()
        if readiness.homing_required:
            return
        self.runtime_store.save_plotter_readiness(
            PlotterReadinessState(
                work_zero_set=readiness.work_zero_set,
                plotter_ready=False,
                homing_required=True,
                message="Controller alarm: position reference lost. Home before printing.",
            )
        )
        append_log(
            "plotter",
            "Controller reported alarm; homing is required before the next print",
            level="warning",
            settings=self.settings,
        )

    def check_fluidnc(self, probe: FluidNCProbeResult | None = None) -> ComponentState:
        probe = probe or self.probe_fluidnc()
        self._reconcile_readiness_with_controller(probe)
        online = probe.online and probe.controller.is_idle
        status = (
            ComponentStatus.RUNNING if online else ComponentStatus.WARNING if probe.online else ComponentStatus.OFFLINE
        )
        append_log(
            "plotter", f"FluidNC check: {probe.message}", level="info" if online else "warning", settings=self.settings
        )
        return self.runtime_store.set_component(
            "fluidnc",
            status,
            message=probe.message,
            last_error=probe.last_error,
            heartbeat=online,
        )

    def probe_fluidnc(self, *, scan: bool = True) -> FluidNCProbeResult:
        probe = self.transport_factory(self.plotter_settings).probe(
            timeout_seconds=self.plotter_settings.fluidnc_connect_timeout_seconds
        )
        if probe.online:
            self._save_fluidnc_endpoint(probe)
            self.runtime_store.save_json("fluidnc_probe", probe.to_dict())
            return probe
        if not scan:
            self.runtime_store.save_json("fluidnc_probe", probe.to_dict())
            return probe
        append_log(
            "plotter",
            f"FluidNC configured endpoint failed, scanning current subnet: {probe.message}",
            level="warning",
            settings=self.settings,
        )
        discovered = discover_fluidnc(self.plotter_settings)
        if discovered.online:
            self._save_fluidnc_endpoint(discovered)
            append_log(
                "plotter",
                f"FluidNC discovered at {discovered.telnet_host}:{discovered.telnet_port}",
                settings=self.settings,
            )
            self.runtime_store.save_json("fluidnc_probe", discovered.to_dict())
            return discovered
        self.runtime_store.save_json("fluidnc_probe", probe.to_dict())
        return probe

    def set_work_zero(self) -> ComponentState:
        if not self._manual_control_allowed("set work zero"):
            return self.runtime_store.load_component_state("ready")
        config = self.runtime_store.load_plotter_config()
        command = self._work_zero_command(config)
        result = self.transport_factory(self.plotter_settings).send_command(command, wait_for_ok=True)
        if not result.ok:
            self.runtime_store.save_plotter_readiness(
                PlotterReadinessState(message=f"Set work zero failed: {result.message}")
            )
            return self._record_fluidnc_command(result, "Set work zero")
        # Preserve an outstanding homing requirement: zeroing at an unknown position does
        # not make the machine safe, and a fresh PlotterReadinessState would silently
        # default homing_required back to False.
        previous = self.runtime_store.load_plotter_readiness()
        readiness = PlotterReadinessState(
            work_zero_set=True,
            plotter_ready=not previous.homing_required,
            homing_required=previous.homing_required,
            message=(
                "Work zero set, but homing is still required"
                if previous.homing_required
                else "Work zero set; plotter ready"
            ),
        )
        self.runtime_store.save_plotter_readiness(readiness)
        self.runtime_store.set_component("ready", ComponentStatus.RUNNING, message=readiness.message, heartbeat=True)
        return self._record_fluidnc_command(result, "Set work zero")

    def _work_zero_command(self, config: PlotterRuntimeConfig) -> str:
        command = (config.work_zero_command or self.plotter_settings.work_zero_command).strip()
        if (config.use_z_servo or self.plotter_settings.use_z_servo) and command.upper() in {
            "G10 L20 P1 X0 Y0",
            "G10 L20 P1 X0 Y0 Z0",
        }:
            return "G10 L20 P1 X0 Y0"
        return command

    def home_fluidnc(self, axis: str | None = None) -> ComponentState:
        if not self._manual_control_allowed("home"):
            return self.runtime_store.load_component_state("fluidnc")
        label = f"Home {axis or 'all'}"
        result = self.transport_factory(self.plotter_settings).home(axis)
        if not result.ok:
            result = _enrich_fluidnc_error(result)
        if result.ok or _homing_disconnect_is_recoverable(result):
            # Only a full home restores the XY reference; "$H=Z" must not clear the flag.
            return self._record_homing_result(result, label, full_home=axis is None)
        return self._record_fluidnc_command(result, label)

    def home_xy_fluidnc(self) -> ComponentState:
        return self.home_fluidnc()

    def jog_fluidnc(self, axis: str, distance: float, feed: float) -> ComponentState:
        if not self._manual_control_allowed("jog"):
            return self.runtime_store.load_component_state("fluidnc")
        result = self.transport_factory(self.plotter_settings).jog(axis, distance, feed)
        return self._record_fluidnc_command(result, f"Jog {axis} {distance:g}mm F{feed:g}")

    def pen_up_fluidnc(self) -> ComponentState:
        if not self._manual_control_allowed("pen up"):
            return self.runtime_store.load_component_state("fluidnc")
        config = self.runtime_store.load_plotter_config()
        if config.use_z_servo or self.plotter_settings.use_z_servo:
            z_up = config.z_up_mm if config.use_z_servo else self.plotter_settings.z_up_mm
            command = f"G0 Z{z_up:.3f}"
            result = self.transport_factory(self.plotter_settings).send_commands(["G21", "G90", "G54", command])
            return self._record_fluidnc_command(result, f"Z up servo {command}")
        result = self.transport_factory(self.plotter_settings).pen_up()
        return self._record_fluidnc_command(result, f"Pen up {self.plotter_settings.pen_up_command}")

    def pen_down_fluidnc(self) -> ComponentState:
        if not self._manual_control_allowed("pen down"):
            return self.runtime_store.load_component_state("fluidnc")
        config = self.runtime_store.load_plotter_config()
        if config.use_z_servo or self.plotter_settings.use_z_servo:
            # Match the sheet G-code path (svg_gcode._pen_down_command): a fed G1, honouring
            # the configured depth and feed. This used to send a hardcoded "G0 Z-25.000",
            # which rapided the servo and ignored z_down_mm entirely.
            z_down = config.z_down_mm if config.use_z_servo else self.plotter_settings.z_down_mm
            z_feed = config.z_feed_mm_min if config.use_z_servo else self.plotter_settings.z_feed_mm_min
            command = f"G1 Z{z_down:.3f} F{z_feed:.2f}"
            result = self.transport_factory(self.plotter_settings).send_commands(["G21", "G90", "G54", command])
            return self._record_fluidnc_command(result, f"Z down servo {command}")
        result = self.transport_factory(self.plotter_settings).pen_down()
        return self._record_fluidnc_command(result, f"Pen down {self.plotter_settings.pen_down_command}")

    def unlock_fluidnc_alarm(self) -> ComponentState:
        if not self._manual_control_allowed("unlock alarm"):
            return self.runtime_store.load_component_state("fluidnc")
        result = self.transport_factory(self.plotter_settings).unlock_alarm()
        if not result.ok:
            result = _enrich_fluidnc_error(result)
        return self._record_fluidnc_command(result, "Unlock alarm")

    def emergency_stop_fluidnc(self) -> ComponentState:
        result = self.transport_factory(self.plotter_settings).feed_hold()
        self.runtime_store.save_plotter_readiness(
            PlotterReadinessState(message="Emergency stop sent; readiness cleared")
        )
        control = self.runtime_store.load_print_control()
        control.print_enabled = False
        control.operator_paused = True
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        level = "warning" if result.ok else "error"
        append_log("plotter", f"Emergency stop/feed hold: {result.message}", level=level, settings=self.settings)
        self.runtime_store.set_component(
            "print", ComponentStatus.STOPPED, message="Emergency stop sent; print disabled"
        )
        return self.runtime_store.set_component(
            "fluidnc",
            ComponentStatus.WARNING if result.ok else ComponentStatus.ERROR,
            message="Emergency stop/feed hold sent" if result.ok else result.message,
            last_error="" if result.ok else result.message,
            heartbeat=result.ok,
        )

    def resume_fluidnc(self) -> ComponentState:
        probe = self.probe_fluidnc()
        if not probe.controller.is_hold:
            return self.runtime_store.set_component(
                "fluidnc",
                ComponentStatus.WARNING,
                message=f"Resume skipped: FluidNC state is {probe.controller.state.value}",
            )
        result = self.transport_factory(self.plotter_settings).cycle_start()
        return self._record_fluidnc_command(result, "Resume/cycle start")

    def soft_reset_fluidnc(self) -> ComponentState:
        result = self.transport_factory(self.plotter_settings).soft_reset()
        self.runtime_store.save_plotter_readiness(PlotterReadinessState(message="Soft reset sent; readiness cleared"))
        control = self.runtime_store.load_print_control()
        control.print_enabled = False
        control.operator_paused = True
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        return self._record_fluidnc_command(result, "Soft reset/abort")

    def check_macmini_agent(self) -> ComponentState:
        agent_url = self._macmini_agent_url()
        if not agent_url:
            return self.runtime_store.set_component(
                "macmini_uploader", ComponentStatus.OFFLINE, message="NEJE_MACMINI_AGENT_URL is not set"
            )
        try:
            payload = httpx.get(
                f"{agent_url.rstrip('/')}/status",
                timeout=self.settings.macmini_agent_timeout_seconds,
                trust_env=False,
            ).json()
        except Exception as exc:  # noqa: BLE001
            append_log("uploader", f"Mac mini uploader offline: {exc}", level="warning", settings=self.settings)
            return self.runtime_store.set_component(
                "macmini_uploader",
                ComponentStatus.OFFLINE,
                message="Mac mini uploader agent offline",
                last_error=str(exc),
            )
        status = ComponentStatus.RUNNING if payload.get("running") else ComponentStatus.STOPPED
        message = str(payload.get("message") or payload.get("status") or "Mac mini uploader agent reachable")
        append_log("uploader", f"Mac mini uploader status: {message}", settings=self.settings)
        return self.runtime_store.set_component("macmini_uploader", status, message=message, heartbeat=True)

    def start_macmini_uploader(self) -> ComponentState:
        return self._post_macmini_control("start")

    def stop_macmini_uploader(self) -> ComponentState:
        return self._post_macmini_control("stop")

    def restart_macmini_uploader(self) -> ComponentState:
        return self._post_macmini_control("restart")

    def scan_macmini_once(self) -> ComponentState:
        agent_url = self._macmini_agent_url()
        if not agent_url:
            discovered = self.discover_macmini_uploader()
            if discovered.status == ComponentStatus.OFFLINE:
                return discovered
            agent_url = self._macmini_agent_url()
        if not agent_url:
            return self.runtime_store.set_component(
                "macmini_uploader", ComponentStatus.OFFLINE, message="Mac mini uploader was not found"
            )
        try:
            payload = httpx.post(
                f"{agent_url.rstrip('/')}/scan-once",
                timeout=self.settings.macmini_agent_timeout_seconds,
                trust_env=False,
            ).json()
        except Exception as exc:  # noqa: BLE001
            append_log(
                "uploader",
                f"Mac mini scan failed: {exc}; trying LAN discovery",
                level="warning",
                settings=self.settings,
            )
            discovered = self.discover_macmini_uploader()
            agent_url = self._macmini_agent_url()
            if discovered.status == ComponentStatus.OFFLINE or not agent_url:
                return self.runtime_store.set_component(
                    "macmini_uploader",
                    ComponentStatus.OFFLINE,
                    message="Mac mini scan failed and discovery found no uploader",
                    last_error=str(exc),
                )
            try:
                payload = httpx.post(
                    f"{agent_url.rstrip('/')}/scan-once",
                    timeout=self.settings.macmini_agent_timeout_seconds,
                    trust_env=False,
                ).json()
            except Exception as retry_exc:  # noqa: BLE001
                append_log(
                    "uploader", f"Mac mini scan retry failed: {retry_exc}", level="warning", settings=self.settings
                )
                return self.runtime_store.set_component(
                    "macmini_uploader",
                    ComponentStatus.OFFLINE,
                    message="Mac mini scan failed",
                    last_error=str(retry_exc),
                )
        append_log(
            "uploader", f"Mac mini scan imported {len(payload.get('imported', []))} session(s)", settings=self.settings
        )
        return self.runtime_store.set_component(
            "macmini_uploader",
            ComponentStatus.RUNNING,
            message=f"Scan imported {len(payload.get('imported', []))} session(s)",
            heartbeat=True,
        )

    def discover_macmini_uploader(self) -> ComponentState:
        candidates = _candidate_macmini_agent_urls(self._macmini_agent_url())
        append_log(
            "uploader",
            f"Scanning LAN for Mac mini uploader across {len(candidates)} candidate host(s)",
            settings=self.settings,
        )
        discovered_url = _discover_uploader_url(candidates, timeout_seconds=0.25)
        if not discovered_url:
            return self.runtime_store.set_component(
                "macmini_uploader",
                ComponentStatus.OFFLINE,
                message="No Mac mini uploader found on this LAN",
                last_error="No /health response on port 8790",
            )
        self.runtime_store.save_json(
            "macmini_agent",
            {
                "url": discovered_url,
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
        )
        append_log("uploader", f"Discovered Mac mini uploader: {discovered_url}", settings=self.settings)
        return self.runtime_store.set_component(
            "macmini_uploader",
            ComponentStatus.STOPPED,
            message=f"Discovered uploader at {discovered_url}",
            heartbeat=True,
        )

    # Thermal printer control. ponytail: still shells out to printer_connect.py — this just
    # relocates the existing subprocess behind the supervisor so the GUI has one facade. Inline
    # the BLE/ESP32 path only if the subprocess boundary ever actually hurts.
    _THERMAL_REPO_ROOT = Path(__file__).resolve().parents[3]

    def save_thermal_printer_url(self, url: str) -> None:
        self.runtime_store.save_json("thermal_printer", {"url": url.strip()})

    def _run_thermal(
        self, action: str, *, esp32_url: str = "", extra_args: tuple[str, ...] = (), timeout: float = 90.0
    ) -> tuple[bool, str]:
        script = self._THERMAL_REPO_ROOT / "ESP32-BTN_Printer" / "tools" / "printer_connect.py"
        url_args = ["--esp32", esp32_url] if esp32_url.strip() else []
        command = [sys.executable, str(script), action, *url_args, *extra_args]
        try:
            result = subprocess.run(
                command, cwd=self._THERMAL_REPO_ROOT, text=True, capture_output=True, timeout=timeout, check=False
            )
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        output = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode == 0, output

    def thermal_status(self, *, esp32_url: str = "") -> tuple[bool, str]:
        return self._run_thermal("status", esp32_url=esp32_url, timeout=20.0)

    def thermal_connect(self, *, esp32_url: str = "") -> tuple[bool, str]:
        return self._run_thermal("connect", esp32_url=esp32_url, timeout=45.0)

    def thermal_test(self, *, message: str = "ORACLE THERMAL TEST", esp32_url: str = "") -> tuple[bool, str]:
        return self._run_thermal("test", esp32_url=esp32_url, extra_args=("--message", message), timeout=60.0)

    def thermal_print_receipt(self, session_dir: Path, *, esp32_url: str = "") -> tuple[bool, str]:
        preview_png = self._THERMAL_REPO_ROOT / "reports" / f"{session_dir.name}_thermal_preview.png"
        return self._run_thermal(
            "receipt",
            esp32_url=esp32_url,
            extra_args=(str(session_dir), "--preview-png", str(preview_png)),
            timeout=120.0,
        )

    def latest_receipt_session_dir(self) -> Path | None:
        session_root = self._THERMAL_REPO_ROOT / "assets" / "sessions"
        if not session_root.exists():
            return None
        candidates = [path for path in session_root.iterdir() if path.is_dir() and any(path.glob("*_receipt.txt"))]
        return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None

    def refresh_all_status(self) -> dict[str, ComponentState]:
        states = self.runtime_store.load_all_component_states()
        for name in (
            "system",
            "macmini_uploader",
            "firebase",
            "plotter",
            "fluidnc",
            "queue",
            "print",
            "ready",
            "live_generator",
        ):
            states.setdefault(name, self.runtime_store.load_component_state(name))
        if (
            self._plotter_thread
            and self._plotter_thread.is_alive()
            and states["plotter"].status not in (ComponentStatus.ERROR, ComponentStatus.WARNING)
        ):
            states["plotter"] = self.runtime_store.set_component(
                "plotter",
                ComponentStatus.RUNNING,
                message=states["plotter"].message or "Local plotter daemon running",
                heartbeat=True,
            )
        return states

    def _live_board_identity(self) -> str | None:
        """Board name the controller is actually running, or None if it cannot be asked."""
        try:
            return self.transport_factory(self.plotter_settings).read_board_identity()
        except Exception:  # noqa: BLE001
            return None

    def _current_work_offset(self) -> tuple[float, float, float] | None:
        """G54 offset from the controller, or None if it cannot be read.

        FluidNC reports WCO only periodically, so a miss here is normal and must not fail
        the check -- callers treat None as "no offset information", not "no offset".
        """
        try:
            return self.probe_fluidnc().controller.work_offset
        except Exception:  # noqa: BLE001
            return None

    def is_printing(self) -> bool:
        """True while a sheet is actively streaming to the controller."""
        return PlotterStore(self.plotter_settings.db_path).load_runtime_state().status == RuntimeStatus.PRINTING

    def _manual_control_allowed(self, action: str) -> bool:
        state = PlotterStore(self.plotter_settings.db_path).load_runtime_state()
        if state.status == RuntimeStatus.PRINTING:
            self.runtime_store.set_component(
                "fluidnc", ComponentStatus.WARNING, message=f"{action} blocked while plotter is printing"
            )
            return False
        control = self.runtime_store.load_print_control()
        if control.print_enabled:
            control.print_enabled = False
            control.operator_paused = True
            self.runtime_store.save_print_control(control)
            PlotterStore(self.plotter_settings.db_path).save_control_state(control)
            self.runtime_store.set_component(
                "print", ComponentStatus.STOPPED, message=f"Print paused before manual {action}"
            )
            append_log("plotter", f"Print paused before manual {action}", level="warning", settings=self.settings)
        return True

    def _record_fluidnc_command(self, result: FluidNCCommandResult, label: str) -> ComponentState:
        level = "info" if result.ok else "error"
        append_log("plotter", f"FluidNC {label}: {result.message}", level=level, settings=self.settings)
        if not result.ok:
            control = self.runtime_store.load_print_control()
            control.print_enabled = False
            control.operator_paused = True
            self.runtime_store.save_print_control(control)
            PlotterStore(self.plotter_settings.db_path).save_control_state(control)
            self.runtime_store.set_component(
                "print", ComponentStatus.STOPPED, message=f"Print disabled after FluidNC error: {result.message}"
            )
        return self.runtime_store.set_component(
            "fluidnc",
            ComponentStatus.RUNNING if result.ok else ComponentStatus.ERROR,
            message=f"{label}: {result.message}",
            last_error="" if result.ok else result.message,
            heartbeat=result.ok,
        )

    def _clear_homing_requirement(self) -> None:
        readiness = self.runtime_store.load_plotter_readiness()
        if not readiness.homing_required:
            return
        self.runtime_store.save_plotter_readiness(
            PlotterReadinessState(
                work_zero_set=readiness.work_zero_set,
                plotter_ready=readiness.work_zero_set,
                homing_required=False,
                message=(
                    "Homing complete; work zero preserved"
                    if readiness.work_zero_set
                    else "Homing complete; set work zero"
                ),
            )
        )

    def _record_homing_result(
        self, result: FluidNCCommandResult, label: str, *, full_home: bool = True
    ) -> ComponentState:
        if result.ok:
            append_log(
                "plotter", f"FluidNC {label}: {result.message}; verifying post-home state", settings=self.settings
            )
        else:
            append_log(
                "plotter",
                f"FluidNC {label}: {result.message}; connection closed during homing, probing controller",
                level="warning",
                settings=self.settings,
            )
        probe = self.probe_fluidnc_after_delay()
        if probe.online and probe.controller.state != FluidNCState.UNKNOWN:
            if probe.controller.is_idle:
                if full_home:
                    self._clear_homing_requirement()
                message = f"{label}: homing complete; FluidNC {probe.controller.state.value}"
                return self.runtime_store.set_component(
                    "fluidnc", ComponentStatus.RUNNING, message=message, heartbeat=True
                )
            self._disable_print_after_fluidnc_issue(f"{label} ended in FluidNC {probe.controller.state.value}")
            return self.runtime_store.set_component(
                "fluidnc",
                ComponentStatus.WARNING,
                message=f"{label}: FluidNC state is {probe.controller.state.value}",
                last_error=probe.last_error,
                heartbeat=True,
            )
        self._disable_print_after_fluidnc_issue(f"{label} post-home probe failed: {probe.message}")
        return self.runtime_store.set_component(
            "fluidnc",
            ComponentStatus.OFFLINE,
            message=f"{label}: connection lost after homing; {probe.message}",
            last_error=probe.last_error or probe.message,
        )

    def probe_fluidnc_after_delay(self) -> FluidNCProbeResult:
        for delay in (0.4, 1.0, 2.0):
            threading.Event().wait(delay)
            probe = self.probe_fluidnc()
            if probe.online and probe.controller.state != FluidNCState.UNKNOWN:
                return probe
        return probe

    def _disable_print_after_fluidnc_issue(self, message: str) -> None:
        control = self.runtime_store.load_print_control()
        control.print_enabled = False
        control.operator_paused = True
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        self.runtime_store.set_component("print", ComponentStatus.STOPPED, message=message)

    def _apply_saved_fluidnc_endpoint(self, settings: PlotterSettings) -> PlotterSettings:
        endpoint = self.runtime_store.load_json("fluidnc_endpoint")
        host = str(endpoint.get("host", "") or "")
        if not host:
            return settings
        port = int(endpoint.get("port", settings.fluidnc_telnet_port) or settings.fluidnc_telnet_port)
        http_url = str(endpoint.get("http_url", f"http://{host}") or f"http://{host}")
        return replace(
            settings,
            fluidnc_http_url=http_url,
            fluidnc_telnet_host=host,
            fluidnc_telnet_port=port,
            fluidnc_host=host,
            fluidnc_port=port,
        )

    def _save_fluidnc_endpoint(self, probe: FluidNCProbeResult) -> None:
        self.runtime_store.save_json(
            "fluidnc_endpoint",
            {
                "host": probe.telnet_host,
                "port": probe.telnet_port,
                "http_url": probe.http_url or f"http://{probe.telnet_host}",
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
        )
        self.plotter_settings = settings_for_fluidnc_host(self.plotter_settings, probe.telnet_host)

    def _post_macmini_control(self, action: str) -> ComponentState:
        agent_url = self._macmini_agent_url()
        if not agent_url:
            if action in {"start", "restart"}:
                discovered = self.discover_macmini_uploader()
                agent_url = self._macmini_agent_url()
                if discovered.status != ComponentStatus.OFFLINE and agent_url:
                    return self._post_macmini_control(action)
            return self.runtime_store.set_component(
                "macmini_uploader", ComponentStatus.OFFLINE, message="NEJE_MACMINI_AGENT_URL is not set"
            )
        try:
            payload = httpx.post(
                f"{agent_url.rstrip('/')}/control/{action}",
                timeout=self.settings.macmini_agent_timeout_seconds,
                trust_env=False,
            ).json()
        except Exception as exc:  # noqa: BLE001
            append_log("uploader", f"Mac mini uploader {action} failed: {exc}", level="warning", settings=self.settings)
            return self.runtime_store.set_component(
                "macmini_uploader",
                ComponentStatus.OFFLINE,
                message=f"Mac mini uploader {action} failed",
                last_error=str(exc),
            )
        running = bool(payload.get("running", action != "stop"))
        append_log("uploader", f"Mac mini uploader {action}: {payload.get('message', '')}", settings=self.settings)
        return self.runtime_store.set_component(
            "macmini_uploader",
            ComponentStatus.RUNNING if running else ComponentStatus.STOPPED,
            message=str(payload.get("message") or f"Mac mini uploader {action}"),
            heartbeat=True,
        )

    def _macmini_agent_url(self) -> str:
        saved = str(self.runtime_store.load_json("macmini_agent", {}).get("url") or "").strip()
        return saved or self.settings.macmini_agent_url


def _candidate_macmini_agent_urls(configured_url: str = "") -> list[str]:
    urls: list[str] = []
    if configured_url:
        urls.append(configured_url.rstrip("/"))
    for host in _candidate_lan_hosts():
        urls.append(f"http://{host}:8790")
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            unique.append(url)
            seen.add(url)
    return unique


def _candidate_lan_hosts() -> list[str]:
    hosts: set[str] = set()
    for address in _local_ipv4_addresses():
        network = ipaddress.ip_network(f"{address}/24", strict=False)
        hosts.update(str(host) for host in network.hosts())
    hosts.discard("127.0.0.1")
    return sorted(hosts, key=lambda value: tuple(int(part) for part in value.split(".")))


def _local_ipv4_addresses() -> list[str]:
    try:
        output = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False).stdout
    except OSError:
        output = ""
    addresses: list[str] = []
    for match in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)\b", output):
        address = match.group(1)
        if address.startswith(("127.", "169.254.")):
            continue
        addresses.append(address)
    return sorted(set(addresses), key=lambda value: tuple(int(part) for part in value.split(".")))


def _discover_uploader_url(candidate_urls: list[str], *, timeout_seconds: float) -> str:
    if not candidate_urls:
        return ""
    with ThreadPoolExecutor(max_workers=min(64, len(candidate_urls))) as executor:
        futures = {
            executor.submit(_probe_uploader_url, url, timeout_seconds=timeout_seconds): url for url in candidate_urls
        }
        for future in as_completed(futures):
            if future.result():
                return futures[future]
    return ""


def _probe_uploader_url(url: str, *, timeout_seconds: float) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    try:
        payload = httpx.get(f"{url.rstrip('/')}/health", timeout=timeout_seconds, trust_env=False).json()
    except Exception:  # noqa: BLE001
        return False
    service = str(payload.get("service", ""))
    return service in {"standalone-macmini-uploader", "neje-uploader-agent"}


def _homing_disconnect_is_recoverable(result: FluidNCCommandResult) -> bool:
    command = result.command.strip().upper()
    message = result.message.lower()
    return command.startswith("$H") and (
        "closed" in message
        or "reset" in message
        or "timed out" in message
        or "connection" in message
        or "broken pipe" in message
    )


def _enrich_fluidnc_error(result: FluidNCCommandResult) -> FluidNCCommandResult:
    message = result.message.lower()
    if "error:5" in message:
        return FluidNCCommandResult(
            ok=False,
            command=result.command,
            response_lines=result.response_lines,
            error=(
                f"{result.message} - FluidNC homing is not enabled/configured. "
                "Skip homing for this setup, jog to the physical origin, lift the pen, then set work zero."
            ),
        )
    if "error:152" not in message:
        return result
    return FluidNCCommandResult(
        ok=False,
        command=result.command,
        response_lines=result.response_lines,
        error=(
            f"{result.message} - FluidNC reports an invalid configuration. "
            "Open the FluidNC WebUI/serial boot messages and fix config.yaml before unlock, homing, or jogging will work."
        ),
    )


OracleSupervisor = SupervisorService
