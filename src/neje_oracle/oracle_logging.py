from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import OracleSupervisorSettings, ensure_dir


def default_log_path(settings: OracleSupervisorSettings | None = None) -> Path:
    resolved = settings or OracleSupervisorSettings()
    return resolved.logs_root / "oracle_supervisor.log"


def append_log(
    category: str,
    message: str,
    *,
    level: str = "info",
    settings: OracleSupervisorSettings | None = None,
) -> None:
    path = default_log_path(settings)
    ensure_dir(path.parent)
    timestamp = datetime.now(tz=UTC).isoformat()
    line = f"{timestamp}\t{level.upper()}\t{category}\t{message}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def read_logs(
    *,
    category_filter: str = "all",
    limit: int = 100,
    settings: OracleSupervisorSettings | None = None,
) -> list[str]:
    path = default_log_path(settings)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if category_filter == "errors":
        lines = [line for line in lines if "\tERROR\t" in line or "\tWARNING\t" in line or "\tCRITICAL\t" in line]
    elif category_filter != "all":
        lines = [line for line in lines if f"\t{category_filter}\t" in line]
    return lines[-limit:]
