from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from neje_oracle.blocks.fluidnc.transport import FluidNCTransport
from neje_oracle.blocks.plotter.daemon import (
    STALE_PLOT_JOB_AFTER,
    PlotterDaemon,
    _apply_current_mark_scale,
    _materialize_scaled_placeholder,
)
from neje_oracle.blocks.symbols.svg_normalizer import normalize_svg_file, read_normalized_svg_metadata
from neje_oracle.shared.config import PlotterSettings
from neje_oracle.shared.models import PlotJobLease, PlotStatus, PlotterControlState, PlotterRuntimeConfig, RuntimeStatus
from neje_oracle.shared.origin_markers import origin_allowed
from neje_oracle.shared.store import OracleRuntimeStore, PlotterStore

SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<path d='M10,10 L90,10 L90,90 L10,90 Z' stroke='black' fill='none'/>"
    "</svg>"
)


def _write_scale_config(symbol_root: Path, payload: dict[str, float]) -> Path:
    symbol_root.mkdir(parents=True, exist_ok=True)
    scale_path = symbol_root / "symbol_scales.json"
    scale_path.write_text(json.dumps(payload), encoding="utf-8")
    return scale_path


class FakeRemoteRepository:
    def __init__(self, jobs: list[PlotJobLease] | None = None, *, fail_claim: bool = False) -> None:
        self.jobs = jobs or []
        self.fail_claim = fail_claim
        self.updates: list[tuple[str, str, str]] = []

    def claim_next_plot_job(
        self, consumer_id: str, *, run_started_at=None, allowed_origins=None
    ) -> PlotJobLease | None:
        if self.fail_claim:
            raise RuntimeError("firestore down")
        for index, job in enumerate(self.jobs):
            if origin_allowed(job.origin, allowed_origins):
                return self.jobs.pop(index)
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
        self.updates.append((session_id, status.value, sheet_id))

    def download_asset(self, storage_path: str, destination: Path) -> None:
        destination.write_text(SVG, encoding="utf-8")


def _config() -> PlotterRuntimeConfig:
    """Sheet geometry for these tests.

    The daemon reads geometry from the oracle runtime store, not PlotterSettings, so tests
    must seed it there. These are the values the suite was written against.
    """
    return PlotterRuntimeConfig(
        sheet_width_mm=594,
        sheet_height_mm=841,
        sheet_margin_mm=24,
        cell_diameter_mm=160,
        layout_mode="hex",
        sample_step_mm=8.0,
        travel_rate=5000,
        draw_rate=1800,
        dry_run=True,
    )


def _seeded_oracle_store(tmp_path: Path, **overrides: object) -> OracleRuntimeStore:
    store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    store.save_plotter_config(replace(_config(), **overrides))  # type: ignore[arg-type]
    return store


def _settings(tmp_path: Path) -> PlotterSettings:
    return PlotterSettings(
        db_path=tmp_path / "runtime" / "plotter.sqlite3",
        placeholder_root=tmp_path / "placeholders",
        spool_root=tmp_path / "spool",
        poll_seconds=0.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
        dry_run=True,
        fluidnc_host="localhost",
        fluidnc_port=23,
        operator_host="127.0.0.1",
        operator_port=8765,
    )


def test_materialize_scaled_placeholder_applies_symbol_scale_config(tmp_path: Path) -> None:
    symbol_root = tmp_path / "symbols"
    symbol_path = symbol_root / "kind.svg"
    symbol_root.mkdir(parents=True)
    symbol_path.write_text(SVG, encoding="utf-8")
    scale_path = _write_scale_config(symbol_root, {"kind.svg": 1.75})

    with patch("neje_oracle.blocks.plotter.daemon._scale_config_path", return_value=scale_path):
        cached = _materialize_scaled_placeholder(symbol_path, tmp_path / "cache")

    metadata = read_normalized_svg_metadata(cached)
    assert metadata.normalized is True
    assert metadata.scale == 1.75


