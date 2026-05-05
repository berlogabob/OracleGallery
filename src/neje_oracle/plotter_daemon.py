from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import SYMBOL_FIT_RATIO, PlotterSettings, ensure_dir
from .firebase_io import FirebaseRemoteRepository
from .layout import build_sheet_layout, calculate_layout_capacity
from .models import ComponentStatus, PlotJobLease, PlotStatus, PlotterControlState, PlotterRuntimeConfig, PlotterRuntimeState, RuntimeStatus, SheetItem
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
            self.oracle_store.set_component("plotter", ComponentStatus.WARNING, message="Sheet finished; waiting reload", heartbeat=True)

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

        try:
            user_jobs = self._claim_user_jobs(sheet_limit)
        except Exception as exc:  # noqa: BLE001
            user_jobs = []
            self._set_state(RuntimeStatus.ERROR, f"Remote queue unavailable: {exc}")

        items = self._materialize_sheet_items(user_jobs, sheet_limit)
        if not items:
            self._set_state(RuntimeStatus.IDLE, "No user jobs or placeholders available")
            return

        sheet_id = datetime.now(tz=UTC).strftime("sheet_%Y%m%d_%H%M%S")
        placements = build_sheet_layout(
            len(items),
            mode=config.layout_mode,
            sheet_width_mm=config.sheet_width_mm,
            sheet_height_mm=config.sheet_height_mm,
            margin_mm=config.sheet_margin_mm,
            diameter_mm=config.cell_diameter_mm,
            gap_mm=config.gap_mm,
        )
        if len(placements) < len(items):
            raise RuntimeError("Sheet layout capacity is smaller than the selected items.")

        for sheet_index, job in enumerate(user_jobs):
            self.remote.update_plot_job(
                job.session_id,
                PlotStatus.PLOTTING,
                sheet_id=sheet_id,
                sheet_index=sheet_index,
            )
            self.store.record_job_status(job.session_id, PlotStatus.PLOTTING, sheet_id=sheet_id)

        gcode = generate_sheet_gcode(
            items,
            placements,
            sample_step_mm=self.settings.sample_step_mm,
            cell_diameter_mm=config.cell_diameter_mm,
            travel_rate=self.settings.travel_rate,
            draw_rate=self.settings.draw_rate,
            pen_up_command=self.settings.pen_up_command,
            pen_down_command=self.settings.pen_down_command,
        )
        manifest_path = self.settings.spool_root / f"{sheet_id}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "sheet_id": sheet_id,
                    "items": [
                        {
                            "session_id": item.session_id,
                            "source_kind": item.source_kind,
                            "svg_path": str(item.svg_path),
                            "sheet_index": index,
                            "center_x_mm": placements[index].center_x_mm,
                            "center_y_mm": placements[index].center_y_mm,
                            "cell_diameter_mm": placements[index].diameter_mm,
                        }
                        for index, item in enumerate(items)
                    ],
                    "layout_mode": config.layout_mode,
                    "cell_diameter_mm": config.cell_diameter_mm,
                    "gap_mm": config.gap_mm,
                    "symbol_fit_ratio": SYMBOL_FIT_RATIO,
                    "dry_run": control.dry_run,
                    "run_mode": control.run_mode,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        total_gcode_lines = len(gcode.splitlines())
        self._set_state(
            RuntimeStatus.PRINTING,
            f"Streaming {sheet_id} to plotter",
            sheet_id=sheet_id,
            gcode_lines_sent=0,
            gcode_lines_total=total_gcode_lines,
            gcode_progress_percent=0.0,
        )
        try:
            gcode_path = self.transport.send(
                gcode=gcode,
                sheet_id=sheet_id,
                dry_run=control.dry_run,
                progress_callback=self._record_gcode_progress,
            )
        except Exception as exc:  # noqa: BLE001
            for job in user_jobs:
                self.remote.update_plot_job(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
                self.store.record_job_status(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
            if self.oracle_store is not None:
                control = self.oracle_store.load_print_control()
                control.print_enabled = False
                control.operator_paused = True
                self.oracle_store.save_print_control(control)
                self.oracle_store.save_real_fluidnc_armed(False)
                self.oracle_store.set_component("print", ComponentStatus.STOPPED, message=f"Print disabled after FluidNC error: {exc}")
            self._set_state(RuntimeStatus.ERROR, f"Plotter transport failed: {exc}", sheet_id=sheet_id)
            return

        for sheet_index, job in enumerate(user_jobs):
            self.remote.update_plot_job(
                job.session_id,
                PlotStatus.PRINTED,
                sheet_id=sheet_id,
                sheet_index=sheet_index,
            )
            self.store.record_job_status(job.session_id, PlotStatus.PRINTED, sheet_id=sheet_id)

        with self.state_lock:
            self.runtime_state.status = RuntimeStatus.PAUSED
            self.runtime_state.message = "Sheet finished. Replace material and confirm reload."
            self.runtime_state.current_sheet_id = sheet_id
            self.runtime_state.last_sheet_path = str(gcode_path)
            self.runtime_state.pending_reload = True
            self.runtime_state.gcode_lines_sent = total_gcode_lines
            self.runtime_state.gcode_lines_total = total_gcode_lines
            self.runtime_state.gcode_progress_percent = 100.0
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
        if self.oracle_store is not None:
            self.oracle_store.set_component("plotter", ComponentStatus.WARNING, message="Sheet finished; waiting reload", heartbeat=True)

    def _claim_user_jobs(self, limit: int) -> list[PlotJobLease]:
        jobs: list[PlotJobLease] = []
        for _ in range(limit):
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
            self.runtime_state.message = f"Streaming G-code: {sent}/{total} lines ({percent:.1f}%)"
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
