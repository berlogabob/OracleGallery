"""Operator event log: one JSON line per event, for the HEART scorecard.

The GUI wraps its task handlers with this so real operator sessions produce task
timings, outcomes and screen switches without any external analytics. Read it back
with scripts/operator_report.py. Lives in shared/ because blocks must not import
blocks.gui; the GUI imports this, never the reverse.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# One id per process: enough to group a gallery day's events into sessions.
_SESSION = f"{os.getpid()}-{int(time.time())}"

EVENTS_FILENAME = "operator_events.jsonl"


def _events_path() -> Path:
    from .config import OracleSupervisorSettings

    root = OracleSupervisorSettings().logs_root
    root.mkdir(parents=True, exist_ok=True)
    return root / EVENTS_FILENAME


def log_event(kind: str, **fields: Any) -> None:
    """Append one event. Never raises: telemetry must not take down a handler."""
    event = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "session": _SESSION,
        "kind": kind,
        **fields,
    }
    try:
        with _events_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
    except OSError:
        pass
