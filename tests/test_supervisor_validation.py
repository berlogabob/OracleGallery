from pathlib import Path

from neje_oracle.config import OracleSupervisorSettings, PlotterSettings
from neje_oracle.models import (
    ComponentStatus,
    FluidNCCommandResult,
    FluidNCControllerState,
    FluidNCProbeResult,
    FluidNCState,
    PlotterReadinessState,
    PreflightCheck,
    PreflightLevel,
    PreflightResult,
    SystemMode,
)
from neje_oracle.supervisor import SupervisorService


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
    return PlotterSettings(
        db_path=tmp_path / "runtime" / "plotter.sqlite3",
        placeholder_root=placeholders,
        spool_root=tmp_path / "spool",
        dry_run=True,
    )


def _supervisor(tmp_path: Path, transport_cls=DryTransport) -> SupervisorService:
    return SupervisorService(
        settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3"),
        plotter_settings=_plotter_settings(tmp_path),
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda settings: transport_cls(settings),  # type: ignore[arg-type]
    )


def _save_ok_preflight_and_ready(supervisor: SupervisorService) -> None:
    supervisor.runtime_store.save_preflight_result(
        PreflightResult(status=PreflightLevel.OK, checks=[PreflightCheck("fluidnc", PreflightLevel.OK, "idle")])
    )
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )


def test_start_print_blocked_without_preflight(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )

    state = supervisor.start_print(SystemMode.TEST)

    assert state.status == ComponentStatus.WARNING
    assert "preflight" in state.message.lower()
    assert supervisor.runtime_store.load_print_control().print_enabled is False


def test_start_print_blocked_without_ready_state(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.runtime_store.save_preflight_result(
        PreflightResult(status=PreflightLevel.OK, checks=[PreflightCheck("fluidnc", PreflightLevel.OK, "idle")])
    )

    state = supervisor.start_print(SystemMode.TEST)

    assert state.status == ComponentStatus.WARNING
    assert "work zero" in state.message.lower()
    assert supervisor.runtime_store.load_print_control().print_enabled is False


def test_exhibition_print_starts_after_preflight_ready_and_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    _save_ok_preflight_and_ready(supervisor)

    state = supervisor.start_print(SystemMode.EXHIBITION)

    assert state.status == ComponentStatus.RUNNING
    control = supervisor.runtime_store.load_print_control()
    assert control.print_enabled is True
    assert control.run_mode == "exhibition"
    assert control.dry_run is False


def test_test_print_starts_after_preflight_ready_and_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    _save_ok_preflight_and_ready(supervisor)

    state = supervisor.start_print(SystemMode.TEST)

    assert state.status == ComponentStatus.RUNNING
    control = supervisor.runtime_store.load_print_control()
    assert control.print_enabled is True
    assert control.run_mode == "test"
    assert control.dry_run is False


def test_real_print_blocked_when_fluidnc_not_idle(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, BusyTransport)
    _save_ok_preflight_and_ready(supervisor)

    state = supervisor.start_print(SystemMode.EXHIBITION)

    assert state.status == ComponentStatus.WARNING
    assert "fluidnc" in state.message.lower()
    assert supervisor.runtime_store.load_print_control().print_enabled is False
