from __future__ import annotations

import threading
import time
import os
import argparse
from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI

from ...shared.config import FirebaseSettings, UploaderSettings
from ..firebase.repository import FirebaseRemoteRepository
from .session_uploader import SessionUploader
from ...shared.store import UploaderStore


class UploaderAgentController:
    def __init__(self, uploader: SessionUploader, settings: UploaderSettings) -> None:
        self.uploader = uploader
        self.settings = settings
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.imported_count = 0
        self.last_imported: list[str] = []
        self.last_error = ""
        self.started_at: datetime | None = None
        self.heartbeat_at: datetime | None = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status("already running")
            self._stop_event.clear()
            self.started_at = datetime.now(tz=UTC)
            self.uploader.store.save_run_started_at(self.started_at)
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        return self.status("started")

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread:
            thread.join(timeout=max(self.settings.poll_seconds * 2, 2.0))
        return self.status("stopped")

    def restart(self) -> dict[str, Any]:
        self.stop()
        return self.start()

    def scan_once(self) -> dict[str, Any]:
        try:
            imported = self.uploader.scan_once()
            self._record_imported(imported)
            return {**self.status("scan complete"), "imported": imported}
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            return {**self.status("scan failed"), "imported": []}

    def status(self, message: str = "") -> dict[str, Any]:
        running = bool(self._thread and self._thread.is_alive())
        return {
            "running": running,
            "message": message or ("running" if running else "stopped"),
            "watched_folder": str(self.settings.session_root),
            "public_folder": str(self.settings.public_root),
            "imported_count": self.imported_count,
            "last_imported": self.last_imported,
            "last_error": self.last_error,
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else "",
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                imported = self.uploader.scan_once()
                self._record_imported(imported)
                self.last_error = ""
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
            self.heartbeat_at = datetime.now(tz=UTC)
            self._stop_event.wait(self.settings.poll_seconds)

    def _record_imported(self, imported: list[str]) -> None:
        if not imported:
            return
        self.imported_count += len(imported)
        self.last_imported = imported[-5:]


def create_app(controller: UploaderAgentController | None = None) -> FastAPI:
    if controller is None:
        uploader_settings = UploaderSettings()
        firebase_settings = FirebaseSettings()
        store = UploaderStore(uploader_settings.db_path)
        remote = FirebaseRemoteRepository(firebase_settings)
        uploader = SessionUploader(uploader_settings, firebase_settings.gallery_base_url, store, remote)
        controller = UploaderAgentController(uploader, uploader_settings)

    app = FastAPI(title="Oracle Uploader Agent")
    app.state.controller = controller

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "neje-uploader-agent", **app.state.controller.status()}

    @app.get("/status")
    def status() -> dict[str, Any]:
        return app.state.controller.status()

    @app.post("/control/start")
    def start() -> dict[str, Any]:
        return app.state.controller.start()

    @app.post("/control/stop")
    def stop() -> dict[str, Any]:
        return app.state.controller.stop()

    @app.post("/control/restart")
    def restart() -> dict[str, Any]:
        return app.state.controller.restart()

    @app.post("/scan-once")
    def scan_once() -> dict[str, Any]:
        return app.state.controller.scan_once()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Oracle Mac mini uploader control agent.")
    parser.add_argument("--host", default=os.getenv("NEJE_UPLOADER_AGENT_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NEJE_UPLOADER_AGENT_PORT", "8790")))
    args = parser.parse_args()
    host = args.host
    port = args.port
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
