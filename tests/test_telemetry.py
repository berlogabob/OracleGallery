"""The event log is the HEART evidence; these pin its shape and its wiring."""

from __future__ import annotations

import asyncio
import json

import pytest

from neje_oracle.shared import telemetry
from neje_oracle.shared.config import OracleSupervisorSettings


def _events() -> list[dict]:
    path = OracleSupervisorSettings().logs_root / telemetry.EVENTS_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_log_event_shape() -> None:
    before = len(_events())
    telemetry.log_event("task_ok", task="demo", duration_s=0.5)
    events = _events()
    assert len(events) == before + 1
    event = events[-1]
    assert event["kind"] == "task_ok"
    assert event["task"] == "demo"
    assert event["duration_s"] == 0.5
    assert event["session"] and event["ts"]


def test_emergency_stop_writes_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same fake pattern as the jog tests: the supervisor and UI are stubbed so the
    coroutine exercises only the telemetry wiring, not FluidNC or run.io_bound."""
    from neje_oracle.blocks.gui.context import GuiContext
    from neje_oracle.shared.gui_settings import GuiSettings
    from neje_oracle.shared.models import ComponentState, ComponentStatus

    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda *a, **k: GuiSettings())
    ctx = GuiContext()
    monkeypatch.setattr("neje_oracle.blocks.gui.context.ui.notify", lambda *a, **k: None)
    monkeypatch.setattr(ctx, "refresh_status", lambda: None)
    monkeypatch.setattr(ctx, "refresh_logs", lambda: None)

    async def fake_blocking(fn, *args, **kwargs):
        return ComponentState(component="plotter", status=ComponentStatus.STOPPED, message="halted")

    monkeypatch.setattr(ctx, "_blocking", fake_blocking)

    before = len(_events())
    asyncio.run(ctx.emergency_stop())
    kinds = [(e["kind"], e["task"]) for e in _events()[before:]]
    assert ("task_start", "emergency_stop") in kinds
    assert any(kind in {"task_ok", "task_fail"} and task == "emergency_stop" for kind, task in kinds)
