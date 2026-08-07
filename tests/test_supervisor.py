from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from neje_oracle.app.supervisor import SupervisorService
from neje_oracle.blocks.gui.support import GuiSettings
from neje_oracle.shared.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings
from neje_oracle.shared.models import (
    ComponentStatus,
    FluidNCCommandResult,
    FluidNCControllerState,
    FluidNCProbeResult,
    FluidNCState,
    PlotterReadinessState,
    PlotterRuntimeConfig,
    PlotterRuntimeState,
    RuntimeStatus,
    SystemMode,
)
from neje_oracle.shared.store import OracleRuntimeStore, PlotterStore


class EmptyRemote:
    def __init__(self) -> None:
        self.skipped_before = None

    def claim_next_plot_job(self, consumer_id: str, *, run_started_at=None):
        return None

    def skip_pending_before(self, cutoff, *, reason: str = "before_run_started_at") -> int:
        self.skipped_before = cutoff
        return 0


class DryTransport:
    def __init__(self, settings: PlotterSettings) -> None:
        self.settings = settings
        self.commands: list[str] = []

    def check_connection(self, *, timeout_seconds: float = 2.0):
        return True, "fake fluidnc online"

    def probe(self, *, timeout_seconds: float = 2.0):
        return FluidNCProbeResult(
            http_online=True,
            telnet_online=True,
            ok=True,
            message="fake fluidnc online",
            controller=FluidNCControllerState(state=FluidNCState.IDLE),
        )

    def feed_hold(self):
        return FluidNCCommandResult(ok=True, command="!", response_lines=["sent"])

    def unlock_alarm(self):
        self.commands.append("$X")
        return FluidNCCommandResult(ok=True, command="$X", response_lines=["ok"])

    def jog(self, axis: str, distance_mm: float, feed_mm_min: float):
        command = f"$J={axis}{distance_mm}"
        self.commands.append(command)
        return FluidNCCommandResult(ok=True, command=command)

    def pen_up(self):
        self.commands.append(self.settings.pen_up_command)
        return FluidNCCommandResult(ok=True, command=self.settings.pen_up_command, response_lines=["ok"])

    def pen_down(self):
        self.commands.append(self.settings.pen_down_command)
        return FluidNCCommandResult(ok=True, command=self.settings.pen_down_command, response_lines=["ok"])

    def send_command(self, command: str, *, wait_for_ok: bool = True, timeout_seconds=None):
        self.commands.append(command)
        return FluidNCCommandResult(ok=True, command=command, response_lines=["ok"])

    def home(self, axis: str | None = None):
        command = "$H" if axis is None else f"$H={axis.upper()}"
        self.commands.append(command)
        return FluidNCCommandResult(ok=True, command=command, response_lines=["ok"])

    def send_commands(self, commands: list[str], *, timeout_seconds=None):
        self.commands.extend(commands)
        return FluidNCCommandResult(ok=True, command=" ; ".join(commands), response_lines=["ok"] * len(commands))

    def send(self, *, gcode: str, sheet_id: str, dry_run=None, progress_callback=None):
        path = self.settings.spool_root / f"{sheet_id}.gcode"
        path.write_text(gcode, encoding="utf-8")
        if progress_callback:
            total = len(gcode.splitlines())
            progress_callback(total, total)
        return path


class HomeReconnectTransport(DryTransport):
    def __init__(self, settings: PlotterSettings) -> None:
        super().__init__(settings)
        self.probe_count = 0

    def home(self, axis: str | None = None):
        command = "$H" if axis is None else f"$H={axis.upper()}"
        self.commands.append(command)
        return FluidNCCommandResult(ok=False, command=command, error="Connection closed by FluidNC")

    def probe(self, *, timeout_seconds: float = 2.0):
        self.probe_count += 1
        return FluidNCProbeResult(
            http_online=True,
            telnet_online=True,
            ok=True,
            message="fake fluidnc idle after homing",
            controller=FluidNCControllerState(state=FluidNCState.IDLE),
        )


class BusyTransport(DryTransport):
    def probe(self, *, timeout_seconds: float = 2.0):
        return FluidNCProbeResult(
            http_online=True,
            telnet_online=True,
            ok=True,
            message="fake fluidnc running",
            controller=FluidNCControllerState(state=FluidNCState.RUN),
        )


class InvalidConfigUnlockTransport(DryTransport):
    def unlock_alarm(self):
        self.commands.append("$X")
        return FluidNCCommandResult(ok=False, command="$X", error="error:152")