def test_apply_current_mark_scale_overrides_downloaded_normalized_svg(tmp_path: Path) -> None:
    symbol_root = tmp_path / "symbols"
    symbol_path = symbol_root / "test_the_kind_soul_220047_plotter.svg"
    symbol_root.mkdir(parents=True)
    symbol_path.write_text(SVG, encoding="utf-8")
    scale_path = _write_scale_config(symbol_root, {"test_the_kind_soul_220047_plotter.svg": 1.8})
    downloaded_svg = tmp_path / "downloaded.svg"
    downloaded_svg.write_text(normalize_svg_file(symbol_path, scale=1.0), encoding="utf-8")

    with (
        patch("neje_oracle.blocks.plotter.daemon._symbol_root", return_value=symbol_root),
        patch("neje_oracle.blocks.plotter.daemon._scale_config_path", return_value=scale_path),
    ):
        _apply_current_mark_scale(downloaded_svg, "THE KIND SOUL")

    metadata = read_normalized_svg_metadata(downloaded_svg)
    assert metadata.scale == 1.8
    text = downloaded_svg.read_text(encoding="utf-8")
    assert 'data-neje-single-stroke="true"' in text
    assert 'data-neje-simplify-mm="0.02"' in text


def test_plotter_finishes_sheet_and_stops_before_next_sheet(tmp_path: Path) -> None:
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
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository(jobs)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=_seeded_oracle_store(tmp_path))

    daemon.run_cycle()

    gcode_files = list((tmp_path / "spool").glob("*.gcode"))
    assert len(gcode_files) > 1
    state = daemon.get_state()
    assert state.status == RuntimeStatus.OPERATOR_PAUSED
    control = store.load_control_state()
    assert control.print_enabled is False
    assert control.operator_paused is True
    assert state.gcode_progress_percent == 100.0
    assert state.sheet_progress_percent == 100.0
    assert state.rows_completed == state.row_count
    assert state.gcode_lines_sent == state.gcode_lines_total
    assert state.gcode_lines_total > 0
    assert ("session_a", PlotStatus.PRINTED.value, state.current_sheet_id) in remote.updates
    assert ("session_b", PlotStatus.PRINTED.value, state.current_sheet_id) in remote.updates
    manifest = next((tmp_path / "spool").glob("sheet_*.json")).read_text(encoding="utf-8")
    assert '"origin": "unknown"' in manifest
    assert '"origin": "filler_macbook"' in manifest
    assert '"marker_position"' in manifest


def test_plotter_can_fall_back_to_placeholders_when_remote_is_down(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository(fail_claim=True)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=_seeded_oracle_store(tmp_path))

    daemon.run_cycle()

    gcode_files = list((tmp_path / "spool").glob("*.gcode"))
    assert gcode_files
    assert daemon.get_state().status == RuntimeStatus.OPERATOR_PAUSED


def test_plotter_stops_before_next_sheet_when_operator_disabled(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=False, operator_paused=True, run_mode="exhibition", dry_run=True)
    )
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=_seeded_oracle_store(tmp_path))

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
    oracle_store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="exhibition", dry_run=False)
    )
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


