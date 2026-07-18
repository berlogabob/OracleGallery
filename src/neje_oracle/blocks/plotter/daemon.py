from __future__ import annotations

import json
import random
import threading
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from ...shared.config import SYMBOL_FIT_RATIO, PlotterSettings, _repo_root, ensure_dir
from ..firebase.repository import FirebaseRemoteRepository
from ..gcode.layout import build_sheet_layout, calculate_layout_capacity, group_layout_rows
from ...shared.models import ComponentStatus, PlotJobLease, PlotStatus, PlotterControlState, PlotterRuntimeConfig, PlotterRuntimeState, RuntimeStatus, SheetItem, SheetPlacement
from ...shared.origin_markers import ALL_ORIGINS, DEFAULT_MARKER_DIAMETER_MM, ORIGIN_FILLER_MACBOOK, marker_position_for_origin, normalize_tags
from ..gcode.sampling import compute_effective_sample_step
from ...shared.store import OracleRuntimeStore, PlotterStore
from ..gcode.svg_gcode import generate_sheet_gcode
from ..symbols.svg_normalizer import (
    DEFAULT_SIMPLIFY_TOLERANCE_MM,
    DEFAULT_SINGLE_STROKE_SYMBOLS,
    MARK_NAMES,
    MAX_SCALE,
    MIN_SCALE,
    normalize_svg_file,
    read_normalized_svg_metadata,
    scale_for_mark_name,
)
from ..fluidnc.transport import FluidNCTransport


