from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import SYMBOL_FIT_RATIO, PlotterSettings, ensure_dir
from .firebase_io import FirebaseRemoteRepository
from .layout import build_sheet_layout, calculate_layout_capacity, group_layout_rows
from .models import ComponentStatus, PlotJobLease, PlotStatus, PlotterControlState, PlotterRuntimeConfig, PlotterRuntimeState, RuntimeStatus, SheetItem, SheetPlacement
from .store import OracleRuntimeStore, PlotterStore
from .svg_gcode import generate_sheet_gcode
from .transport import FluidNCTransport


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

    def confirm_reload(self) -> None:
        with self.state_lock:
            self.runtime_state.pending_reload = False
            self.runtime_state.status = RuntimeStatus.IDLE
            self.runtime_state.message = "Operator confirmed reload"
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
        if self.oracle_store is not None:
            self.oracle_store.set_component("plotter", ComponentStatus.RUNNING, message="Reload confirmed", heartbeat=True)

    def run_cycle(self) -> None:
        if self.oracle_store is not None:
            self.oracle_store.set_component("plotter", ComponentStatus.RUNNING, message="Daemon cycle", heartbeat=True)
        with self.state_lock:
            if self.runtime_state.pending_reload:
                self.runtime_state.message = "Waiting for operator reload confirmation"
                self.runtime_state.updated_at = datetime.now(tz=UTC)
                self.store.save_runtime_state(self.runtime_state)
                return

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
        )
        layout_rows = group_layout_rows(placements)
        if not layout_rows:
            self._set_state(RuntimeStatus.ERROR, "Sheet layout has no printable rows")
            return

        manifest_path = self.settings.spool_root / f"{sheet_id}.json"
        manifest: dict[str, object] = {
            "sheet_id": sheet_id,
            "items": [],
            "rows": [],
            "layout_mode": config.layout_mode,
            "cell_diameter_mm": config.cell_diameter_mm,
            "gap_mm": config.gap_mm,
            "symbol_fit_ratio": SYMBOL_FIT_RATIO,
            "dry_run": control.dry_run,
            "run_mode": control.run_mode,
            "include_rings": config.include_rings,
            "use_z_servo": config.use_z_servo,
            "z_up_mm": config.z_up_mm,
            "z_down_mm": config.z_down_mm,
            "row_count": len(layout_rows),
        }
        self._write_manifest(manifest_path, manifest)

        rows_printed = 0
        cells_completed = 0
        last_gcode_path: Path | None = None
        for row_index, row_placements in enumerate(layout_rows, start=1):
            if self.stop_event.is_set():
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
                sample_step_mm=self.settings.sample_step_mm,
                cell_diameter_mm=config.cell_diameter_mm,
                travel_rate=self.settings.travel_rate,
                draw_rate=self.settings.draw_rate,
                pen_up_command=self.settings.pen_up_command,
                pen_down_command=self.settings.pen_down_command,
                title=f"{sheet_id} row {row_index}/{len(layout_rows)}",
                return_home=row_index == len(layout_rows),
                include_rings=config.include_rings,
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
                    self.oracle_store.save_real_fluidnc_armed(False)
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
                self.oracle_store.save_real_fluidnc_armed(False)
                self.oracle_store.set_component("print", ComponentStatus.STOPPED, message=f"Print disabled after post-sheet safety failure: {exc}")
            self._set_state(RuntimeStatus.ERROR, f"Post-sheet safety failed: {exc}", sheet_id=sheet_id)
            return

        with self.state_lock:
            self.runtime_state.status = RuntimeStatus.PAUSED
            self.runtime_state.message = "Sheet finished. Replace material and confirm reload."
            self.runtime_state.current_sheet_id = sheet_id
            self.runtime_state.last_sheet_path = str(last_gcode_path or manifest_path)
            self.runtime_state.pending_reload = True
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
            self.oracle_store.set_component("plotter", ComponentStatus.WARNING, message="Sheet finished; waiting reload", heartbeat=True)

    def _post_sheet_safety_gcode(self, config: PlotterRuntimeConfig, sheet_id: str) -> str:
        if config.use_z_servo:
            pen_up = f"G0 Z{config.z_up_mm:.3f}"
        else:
            pen_up = self.settings.pen_up_command
        return "\n".join(
            [
                f"; Neje Oracle {sheet_id} post-sheet safety",
                "G21",
                "G90",
                f"G0 F{self.settings.travel_rate:.2f}",
                pen_up,
                "G0 X0 Y0",
                "",
            ]
        )

    def _claim_user_jobs(self, limit: int) -> list[PlotJobLease]:
        jobs: list[PlotJobLease] = []
        run_started_at = self.oracle_store.load_run_started_at() if self.oracle_store is not None else None
        for _ in range(limit):
            try:
                job = self.remote.claim_next_plot_job("macbook-plotter", run_started_at=run_started_at)
            except TypeError:
                job = self.remote.claim_next_plot_job("macbook-plotter")
            if job is None:
                break
            jobs.append(job)
        return jobs

    def _materialize_sheet_items(self, user_jobs: list[PlotJobLease], sheet_limit: int) -> list[SheetItem]:
        items: list[SheetItem] = []
        cache_dir = self.settings.spool_root / "cache"
        ensure_dir(cache_dir)

        for job in user_jobs:
            local_svg = cache_dir / f"{job.session_id}.svg"
            self.remote.download_asset(job.svg_storage_path, local_svg)
            items.append(
                SheetItem(
                    source_kind="user",
                    session_id=job.session_id,
                    title=job.title,
                    svg_path=local_svg,
                )
            )

        remaining = sheet_limit - len(items)
        if remaining <= 0:
            return items

        placeholders = sorted(self.settings.placeholder_root.glob("*.svg"))
        if not placeholders:
            return items

        start_index = self.runtime_state.placeholder_index
        for offset in range(remaining):
            svg_path = placeholders[(start_index + offset) % len(placeholders)]
            items.append(
                SheetItem(
                    source_kind="placeholder",
                    session_id=f"placeholder_{start_index + offset}",
                    title=svg_path.stem,
                    svg_path=svg_path,
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
    ) -> dict[str, object]:
        return {
            "row_index": row_index,
            "row_id": row_id,
            "status": status,
            "items": [
                {
                    "session_id": item.session_id,
                    "source_kind": item.source_kind,
                    "svg_path": str(item.svg_path),
                    "sheet_index": placement.index,
                    "center_x_mm": placement.center_x_mm,
                    "center_y_mm": placement.center_y_mm,
                    "cell_diameter_mm": placement.diameter_mm,
                }
                for item, placement in zip(items, placements, strict=True)
            ],
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

    def _write_manifest(self, path: Path, manifest: dict[str, object]) -> None:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

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
            run_mode="exhibition",
            dry_run=self.settings.dry_run,
            include_rings=True,
            use_z_servo=self.settings.use_z_servo,
            z_down_mm=self.settings.z_down_mm,
            z_up_mm=self.settings.z_up_mm,
            z_feed_mm_min=self.settings.z_feed_mm_min,
            work_zero_command=self.settings.work_zero_command,
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
            if status in {RuntimeStatus.PAUSED, RuntimeStatus.OPERATOR_PAUSED}:
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