class HomingDisabledTransport(DryTransport):
    def home(self, axis: str | None = None):
        command = "$H" if axis is None else f"$H={axis.upper()}"
        self.commands.append(command)
        return FluidNCCommandResult(ok=False, command=command, error="error:5")


def _plotter_settings(tmp_path: Path) -> PlotterSettings:
    placeholders = tmp_path / "placeholders"
    placeholders.mkdir(parents=True)
    (placeholders / "idle.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )
    tinybee_config = tmp_path / "tinybee.json"
    _write_tinybee_config(tinybee_config)
    return PlotterSettings(
        db_path=tmp_path / "runtime" / "plotter.sqlite3",
        placeholder_root=placeholders,
        spool_root=tmp_path / "spool",
        tinybee_config_path=tinybee_config,
        poll_seconds=10.0,
        dry_run=True,
    )


def _write_tinybee_config(
    path: Path, *, x_travel: float = 255.0, y_travel: float = 440.0, z_travel: float = 25.0
) -> None:
    settings = {
        "Flash": {"Settings": [{"id": "Telnet/Enable", "value": "1"}, {"id": "Telnet/Port", "value": "23"}]},
        "Running": {
            "Config": [
                {"id": "/board", "value": "MKS TinyBee V1.0 XXYYZ"},
                {"id": "/axes/X/max_travel_mm", "value": f"{x_travel:.3f}"},
                {"id": "/axes/Y/max_travel_mm", "value": f"{y_travel:.3f}"},
                {"id": "/axes/Z/max_travel_mm", "value": f"{z_travel:.3f}"},
                {"id": "/axes/X/homing/allow_single_axis", "value": "1"},
                {"id": "/axes/Y/homing/allow_single_axis", "value": "1"},
                {"id": "/axes/Z/homing/allow_single_axis", "value": "1"},
                {"id": "/axes/Z/motor0/rc_servo/pwm_hz", "value": "50"},
            ]
        },
    }
    path.write_text(json.dumps(settings), encoding="utf-8")


def _firebase_settings(tmp_path: Path) -> FirebaseSettings:
    credentials = tmp_path / "firebase.json"
    credentials.write_text("{}", encoding="utf-8")
    return FirebaseSettings(
        project_id="test-project", storage_bucket="test-project.appspot.com", credentials_path=credentials
    )


def _supervisor(tmp_path: Path, transport_cls=DryTransport) -> SupervisorService:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    return SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        firebase_settings=_firebase_settings(tmp_path),
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport_cls(resolved),  # type: ignore[arg-type]
    )


def test_oracle_runtime_store_roundtrip(tmp_path: Path) -> None:
    store = OracleRuntimeStore(tmp_path / "oracle.sqlite3")
    config = PlotterRuntimeConfig(layout_mode="grid", sheet_width_mm=300, sheet_height_mm=200, cell_diameter_mm=50)

    store.save_plotter_config(config)
    store.set_component("plotter", ComponentStatus.RUNNING, message="ok", heartbeat=True, started=True)

    assert store.load_plotter_config().layout_mode == "grid"
    assert store.load_plotter_config().cell_diameter_mm == 50
    assert store.load_component_state("plotter").status == ComponentStatus.RUNNING
    assert store.load_component_state("plotter").heartbeat_at is not None


