from __future__ import annotations

import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .config import FirebaseSettings, PlotterSettings
from .firebase_io import FirebaseRemoteRepository
from .models import HealthResponse, ReloadResponse
from .plotter_daemon import PlotterDaemon
from .store import PlotterStore
from .transport import FluidNCTransport


def create_app() -> FastAPI:
    settings = PlotterSettings()
    remote = FirebaseRemoteRepository(FirebaseSettings())
    store = PlotterStore(settings.db_path)
    transport = FluidNCTransport(settings)
    daemon = PlotterDaemon(settings, store, remote, transport)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        thread = threading.Thread(target=daemon.run_forever, daemon=True)
        thread.start()
        try:
            yield
        finally:
            daemon.stop()
            thread.join(timeout=5.0)

    app = FastAPI(title="Neje Plotter Operator", lifespan=lifespan)
    app.state.daemon = daemon
    app.state.store = store

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        state = app.state.daemon.get_state().to_dict()
        state.update(app.state.store.load_control_state().to_dict())
        return HealthResponse(ok=True, status=state["status"], detail=state)

    @app.get("/status", response_model=HealthResponse)
    def status() -> HealthResponse:
        state = app.state.daemon.get_state().to_dict()
        state.update(app.state.store.load_control_state().to_dict())
        return HealthResponse(ok=True, status=state["status"], detail=state)

    @app.post("/operator/reload", response_model=ReloadResponse)
    def reload_sheet() -> ReloadResponse:
        app.state.daemon.confirm_reload()
        return ReloadResponse(ok=True, status="reloaded")

    @app.post("/operator/start", response_model=ReloadResponse)
    def start_print() -> ReloadResponse:
        control = app.state.store.load_control_state()
        control.print_enabled = True
        control.operator_paused = False
        app.state.store.save_control_state(control)
        return ReloadResponse(ok=True, status="print_enabled")

    @app.post("/operator/stop", response_model=ReloadResponse)
    def stop_print() -> ReloadResponse:
        control = app.state.store.load_control_state()
        control.print_enabled = False
        control.operator_paused = True
        app.state.store.save_control_state(control)
        return ReloadResponse(ok=True, status="operator_paused")

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        state = app.state.daemon.get_state().to_dict()
        control = app.state.store.load_control_state().to_dict()
        reload_button = (
            "<form method='post' action='/operator/reload'><button type='submit'>Confirm reload</button></form>"
            if state["pending_reload"]
            else ""
        )
        start_stop = (
            "<form method='post' action='/operator/stop'><button type='submit'>Stop after sheet</button></form>"
            if control["print_enabled"]
            else "<form method='post' action='/operator/start'><button type='submit'>Start print</button></form>"
        )
        return f"""
        <html>
          <head>
            <title>Neje Plotter Operator</title>
            <style>
              body {{ font-family: Helvetica, Arial, sans-serif; margin: 32px; background: #f6f2ea; color: #1f1a17; }}
              .card {{ max-width: 720px; padding: 24px; border-radius: 18px; background: white; box-shadow: 0 8px 32px rgba(0,0,0,0.08); }}
              .status {{ font-size: 28px; margin-bottom: 8px; }}
              button {{ padding: 12px 20px; border: 0; border-radius: 999px; background: #1f1a17; color: white; font-size: 16px; }}
              code {{ font-size: 14px; }}
            </style>
          </head>
          <body>
            <div class="card">
              <div class="status">Status: {state["status"]}</div>
              <p>{state["message"]}</p>
              <p>Print enabled: <code>{control["print_enabled"]}</code></p>
              <p>Mode: <code>{control["run_mode"]}</code>, dry-run: <code>{control["dry_run"]}</code></p>
              <p>Current sheet: <code>{state["current_sheet_id"] or "-"}</code></p>
              <p>Last gcode: <code>{state["last_sheet_path"] or "-"}</code></p>
              {start_stop}
              {reload_button}
            </div>
          </body>
        </html>
        """

    return app


def main() -> None:
    settings = PlotterSettings()
    uvicorn.run(create_app(), host=settings.operator_host, port=settings.operator_port)
