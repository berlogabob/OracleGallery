from __future__ import annotations

from dataclasses import replace
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
    assert len(gcode_files) > 1
    state = daemon.get_state()
    assert state.status == RuntimeStatus.PAUSED
    assert state.pending_reload is True
    assert state.gcode_progress_percent == 100.0
    assert state.sheet_progress_percent == 100.0
    assert state.rows_completed == state.row_count
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
    assert gcode_files
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


def test_plotter_transport_failure_does_not_mark_job_printed(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    oracle_store.save_print_control(PlotterControlState(print_enabled=True, operator_paused=False, run_mode="exhibition", dry_run=False))
    remote = FakeRemoteRepository(
        [
            PlotJobLease(
                session_id="session_fail",
                title="fail",
                summary="",
                created_at=datetime.now(tz=UTC),
                priority="user",
                queue="user",
                svg_storage_path="sessions/fail/artwork.svg",
                svg_url="",
            )
        ]
    )

    class FailingTransport:
        def send(self, **kwargs):
            raise RuntimeError("fluidnc timeout")

    daemon = PlotterDaemon(settings, store, remote, FailingTransport(), oracle_store=oracle_store)  # type: ignore[arg-type]

    daemon.run_cycle()

    assert ("session_fail", PlotStatus.FAILED.value, daemon.get_state().current_sheet_id) in remote.updates
    assert all(update[1] != PlotStatus.PRINTED.value for update in remote.updates)
    assert oracle_store.load_print_control().print_enabled is False
    assert oracle_store.load_real_fluidnc_armed() is False


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


def test_plotter_writes_explicit_post_sheet_safety_gcode(tmp_path: Path) -> None:
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
            sheet_width_mm=180,
            sheet_height_mm=100,
            cell_diameter_mm=80,
            run_mode="test",
            dry_run=True,
            use_z_servo=True,
            z_up_mm=25.0,
        )
    )
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)

    daemon.run_cycle()

    safety_files = list((tmp_path / "spool").glob("*_sheet_end.gcode"))
    assert len(safety_files) == 1
    safety_gcode = safety_files[0].read_text(encoding="utf-8")
    assert "post-sheet safety" in safety_gcode
    assert "G0 Z25.000" in safety_gcode
    assert "G0 X0 Y0" in safety_gcode
    manifest = next((tmp_path / "spool").glob("*.json")).read_text(encoding="utf-8")
    assert "post_sheet_safety_gcode_path" in manifest


def test_plotter_progress_uses_cell_markers_instead_of_row_fraction(tmp_path: Path) -> None:
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
            sheet_width_mm=240,
            sheet_height_mm=80,
            cell_diameter_mm=80,
            run_mode="test",
            dry_run=True,
        )
    )
    remote = FakeRemoteRepository()

    class MarkerTransport:
        def __init__(self) -> None:
            self.observed_cell_index = -1
            self.observed_cell_in_row = -1

        def send(self, *, gcode, sheet_id, dry_run, progress_callback):
            path = settings.spool_root / f"{sheet_id}.gcode"
            path.write_text(gcode, encoding="utf-8")
            if progress_callback and "row_01" in sheet_id:
                threshold = _command_threshold_for_cell_start(gcode, cell_offset=1)
                total = _sendable_command_count(gcode)
                progress_callback(threshold, total)
                observed = store.load_runtime_state()
                self.observed_cell_index = observed.current_cell_index
                self.observed_cell_in_row = observed.current_cell_in_row
            return path

    transport = MarkerTransport()
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)  # type: ignore[arg-type]

    daemon.run_cycle()

    assert transport.observed_cell_in_row == 2
    assert transport.observed_cell_index == 1


def test_plotter_claims_late_user_job_before_next_row(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
        sheet_width_mm=300,
        sheet_height_mm=260,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="hex",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True))
    remote = FakeRemoteRepository([])

    class RowTransport:
        def __init__(self) -> None:
            self.calls = 0

        def send(self, *, gcode, sheet_id, dry_run, progress_callback):
            self.calls += 1
            if progress_callback:
                total = len(gcode.splitlines())
                progress_callback(total, total)
            path = settings.spool_root / f"{sheet_id}.gcode"
            path.write_text(gcode, encoding="utf-8")
            if self.calls == 1:
                remote.jobs.append(
                    PlotJobLease(
                        session_id="late_user",
                        title="late",
                        summary="",
                        created_at=datetime.now(tz=UTC),
                        priority="user",
                        queue="user",
                        svg_storage_path="sessions/late/artwork.svg",
                        svg_url="",
                    )
                )
            return path

    daemon = PlotterDaemon(settings, store, remote, RowTransport())  # type: ignore[arg-type]

    daemon.run_cycle()

    assert any(update[0] == "late_user" and update[1] == PlotStatus.PRINTED.value for update in remote.updates)


def _command_threshold_for_cell_start(gcode: str, *, cell_offset: int) -> int:
    command_count = 0
    target = f"; cell-start {cell_offset}/"
    for line in gcode.splitlines():
        stripped = line.strip()
        if stripped.startswith(target):
            return command_count + 1
        if stripped and not stripped.startswith(";"):
            command_count += 1
    raise AssertionError(f"missing {target}")


def _sendable_command_count(gcode: str) -> int:
    return sum(1 for line in gcode.splitlines() if line.strip() and not line.strip().startswith(";"))
