from __future__ import annotations

import json
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
        tinybee_config_path=tmp_path / "tinybee.json",
        dry_run=True,
    )


def _write_tinybee_config(path: Path, *, x_travel: float = 255.0, y_travel: float = 440.0, z_travel: float = 25.0) -> None:
    settings = {
        "Flash": {
            "Settings": [
                {"id": "Telnet/Enable", "value": "1"},
                {"id": "Telnet/Port", "value": "23"},
            ]
        },
        "Running": {
            "Config": [
                {"id": "/board", "value": "MKS TinyBee V1.0 XXYYZ"},
                {"id": "/axes/X/max_travel_mm", "value": f"{x_travel:.3f}"},
                {"id": "/axes/Y/max_travel_mm", "value": f"{y_travel:.3f}"},
                {"id": "/axes/Z/max_travel_mm", "value": f"{z_travel:.3f}"},
                {"id": "/axes/X/homing/allow_single_axis", "value": "1"},
                {"id": "/axes/Y/homing/allow_single_axis", "value": "1"},
                {"id": "/axes/Z/motor0/rc_servo/pwm_hz", "value": "50"},
            ]
        },
    }
    path.write_text(json.dumps(settings), encoding="utf-8")


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


def test_preflight_validates_tinybee_hardware_config(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    service = PreflightService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"),
        fluidnc_checker=lambda timeout: (True, "Idle"),
    )

    result = service.run(mode=SystemMode.TEST, gui_settings=GuiSettings(system_mode=SystemMode.TEST.value))

    assert any(check.name == "tinybee hardware" and check.level == PreflightLevel.OK for check in result.checks)


def test_preflight_blocks_layout_larger_than_tinybee_travel(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path, x_travel=200.0)
    service = PreflightService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"),
        fluidnc_checker=lambda timeout: (True, "Idle"),
    )

    result = service.run(
        mode=SystemMode.TEST,
        gui_settings=GuiSettings(system_mode=SystemMode.TEST.value, sheet_width_mm=250.0, sheet_height_mm=440.0),
    )

    assert any(check.name == "tinybee hardware" and check.level == PreflightLevel.CRITICAL for check in result.checks)
