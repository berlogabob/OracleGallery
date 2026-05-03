from __future__ import annotations

from pathlib import Path

from neje_oracle.config import OracleSupervisorSettings, PlotterSettings
from neje_oracle.models import ComponentStatus, PlotterRuntimeConfig, PreflightCheck, PreflightLevel, PreflightResult, SystemMode
from neje_oracle.store import OracleRuntimeStore
from neje_oracle.supervisor import SupervisorService


class EmptyRemote:
    def claim_next_plot_job(self, consumer_id: str):
        return None


class DryTransport:
    def __init__(self, settings: PlotterSettings) -> None:
        self.settings = settings

    def check_connection(self, *, timeout_seconds: float = 2.0):
        return True, "fake fluidnc online"

    def send(self, *, gcode: str, sheet_id: str, dry_run=None, progress_callback=None):
        path = self.settings.spool_root / f"{sheet_id}.gcode"
        path.write_text(gcode, encoding="utf-8")
        if progress_callback:
            total = len(gcode.splitlines())
            progress_callback(total, total)
        return path


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
        poll_seconds=10.0,
        dry_run=True,
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


def test_start_system_reports_plotter_start_failure(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=_plotter_settings(tmp_path),
        remote_factory=lambda: (_ for _ in ()).throw(RuntimeError("firebase unavailable")),
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    states = supervisor.start_system(PlotterRuntimeConfig(dry_run=True))

    assert states["plotter"].status == ComponentStatus.ERROR
    assert states["system"].status == ComponentStatus.ERROR
    assert "firebase unavailable" in states["plotter"].last_error


def test_real_print_requires_arm_and_successful_preflight(tmp_path: Path) -> None:
    settings = OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3")
    supervisor = SupervisorService(
        settings=settings,
        plotter_settings=_plotter_settings(tmp_path),
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: DryTransport(resolved),  # type: ignore[arg-type]
    )

    blocked = supervisor.start_print(SystemMode.EXHIBITION_REAL)
    assert blocked.status == ComponentStatus.WARNING
    assert supervisor.runtime_store.load_print_control().print_enabled is False

    supervisor.runtime_store.save_preflight_result(
        PreflightResult(
            status=PreflightLevel.OK,
            checks=[PreflightCheck("fluidnc", PreflightLevel.OK, "online")],
        )
    )
    armed = supervisor.arm_real_fluidnc(SystemMode.EXHIBITION_REAL)
    started = supervisor.start_print(SystemMode.EXHIBITION_REAL)

    assert "armed" in armed.message.lower()
    assert started.status == ComponentStatus.RUNNING
    assert supervisor.runtime_store.load_print_control().print_enabled is True
    assert supervisor.runtime_store.load_print_control().dry_run is False
