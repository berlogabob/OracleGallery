from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ensure_parent
from .models import (
    ComponentState,
    ComponentStatus,
    SystemCheckResult,
    PlotterControlState,
    PlotterRuntimeConfig,
    PlotterRuntimeState,
    PlotStatus,
    PlotterReadinessState,
    PublicStatus,
    SessionRecord,
    SystemMode,
)
from .origin_markers import ALL_ORIGINS, normalize_origin


class _SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        ensure_parent(db_path)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            self._connection.commit()
            return cursor

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            return cursor.fetchone()


class UploaderStore(_SQLiteStore):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY,
              source_dir TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              public_status TEXT NOT NULL,
              plot_status TEXT NOT NULL,
              mark_name TEXT NOT NULL,
              oracle_text TEXT NOT NULL,
              themes_json TEXT NOT NULL,
              measures_json TEXT NOT NULL,
              priority TEXT NOT NULL,
              qr_url TEXT NOT NULL,
              public_svg_path TEXT NOT NULL,
              public_receipt_path TEXT NOT NULL,
              public_qr_path TEXT NOT NULL,
              public_manifest_path TEXT NOT NULL,
              public_svg_url TEXT NOT NULL,
              public_receipt_url TEXT NOT NULL,
              public_qr_url TEXT NOT NULL,
              last_error TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        self._ensure_columns(
            "sessions",
            {
                "mark_name": "TEXT NOT NULL DEFAULT ''",
                "oracle_text": "TEXT NOT NULL DEFAULT ''",
                "themes_json": "TEXT NOT NULL DEFAULT '[]'",
                "measures_json": "TEXT NOT NULL DEFAULT '{}'",
                "public_receipt_path": "TEXT NOT NULL DEFAULT ''",
                "public_manifest_path": "TEXT NOT NULL DEFAULT ''",
                "public_receipt_url": "TEXT NOT NULL DEFAULT ''",
            },
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        return self._fetchone("SELECT * FROM sessions WHERE session_id = ?", (session_id,))

    def get_session_by_source(self, source_dir: Path) -> sqlite3.Row | None:
        return self._fetchone("SELECT * FROM sessions WHERE source_dir = ?", (str(source_dir),))

    def upsert_session(self, record: SessionRecord) -> None:
        self._execute(
            """
            INSERT INTO sessions (
              session_id, source_dir, created_at, title, summary, public_status, plot_status,
              mark_name, oracle_text, themes_json, measures_json, priority, qr_url,
              public_svg_path, public_receipt_path, public_qr_path, public_manifest_path,
              public_svg_url, public_receipt_url, public_qr_url, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              source_dir=excluded.source_dir,
              created_at=excluded.created_at,
              title=excluded.title,
              summary=excluded.summary,
              public_status=excluded.public_status,
              plot_status=excluded.plot_status,
              mark_name=excluded.mark_name,
              oracle_text=excluded.oracle_text,
              themes_json=excluded.themes_json,
              measures_json=excluded.measures_json,
              priority=excluded.priority,
              qr_url=excluded.qr_url,
              public_svg_path=excluded.public_svg_path,
              public_receipt_path=excluded.public_receipt_path,
              public_qr_path=excluded.public_qr_path,
              public_manifest_path=excluded.public_manifest_path,
              public_svg_url=excluded.public_svg_url,
              public_receipt_url=excluded.public_receipt_url,
              public_qr_url=excluded.public_qr_url,
              last_error=excluded.last_error,
              updated_at=excluded.updated_at
            """,
            (
                record.session_id,
                str(record.source_dir),
                record.created_at.isoformat(),
                record.title,
                record.summary,
                record.public_status.value,
                record.plot_status.value,
                record.mark_name,
                record.oracle_text,
                json.dumps(record.themes, ensure_ascii=False),
                json.dumps(record.measures, ensure_ascii=False),
                record.priority,
                record.qr_url,
                record.public_svg_path,
                record.public_receipt_path,
                record.public_qr_path,
                record.public_manifest_path,
                record.public_svg_url,
                record.public_receipt_url,
                record.public_qr_url,
                record.last_error,
                datetime.now(tz=UTC).isoformat(),
            ),
        )

    def save_run_started_at(self, value: datetime) -> None:
        self._execute(
            """
            INSERT INTO runtime_state (key, value)
            VALUES ('run_started_at', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (value.isoformat(),),
        )

    def load_run_started_at(self) -> datetime | None:
        row = self._fetchone("SELECT value FROM runtime_state WHERE key = 'run_started_at'")
        if not row:
            return None
        return datetime.fromisoformat(str(row["value"]))

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        with self._lock:
            existing = {
                row["name"]
                for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
        for name, definition in columns.items():
            if name not in existing:
                self._execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


class PlotterStore(_SQLiteStore):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS plot_jobs (
              session_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              sheet_id TEXT NOT NULL,
              error TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )

    def record_job_status(self, session_id: str, status: PlotStatus, sheet_id: str = "", error: str = "") -> None:
        self._execute(
            """
            INSERT INTO plot_jobs (session_id, status, sheet_id, error, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              status=excluded.status,
              sheet_id=excluded.sheet_id,
              error=excluded.error,
              updated_at=excluded.updated_at
            """,
            (session_id, status.value, sheet_id, error, datetime.now(tz=UTC).isoformat()),
        )

    def save_runtime_state(self, state: PlotterRuntimeState) -> None:
        self._execute(
            """
            INSERT INTO runtime_state (key, value)
            VALUES ('plotter', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (json.dumps(state.to_dict()),),
        )

    def save_control_state(self, state: PlotterControlState) -> None:
        self._execute(
            """
            INSERT INTO runtime_state (key, value)
            VALUES ('control', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (json.dumps(state.to_dict()),),
        )

    def load_runtime_state(self) -> PlotterRuntimeState:
        row = self._fetchone("SELECT value FROM runtime_state WHERE key = 'plotter'")
        if not row:
            return PlotterRuntimeState()
        return PlotterRuntimeState.from_dict(json.loads(row["value"]))

    def load_control_state(self) -> PlotterControlState:
        row = self._fetchone("SELECT value FROM runtime_state WHERE key = 'control'")
        if not row:
            return PlotterControlState()
        return PlotterControlState.from_dict(json.loads(row["value"]))


class OracleRuntimeStore(_SQLiteStore):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS oracle_runtime (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS component_state (
              component TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )

    def save_component_state(self, state: ComponentState) -> None:
        self._execute(
            """
            INSERT INTO component_state (component, value)
            VALUES (?, ?)
            ON CONFLICT(component) DO UPDATE SET value=excluded.value
            """,
            (state.component, json.dumps(state.to_dict())),
        )

    def load_component_state(self, component: str) -> ComponentState:
        row = self._fetchone("SELECT value FROM component_state WHERE component = ?", (component,))
        if not row:
            return ComponentState(component=component, status=ComponentStatus.STOPPED)
        return ComponentState.from_dict(json.loads(row["value"]))

    def load_all_component_states(self) -> dict[str, ComponentState]:
        with self._lock:
            rows = self._connection.execute("SELECT component, value FROM component_state").fetchall()
        return {row["component"]: ComponentState.from_dict(json.loads(row["value"])) for row in rows}

    def set_component(
        self,
        component: str,
        status: ComponentStatus,
        *,
        message: str = "",
        last_error: str = "",
        heartbeat: bool = False,
        started: bool = False,
    ) -> ComponentState:
        now = datetime.now(tz=UTC)
        previous = self.load_component_state(component)
        state = ComponentState(
            component=component,
            status=status,
            message=message,
            last_error=last_error,
            heartbeat_at=now if heartbeat else previous.heartbeat_at,
            started_at=now if started else previous.started_at,
            updated_at=now,
        )
        self.save_component_state(state)
        return state

    def save_plotter_config(self, config: PlotterRuntimeConfig) -> None:
        self._execute(
            """
            INSERT INTO oracle_runtime (key, value)
            VALUES ('plotter_config', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (json.dumps(config.to_dict()),),
        )

    def load_plotter_config(self, default: PlotterRuntimeConfig | None = None) -> PlotterRuntimeConfig:
        row = self._fetchone("SELECT value FROM oracle_runtime WHERE key = 'plotter_config'")
        if not row:
            return default or PlotterRuntimeConfig()
        return PlotterRuntimeConfig.from_dict(json.loads(row["value"]))

    def save_origin_filters(
        self,
        *,
        show_origins: list[str] | tuple[str, ...] | set[str],
        print_origins: list[str] | tuple[str, ...] | set[str],
    ) -> None:
        self.save_json(
            "origin_filters",
            {
                "show_origins": _normalized_origin_list(show_origins),
                "print_origins": _normalized_origin_list(print_origins),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
        )

    def load_origin_filters(self) -> dict[str, list[str]]:
        payload = self.load_json(
            "origin_filters",
            {
                "show_origins": list(ALL_ORIGINS),
                "print_origins": list(ALL_ORIGINS),
            },
        )
        return {
            "show_origins": _normalized_origin_list(payload.get("show_origins", ALL_ORIGINS)),
            "print_origins": _normalized_origin_list(payload.get("print_origins", ALL_ORIGINS)),
        }

    def save_print_control(self, state: PlotterControlState) -> None:
        self._execute(
            """
            INSERT INTO oracle_runtime (key, value)
            VALUES ('print_control', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (json.dumps(state.to_dict()),),
        )

    def load_print_control(self, default: PlotterControlState | None = None) -> PlotterControlState:
        row = self._fetchone("SELECT value FROM oracle_runtime WHERE key = 'print_control'")
        if not row:
            return default or PlotterControlState()
        return PlotterControlState.from_dict(json.loads(row["value"]))

    def save_run_started_at(self, value: datetime) -> None:
        self.save_json("run_started_at", {"run_started_at": value.isoformat()})

    def load_run_started_at(self) -> datetime | None:
        payload = self.load_json("run_started_at")
        if not payload.get("run_started_at"):
            return None
        return datetime.fromisoformat(str(payload["run_started_at"]))

    def save_plotter_readiness(self, state: PlotterReadinessState) -> None:
        self.save_json("plotter_readiness", state.to_dict())

    def load_plotter_readiness(self) -> PlotterReadinessState:
        return PlotterReadinessState.from_dict(self.load_json("plotter_readiness"))

    def save_json(self, key: str, payload: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO oracle_runtime (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, json.dumps(payload)),
        )

    def load_json(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        row = self._fetchone("SELECT value FROM oracle_runtime WHERE key = ?", (key,))
        if not row:
            return default or {}
        return dict(json.loads(row["value"]))

    def save_system_mode(self, mode: SystemMode) -> None:
        self.save_json("system_mode", {"mode": mode.value, "updated_at": datetime.now(tz=UTC).isoformat()})

    def load_system_mode(self, default: SystemMode = SystemMode.EXHIBITION) -> SystemMode:
        payload = self.load_json("system_mode", {"mode": default.value})
        return SystemMode(payload.get("mode", default.value))

    def save_system_check_result(self, result: SystemCheckResult) -> None:
        self.save_json("system_check_result", result.to_dict())

    def load_system_check_result(self) -> SystemCheckResult | None:
        payload = self.load_json("system_check_result")
        if not payload:
            return None
        return SystemCheckResult.from_dict(payload)


def _normalized_origin_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        values = ALL_ORIGINS
    result: list[str] = []
    for value in values:
        origin = normalize_origin(value)
        if origin not in result:
            result.append(origin)
    return result or list(ALL_ORIGINS)
