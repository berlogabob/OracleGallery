"""Cached plot-job queue status read from Firestore."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .repository import FirebaseRemoteRepository
from ...shared.config import FirebaseSettings, OracleSupervisorSettings, firebase_enabled
from ...shared.store import OracleRuntimeStore

_QUEUE_STATUS_CACHE: tuple[datetime, dict[str, Any]] | None = None


def read_queue_status(*, force: bool = False, ttl_seconds: float = 10.0) -> dict[str, Any]:
    global _QUEUE_STATUS_CACHE
    now = datetime.now(tz=UTC)
    if not force and _QUEUE_STATUS_CACHE is not None:
        cached_at, cached_payload = _QUEUE_STATUS_CACHE
        if (now - cached_at).total_seconds() < ttl_seconds:
            return cached_payload
    if not firebase_enabled():
        payload = _queue_status_offline("Firebase is not configured")
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload

    try:
        oracle_store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
        baseline = oracle_store.load_run_started_at()
        payload = FirebaseRemoteRepository(FirebaseSettings()).get_plot_job_counts(run_started_at=baseline)
        payload["runStartedAt"] = baseline.isoformat() if baseline else ""
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        payload = _queue_status_offline(str(exc))
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload


def _queue_status_offline(message: str) -> dict[str, Any]:
    return {
        "online": False,
        "total": 0,
        "limitedTo": 0,
        "pending": 0,
        "pendingAfterBaseline": 0,
        "pendingUserAfterBaseline": 0,
        "pendingFillerAfterBaseline": 0,
        "pendingBeforeBaseline": 0,
        "leased": 0,
        "plotting": 0,
        "printed": 0,
        "failed": 0,
        "skipped": 0,
        "hidden": 0,
        "unknown": 0,
        "runStartedAt": "",
        "message": message,
    }