def test_plotter_uses_oracle_runtime_config_for_next_sheet(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    oracle_store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    oracle_store.save_plotter_config(
        PlotterRuntimeConfig(
            layout_mode="grid",
            sheet_width_mm=300,
            sheet_height_mm=220,
            sheet_margin_mm=0,
            cell_diameter_mm=80,
            gap_mm=20,
            organic_enabled=True,
            organic_cell_size_mm=12,
            organic_rotation_ramp=1,
            organic_scale_ramp=0.5,
            organic_seed=99,
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
    assert '"organic_enabled": true' in manifest
    assert '"organic_cell_size_mm": 12' in manifest
    assert '"organic_rotation_ramp": 1' in manifest
    assert '"organic_scale_ramp": 0.5' in manifest
    assert '"organic_seed": 99' in manifest
    assert '"rotation_deg":' in manifest
    assert '"symbol_scale":' in manifest


def test_plotter_writes_explicit_post_sheet_safety_gcode(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    oracle_store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
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
    assert "$H=Z" in safety_gcode
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
    oracle_store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
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
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=300,
        sheet_height_mm=260,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="hex",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
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

    daemon = PlotterDaemon(settings, store, remote, RowTransport(), oracle_store=oracle_store)  # type: ignore[arg-type]

    daemon.run_cycle()

    assert any(update[0] == "late_user" and update[1] == PlotStatus.PRINTED.value for update in remote.updates)


def test_plotter_stops_sending_rows_when_operator_pauses_mid_sheet(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=80,
        sheet_height_mm=160,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="grid",
    )
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    oracle_store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository()

    class PausingTransport:
        def __init__(self) -> None:
            self.calls = 0

        def send(self, *, gcode, sheet_id, dry_run, progress_callback):
            self.calls += 1
            path = settings.spool_root / f"{sheet_id}.gcode"
            path.write_text(gcode, encoding="utf-8")
            oracle_store.save_print_control(
                PlotterControlState(print_enabled=False, operator_paused=True, run_mode="test", dry_run=True)
            )
            return path

    transport = PausingTransport()
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)  # type: ignore[arg-type]

    daemon.run_cycle()

    assert transport.calls == 1
    assert daemon.get_state().status == RuntimeStatus.OPERATOR_PAUSED


def test_plotter_origin_filter_leaves_disallowed_job_pending_and_fills_row(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=100,
        sheet_height_mm=100,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="grid",
    )
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "runtime" / "oracle.sqlite3")
    oracle_store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    oracle_store.save_origin_filters(show_origins=["real_macmini", "test_macbook"], print_origins=["real_macmini"])
    remote = FakeRemoteRepository(
        [
            PlotJobLease(
                session_id="test_user",
                title="test",
                summary="",
                created_at=datetime.now(tz=UTC),
                priority="user",
                queue="user",
                svg_storage_path="sessions/test/artwork.svg",
                svg_url="",
                origin="test_macbook",
                tags=["test", "generated", "macbook"],
            )
        ]
    )
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)

    daemon.run_cycle()

    assert remote.jobs and remote.jobs[0].session_id == "test_user"
    assert all(update[0] != "test_user" for update in remote.updates)
    manifest = next((tmp_path / "spool").glob("sheet_*.json")).read_text(encoding="utf-8")
    assert '"origin": "filler_macbook"' in manifest


def test_plotter_can_use_filler_session_package_folders(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    filler_dir = placeholder_root / "filler_20260508_000000_001"
    filler_dir.mkdir(parents=True)
    (filler_dir / "filler_20260508_000000_001_plotter.svg").write_text(SVG, encoding="utf-8")
    (filler_dir / "filler_20260508_000000_001_receipt.txt").write_text("Local filler", encoding="utf-8")
    (filler_dir / "metadata.json").write_text('{"origin":"filler_macbook"}', encoding="utf-8")
    (filler_dir / "READY").write_text("", encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
        placeholder_root=placeholder_root,
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=100,
        sheet_height_mm=100,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="grid",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)

    daemon.run_cycle()

    manifest = next((tmp_path / "spool").glob("sheet_*.json")).read_text(encoding="utf-8")
    assert "filler_20260508_000000_001_plotter.svg" in manifest
    assert '"origin": "filler_macbook"' in manifest


def test_plotter_materializes_remote_filler_queue_job_as_placeholder(tmp_path: Path) -> None:
    settings = replace(
        _settings(tmp_path),
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=100,
        sheet_height_mm=100,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="grid",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository(
        [
            PlotJobLease(
                session_id="filler_cloud",
                title="filler",
                summary="",
                created_at=datetime.now(tz=UTC),
                priority="filler",
                queue="filler",
                svg_storage_path="sessions/filler_cloud/artwork.svg",
                svg_url="",
                origin="filler_macbook",
                tags=["filler", "local", "macbook"],
            )
        ]
    )
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)

    daemon.run_cycle()

    manifest = next((tmp_path / "spool").glob("sheet_*.json")).read_text(encoding="utf-8")
    assert '"session_id": "filler_cloud"' in manifest
    assert '"source_kind": "placeholder"' in manifest
    assert '"origin": "filler_macbook"' in manifest
    assert ("filler_cloud", PlotStatus.PRINTED.value, daemon.get_state().current_sheet_id) in remote.updates


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


def test_daemon_uses_effective_sample_step_not_raw_config_step(tmp_path: Path):
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
        placeholder_root=placeholder_root,
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=200.0,
        sheet_height_mm=200.0,
        sheet_margin_mm=0.0,
        cell_diameter_mm=200.0,
        sample_step_mm=1.0,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.0,
        sample_min_step_mm=0.25,
        sample_max_step_mm=3.0,
        streaming_mode="row",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)
    sample_steps: list[float] = []

    def fake_generate_sheet_gcode(*args, **kwargs):
        sample_steps.append(kwargs["sample_step_mm"])
        return "G21\n; cell-start 0/1\nG0 X0 Y0\n"

    with patch("neje_oracle.blocks.plotter.daemon.generate_sheet_gcode", side_effect=fake_generate_sheet_gcode):
        daemon.run_cycle()

    assert sample_steps
    assert all(step == 0.4 for step in sample_steps)
    assert daemon.get_state().status == RuntimeStatus.OPERATOR_PAUSED


def test_daemon_manifest_has_raw_sample_settings(tmp_path: Path):
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
        placeholder_root=placeholder_root,
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=200.0,
        sheet_height_mm=200.0,
        sheet_margin_mm=0.0,
        cell_diameter_mm=200.0,
        sample_step_mm=1.0,
        sample_density_exponent=2.0,
        sample_reference_cell_mm=80.0,
        sample_min_step_mm=0.1,
        sample_max_step_mm=10.0,
        xy_acceleration_mm_s2=75.0,
        streaming_mode="row",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository()
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)
    daemon.run_cycle()

    manifests = sorted(settings.spool_root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert manifests, "No manifest written by daemon"
    manifest_payload = json.loads(manifests[0].read_text())
    assert manifest_payload["sample_step_mm"] == 1.0
    assert manifest_payload["sample_density_exponent"] == 2.0
    assert manifest_payload["sample_reference_cell_mm"] == 80.0
    assert manifest_payload["sample_min_step_mm"] == 0.1
    assert manifest_payload["sample_max_step_mm"] == 10.0
    assert abs(manifest_payload["effective_sample_step_mm"] - 0.16) < 1e-9
    assert manifest_payload["streaming_mode"] == "row"
    assert manifest_payload["xy_acceleration_mm_s2"] == 75.0


def test_cell_streaming_sends_one_file_per_cell_and_records_manifest(tmp_path: Path) -> None:
    placeholder_root = tmp_path / "placeholders"
    placeholder_root.mkdir(parents=True)
    (placeholder_root / "idle.svg").write_text(SVG, encoding="utf-8")

    settings = replace(
        _settings(tmp_path),
        placeholder_root=placeholder_root,
    )
    oracle_store = _seeded_oracle_store(
        tmp_path,
        sheet_width_mm=240,
        sheet_height_mm=80,
        sheet_margin_mm=0,
        cell_diameter_mm=80,
        layout_mode="grid",
        streaming_mode="cell",
    )
    store = PlotterStore(settings.db_path)
    store.save_control_state(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode="test", dry_run=True)
    )
    remote = FakeRemoteRepository(
        [
            PlotJobLease(
                session_id="real_user",
                title="real",
                summary="",
                created_at=datetime.now(tz=UTC),
                priority="user",
                queue="user",
                svg_storage_path="sessions/real/artwork.svg",
                svg_url="",
                origin="real_macmini",
                tags=["real"],
            ),
            PlotJobLease(
                session_id="filler_cloud",
                title="filler",
                summary="",
                created_at=datetime.now(tz=UTC),
                priority="filler",
                queue="filler",
                svg_storage_path="sessions/filler/artwork.svg",
                svg_url="",
                origin="filler_macbook",
                tags=["filler", "local", "macbook"],
            ),
        ]
    )
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport, oracle_store=oracle_store)

    daemon.run_cycle()

    cell_files = sorted(settings.spool_root.glob("*_cell_*.gcode"))
    assert len(cell_files) == 3
    manifest_payload = json.loads(next(settings.spool_root.glob("sheet_*.json")).read_text(encoding="utf-8"))
    assert manifest_payload["streaming_mode"] == "cell"
    assert len(manifest_payload["cells"]) == 3
    assert [cell["status"] for cell in manifest_payload["cells"]] == ["printed", "printed", "printed"]
    assert manifest_payload["cells"][0]["item"]["session_id"] == "real_user"
    assert manifest_payload["cells"][0]["item"]["source_kind"] == "user"
    assert manifest_payload["cells"][1]["item"]["session_id"] == "filler_cloud"
    assert manifest_payload["cells"][1]["item"]["source_kind"] == "placeholder"
    assert manifest_payload["cells"][2]["item"]["origin"] == "filler_macbook"
    assert ("real_user", PlotStatus.PRINTED.value, daemon.get_state().current_sheet_id) in remote.updates
    assert ("filler_cloud", PlotStatus.PRINTED.value, daemon.get_state().current_sheet_id) in remote.updates
    assert daemon.get_state().status == RuntimeStatus.OPERATOR_PAUSED