def test_supervisor_starts_and_stops_local_plotter_once(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = replace(_plotter_settings(tmp_path), poll_seconds=0.01)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    first = supervisor.start_plotter(PlotterRuntimeConfig(dry_run=True))
    second = supervisor.start_plotter(PlotterRuntimeConfig(dry_run=True))

    assert first.status == ComponentStatus.RUNNING
    assert second.status == ComponentStatus.RUNNING
    assert supervisor.refresh_all_status()["plotter"].status == ComponentStatus.RUNNING

    stopped = supervisor.stop_plotter()

    assert stopped.status == ComponentStatus.STOPPED


def test_stop_plotter_keeps_still_running_daemon_references(tmp_path: Path) -> None:
    class StuckDaemon:
        stop_requested = False

        def stop(self) -> None:
            self.stop_requested = True

    class StuckThread:
        def join(self, *, timeout: float | None = None) -> None:
            assert timeout == 5.0

        def is_alive(self) -> bool:
            return True

    supervisor = _supervisor(tmp_path)
    daemon = StuckDaemon()
    thread = StuckThread()
    supervisor._plotter_daemon = daemon  # type: ignore[assignment]
    supervisor._plotter_thread = thread  # type: ignore[assignment]

    stopped = supervisor.stop_plotter()

    assert stopped.status == ComponentStatus.WARNING
    assert daemon.stop_requested is True
    assert supervisor._plotter_thread is thread
    assert supervisor._plotter_daemon is daemon

    restarted = supervisor.start_plotter()

    assert restarted.status == ComponentStatus.RUNNING
    assert "already running" in restarted.message.lower()
    assert supervisor._plotter_thread is thread


def test_refresh_all_status_preserves_plotter_error(tmp_path: Path) -> None:
    class LiveThread:
        def is_alive(self) -> bool:
            return True

    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.set_component("plotter", ComponentStatus.ERROR, message="Plotter failed")
    supervisor._plotter_thread = LiveThread()  # type: ignore[assignment]

    states = supervisor.refresh_all_status()

    assert states["plotter"].status == ComponentStatus.ERROR


def test_start_system_uses_local_idle_remote_when_firebase_missing_in_dry_run(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=_plotter_settings(tmp_path),
        remote_factory=lambda: (_ for _ in ()).throw(RuntimeError("firebase unavailable")),
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    states = supervisor.start_system(PlotterRuntimeConfig(dry_run=True))

    assert states["plotter"].status == ComponentStatus.RUNNING
    assert states["queue"].status == ComponentStatus.WARNING
    assert "local idle" in states["queue"].message.lower()
    supervisor.stop_plotter()


def test_start_system_reports_plotter_start_failure_in_real_mode(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=_plotter_settings(tmp_path),
        remote_factory=lambda: (_ for _ in ()).throw(RuntimeError("firebase unavailable")),
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    states = supervisor.start_system(PlotterRuntimeConfig(dry_run=False))

    assert states["plotter"].status == ComponentStatus.ERROR
    assert states["system"].status == ComponentStatus.ERROR
    assert "firebase unavailable" in states["plotter"].last_error


def test_real_print_requires_system_checks_and_work_zero(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=_plotter_settings(tmp_path),
        firebase_settings=_firebase_settings(tmp_path),
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    blocked = supervisor.start_print(GuiSettings(system_mode=SystemMode.EXHIBITION.value))
    assert blocked.status == ComponentStatus.WARNING
    assert supervisor.runtime_store.load_print_control().print_enabled is False

    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    started = supervisor.start_print(GuiSettings(system_mode=SystemMode.EXHIBITION.value))

    assert started.status == ComponentStatus.RUNNING
    assert supervisor.runtime_store.load_print_control().print_enabled is True
    assert supervisor.runtime_store.load_print_control().dry_run is False


def test_print_uploaded_svg_sends_direct_gcode_when_fluidnc_idle(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = DryTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>"
    )

    state = supervisor.print_uploaded_svg(
        GuiSettings(system_mode=SystemMode.TEST.value, sheet_width_mm=200, sheet_height_mm=120, cell_diameter_mm=80),
        svg_bytes=svg.encode("utf-8"),
        original_name="label-test.svg",
    )

    assert state.status == ComponentStatus.STOPPED
    gcode_files = list(plotter_settings.spool_root.glob("testsvg_*.gcode"))
    assert len(gcode_files) == 1
    gcode = gcode_files[0].read_text(encoding="utf-8")
    assert "direct SVG LABEL TEST" in gcode
    assert "G0 Z" in gcode
    assert "G0 X0 Y0" in gcode
    runtime = PlotterStore(plotter_settings.db_path).load_runtime_state()
    assert runtime.status == RuntimeStatus.OPERATOR_PAUSED
    assert runtime.sheet_progress_percent == 100.0


def test_print_uploaded_svg_blocks_when_fluidnc_not_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, transport_cls=BusyTransport)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>"
    )

    state = supervisor.print_uploaded_svg(GuiSettings(), svg_bytes=svg.encode("utf-8"), original_name="busy.svg")

    assert state.status == ComponentStatus.WARNING
    assert "Idle" in state.message
    assert not list(supervisor.plotter_settings.spool_root.glob("testsvg_*.gcode"))


def test_emergency_stop_disables_print_and_clears_readiness(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))

    state = supervisor.emergency_stop_fluidnc()

    assert state.status == ComponentStatus.WARNING
    assert supervisor.runtime_store.load_print_control().print_enabled is False
    assert supervisor.runtime_store.load_plotter_readiness().plotter_ready is False


def test_jog_blocked_while_printing(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    PlotterStore(plotter_settings.db_path).save_runtime_state(PlotterRuntimeState(status=RuntimeStatus.PRINTING))
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    supervisor.jog_fluidnc("X", 1.0, 1000)

    assert supervisor.runtime_store.load_component_state("fluidnc").status == ComponentStatus.WARNING


def test_manual_control_pauses_enabled_print_before_jog(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))
    assert supervisor.runtime_store.load_print_control().print_enabled is True

    state = supervisor.jog_fluidnc("X", 5.0, 1000)

    assert state.status == ComponentStatus.RUNNING
    assert supervisor.runtime_store.load_print_control().print_enabled is False


def test_manual_z_control_uses_absolute_servo_z_not_jog(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = DryTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_config(PlotterRuntimeConfig(use_z_servo=True, z_down_mm=-12.0))

    up = supervisor.pen_up_fluidnc()
    down = supervisor.pen_down_fluidnc()

    assert up.status == ComponentStatus.RUNNING
    assert down.status == ComponentStatus.RUNNING
    assert transport.commands == [
        "G21",
        "G90",
        "G54",
        "G0 Z0.000",
        "G21",
        "G90",
        "G54",
        # Honours the configured z_down_mm (-12.0) at the configured feed, matching the
        # sheet G-code path. Previously this was a hardcoded rapid "G0 Z-25.000", which
        # ignored the config and slammed the servo to a depth the operator never chose.
        "G1 Z-12.000 F1000.00",
    ]
    assert all(not command.startswith("$J=") for command in transport.commands)


def test_set_work_zero_migrates_legacy_z_zero_for_servo(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = DryTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_config(PlotterRuntimeConfig(work_zero_command="G10 L20 P1 X0 Y0 Z0"))

    supervisor.set_work_zero()

    assert transport.commands == ["G10 L20 P1 X0 Y0"]


def test_set_work_zero_sets_ready_state(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_config(PlotterRuntimeConfig(work_zero_command="G10 L20 P1 X0 Y0"))

    state = supervisor.set_work_zero()

    assert state.status == ComponentStatus.RUNNING
    readiness = supervisor.runtime_store.load_plotter_readiness()
    assert readiness.work_zero_set is True
    assert readiness.plotter_ready is True


def test_home_recovers_when_fluidnc_closes_connection_during_homing(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = HomeReconnectTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )

    state = supervisor.home_fluidnc()

    assert state.status == ComponentStatus.RUNNING
    assert "$H" in transport.commands
    assert transport.probe_count >= 1
    assert "homing complete" in state.message.lower()


def test_home_xy_button_uses_full_homing_command(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = DryTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )

    state = supervisor.home_xy_fluidnc()

    assert state.status == ComponentStatus.RUNNING
    assert "$H" in transport.commands
    assert "$H=XY" not in transport.commands


def test_unlock_alarm_sends_x_without_requiring_alarm_probe(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = DryTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )

    state = supervisor.unlock_fluidnc_alarm()

    assert state.status == ComponentStatus.RUNNING
    assert "$X" in transport.commands


def test_unlock_alarm_explains_invalid_fluidnc_config(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = InvalidConfigUnlockTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )

    state = supervisor.unlock_fluidnc_alarm()

    assert state.status == ComponentStatus.ERROR
    assert "$X" in transport.commands
    assert "invalid configuration" in state.message.lower()


def test_home_explains_disabled_fluidnc_homing(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    plotter_settings = _plotter_settings(tmp_path)
    transport = HomingDisabledTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )

    state = supervisor.home_fluidnc()

    assert state.status == ComponentStatus.ERROR
    assert "$H" in transport.commands
    assert "homing is not enabled" in state.message.lower()


def test_start_print_blocked_without_ready_state(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=_plotter_settings(tmp_path),
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    blocked = supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))

    assert blocked.status == ComponentStatus.WARNING
    assert supervisor.runtime_store.load_print_control().print_enabled is False


def test_stop_print_disables_printing_in_both_stores(tmp_path: Path) -> None:
    """STOP PRINT must reach the store the daemon actually polls.

    The daemon re-reads print_enabled from PlotterStore, so writing only the oracle
    runtime store would leave the sheet streaming.
    """
    supervisor = _supervisor(tmp_path)
    control = supervisor.runtime_store.load_print_control()
    control.print_enabled = True
    control.operator_paused = False
    supervisor.runtime_store.save_print_control(control)
    PlotterStore(supervisor.plotter_settings.db_path).save_control_state(control)

    state = supervisor.stop_print()

    assert state.status == ComponentStatus.STOPPED
    assert supervisor.runtime_store.load_print_control().print_enabled is False
    assert PlotterStore(supervisor.plotter_settings.db_path).load_control_state().print_enabled is False


def test_is_printing_reflects_plotter_runtime_state(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    store = PlotterStore(supervisor.plotter_settings.db_path)

    store.save_runtime_state(PlotterRuntimeState(status=RuntimeStatus.OPERATOR_PAUSED))
    assert supervisor.is_printing() is False

    store.save_runtime_state(PlotterRuntimeState(status=RuntimeStatus.PRINTING))
    assert supervisor.is_printing() is True


def _probe_in_state(state: FluidNCState, position: tuple[float, float, float]) -> FluidNCProbeResult:
    return FluidNCProbeResult(
        http_online=True,
        telnet_online=True,
        ok=True,
        message=state.value,
        controller=FluidNCControllerState(state=state, machine_position=position),
    )


def _alarm_probe() -> FluidNCProbeResult:
    return _probe_in_state(FluidNCState.ALARM, (0.0, 0.0, 0.0))


def _idle_probe() -> FluidNCProbeResult:
    return _probe_in_state(FluidNCState.IDLE, (0.0, 0.0, 0.0))


def test_controller_alarm_invalidates_readiness(tmp_path: Path) -> None:
    """A panic/reboot must not leave the app reporting "plotter ready".

    Observed live 2026-08-07: FluidNC panicked mid-print and came back in Alarm with its
    position reference gone, while readiness still said work_zero_set/plotter_ready True
    and the UI invited START PRINT.
    """
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="Work zero set; plotter ready")
    )

    supervisor.check_fluidnc(_alarm_probe())

    readiness = supervisor.runtime_store.load_plotter_readiness()
    assert readiness.homing_required is True
    assert readiness.plotter_ready is False
    assert readiness.work_zero_set is True  # G54 survives; only homing is needed


def test_unlocking_an_alarm_does_not_make_the_plotter_printable(tmp_path: Path) -> None:
    """$X clears the alarm to Idle without restoring the reference.

    This is the hazard path: after a reboot the head sat at ~(129, 142) while the
    controller believed 0,0,0. Unlock made it read Idle, which was the single condition
    guarding START PRINT.
    """
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="Work zero set; plotter ready")
    )
    supervisor.check_fluidnc(_alarm_probe())

    # Operator presses UNLOCK; controller now reports Idle again.
    supervisor.check_fluidnc(_idle_probe())

    blocked = supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))
    assert blocked.status == ComponentStatus.WARNING
    assert "HOME ALL" in blocked.message
    assert supervisor.runtime_store.load_print_control().print_enabled is False


