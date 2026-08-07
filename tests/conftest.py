"""Sandbox every machine-writable root before neje_oracle is imported.

`PlotterSettings`/`UploaderSettings`/`OracleSupervisorSettings` read their defaults
via `os.getenv` in dataclass field defaults, which are evaluated once when the class
body executes — i.e. at import time. Setting these here (pytest imports conftest before
any test module, and this file imports nothing from neje_oracle) is what makes the
redirect stick.

Without it the suite writes real G-code into the repo's own `spool/`: a plain
`generate_dry_run_sheet()` with no explicit `spool_root` falls back to
`PlotterSettings().spool_root`. Test runs then leave operational artefacts behind and
mix with genuine print history.

Read-only asset roots (`NEJE_PLOTTER_PLACEHOLDER_ROOT`, tinybee config) are deliberately
NOT redirected — tests need the real bundled symbols.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_SANDBOX = Path(tempfile.mkdtemp(prefix="neje-tests-"))

# Assignment, not setdefault: .env is loaded with setdefault later, so whatever we set
# here wins, and a developer's real .env cannot redirect tests back onto live data.
os.environ["NEJE_PLOTTER_SPOOL_ROOT"] = str(_SANDBOX / "spool")
os.environ["NEJE_PLOTTER_DB_PATH"] = str(_SANDBOX / "runtime" / "plotter.sqlite3")
os.environ["NEJE_UPLOADER_SESSION_ROOT"] = str(_SANDBOX / "sessions_raw")
os.environ["NEJE_UPLOADER_PUBLIC_ROOT"] = str(_SANDBOX / "sessions_public")
os.environ["NEJE_UPLOADER_DB_PATH"] = str(_SANDBOX / "runtime" / "uploader.sqlite3")
os.environ["NEJE_ORACLE_RUNTIME_DB_PATH"] = str(_SANDBOX / "runtime" / "oracle_runtime.sqlite3")
os.environ["NEJE_ORACLE_LOGS_ROOT"] = str(_SANDBOX / "logs")
# save_gui_settings() writes this file. Unsandboxed, any test that persists settings
# overwrites the operator's live machine calibration (sheet size, feeds, Z heights).
os.environ["NEJE_GUI_SETTINGS_PATH"] = str(_SANDBOX / "runtime" / "gui_settings.json")


def pytest_report_header() -> str:
    return f"neje sandbox roots: {_SANDBOX}"
