import json
from pathlib import Path

from neje_oracle.shared.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings
from neje_oracle.blocks.gui.support import GuiSettings
from neje_oracle.shared.models import (
    ComponentStatus,
    FluidNCCommandResult,
    FluidNCControllerState,
    FluidNCProbeResult,
    FluidNCState,
    PlotterReadinessState,
    SystemMode,
)
from neje_oracle.app.supervisor import SupervisorService


class EmptyRemote:
    def claim_next_plot_job(self, consumer_id: str, *, run_started_at=None):
        return None

    def skip_pending_before(self, cutoff, *, reason: str = "before_run_started_at") -> int:
        return 0


class DryTransport:
    def __init__(self, settings: PlotterSettings) -> None:
        self.settings = settings

    def probe(self, *, timeout_seconds: float = 2.0):
        return FluidNCProbeResult(
            http_online=True,
            telnet_online=True,
            ok=True,
            message="fake fluidnc idle",
            controller=FluidNCControllerState(state=FluidNCState.IDLE),
        )

    def feed_hold(self):
        return FluidNCCommandResult(ok=True, command="!", response_lines=["sent"])


class BusyTransport(DryTransport):
    def probe(self, *, timeout_seconds: float = 2.0):
        return FluidNCProbeResult(
            http_online=True,
            telnet_online=True,
            ok=True,
            message="fake fluidnc run",
            controller=FluidNCControllerState(state=FluidNCState.RUN),
        )


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
    return SupervisorService(
        settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3"),
        plotter_settings=_plotter_settings(tmp_path),
        firebase_settings=_firebase_settings(tmp_path),
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda settings: transport_cls(settings),  # type: ignore[arg-type]
    )


def _save_ready(supervisor: SupervisorService) -> None:
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )


def test_start_print_runs_live_checks_without_saved_result(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    _save_ready(supervisor)

    state = supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))

    assert state.status == ComponentStatus.RUNNING
    assert supervisor.runtime_store.load_system_check_result() is not None
    assert supervisor.runtime_store.load_print_control().print_enabled is True


def test_start_print_blocked_without_ready_state(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)

    state = supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))

    assert state.status == ComponentStatus.WARNING
    assert "work zero" in state.message.lower()
    assert supervisor.runtime_store.load_print_control().print_enabled is False


def test_exhibition_print_starts_after_system_checks_ready_and_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    _save_ready(supervisor)

    state = supervisor.start_print(GuiSettings(system_mode=SystemMode.EXHIBITION.value))

    assert state.status == ComponentStatus.RUNNING
    control = supervisor.runtime_store.load_print_control()
    assert control.print_enabled is True
    assert control.run_mode == "exhibition"
    assert control.dry_run is False


def test_test_print_starts_after_system_checks_ready_and_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    _save_ready(supervisor)

    state = supervisor.start_print(GuiSettings(system_mode=SystemMode.TEST.value))

    assert state.status == ComponentStatus.RUNNING
    control = supervisor.runtime_store.load_print_control()
    assert control.print_enabled is True
    assert control.run_mode == "test"
    assert control.dry_run is False


def test_real_print_blocked_when_fluidnc_not_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, BusyTransport)
    _save_ready(supervisor)

    state = supervisor.start_print(GuiSettings(system_mode=SystemMode.EXHIBITION.value))

    assert state.status == ComponentStatus.WARNING
    assert "fluidnc" in state.message.lower()
    assert supervisor.runtime_store.load_print_control().print_enabled is False
