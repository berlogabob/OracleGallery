from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from neje_oracle.config import PlotterSettings
from neje_oracle.models import PlotJobLease, PlotStatus, RuntimeStatus
from neje_oracle.plotter_daemon import PlotterDaemon
from neje_oracle.store import PlotterStore
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

    def update_plot_job(self, session_id: str, status: PlotStatus, *, sheet_id: str = "", error: str = "") -> None:
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
        sheet_capacity=3,
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
            svg_storage_path="sessions/a/artwork.svg",
            svg_url="",
            preview_url="",
        ),
        PlotJobLease(
            session_id="session_b",
            title="B",
            summary="",
            created_at=datetime.now(tz=UTC),
            priority="user",
            svg_storage_path="sessions/b/artwork.svg",
            svg_url="",
            preview_url="",
        ),
    ]
    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    remote = FakeRemoteRepository(jobs)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport)

    daemon.run_cycle()

    gcode_files = list((tmp_path / "spool").glob("*.gcode"))
    assert len(gcode_files) == 1
    state = daemon.get_state()
    assert state.status == RuntimeStatus.PAUSED
    assert state.pending_reload is True
    assert ("session_a", PlotStatus.PRINTED.value, state.current_sheet_id) in remote.updates
    assert ("session_b", PlotStatus.PRINTED.value, state.current_sheet_id) in remote.updates


def test_plotter_can_fall_back_to_placeholders_when_remote_is_down(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    remote = FakeRemoteRepository(fail_claim=True)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport)

    daemon.run_cycle()

    gcode_files = list((tmp_path / "spool").glob("*.gcode"))
    assert len(gcode_files) == 1
    assert daemon.get_state().status == RuntimeStatus.PAUSED
