"""Guard: the suite must never write into the repo's live operational directories."""

from __future__ import annotations

from pathlib import Path

from neje_oracle.blocks.gui.support import default_gui_settings_path
from neje_oracle.shared.config import OracleSupervisorSettings, PlotterSettings, UploaderSettings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_writable_roots_are_sandboxed_away_from_the_repo() -> None:
    """Every writable root must resolve outside the repo (see tests/conftest.py)."""
    plotter, uploader, oracle = PlotterSettings(), UploaderSettings(), OracleSupervisorSettings()
    roots = {
        "plotter.spool_root": plotter.spool_root,
        "plotter.db_path": plotter.db_path,
        "uploader.session_root": uploader.session_root,
        "uploader.public_root": uploader.public_root,
        "uploader.db_path": uploader.db_path,
        "oracle.runtime_db_path": oracle.runtime_db_path,
        "oracle.logs_root": oracle.logs_root,
        "gui.settings_path": default_gui_settings_path(),
    }
    leaked = {
        name: str(path)
        for name, path in roots.items()
        if REPO_ROOT in Path(path).resolve().parents or Path(path).resolve() == REPO_ROOT
    }
    assert not leaked, f"these would write into the working repo during tests: {leaked}"


def test_dry_run_sheet_defaults_do_not_touch_the_repo_spool() -> None:
    """generate_dry_run_sheet() with no spool_root falls back to settings; it must be sandboxed."""
    from neje_oracle.blocks.gcode.dry_run import generate_dry_run_sheet  # noqa: F401

    assert REPO_ROOT not in PlotterSettings().spool_root.resolve().parents
