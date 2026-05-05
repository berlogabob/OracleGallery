from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Callable

import httpx

from .config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings
from .firebase_io import FirebaseRemoteRepository
from .gui_modes import mode_to_control
from .gui_support import GuiSettings
from .models import (
    ComponentState,
    ComponentStatus,
    FluidNCCommandResult,
    FluidNCProbeResult,
    PlotterControlState,
    PlotterRuntimeConfig,
    PreflightLevel,
    PreflightResult,
    RuntimeStatus,
    SystemMode,
)
from .oracle_logging import append_log
from .plotter_daemon import PlotterDaemon
from .preflight import PreflightService
from .store import OracleRuntimeStore, PlotterStore
from .transport import FluidNCTransport


class SupervisorService:
    def __init__(
        self,
        *,
        settings: OracleSupervisorSettings | None = None,
        plotter_settings: PlotterSettings | None = None,
        runtime_store: OracleRuntimeStore | None = None,
        remote_factory: Callable[[], FirebaseRemoteRepository] | None = None,
        transport_factory: Callable[[PlotterSettings], FluidNCTransport] | None = None,
    ) -> None:
        self.settings = settings or OracleSupervisorSettings()
        self.plotter_settings = plotter_settings or PlotterSettings()
        self.runtime_store = runtime_store or OracleRuntimeStore(self.settings.runtime_db_path)
        self.remote_factory = remote_factory or (lambda: FirebaseRemoteRepository(FirebaseSettings()))
        self.transport_factory = transport_factory or (lambda resolved_settings: FluidNCTransport(resolved_settings))
        self._plotter_daemon: PlotterDaemon | None = None
        self._plotter_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start_system(self, config: PlotterRuntimeConfig) -> dict[str, ComponentState]:
        self.runtime_store.save_plotter_config(config)
        self.runtime_store.save_print_control(
            PlotterControlState(print_enabled=False, operator_paused=True, run_mode=config.run_mode, dry_run=config.dry_run)
        )
        append_log("system", "Start system requested", settings=self.settings)
        self.runtime_store.set_component("system", ComponentStatus.STARTING, message="Starting supervised system", started=True)
        firebase_state = self.check_firebase()
        macmini_state = self.check_macmini_agent()
        if macmini_state.status != ComponentStatus.OFFLINE:
            macmini_state = self.start_macmini_uploader()
        fluidnc_state = self.check_fluidnc()
        plotter_state = self.start_plotter(config)
        self.runtime_store.set_component("queue", ComponentStatus.RUNNING, message="Queue transport via Firebase")
        self.runtime_store.set_component("print", ComponentStatus.STOPPED, message="Print disabled until START PRINT")
        component_states = {
            "firebase": firebase_state,
            "macmini_uploader": macmini_state,
            "fluidnc": fluidnc_state,
            "plotter": plotter_state,
        }
        if plotter_state.status == ComponentStatus.ERROR:
            self.runtime_store.set_component("system", ComponentStatus.ERROR, message="Supervisor started with plotter error", last_error=plotter_state.last_error)
        elif any(state.status in {ComponentStatus.ERROR, ComponentStatus.WARNING, ComponentStatus.OFFLINE} for state in component_states.values()):
            self.runtime_store.set_component("system", ComponentStatus.WARNING, message="Supervisor running with warnings", heartbeat=True)
        else:
            self.runtime_store.set_component("system", ComponentStatus.RUNNING, message="Supervisor is running", heartbeat=True)
        return self.refresh_all_status()

    def stop_system(self) -> dict[str, ComponentState]:
        append_log("system", "Stop system requested", level="warning", settings=self.settings)
        self.stop_plotter()
        self.stop_macmini_uploader()
        self.runtime_store.save_print_control(PlotterControlState(print_enabled=False, operator_paused=True))
        self.runtime_store.set_component("live_generator", ComponentStatus.STOPPED, message="Live generation stopped")
        self.runtime_store.set_component("queue", ComponentStatus.STOPPED, message="Queue stopped with system")
        self.runtime_store.set_component("print", ComponentStatus.STOPPED, message="Print stopped by operator")
        self.runtime_store.set_component("system", ComponentStatus.STOPPED, message="System stopped by operator")
        return self.refresh_all_status()

    def set_system_mode(self, mode: SystemMode) -> ComponentState:
        self.runtime_store.save_system_mode(mode)
        self.runtime_store.save_real_fluidnc_armed(False)
        control = mode_to_control(mode, print_enabled=False)
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        append_log("system", f"System mode changed to {mode.value}; real FluidNC disarmed", settings=self.settings)
        return self.runtime_store.set_component("system", ComponentStatus.STOPPED, message=f"Mode set to {mode.value}")

    def run_preflight(self, gui_settings: GuiSettings) -> PreflightResult:
        mode = gui_settings.mode
        append_log("preflight", f"Preflight started for {mode.value}", settings=self.settings)
        result = PreflightService(
            supervisor_settings=self.settings,
            plotter_settings=self.plotter_settings,
        ).run(
            mode=mode,
            gui_settings=gui_settings,
        )
        self.runtime_store.save_preflight_result(result)
        status = ComponentStatus.RUNNING
        level = "info"
        if result.status == PreflightLevel.WARNING:
            status = ComponentStatus.WARNING
            level = "warning"
        elif result.status == PreflightLevel.CRITICAL:
            status = ComponentStatus.ERROR
            level = "error"
            self.runtime_store.save_real_fluidnc_armed(False)
        message = f"Preflight {result.status.value}: {len(result.checks)} checks"
        append_log("preflight", message, level=level, settings=self.settings)
        for check in result.checks:
            append_log("preflight", f"{check.level.value}: {check.name}: {check.message}", level=check.level.value if check.level != PreflightLevel.OK else "info", settings=self.settings)
        self.runtime_store.set_component("preflight", status, message=message, heartbeat=True)
        return result

    def arm_real_fluidnc(self, mode: SystemMode) -> ComponentState:
        if mode != SystemMode.EXHIBITION_REAL:
            self.runtime_store.save_real_fluidnc_armed(False)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message="REAL FluidNC can only be armed in EXHIBITION REAL")
        preflight = self.runtime_store.load_preflight_result()
        if preflight is None or preflight.has_critical:
            self.runtime_store.save_real_fluidnc_armed(False)
            append_log("plotter", "Real FluidNC arm blocked by preflight", level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message="Run successful preflight before arming REAL FluidNC")
        fluidnc_state = self.check_fluidnc()
        if fluidnc_state.status != ComponentStatus.RUNNING:
            self.runtime_store.save_real_fluidnc_armed(False)
            append_log("plotter", "Real FluidNC arm blocked: FluidNC offline", level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message="FluidNC is not Idle/online; REAL print blocked")
        self.runtime_store.save_real_fluidnc_armed(True)
        append_log("plotter", "REAL FluidNC armed by operator", level="warning", settings=self.settings)
        return self.runtime_store.set_component("print", ComponentStatus.WARNING, message="REAL FluidNC armed; START PRINT will send to plotter", heartbeat=True)

    def start_print(self, mode: SystemMode) -> ComponentState:
        control = mode_to_control(mode, print_enabled=True)
        if mode == SystemMode.EXHIBITION_REAL and not self.runtime_store.load_real_fluidnc_armed():
            append_log("plotter", "Start print blocked: REAL FluidNC not armed", level="warning", settings=self.settings)
            return self.runtime_store.set_component("print", ComponentStatus.WARNING, message="REAL FluidNC is not armed")
        if mode == SystemMode.EXHIBITION_REAL:
            fluidnc_state = self.check_fluidnc()
            if fluidnc_state.status != ComponentStatus.RUNNING:
                self.runtime_store.save_real_fluidnc_armed(False)
                append_log("plotter", "Start print blocked: FluidNC not Idle/online", level="warning", settings=self.settings)
                return self.runtime_store.set_component("print", ComponentStatus.WARNING, message="FluidNC must be online and Idle before real print")
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        append_log("plotter", f"Print enabled in {mode.value}", level="warning" if not control.dry_run else "info", settings=self.settings)
        return self.runtime_store.set_component("print", ComponentStatus.RUNNING, message=f"Print enabled: {mode.value}", heartbeat=True)

    def stop_print(self) -> ComponentState:
        previous = self.runtime_store.load_print_control()
        previous.print_enabled = False
        previous.operator_paused = True
        self.runtime_store.save_print_control(previous)
        PlotterStore(self.plotter_settings.db_path).save_control_state(previous)
        append_log("plotter", "Stop after sheet requested", level="warning", settings=self.settings)
        return self.runtime_store.set_component("print", ComponentStatus.STOPPED, message="Will stop before next sheet")

    def start_plotter(self, config: PlotterRuntimeConfig | None = None) -> ComponentState:
        with self._lock:
            if self._plotter_thread and self._plotter_thread.is_alive():
                return self.runtime_store.set_component("plotter", ComponentStatus.RUNNING, message="Plotter already running", heartbeat=True)
            if config is not None:
                self.runtime_store.save_plotter_config(config)
            self.runtime_store.set_component("plotter", ComponentStatus.STARTING, message="Starting local plotter daemon", started=True)
            try:
                plotter_store = PlotterStore(self.plotter_settings.db_path)
                remote = self.remote_factory()
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
                return self.runtime_store.set_component("plotter", ComponentStatus.ERROR, message="Plotter failed to start", last_error=str(exc))
        return self.runtime_store.set_component("plotter", ComponentStatus.RUNNING, message="Local plotter daemon running", heartbeat=True)

    def stop_plotter(self) -> ComponentState:
        with self._lock:
            daemon = self._plotter_daemon
            thread = self._plotter_thread
            if daemon is not None:
                daemon.stop()
            if thread is not None:
                thread.join(timeout=5.0)
            self._plotter_daemon = None
            self._plotter_thread = None
        return self.runtime_store.set_component("plotter", ComponentStatus.STOPPED, message="Local plotter daemon stopped")

    def check_firebase(self) -> ComponentState:
        firebase = FirebaseSettings()
        if not firebase.enabled:
            append_log("system", "Firebase is not configured", level="warning", settings=self.settings)
            return self.runtime_store.set_component("firebase", ComponentStatus.WARNING, message="Firebase is not configured")
        append_log("system", f"Firebase configured: {firebase.project_id}", settings=self.settings)
        return self.runtime_store.set_component("firebase", ComponentStatus.RUNNING, message=f"Configured: {firebase.project_id}", heartbeat=True)

    def check_fluidnc(self) -> ComponentState:
        probe = self.probe_fluidnc()
        online = probe.online and probe.controller.is_idle
        status = ComponentStatus.RUNNING if online else ComponentStatus.WARNING if probe.online else ComponentStatus.OFFLINE
        append_log("plotter", f"FluidNC check: {probe.message}", level="info" if online else "warning", settings=self.settings)
        return self.runtime_store.set_component(
            "fluidnc",
            status,
            message=probe.message,
            last_error=probe.last_error,
            heartbeat=online,
        )

    def probe_fluidnc(self) -> FluidNCProbeResult:
        probe = self.transport_factory(self.plotter_settings).probe(timeout_seconds=self.plotter_settings.fluidnc_connect_timeout_seconds)
        self.runtime_store.save_json("fluidnc_probe", probe.to_dict())
        return probe

    def home_fluidnc(self, axis: str | None = None) -> ComponentState:
        if not self._manual_control_allowed("home"):
            return self.runtime_store.load_component_state("fluidnc")
        result = self.transport_factory(self.plotter_settings).home(axis)
        return self._record_fluidnc_command(result, f"Home {axis or 'all'}")

    def jog_fluidnc(self, axis: str, distance: float, feed: float) -> ComponentState:
        if not self._manual_control_allowed("jog"):
            return self.runtime_store.load_component_state("fluidnc")
        result = self.transport_factory(self.plotter_settings).jog(axis, distance, feed)
        return self._record_fluidnc_command(result, f"Jog {axis} {distance:g}mm F{feed:g}")

    def unlock_fluidnc_alarm(self) -> ComponentState:
        probe = self.probe_fluidnc()
        if not probe.controller.is_alarm:
            return self.runtime_store.set_component("fluidnc", ComponentStatus.WARNING, message=f"Unlock skipped: FluidNC state is {probe.controller.state.value}")
        result = self.transport_factory(self.plotter_settings).unlock_alarm()
        return self._record_fluidnc_command(result, "Unlock alarm")

    def emergency_stop_fluidnc(self) -> ComponentState:
        result = self.transport_factory(self.plotter_settings).feed_hold()
        self.runtime_store.save_real_fluidnc_armed(False)
        control = self.runtime_store.load_print_control()
        control.print_enabled = False
        control.operator_paused = True
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        level = "warning" if result.ok else "error"
        append_log("plotter", f"Emergency stop/feed hold: {result.message}", level=level, settings=self.settings)
        self.runtime_store.set_component("print", ComponentStatus.STOPPED, message="Emergency stop sent; print disabled")
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
            return self.runtime_store.set_component("fluidnc", ComponentStatus.WARNING, message=f"Resume skipped: FluidNC state is {probe.controller.state.value}")
        result = self.transport_factory(self.plotter_settings).cycle_start()
        return self._record_fluidnc_command(result, "Resume/cycle start")

    def soft_reset_fluidnc(self) -> ComponentState:
        result = self.transport_factory(self.plotter_settings).soft_reset()
        self.runtime_store.save_real_fluidnc_armed(False)
        control = self.runtime_store.load_print_control()
        control.print_enabled = False
        control.operator_paused = True
        self.runtime_store.save_print_control(control)
        PlotterStore(self.plotter_settings.db_path).save_control_state(control)
        return self._record_fluidnc_command(result, "Soft reset/abort")

    def check_macmini_agent(self) -> ComponentState:
        if not self.settings.macmini_agent_url:
            return self.runtime_store.set_component("macmini_uploader", ComponentStatus.OFFLINE, message="NEJE_MACMINI_AGENT_URL is not set")
        try:
            payload = httpx.get(
                f"{self.settings.macmini_agent_url.rstrip('/')}/status",
                timeout=self.settings.macmini_agent_timeout_seconds,
            ).json()
        except Exception as exc:  # noqa: BLE001
            append_log("uploader", f"Mac mini uploader offline: {exc}", level="warning", settings=self.settings)
            return self.runtime_store.set_component("macmini_uploader", ComponentStatus.OFFLINE, message="Mac mini uploader agent offline", last_error=str(exc))
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
        if not self.settings.macmini_agent_url:
            return self.runtime_store.set_component("macmini_uploader", ComponentStatus.OFFLINE, message="NEJE_MACMINI_AGENT_URL is not set")
        try:
            payload = httpx.post(
                f"{self.settings.macmini_agent_url.rstrip('/')}/scan-once",
                timeout=self.settings.macmini_agent_timeout_seconds,
            ).json()
        except Exception as exc:  # noqa: BLE001
            append_log("uploader", f"Mac mini scan failed: {exc}", level="warning", settings=self.settings)
            return self.runtime_store.set_component("macmini_uploader", ComponentStatus.OFFLINE, message="Mac mini scan failed", last_error=str(exc))
        append_log("uploader", f"Mac mini scan imported {len(payload.get('imported', []))} session(s)", settings=self.settings)
        return self.runtime_store.set_component(
            "macmini_uploader",
            ComponentStatus.RUNNING,
            message=f"Scan imported {len(payload.get('imported', []))} session(s)",
            heartbeat=True,
        )

    def refresh_all_status(self) -> dict[str, ComponentState]:
        states = self.runtime_store.load_all_component_states()
        for name in ("system", "macmini_uploader", "firebase", "plotter", "fluidnc", "queue", "print", "live_generator"):
            states.setdefault(name, self.runtime_store.load_component_state(name))
        if self._plotter_thread and self._plotter_thread.is_alive():
            states["plotter"] = self.runtime_store.set_component("plotter", ComponentStatus.RUNNING, message=states["plotter"].message or "Local plotter daemon running", heartbeat=True)
        return states

    def _manual_control_allowed(self, action: str) -> bool:
        state = PlotterStore(self.plotter_settings.db_path).load_runtime_state()
        if state.status == RuntimeStatus.PRINTING:
            self.runtime_store.set_component("fluidnc", ComponentStatus.WARNING, message=f"{action} blocked while plotter is printing")
            return False
        control = self.runtime_store.load_print_control()
        if control.print_enabled:
            control.print_enabled = False
            control.operator_paused = True
            self.runtime_store.save_print_control(control)
            PlotterStore(self.plotter_settings.db_path).save_control_state(control)
            self.runtime_store.save_real_fluidnc_armed(False)
            self.runtime_store.set_component("print", ComponentStatus.STOPPED, message=f"Print paused before manual {action}")
            append_log("plotter", f"Print paused before manual {action}", level="warning", settings=self.settings)
        return True

    def _record_fluidnc_command(self, result: FluidNCCommandResult, label: str) -> ComponentState:
        level = "info" if result.ok else "error"
        append_log("plotter", f"FluidNC {label}: {result.message}", level=level, settings=self.settings)
        if not result.ok:
            self.runtime_store.save_real_fluidnc_armed(False)
            control = self.runtime_store.load_print_control()
            control.print_enabled = False
            control.operator_paused = True
            self.runtime_store.save_print_control(control)
            PlotterStore(self.plotter_settings.db_path).save_control_state(control)
            self.runtime_store.set_component("print", ComponentStatus.STOPPED, message=f"Print disabled after FluidNC error: {result.message}")
        return self.runtime_store.set_component(
            "fluidnc",
            ComponentStatus.RUNNING if result.ok else ComponentStatus.ERROR,
            message=f"{label}: {result.message}",
            last_error="" if result.ok else result.message,
            heartbeat=result.ok,
        )

    def component_summary(self) -> dict[str, dict[str, Any]]:
        return {name: state.to_dict() for name, state in self.refresh_all_status().items()}

    def _post_macmini_control(self, action: str) -> ComponentState:
        if not self.settings.macmini_agent_url:
            return self.runtime_store.set_component("macmini_uploader", ComponentStatus.OFFLINE, message="NEJE_MACMINI_AGENT_URL is not set")
        try:
            payload = httpx.post(
                f"{self.settings.macmini_agent_url.rstrip('/')}/control/{action}",
                timeout=self.settings.macmini_agent_timeout_seconds,
            ).json()
        except Exception as exc:  # noqa: BLE001
            append_log("uploader", f"Mac mini uploader {action} failed: {exc}", level="warning", settings=self.settings)
            return self.runtime_store.set_component("macmini_uploader", ComponentStatus.OFFLINE, message=f"Mac mini uploader {action} failed", last_error=str(exc))
        running = bool(payload.get("running", action != "stop"))
        append_log("uploader", f"Mac mini uploader {action}: {payload.get('message', '')}", settings=self.settings)
        return self.runtime_store.set_component(
            "macmini_uploader",
            ComponentStatus.RUNNING if running else ComponentStatus.STOPPED,
            message=str(payload.get("message") or f"Mac mini uploader {action}"),
            heartbeat=True,
        )


def plotter_config_from_values(
    *,
    layout_mode: str,
    sheet_width_mm: float,
    sheet_height_mm: float,
    sheet_margin_mm: float,
    cell_diameter_mm: float,
    gap_mm: float,
    run_mode: str,
    dry_run: bool,
) -> PlotterRuntimeConfig:
    return PlotterRuntimeConfig(
        layout_mode=layout_mode,
        sheet_width_mm=sheet_width_mm,
        sheet_height_mm=sheet_height_mm,
        sheet_margin_mm=sheet_margin_mm,
        cell_diameter_mm=cell_diameter_mm,
        gap_mm=gap_mm,
        run_mode=run_mode,
        dry_run=dry_run,
        updated_at=datetime.now(tz=UTC),
    )
