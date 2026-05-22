from __future__ import annotations

import json
from pathlib import Path

from neje_oracle.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings
from neje_oracle.gui_support import GuiSettings
from neje_oracle.models import (
    ComponentStatus,
    FluidNCCommandResult,
    FluidNCControllerState,
    FluidNCProbeResult,
    FluidNCState,
    PlotterControlState,
    PlotterRuntimeConfig,
    PlotterReadinessState,
    PlotterRuntimeState,
    RuntimeStatus,
    SystemMode,
)
from neje_oracle.store import OracleRuntimeStore, PlotterStore
from neje_oracle.supervisor import SupervisorService


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


def _write_tinybee_config(path: Path, *, x_travel: float = 255.0, y_travel: float = 440.0, z_travel: float = 25.0) -> None:
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
    return FirebaseSettings(project_id="test-project", storage_bucket="test-project.appspot.com", credentials_path=credentials)


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
    plotter_settings = _plotter_settings(tmp_path)
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
        "G0 Z-25.000",
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