def test_feed_hold_does_not_require_rehoming(tmp_path: Path) -> None:
    """Hold preserves MPos and G54, so it must not force a re-home."""
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="Work zero set; plotter ready")
    )

    supervisor.check_fluidnc(_probe_in_state(FluidNCState.HOLD, (57.5, 45.2, -17.4)))

    assert supervisor.runtime_store.load_plotter_readiness().homing_required is False


def test_set_work_zero_does_not_clear_an_outstanding_homing_requirement(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    supervisor.check_fluidnc(_alarm_probe())

    supervisor.set_work_zero()

    readiness = supervisor.runtime_store.load_plotter_readiness()
    assert readiness.homing_required is True
    assert readiness.plotter_ready is False


def test_full_homing_clears_the_requirement_and_keeps_work_zero(tmp_path: Path) -> None:
    """Homing is what restores safety; G54 lives in flash so no re-zero is needed."""
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    supervisor.check_fluidnc(_alarm_probe())
    assert supervisor.runtime_store.load_plotter_readiness().homing_required is True

    supervisor.home_fluidnc()

    readiness = supervisor.runtime_store.load_plotter_readiness()
    assert readiness.homing_required is False
    assert readiness.work_zero_set is True
    assert readiness.plotter_ready is True


def test_single_axis_homing_does_not_clear_the_requirement(tmp_path: Path) -> None:
    """$H=Z restores nothing about XY, so it must not mark the machine safe."""
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    supervisor.check_fluidnc(_alarm_probe())

    supervisor.home_fluidnc("Z")

    assert supervisor.runtime_store.load_plotter_readiness().homing_required is True