def test_sheet_progress_is_cell_based_and_never_runs_backwards(tmp_path: Path) -> None:
    """Mid-stream progress must use the same unit as the cell-completion writer.

    Regression: sheet_progress_percent added the fraction of the current *stream* to
    rows_completed as if a stream were a whole row. In cell streaming mode one stream
    is one cell, so a single cell drove the bar to a full row's worth and it jumped
    backwards every time a cell actually completed (observed live: 25% -> 6.25% -> 0.87%).
    """
    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    daemon = PlotterDaemon(
        settings, store, FakeRemoteRepository(), FluidNCTransport(settings), oracle_store=_seeded_oracle_store(tmp_path)
    )

    # 5-cell sheet streamed one cell at a time, as the live rig does.
    daemon._sheet_total_cells = 5
    daemon._current_row_cell_count = 1
    daemon.runtime_state.row_count = 3
    daemon.runtime_state.rows_completed = 0

    seen: list[float] = []
    for cell_index in range(5):
        daemon._cells_completed_before_row = cell_index
        daemon._current_row_sheet_indexes = [cell_index]
        daemon._current_row_cell_markers = []
        for sent in (0, 25, 50, 75, 100):
            daemon._record_gcode_progress(sent, 100)
            seen.append(daemon.get_state().sheet_progress_percent)

    assert seen == sorted(seen), f"sheet progress ran backwards: {seen}"
    assert seen[0] == 0.0
    assert seen[-1] == 100.0
    # Completing cell 1 of 5 must read 20%, matching the cell-completion writer.
    assert seen[4] == 20.0


