from __future__ import annotations

import json
from pathlib import Path

from neje_oracle.app.system_checks import SystemCheckService
from neje_oracle.blocks.gui.support import GuiSettings
from neje_oracle.shared.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings
from neje_oracle.shared.models import SystemCheckLevel, SystemMode


def _plotter_settings(tmp_path: Path) -> PlotterSettings:
    return PlotterSettings(
        db_path=tmp_path / "runtime" / "plotter.sqlite3",
        spool_root=tmp_path / "spool",
        fluidnc_host="localhost",
        tinybee_config_path=tmp_path / "tinybee.json",
        dry_run=True,
    )


def _write_tinybee_config(
    path: Path, *, x_travel: float = 255.0, y_travel: float = 440.0, z_travel: float = 25.0
) -> None:
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
                {"id": "/axes/Z/homing/allow_single_axis", "value": "1"},
                {"id": "/axes/Z/motor0/rc_servo/pwm_hz", "value": "50"},
            ]
        },
    }
    path.write_text(json.dumps(settings), encoding="utf-8")


def test_system_check_marks_real_mode_critical_when_fluidnc_offline(tmp_path: Path) -> None:
    service = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=_plotter_settings(tmp_path),
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(
            project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"
        ),
        fluidnc_checker=lambda timeout: (False, "offline"),
    )

    result = service.run(mode=SystemMode.EXHIBITION, gui_settings=GuiSettings(system_mode=SystemMode.EXHIBITION.value))

    assert result.status == SystemCheckLevel.CRITICAL
    assert any(check.name == "fluidnc" and check.level == SystemCheckLevel.CRITICAL for check in result.checks)


def test_system_check_blocks_test_print_with_offline_fluidnc(tmp_path: Path) -> None:
    service = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=_plotter_settings(tmp_path),
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(
            project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"
        ),
        fluidnc_checker=lambda timeout: (False, "offline"),
    )

    result = service.run(mode=SystemMode.TEST, gui_settings=GuiSettings(system_mode=SystemMode.TEST.value))

    assert any(check.name == "fluidnc" and check.level == SystemCheckLevel.CRITICAL for check in result.checks)


def test_system_check_allows_test_without_firebase_as_warning(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    service = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(
            project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"
        ),
        fluidnc_checker=lambda timeout: (True, "Idle"),
    )

    result = service.run(mode=SystemMode.TEST, gui_settings=GuiSettings(system_mode=SystemMode.TEST.value))

    assert result.status == SystemCheckLevel.WARNING
    assert any(check.name == "firebase config" and check.level == SystemCheckLevel.WARNING for check in result.checks)
    assert not result.has_critical


def test_system_check_blocks_exhibition_without_firebase(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    service = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(
            project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"
        ),
        fluidnc_checker=lambda timeout: (True, "Idle"),
    )

    result = service.run(mode=SystemMode.EXHIBITION, gui_settings=GuiSettings(system_mode=SystemMode.EXHIBITION.value))

    assert result.status == SystemCheckLevel.CRITICAL
    assert any(check.name == "firebase config" and check.level == SystemCheckLevel.CRITICAL for check in result.checks)


def test_system_check_validates_tinybee_hardware_config(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    service = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(
            project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"
        ),
        fluidnc_checker=lambda timeout: (True, "Idle"),
    )

    result = service.run(mode=SystemMode.TEST, gui_settings=GuiSettings(system_mode=SystemMode.TEST.value))

    assert any(check.name == "tinybee hardware" and check.level == SystemCheckLevel.OK for check in result.checks)


def test_system_check_blocks_layout_larger_than_tinybee_travel(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path, x_travel=200.0)
    service = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "runtime" / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions"),
        firebase_settings=FirebaseSettings(
            project_id="", storage_bucket="", credentials_path=tmp_path / "missing.json"
        ),
        fluidnc_checker=lambda timeout: (True, "Idle"),
    )

    result = service.run(
        mode=SystemMode.TEST,
        gui_settings=GuiSettings(system_mode=SystemMode.TEST.value, sheet_width_mm=250.0, sheet_height_mm=440.0),
    )

    assert any(check.name == "tinybee hardware" and check.level == SystemCheckLevel.CRITICAL for check in result.checks)


