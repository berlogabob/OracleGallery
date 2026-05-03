from __future__ import annotations

from pathlib import Path

from neje_oracle.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings
from neje_oracle.gui_support import GuiSettings
from neje_oracle.models import PreflightLevel, SystemMode
from neje_oracle.preflight import PreflightService


def _plotter_settings(tmp_path: Path) -> PlotterSettings:
    return PlotterSettings(
        db_path=tmp_path / "runtime" / "plotter.sqlite3",
        spool_root=tmp_path / "spool",
        fluidnc_host="localhost",
        dry_run=True,
    )


def test_preflight_marks_real_mode_critical_when_fluidnc_offline(tmp_path: Path) -> None:
    service = PreflightService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=_plotter_settings(tmp_path),
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"),
        fluidnc_checker=lambda timeout: (False, "offline"),
    )

    result = service.run(mode=SystemMode.EXHIBITION_REAL, gui_settings=GuiSettings(system_mode=SystemMode.EXHIBITION_REAL.value))

    assert result.status == PreflightLevel.CRITICAL
    assert any(check.name == "fluidnc" and check.level == PreflightLevel.CRITICAL for check in result.checks)


def test_preflight_allows_test_mode_with_offline_fluidnc_as_warning(tmp_path: Path) -> None:
    service = PreflightService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=_plotter_settings(tmp_path),
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"),
        fluidnc_checker=lambda timeout: (False, "offline"),
    )

    result = service.run(mode=SystemMode.TEST, gui_settings=GuiSettings(system_mode=SystemMode.TEST.value))

    assert any(check.name == "fluidnc" and check.level == PreflightLevel.WARNING for check in result.checks)