class RequeueTrackingRemote(FakeRemoteRepository):
    """Remote that records the requeue sweep the daemon performs on start."""

    def __init__(self, requeued: list[str] | None = None, fail: bool = False) -> None:
        super().__init__()
        self._requeued = requeued or []
        self._fail = fail
        self.requeue_calls: list[timedelta] = []

    def requeue_stale_plot_jobs(self, *, stale_after: timedelta, now=None) -> list[str]:
        self.requeue_calls.append(stale_after)
        if self._fail:
            raise RuntimeError("firestore unavailable")
        return self._requeued


def test_daemon_requeues_unfinished_jobs_on_start(tmp_path: Path) -> None:
    """An interrupted run must not strand its claimed job.

    claim_next_plot_job() only queries PENDING, so before this a panic/E-stop/restart left
    the job claimed forever. Live evidence: session 20260413_192853 sat in `plotting` for
    nearly four months.
    """
    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "oracle.sqlite3")
    remote = RequeueTrackingRemote(requeued=["20260413_192853"])
    daemon = PlotterDaemon(settings, store, remote, FluidNCTransport(settings), oracle_store=oracle_store)

    daemon._requeue_stale_jobs_on_start()

    assert remote.requeue_calls == [STALE_PLOT_JOB_AFTER]
    queue_state = oracle_store.load_component_state("queue")
    assert "20260413_192853" in queue_state.message
    assert "Requeued 1" in queue_state.message


def test_daemon_start_survives_a_failing_requeue(tmp_path: Path) -> None:
    """Recovery is best-effort: an unreachable queue must not stop the daemon starting."""
    settings = _settings(tmp_path)
    store = PlotterStore(settings.db_path)
    oracle_store = OracleRuntimeStore(tmp_path / "oracle.sqlite3")
    daemon = PlotterDaemon(
        settings, store, RequeueTrackingRemote(fail=True), FluidNCTransport(settings), oracle_store=oracle_store
    )

    daemon._requeue_stale_jobs_on_start()

    assert "Could not requeue" in oracle_store.load_component_state("queue").message