class PlotterDaemon:
    def __init__(
        self,
        settings: PlotterSettings,
        store: PlotterStore,
        remote: FirebaseRemoteRepository,
        transport: FluidNCTransport,
        oracle_store: OracleRuntimeStore | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.remote = remote
        self.transport = transport
        self.oracle_store = oracle_store
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.runtime_state = self.store.load_runtime_state()
        self._current_row_sheet_indexes: list[int] = []
        self._current_row_cell_count = 0
        self._current_row_cell_markers: list[tuple[int, int, int]] = []
        self._cells_completed_before_row = 0
        ensure_dir(self.settings.placeholder_root)
        ensure_dir(self.settings.spool_root)

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as exc:  # noqa: BLE001
                self._set_state(RuntimeStatus.ERROR, f"Unhandled plotter error: {exc}")
            time.sleep(self.settings.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()

    def get_state(self) -> PlotterRuntimeState:
        with self.state_lock:
            return self.runtime_state

    def run_cycle(self) -> None:
        if self.oracle_store is not None:
            self.oracle_store.set_component("plotter", ComponentStatus.RUNNING, message="Daemon cycle", heartbeat=True)

        config = self._load_plotter_config()
        control = self._load_control_state()
        if not control.print_enabled:
            with self.state_lock:
                self.runtime_state.status = RuntimeStatus.OPERATOR_PAUSED
                self.runtime_state.message = "Print is stopped by operator. Press START PRINT to enable the next sheet."
                self.runtime_state.updated_at = datetime.now(tz=UTC)
                self.store.save_runtime_state(self.runtime_state)
            return

        with self.state_lock:
            self.runtime_state.status = RuntimeStatus.PREPARING
            self.runtime_state.message = "Preparing next sheet"
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
        if self.oracle_store is not None:
            self.oracle_store.set_component("plotter", ComponentStatus.RUNNING, message="Preparing next sheet", heartbeat=True)

        layout_capacity = calculate_layout_capacity(
            mode=config.layout_mode,
            sheet_width_mm=config.sheet_width_mm,
            sheet_height_mm=config.sheet_height_mm,
            margin_mm=config.sheet_margin_mm,
            diameter_mm=config.cell_diameter_mm,
            gap_mm=config.gap_mm,
        )
        sheet_limit = layout_capacity
        if sheet_limit <= 0:
            self._set_state(RuntimeStatus.ERROR, "Sheet layout has no printable cells")
            return

        sheet_id = datetime.now(tz=UTC).strftime("sheet_%Y%m%d_%H%M%S")
        placements = build_sheet_layout(
            sheet_limit,
            mode=config.layout_mode,
            sheet_width_mm=config.sheet_width_mm,
            sheet_height_mm=config.sheet_height_mm,
            margin_mm=config.sheet_margin_mm,
            diameter_mm=config.cell_diameter_mm,
            gap_mm=config.gap_mm,
            organic_enabled=config.organic_enabled,
            organic_cell_size_mm=config.organic_cell_size_mm,
            organic_rotation_ramp=config.organic_rotation_ramp,
            organic_scale_ramp=config.organic_scale_ramp,
            organic_seed=config.organic_seed,
        )
        layout_rows = group_layout_rows(placements)
        if not layout_rows:
            self._set_state(RuntimeStatus.ERROR, "Sheet layout has no printable rows")
            return

        effective_step = compute_effective_sample_step(
            sample_step_mm=config.sample_step_mm,
            cell_diameter_mm=config.cell_diameter_mm,
            sample_reference_cell_mm=config.sample_reference_cell_mm,
            sample_density_exponent=config.sample_density_exponent,
            sample_min_step_mm=config.sample_min_step_mm,
            sample_max_step_mm=config.sample_max_step_mm,
        )
        manifest_path = self.settings.spool_root / f"{sheet_id}.json"
        manifest: dict[str, object] = {
            "sheet_id": sheet_id,
            "items": [],
            "rows": [],
            "layout_mode": config.layout_mode,
            "cell_diameter_mm": config.cell_diameter_mm,
            "gap_mm": config.gap_mm,
            "organic_enabled": config.organic_enabled,
            "organic_cell_size_mm": config.organic_cell_size_mm,
            "organic_rotation_ramp": config.organic_rotation_ramp,
            "organic_scale_ramp": config.organic_scale_ramp,
            "organic_seed": config.organic_seed,
            "symbol_fit_ratio": SYMBOL_FIT_RATIO,
            "dry_run": control.dry_run,
            "run_mode": control.run_mode,
            "include_rings": config.include_rings,
            "include_markers": config.include_markers,
            "marker_diameter_mm": config.marker_diameter_mm,
            "use_z_servo": config.use_z_servo,
            "z_up_mm": config.z_up_mm,
            "z_down_mm": config.z_down_mm,
            "row_count": len(layout_rows),
            "sample_step_mm": config.sample_step_mm,
            "sample_reference_cell_mm": config.sample_reference_cell_mm,
            "sample_density_exponent": config.sample_density_exponent,
            "sample_min_step_mm": config.sample_min_step_mm,
            "sample_max_step_mm": config.sample_max_step_mm,
            "effective_sample_step_mm": effective_step,
            "streaming_mode": config.streaming_mode,
            "xy_acceleration_mm_s2": config.xy_acceleration_mm_s2,
        }
        self._write_manifest(manifest_path, manifest)

        rows_printed = 0
        cells_completed = 0
        last_gcode_path: Path | None = None
        if str(config.streaming_mode).lower() == "cell":
            stream_result = self._stream_sheet_cells(
                config=config,
                control=control,
                sheet_id=sheet_id,
                layout_rows=layout_rows,
                manifest_path=manifest_path,
                manifest=manifest,
                effective_step=effective_step,
            )
            if stream_result is None:
                return
            rows_printed, cells_completed, last_gcode_path = stream_result
        else:
            for row_index, row_placements in enumerate(layout_rows, start=1):
                if self.stop_event.is_set():
                    return
                control = self._load_control_state()
                if not control.print_enabled:
                    self._set_state(RuntimeStatus.OPERATOR_PAUSED, "Print paused by operator mid-sheet")
                    return
                row_limit = len(row_placements)
                try:
                    user_jobs = self._claim_user_jobs(row_limit)
                except Exception as exc:  # noqa: BLE001
                    user_jobs = []
                    if self.oracle_store is not None:
                        self.oracle_store.set_component("queue", ComponentStatus.WARNING, message=f"Remote queue unavailable; using idle symbols: {exc}", heartbeat=True)

                items = self._materialize_sheet_items(user_jobs, row_limit)
                if not items:
                    continue
                active_placements = row_placements[: len(items)]
                for offset, job in enumerate(user_jobs):
                    sheet_index = active_placements[offset].index
                    self.remote.update_plot_job(
                        job.session_id,
                        PlotStatus.PLOTTING,
                        sheet_id=sheet_id,
                        sheet_index=sheet_index,
                    )
                    self.store.record_job_status(job.session_id, PlotStatus.PLOTTING, sheet_id=sheet_id)

                row_gcode = generate_sheet_gcode(
                    items,
                    active_placements,
                    sample_step_mm=effective_step,
                    cell_diameter_mm=config.cell_diameter_mm,
                    travel_rate=config.travel_rate,
                    draw_rate=config.draw_rate,
                    xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
                    pen_up_command=self.settings.pen_up_command,
                    pen_down_command=self.settings.pen_down_command,
                    title=f"{sheet_id} row {row_index}/{len(layout_rows)}",
                    return_home=row_index == len(layout_rows),
                    include_rings=config.include_rings,
                    include_markers=config.include_markers,
                    marker_diameter_mm=config.marker_diameter_mm,
                    use_z_servo=config.use_z_servo,
                    z_down_mm=config.z_down_mm,
                    z_up_mm=config.z_up_mm,
                    z_feed_mm_min=config.z_feed_mm_min,
                )
                total_gcode_lines = len(row_gcode.splitlines())
                row_id = f"{sheet_id}_row_{row_index:02d}"
                self._current_row_sheet_indexes = [placement.index for placement in active_placements]
                self._current_row_cell_count = len(active_placements)
                self._current_row_cell_markers = self._build_cell_progress_markers(row_gcode, active_placements)
                self._cells_completed_before_row = cells_completed
                self._set_state(
                    RuntimeStatus.PRINTING,
                    f"Streaming row {row_index}/{len(layout_rows)} of {sheet_id}",
                    sheet_id=sheet_id,
                    gcode_lines_sent=0,
                    gcode_lines_total=total_gcode_lines,
                    gcode_progress_percent=0.0,
                    current_row_index=row_index,
                    row_count=len(layout_rows),
                    current_cell_index=active_placements[0].index if active_placements else 0,
                    current_cell_in_row=1 if active_placements else 0,
                    row_cell_count=len(active_placements),
                    cells_completed=cells_completed,
                    rows_completed=rows_printed,
                    sheet_progress_percent=(rows_printed / len(layout_rows)) * 100.0,
                )
                row_payload = self._manifest_row_payload(
                    row_index=row_index,
                    row_id=row_id,
                    items=items,
                    placements=active_placements,
                    status="streaming",
                    marker_diameter_mm=config.marker_diameter_mm,
                )
                self._append_manifest_row(manifest_path, manifest, row_payload)
                try:
                    gcode_path = self.transport.send(
                        gcode=row_gcode,
                        sheet_id=row_id,
                        dry_run=control.dry_run,
                        progress_callback=self._record_gcode_progress,
                    )
                except Exception as exc:  # noqa: BLE001
                    for job in user_jobs:
                        self.remote.update_plot_job(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
                        self.store.record_job_status(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
                    row_payload["status"] = "failed"
                    row_payload["error"] = str(exc)
                    self._replace_manifest_row(manifest_path, manifest, row_index, row_payload)
                    if self.oracle_store is not None:
                        control = self.oracle_store.load_print_control()
                        control.print_enabled = False
                        control.operator_paused = True
                        self.oracle_store.save_print_control(control)
                        self.oracle_store.set_component("print", ComponentStatus.STOPPED, message=f"Print disabled after FluidNC error: {exc}")
                    self._set_state(RuntimeStatus.ERROR, f"Plotter transport failed on row {row_index}: {exc}", sheet_id=sheet_id)
                    return

                last_gcode_path = gcode_path
                rows_printed += 1
                cells_completed += len(items)
                row_payload["status"] = "printed"
                row_payload["gcode_path"] = str(gcode_path)
                self._replace_manifest_row(manifest_path, manifest, row_index, row_payload)
                for offset, job in enumerate(user_jobs):
                    sheet_index = active_placements[offset].index
                    self.remote.update_plot_job(
                        job.session_id,
                        PlotStatus.PRINTED,
                        sheet_id=sheet_id,
                        sheet_index=sheet_index,
                    )
                    self.store.record_job_status(job.session_id, PlotStatus.PRINTED, sheet_id=sheet_id)

        if rows_printed <= 0:
            self._set_state(RuntimeStatus.IDLE, "No user jobs or placeholders available", sheet_id=sheet_id)
            return

        try:
            safety_gcode = self._post_sheet_safety_gcode(config, sheet_id)
            last_gcode_path = self.transport.send(
                gcode=safety_gcode,
                sheet_id=f"{sheet_id}_sheet_end",
                dry_run=control.dry_run,
                progress_callback=None,
            )
            manifest["post_sheet_safety_gcode_path"] = str(last_gcode_path)
            self._write_manifest(manifest_path, manifest)
        except Exception as exc:  # noqa: BLE001
            if self.oracle_store is not None:
                control = self.oracle_store.load_print_control()
                control.print_enabled = False
                control.operator_paused = True
                self.oracle_store.save_print_control(control)
                self.oracle_store.set_component("print", ComponentStatus.STOPPED, message=f"Print disabled after post-sheet safety failure: {exc}")
            self._set_state(RuntimeStatus.ERROR, f"Post-sheet safety failed: {exc}", sheet_id=sheet_id)
            return

        control.print_enabled = False
        control.operator_paused = True
        self.store.save_control_state(control)
        if self.oracle_store is not None:
            self.oracle_store.save_print_control(control)
        with self.state_lock:
            self.runtime_state.status = RuntimeStatus.OPERATOR_PAUSED
            self.runtime_state.message = "Sheet finished. Press START PRINT for the next sheet."
            self.runtime_state.current_sheet_id = sheet_id
            self.runtime_state.last_sheet_path = str(last_gcode_path or manifest_path)
            self.runtime_state.gcode_lines_sent = self.runtime_state.gcode_lines_total
            self.runtime_state.gcode_progress_percent = 100.0
            self.runtime_state.current_row_index = rows_printed
            self.runtime_state.row_count = len(layout_rows)
            self.runtime_state.current_cell_index = 0
            self.runtime_state.current_cell_in_row = 0
            self.runtime_state.row_cell_count = 0
            self.runtime_state.cells_completed = cells_completed
            self.runtime_state.rows_completed = rows_printed
            self.runtime_state.sheet_progress_percent = 100.0
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
        if self.oracle_store is not None:
            self.oracle_store.set_component("plotter", ComponentStatus.WARNING, message="Sheet finished; print stopped", heartbeat=True)

    def _post_sheet_safety_gcode(self, config: PlotterRuntimeConfig, sheet_id: str) -> str:
        if config.use_z_servo:
            pen_up = "$H=Z"
        else:
            pen_up = self.settings.pen_up_command
        return "\n".join(
            [
                f"; Neje Oracle {sheet_id} post-sheet safety",
                "G21",
                "G90",
                f"G0 F{config.travel_rate:.2f}",
                pen_up,
                "G0 X0 Y0",
                "",
            ]
        )

    def _stream_sheet_cells(
        self,
        *,
        config: PlotterRuntimeConfig,
        control: PlotterControlState,
        sheet_id: str,
        layout_rows: list[list[SheetPlacement]],
        manifest_path: Path,
        manifest: dict[str, object],
        effective_step: float,
    ) -> tuple[int, int, Path | None] | None:
        rows_printed = 0
        cells_completed = 0
        last_gcode_path: Path | None = None
        total_cells = sum(len(row) for row in layout_rows)
        for row_index, row_placements in enumerate(layout_rows, start=1):
            row_had_printed_cell = False
            for cell_offset, placement in enumerate(row_placements):
                if self.stop_event.is_set():
                    return None
                control = self._load_control_state()
                if not control.print_enabled:
                    self._set_state(RuntimeStatus.OPERATOR_PAUSED, "Print paused by operator mid-sheet")
                    return None
                try:
                    user_jobs = self._claim_user_jobs(1)
                except Exception as exc:  # noqa: BLE001
                    user_jobs = []
                    if self.oracle_store is not None:
                        self.oracle_store.set_component("queue", ComponentStatus.WARNING, message=f"Remote queue unavailable; using idle symbols: {exc}", heartbeat=True)

                items = self._materialize_sheet_items(user_jobs, 1)
                if not items:
                    continue
                item = items[0]
                if user_jobs:
                    job = user_jobs[0]
                    self.remote.update_plot_job(
                        job.session_id,
                        PlotStatus.PLOTTING,
                        sheet_id=sheet_id,
                        sheet_index=placement.index,
                    )
                    self.store.record_job_status(job.session_id, PlotStatus.PLOTTING, sheet_id=sheet_id)

                cell_id = f"{sheet_id}_cell_{placement.index:03d}"
                cell_gcode = generate_sheet_gcode(
                    [item],
                    [placement],
                    sample_step_mm=effective_step,
                    cell_diameter_mm=config.cell_diameter_mm,
                    travel_rate=config.travel_rate,
                    draw_rate=config.draw_rate,
                    xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
                    pen_up_command=self.settings.pen_up_command,
                    pen_down_command=self.settings.pen_down_command,
                    title=f"{sheet_id} cell {placement.index + 1}/{total_cells}",
                    return_home=False,
                    include_rings=config.include_rings,
                    include_markers=config.include_markers,
                    marker_diameter_mm=config.marker_diameter_mm,
                    use_z_servo=config.use_z_servo,
                    z_down_mm=config.z_down_mm,
                    z_up_mm=config.z_up_mm,
                    z_feed_mm_min=config.z_feed_mm_min,
                )
                total_gcode_lines = len(cell_gcode.splitlines())
                self._current_row_sheet_indexes = [placement.index]
                self._current_row_cell_count = 1
                self._current_row_cell_markers = self._build_cell_progress_markers(cell_gcode, [placement])
                self._cells_completed_before_row = cells_completed
                self._set_state(
                    RuntimeStatus.PRINTING,
                    f"Streaming cell {placement.index + 1}/{total_cells} of {sheet_id}",
                    sheet_id=sheet_id,
                    gcode_lines_sent=0,
                    gcode_lines_total=total_gcode_lines,
                    gcode_progress_percent=0.0,
                    current_row_index=row_index,
                    row_count=len(layout_rows),
                    current_cell_index=placement.index,
                    current_cell_in_row=cell_offset + 1,
                    row_cell_count=len(row_placements),
                    cells_completed=cells_completed,
                    rows_completed=rows_printed,
                    sheet_progress_percent=(cells_completed / total_cells) * 100.0 if total_cells else 0.0,
                )
                cell_payload = self._manifest_cell_payload(
                    row_index=row_index,
                    cell_id=cell_id,
                    item=item,
                    placement=placement,
                    status="streaming",
                    marker_diameter_mm=config.marker_diameter_mm,
                )
                self._append_manifest_cell(manifest_path, manifest, cell_payload)
                try:
                    gcode_path = self.transport.send(
                        gcode=cell_gcode,
                        sheet_id=cell_id,
                        dry_run=control.dry_run,
                        progress_callback=self._record_gcode_progress,
                    )
                except Exception as exc:  # noqa: BLE001
                    for job in user_jobs:
                        self.remote.update_plot_job(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
                        self.store.record_job_status(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
                    cell_payload["status"] = "failed"
                    cell_payload["error"] = str(exc)
                    self._replace_manifest_cell(manifest_path, manifest, cell_id, cell_payload)
                    if self.oracle_store is not None:
                        failed_control = self.oracle_store.load_print_control()
                        failed_control.print_enabled = False
                        failed_control.operator_paused = True
                        self.oracle_store.save_print_control(failed_control)
                        self.oracle_store.set_component("print", ComponentStatus.STOPPED, message=f"Print disabled after FluidNC error: {exc}")
                    self._set_state(RuntimeStatus.ERROR, f"Plotter transport failed on cell {placement.index + 1}: {exc}", sheet_id=sheet_id)
                    return None

                last_gcode_path = gcode_path
                cells_completed += 1
                row_had_printed_cell = True
                if user_jobs:
                    job = user_jobs[0]
                    self.remote.update_plot_job(
                        job.session_id,
                        PlotStatus.PRINTED,
                        sheet_id=sheet_id,
                        sheet_index=placement.index,
                    )
                    self.store.record_job_status(job.session_id, PlotStatus.PRINTED, sheet_id=sheet_id)
                cell_payload["status"] = "printed"
                cell_payload["gcode_path"] = str(gcode_path)
                self._replace_manifest_cell(manifest_path, manifest, cell_id, cell_payload)
                completed_rows = rows_printed + (1 if cell_offset == len(row_placements) - 1 else 0)
                self._set_state(
                    RuntimeStatus.PRINTING,
                    f"Printed cell {placement.index + 1}/{total_cells} of {sheet_id}",
                    sheet_id=sheet_id,
                    gcode_lines_sent=total_gcode_lines,
                    gcode_lines_total=total_gcode_lines,
                    gcode_progress_percent=100.0,
                    current_row_index=row_index,
                    row_count=len(layout_rows),
                    current_cell_index=placement.index,
                    current_cell_in_row=cell_offset + 1,
                    row_cell_count=len(row_placements),
                    cells_completed=cells_completed,
                    rows_completed=completed_rows,
                    sheet_progress_percent=(cells_completed / total_cells) * 100.0 if total_cells else 100.0,
                )
            if row_had_printed_cell:
                rows_printed += 1
        return rows_printed, cells_completed, last_gcode_path

    def _claim_user_jobs(self, limit: int) -> list[PlotJobLease]:
        jobs: list[PlotJobLease] = []
        run_started_at = self.oracle_store.load_run_started_at() if self.oracle_store is not None else None
        allowed_origins = self._load_print_origins()
        for _ in range(limit):
            try:
                job = self.remote.claim_next_plot_job(
                    "macbook-plotter",
                    run_started_at=run_started_at,
                    allowed_origins=allowed_origins,
                )
            except TypeError:
                try:
                    job = self.remote.claim_next_plot_job("macbook-plotter", run_started_at=run_started_at)
                except TypeError:
                    job = self.remote.claim_next_plot_job("macbook-plotter")
            if job is None:
                break
            jobs.append(job)
        return jobs

    def _load_print_origins(self) -> list[str]:
        if self.oracle_store is None:
            return list(ALL_ORIGINS)
        return self.oracle_store.load_origin_filters()["print_origins"]

    def _materialize_sheet_items(self, user_jobs: list[PlotJobLease], sheet_limit: int) -> list[SheetItem]:
        items: list[SheetItem] = []
        cache_dir = self.settings.spool_root / "cache"
        ensure_dir(cache_dir)

        for job in user_jobs:
            local_svg = cache_dir / f"{job.session_id}.svg"
            self.remote.download_asset(job.svg_storage_path, local_svg)
            _apply_current_mark_scale(local_svg, job.title)
            source_kind = "placeholder" if job.queue == "filler" or job.priority == "filler" or job.origin == ORIGIN_FILLER_MACBOOK else "user"
            items.append(
                SheetItem(
                    source_kind=source_kind,
                    session_id=job.session_id,
                    title=job.title,
                    svg_path=local_svg,
                    origin=job.origin,
                    tags=job.tags,
                    marker_position=marker_position_for_origin(job.origin),
                )
            )

        remaining = sheet_limit - len(items)
        if remaining <= 0:
            return items

        placeholders = _list_placeholder_svg_paths(self.settings.placeholder_root)
        if not placeholders:
            return items

        start_index = self.runtime_state.placeholder_index
        placeholders = list(placeholders)
        random.Random(time.time_ns() + start_index).shuffle(placeholders)
        for offset in range(remaining):
            svg_path = placeholders[(start_index + offset) % len(placeholders)]
            local_svg = _materialize_scaled_placeholder(svg_path, cache_dir)
            items.append(
                SheetItem(
                    source_kind="placeholder",
                    session_id=f"placeholder_{start_index + offset}",
                    title=svg_path.stem,
                    svg_path=local_svg,
                    origin=ORIGIN_FILLER_MACBOOK,
                    tags=normalize_tags(["filler", "local", "macbook"]),
                    marker_position=marker_position_for_origin(ORIGIN_FILLER_MACBOOK),
                )
            )
        with self.state_lock:
            self.runtime_state.placeholder_index = (start_index + remaining) % len(placeholders)
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
        return items

    def _manifest_row_payload(
        self,
        *,
        row_index: int,
        row_id: str,
        items: list[SheetItem],
        placements: list[SheetPlacement],
        status: str,
        marker_diameter_mm: float = DEFAULT_MARKER_DIAMETER_MM,
    ) -> dict[str, object]:
        return {
            "row_index": row_index,
            "row_id": row_id,
            "status": status,
            "items": [
                {
                    "session_id": item.session_id,
                    "source_kind": item.source_kind,
                    "origin": item.origin,
                    "tags": item.tags,
                    "marker_position": item.marker_position or marker_position_for_origin(item.origin),
                    "marker_diameter_mm": marker_diameter_mm,
                    "svg_path": str(item.svg_path),
                    "sheet_index": placement.index,
                    "center_x_mm": placement.center_x_mm,
                    "center_y_mm": placement.center_y_mm,
                    "cell_diameter_mm": placement.diameter_mm,
                    "rotation_deg": placement.rotation_deg,
                    "symbol_scale": placement.symbol_scale,
                    "row_y_mm": placement.row_y_mm,
                }
                for item, placement in zip(items, placements, strict=True)
            ],
        }

    def _manifest_cell_payload(
        self,
        *,
        row_index: int,
        cell_id: str,
        item: SheetItem,
        placement: SheetPlacement,
        status: str,
        marker_diameter_mm: float = DEFAULT_MARKER_DIAMETER_MM,
    ) -> dict[str, object]:
        return {
            "row_index": row_index,
            "cell_id": cell_id,
            "status": status,
            "item": self._manifest_item_payload(item, placement, marker_diameter_mm=marker_diameter_mm),
        }

    def _manifest_item_payload(
        self,
        item: SheetItem,
        placement: SheetPlacement,
        *,
        marker_diameter_mm: float = DEFAULT_MARKER_DIAMETER_MM,
    ) -> dict[str, object]:
        return {
            "session_id": item.session_id,
            "source_kind": item.source_kind,
            "origin": item.origin,
            "tags": item.tags,
            "marker_position": item.marker_position or marker_position_for_origin(item.origin),
            "marker_diameter_mm": marker_diameter_mm,
            "svg_path": str(item.svg_path),
            "sheet_index": placement.index,
            "center_x_mm": placement.center_x_mm,
            "center_y_mm": placement.center_y_mm,
            "cell_diameter_mm": placement.diameter_mm,
            "rotation_deg": placement.rotation_deg,
            "symbol_scale": placement.symbol_scale,
            "row_y_mm": placement.row_y_mm,
        }

    def _append_manifest_row(self, path: Path, manifest: dict[str, object], row_payload: dict[str, object]) -> None:
        rows = manifest.setdefault("rows", [])
        items = manifest.setdefault("items", [])
        if isinstance(rows, list):
            rows.append(row_payload)
        if isinstance(items, list):
            row_items = row_payload.get("items", [])
            if isinstance(row_items, list):
                items.extend(row_items)
        self._write_manifest(path, manifest)

    def _append_manifest_cell(self, path: Path, manifest: dict[str, object], cell_payload: dict[str, object]) -> None:
        cells = manifest.setdefault("cells", [])
        items = manifest.setdefault("items", [])
        if isinstance(cells, list):
            cells.append(cell_payload)
        if isinstance(items, list):
            item = cell_payload.get("item")
            if isinstance(item, dict):
                items.append(item)
        self._write_manifest(path, manifest)

    def _replace_manifest_row(
        self,
        path: Path,
        manifest: dict[str, object],
        row_index: int,
        row_payload: dict[str, object],
    ) -> None:
        rows = manifest.get("rows", [])
        if isinstance(rows, list):
            for index, existing_row in enumerate(rows):
                if isinstance(existing_row, dict) and existing_row.get("row_index") == row_index:
                    rows[index] = row_payload
                    break
        self._write_manifest(path, manifest)

    def _replace_manifest_cell(
        self,
        path: Path,
        manifest: dict[str, object],
        cell_id: str,
        cell_payload: dict[str, object],
    ) -> None:
        cells = manifest.get("cells", [])
        if isinstance(cells, list):
            for index, existing_cell in enumerate(cells):
                if isinstance(existing_cell, dict) and existing_cell.get("cell_id") == cell_id:
                    cells[index] = cell_payload
                    break
        self._write_manifest(path, manifest)

    def _write_manifest(self, path: Path, manifest: dict[str, object]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def _build_cell_progress_markers(
        self,
        gcode: str,
        placements: list[SheetPlacement],
    ) -> list[tuple[int, int, int]]:
        markers: list[tuple[int, int, int]] = []
        command_count = 0
        for line in gcode.splitlines():
            stripped = line.strip()
            if stripped.startswith("; cell-start "):
                raw = stripped.removeprefix("; cell-start ").strip()
                try:
                    current, _total = raw.split("/", 1)
                    cell_offset = int(current)
                except ValueError:
                    cell_offset = -1
                if 0 <= cell_offset < len(placements):
                    # FluidNCTransport does not send comments. The marker maps to the next real command.
                    markers.append((max(command_count + 1, 1), cell_offset + 1, placements[cell_offset].index))
            if stripped and not stripped.startswith(";"):
                command_count += 1
        return markers

    def _load_plotter_config(self) -> PlotterRuntimeConfig:
        default = PlotterRuntimeConfig(
            layout_mode=self.settings.layout_mode,
            sheet_width_mm=self.settings.sheet_width_mm,
            sheet_height_mm=self.settings.sheet_height_mm,
            sheet_margin_mm=self.settings.sheet_margin_mm,
            cell_diameter_mm=self.settings.cell_diameter_mm,
            gap_mm=self.settings.cell_gap_mm,
            organic_enabled=self.settings.organic_enabled,
            organic_cell_size_mm=self.settings.organic_cell_size_mm,
            organic_rotation_ramp=self.settings.organic_rotation_ramp,
            organic_scale_ramp=self.settings.organic_scale_ramp,
            organic_seed=self.settings.organic_seed,
            run_mode="exhibition",
            dry_run=self.settings.dry_run,
            include_rings=True,
            include_markers=self.settings.include_markers,
            marker_diameter_mm=self.settings.marker_diameter_mm,
            xy_acceleration_mm_s2=self.settings.xy_acceleration_mm_s2,
            use_z_servo=self.settings.use_z_servo,
            z_down_mm=self.settings.z_down_mm,
            z_up_mm=self.settings.z_up_mm,
            z_feed_mm_min=self.settings.z_feed_mm_min,
            work_zero_command=self.settings.work_zero_command,
            sample_step_mm=self.settings.sample_step_mm,
            sample_reference_cell_mm=self.settings.sample_reference_cell_mm,
            sample_density_exponent=self.settings.sample_density_exponent,
            sample_min_step_mm=self.settings.sample_min_step_mm,
            sample_max_step_mm=self.settings.sample_max_step_mm,
            streaming_mode=self.settings.streaming_mode,
        )
        if self.oracle_store is None:
            return default
        return self.oracle_store.load_plotter_config(default)

    def _load_control_state(self) -> PlotterControlState:
        default = self.store.load_control_state()
        if self.oracle_store is None:
            return default
        control = self.oracle_store.load_print_control(default)
        self.store.save_control_state(control)
        return control

    def _set_state(
        self,
        status: RuntimeStatus,
        message: str,
        *,
        sheet_id: str = "",
        gcode_lines_sent: int | None = None,
        gcode_lines_total: int | None = None,
        gcode_progress_percent: float | None = None,
        current_row_index: int | None = None,
        row_count: int | None = None,
        rows_completed: int | None = None,
        current_cell_index: int | None = None,
        current_cell_in_row: int | None = None,
        row_cell_count: int | None = None,
        cells_completed: int | None = None,
        sheet_progress_percent: float | None = None,
    ) -> None:
        with self.state_lock:
            self.runtime_state.status = status
            self.runtime_state.message = message
            if sheet_id:
                self.runtime_state.current_sheet_id = sheet_id
            if gcode_lines_sent is not None:
                self.runtime_state.gcode_lines_sent = gcode_lines_sent
            if gcode_lines_total is not None:
                self.runtime_state.gcode_lines_total = gcode_lines_total
            if gcode_progress_percent is not None:
                self.runtime_state.gcode_progress_percent = gcode_progress_percent
            if current_row_index is not None:
                self.runtime_state.current_row_index = current_row_index
            if row_count is not None:
                self.runtime_state.row_count = row_count
            if rows_completed is not None:
                self.runtime_state.rows_completed = rows_completed
            if current_cell_index is not None:
                self.runtime_state.current_cell_index = current_cell_index
            if current_cell_in_row is not None:
                self.runtime_state.current_cell_in_row = current_cell_in_row
            if row_cell_count is not None:
                self.runtime_state.row_cell_count = row_cell_count
            if cells_completed is not None:
                self.runtime_state.cells_completed = cells_completed
            if sheet_progress_percent is not None:
                self.runtime_state.sheet_progress_percent = sheet_progress_percent
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
        if self.oracle_store is not None:
            component_status = ComponentStatus.ERROR if status == RuntimeStatus.ERROR else ComponentStatus.RUNNING
            if status == RuntimeStatus.OPERATOR_PAUSED:
                component_status = ComponentStatus.WARNING
            self.oracle_store.set_component(
                "plotter",
                component_status,
                message=message,
                last_error=message if status == RuntimeStatus.ERROR else "",
                heartbeat=True,
            )

    def _record_gcode_progress(self, sent: int, total: int) -> None:
        percent = 100.0 if total <= 0 else min(max((sent / total) * 100.0, 0.0), 100.0)
        with self.state_lock:
            self.runtime_state.gcode_lines_sent = sent
            self.runtime_state.gcode_lines_total = total
            self.runtime_state.gcode_progress_percent = percent
            row_label = ""
            if self.runtime_state.row_count:
                row_label = f"row {self.runtime_state.current_row_index}/{self.runtime_state.row_count}: "
                completed_fraction = min(max(sent / total, 0.0), 1.0) if total > 0 else 1.0
                if self._current_row_cell_count > 0:
                    current_cell_in_row, current_sheet_index = self._cell_progress_for_sent_count(sent)
                    self.runtime_state.current_cell_in_row = current_cell_in_row
                    self.runtime_state.row_cell_count = self._current_row_cell_count
                    self.runtime_state.current_cell_index = current_sheet_index
                    self.runtime_state.cells_completed = self._cells_completed_before_row + max(0, current_cell_in_row - 1)
                self.runtime_state.sheet_progress_percent = min(
                    max(((self.runtime_state.rows_completed + completed_fraction) / self.runtime_state.row_count) * 100.0, 0.0),
                    100.0,
                )
            cell_label = ""
            if self.runtime_state.row_cell_count:
                cell_label = f" cell {self.runtime_state.current_cell_in_row}/{self.runtime_state.row_cell_count},"
            self.runtime_state.message = f"Streaming {row_label}{cell_label} {sent}/{total} lines ({percent:.1f}%)"
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)

    def _cell_progress_for_sent_count(self, sent: int) -> tuple[int, int]:
        if not self._current_row_cell_markers:
            return 1, self._current_row_sheet_indexes[0]
        current_cell_in_row = self._current_row_cell_markers[0][1]
        current_sheet_index = self._current_row_cell_markers[0][2]
        for command_threshold, cell_in_row, sheet_index in self._current_row_cell_markers:
            if sent < command_threshold:
                break
            current_cell_in_row = cell_in_row
            current_sheet_index = sheet_index
        return current_cell_in_row, current_sheet_index


def _list_placeholder_svg_paths(root: Path) -> list[Path]:
    flat_svgs = sorted(path for path in root.glob("*.svg") if path.is_file())
    package_svgs: list[Path] = []
    for session_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        package_svgs.extend(sorted(session_dir.glob("*_plotter.svg")))
    return flat_svgs + package_svgs


def _apply_current_mark_scale(svg_path: Path, mark_name: str) -> None:
    scale = _current_scale_for_mark(mark_name)
    try:
        metadata = read_normalized_svg_metadata(svg_path)
    except ET.ParseError:
        return
    tree = ET.parse(svg_path)
    root = tree.getroot()
    changed = False
    if metadata.normalized and scale is not None:
        bounded = _bounded_symbol_scale(scale)
        if abs(metadata.scale - bounded) >= 0.0001:
            root.set("data-neje-scale", f"{bounded:.6g}")
            changed = True
    symbol_name = _symbol_file_name_for_mark(mark_name)
    if symbol_name in DEFAULT_SINGLE_STROKE_SYMBOLS and root.get("data-neje-single-stroke") != "true":
        root.set("data-neje-single-stroke", "true")
        changed = True
    simplify_tolerance = DEFAULT_SIMPLIFY_TOLERANCE_MM.get(symbol_name or "", 0.0)
    if simplify_tolerance > 0 and root.get("data-neje-simplify-mm") != f"{simplify_tolerance:.6g}":
        root.set("data-neje-simplify-mm", f"{simplify_tolerance:.6g}")
        changed = True
    if changed:
        tree.write(svg_path, encoding="unicode")


def _materialize_scaled_placeholder(svg_path: Path, cache_dir: Path) -> Path:
    scale = _current_scale_for_symbol_file(svg_path)
    ensure_dir(cache_dir)
    cache_path = cache_dir / f"placeholder_{svg_path.stem}.svg"
    cache_path.write_text(
        normalize_svg_file(svg_path, marker_kind="idle", scale=scale, include_rings=False),
        encoding="utf-8",
    )
    return cache_path


def _current_scale_for_mark(mark_name: str) -> float | None:
    normalized_name = mark_name.strip().upper()
    if not normalized_name:
        return None
    scale = scale_for_mark_name(normalized_name, _symbol_root(), _scale_config_path())
    return _bounded_symbol_scale(scale)


def _symbol_file_name_for_mark(mark_name: str) -> str | None:
    normalized_name = mark_name.strip().upper()
    if normalized_name not in MARK_NAMES:
        return None
    symbol_index = MARK_NAMES.index(normalized_name)
    symbols = sorted(path for path in _symbol_root().glob("*.svg") if path.is_file())
    if symbol_index >= len(symbols):
        return None
    return symbols[symbol_index].name


def _current_scale_for_symbol_file(svg_path: Path) -> float:
    payload = _load_scale_payload()
    return _bounded_symbol_scale(float(payload.get(svg_path.name, 1.0)))


def _load_scale_payload() -> dict[str, float]:
    path = _scale_config_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): float(value) for key, value in raw.items()}


def _bounded_symbol_scale(value: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, float(value)))


def _symbol_root() -> Path:
    return _repo_root() / "assets" / "symbols"


def _scale_config_path() -> Path:
    return _symbol_root() / "symbol_scales.json"
