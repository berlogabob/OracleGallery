from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import PlotterSettings, ensure_dir
from .firebase_io import FirebaseRemoteRepository
from .layout import build_hex_layout
from .models import PlotJobLease, PlotStatus, PlotterRuntimeState, RuntimeStatus, SheetItem
from .store import PlotterStore
from .svg_gcode import generate_sheet_gcode
from .transport import FluidNCTransport


class PlotterDaemon:
    def __init__(
        self,
        settings: PlotterSettings,
        store: PlotterStore,
        remote: FirebaseRemoteRepository,
        transport: FluidNCTransport,
    ) -> None:
        self.settings = settings
        self.store = store
        self.remote = remote
        self.transport = transport
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

    def run_cycle(self) -> None:
        with self.state_lock:
            if self.runtime_state.pending_reload:
                self.runtime_state.message = "Waiting for operator reload confirmation"
                self.runtime_state.updated_at = datetime.now(tz=UTC)
                self.store.save_runtime_state(self.runtime_state)
                return
            self.runtime_state.status = RuntimeStatus.PREPARING
            self.runtime_state.message = "Preparing next sheet"
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)

        try:
            user_jobs = self._claim_user_jobs(self.settings.sheet_capacity)
        except Exception as exc:  # noqa: BLE001
            user_jobs = []
            self._set_state(RuntimeStatus.ERROR, f"Remote queue unavailable: {exc}")

        items = self._materialize_sheet_items(user_jobs)
        if not items:
            self._set_state(RuntimeStatus.IDLE, "No user jobs or placeholders available")
            return

        sheet_id = datetime.now(tz=UTC).strftime("sheet_%Y%m%d_%H%M%S")
        placements = build_hex_layout(
            len(items),
            sheet_width_mm=self.settings.sheet_width_mm,
            sheet_height_mm=self.settings.sheet_height_mm,
            margin_mm=self.settings.sheet_margin_mm,
            diameter_mm=self.settings.cell_diameter_mm,
        )
        if len(placements) < len(items):
            raise RuntimeError("Sheet layout capacity is smaller than the selected items.")

        for job in user_jobs:
            self.remote.update_plot_job(job.session_id, PlotStatus.PLOTTING, sheet_id=sheet_id)
            self.store.record_job_status(job.session_id, PlotStatus.PLOTTING, sheet_id=sheet_id)

        gcode = generate_sheet_gcode(
            items,
            placements,
            sample_step_mm=self.settings.sample_step_mm,
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
                        }
                        for item in items
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self._set_state(RuntimeStatus.PRINTING, f"Streaming {sheet_id} to plotter", sheet_id=sheet_id)
        try:
            gcode_path = self.transport.send(gcode=gcode, sheet_id=sheet_id)
        except Exception as exc:  # noqa: BLE001
            for job in user_jobs:
                self.remote.update_plot_job(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
                self.store.record_job_status(job.session_id, PlotStatus.FAILED, sheet_id=sheet_id, error=str(exc))
            self._set_state(RuntimeStatus.ERROR, f"Plotter transport failed: {exc}", sheet_id=sheet_id)
            return

        for job in user_jobs:
            self.remote.update_plot_job(job.session_id, PlotStatus.PRINTED, sheet_id=sheet_id)
            self.store.record_job_status(job.session_id, PlotStatus.PRINTED, sheet_id=sheet_id)

        with self.state_lock:
            self.runtime_state.status = RuntimeStatus.PAUSED
            self.runtime_state.message = "Sheet finished. Replace material and confirm reload."
            self.runtime_state.current_sheet_id = sheet_id
            self.runtime_state.last_sheet_path = str(gcode_path)
            self.runtime_state.pending_reload = True
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)

    def _claim_user_jobs(self, limit: int) -> list[PlotJobLease]:
        jobs: list[PlotJobLease] = []
        for _ in range(limit):
            job = self.remote.claim_next_plot_job("macbook-plotter")
            if job is None:
                break
            jobs.append(job)
        return jobs

    def _materialize_sheet_items(self, user_jobs: list[PlotJobLease]) -> list[SheetItem]:
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
                    preview_url=job.preview_url,
                )
            )

        remaining = self.settings.sheet_capacity - len(items)
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

    def _set_state(self, status: RuntimeStatus, message: str, *, sheet_id: str = "") -> None:
        with self.state_lock:
            self.runtime_state.status = status
            self.runtime_state.message = message
            if sheet_id:
                self.runtime_state.current_sheet_id = sheet_id
            self.runtime_state.updated_at = datetime.now(tz=UTC)
            self.store.save_runtime_state(self.runtime_state)
