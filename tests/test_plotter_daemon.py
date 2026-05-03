from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from neje_oracle.config import PlotterSettings
from neje_oracle.models import PlotJobLease, PlotStatus, PlotterControlState, PlotterRuntimeConfig, RuntimeStatus
from neje_oracle.plotter_daemon import PlotterDaemon
from neje_oracle.store import OracleRuntimeStore, PlotterStore
from neje_oracle.transport import FluidNCTransport


SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
    "</svg>"
)


class FakeRemoteRepository:
    def __init__(self, jobs: list[PlotJobLease] | None = None, *, fail_claim: bool = False) -> None:
        self.jobs = jobs or []
        self.fail_claim = fail_claim
        self.updates: list[tuple[str, str, str]] = []

    def claim_next_plot_job(self, consumer_id: str) -> PlotJobLease | None:
        if self.fail_claim:
            raise RuntimeError("firestore down")
        if not self.jobs:
            return None
        return self.jobs.pop(0)

    def update_plot_job(
        self,
        session_id: str,
        status: PlotStatus,
        *,
        sheet_id: str = "",
        sheet_index: int | None = None,
        error: str = "",
    ) -> None:
        self.updates.append((session_id, status.value, sheet_id))

    def download_asset(self, storage_path: str, destination: Path) -> None:
        destination.write_text(SVG, encoding="utf-8")


def _settings(tmp_path: Path) -> PlotterSettings:
    return PlotterSettings(
        db_path=tmp_path / "runtime" / "plotter.sqlite3",
        placeholder_root=tmp_path / "placeholders",
        spool_root=tmp_path / "spool",
        poll_seconds=0.0,
        sheet_width_mm=594,
        sheet_height_mm=841,
        sheet_margin_mm=24,
        cell_diameter_mm=160,
        layout_mode="hex",
        sample_step_mm=8.0,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        dry_run=True,
        fluidnc_host="localhost",
        fluidnc_port=23,
        operator_host="127.0.0.1",
        operator_port=8765,
    )


def test_plotter_finishes_sheet_and_pauses_for_reload(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    jobs = [
        PlotJobLease(
            session_id="session_a",
            title="A",
            summary="",
            created_at=datetime.now(tz=UTC),
            priority="user",
            queue="user",
            svg_storage_path="sessions/a/artwork.svg",
            svg_url="",
        ),
        PlotJobLease(
            session_id="session_b",
            title="B",
            summary="",
            created_at=datetime.now(tz=UTC),
            priority="user",
            queue="user",
            svg_storage_path="sessions/b/artwork.svg",
            svg_url="",
        ),
    ]
    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    store.save_control_state(PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True))
    remote = FakeRemoteRepository(jobs)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport)

    daemon.run_cycle()

    gcode_files = list((tmp_path / "spool").glob("*.gcode"))
    assert len(gcode_files) == 1
    state = daemon.get_state()
    assert state.status == RuntimeStatus.PAUSED
    assert state.pending_reload is True
    assert state.gcode_progress_percent == 100.0
    assert state.gcode_lines_sent == state.gcode_lines_total
    assert state.gcode_lines_total > 0
    assert ("session_a", PlotStatus.PRINTED.value, state.current_sheet_id) in remote.updates
    assert ("session_b", PlotStatus.PRINTED.value, state.current_sheet_id) in remote.updates


def test_plotter_can_fall_back_to_placeholders_when_remote_is_down(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    store.save_control_state(PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True))
    remote = FakeRemoteRepository(fail_claim=True)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport)

    daemon.run_cycle()

    gcode_files = list((tmp_path / "spool").glob("*.gcode"))
    assert len(gcode_files) == 1
    assert daemon.get_state().status == RuntimeStatus.PAUSED


def test_plotter_stops_before_next_sheet_when_operator_disabled(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    store.save_control_state(PlotterControlState(print_enabled=False, operator_paused=True, run_mode="exhibition", dry_run=True))
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport)

    daemon.run_cycle()

    assert not list((tmp_path / "spool").glob("*.gcode"))
    assert daemon.get_state().status == RuntimeStatus.OPERATOR_PAUSED


def test_plotter_uses_oracle_runtime_config_for_next_sheet(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    oracle_store.save_print_control(PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True))
    oracle_store.save_plotter_config(
        PlotterRuntimeConfig(
            layout_mode="grid",
            sheet_width_mm=300,
            sheet_height_mm=220,
            sheet_margin_mm=0,
            cell_diameter_mm=80,
            gap_mm=20,
            run_mode="test",
            dry_run=True,
        )
    )
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)

    daemon.run_cycle()

    manifest = next((tmp_path / "spool").glob("*.json")).read_text(encoding="utf-8")
    assert '"layout_mode": "grid"' in manifest
    assert '"cell_diameter_mm": 80' in manifest
    assert '"gap_mm": 20' in manifest