def test_tinybee_check_counts_work_zero_offset_against_travel(tmp_path: Path) -> None:
    """A 440mm sheet does not fit in 440mm of travel once work zero is at Y5.

    Regression: the check compared sheet size against raw travel and ignored the G54
    offset, so it passed a setup whose G-code reached 443.2mm on a 440mm axis -- i.e.
    straight into the Y limit switch, mid-sheet.
    """
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path, x_travel=255.0, y_travel=440.0)
    gui_settings = GuiSettings(sheet_width_mm=250.0, sheet_height_mm=440.0)

    without_offset = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions", public_root=tmp_path / "public"),
        firebase_settings=FirebaseSettings(),
        work_offset_provider=lambda: None,
    ).run(mode=SystemMode.TEST, gui_settings=gui_settings)
    tinybee = next(c for c in without_offset.checks if c.name == "tinybee hardware")
    assert tinybee.level != SystemCheckLevel.CRITICAL

    with_offset = SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions", public_root=tmp_path / "public"),
        firebase_settings=FirebaseSettings(),
        work_offset_provider=lambda: (5.0, 5.0, 0.0),
    ).run(mode=SystemMode.TEST, gui_settings=gui_settings)
    tinybee = next(c for c in with_offset.checks if c.name == "tinybee hardware")
    assert tinybee.level == SystemCheckLevel.CRITICAL
    assert "usable Y travel" in tinybee.message
    assert "work zero Y5.0" in tinybee.message


def _service(tmp_path: Path, settings: PlotterSettings, **kwargs: object) -> SystemCheckService:
    return SystemCheckService(
        supervisor_settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3"),
        plotter_settings=settings,
        uploader_settings=UploaderSettings(session_root=tmp_path / "sessions", public_root=tmp_path / "public"),
        firebase_settings=FirebaseSettings(),
        **kwargs,  # type: ignore[arg-type]
    )


def test_tinybee_check_fails_when_controller_runs_the_fallback_config(tmp_path: Path) -> None:
    """The snapshot on disk says TinyBee; the controller says otherwise.

    Regression: after a FluidNC panic the board boots "Default (Test Drive)" -- no motor
    pins, no limits, steps_per_mm 80 against the real 40 -- while assets/tinybee.json still
    describes a perfect machine. Preflight validated only the JSON and reported green on a
    board that could not even home (observed live 2026-08-07, HOME ALL -> error:152).
    """
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    gui_settings = GuiSettings(sheet_width_mm=200.0, sheet_height_mm=200.0)

    result = _service(tmp_path, settings, board_identity_provider=lambda: "None").run(
        mode=SystemMode.TEST, gui_settings=gui_settings
    )

    tinybee = next(c for c in result.checks if c.name == "tinybee hardware")
    assert tinybee.level == SystemCheckLevel.CRITICAL
    assert "panicked" in tinybee.message
    assert "power-cycle" in tinybee.message


def test_tinybee_check_passes_when_controller_matches_snapshot(tmp_path: Path) -> None:
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    gui_settings = GuiSettings(sheet_width_mm=200.0, sheet_height_mm=200.0)

    result = _service(tmp_path, settings, board_identity_provider=lambda: "MKS TinyBee V1.0 XXYYZ").run(
        mode=SystemMode.TEST, gui_settings=gui_settings
    )

    tinybee = next(c for c in result.checks if c.name == "tinybee hardware")
    assert tinybee.level != SystemCheckLevel.CRITICAL


def test_tinybee_check_tolerates_unreachable_controller(tmp_path: Path) -> None:
    """An unaskable controller must not fail this check -- the fluidnc check covers offline."""
    settings = _plotter_settings(tmp_path)
    _write_tinybee_config(settings.tinybee_config_path)
    gui_settings = GuiSettings(sheet_width_mm=200.0, sheet_height_mm=200.0)

    result = _service(tmp_path, settings, board_identity_provider=lambda: None).run(
        mode=SystemMode.TEST, gui_settings=gui_settings
    )

    tinybee = next(c for c in result.checks if c.name == "tinybee hardware")
    assert tinybee.level != SystemCheckLevel.CRITICAL
