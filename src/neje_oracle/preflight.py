from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from .config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings, ensure_dir
from .gui_modes import mode_policy
from .gui_support import GuiSettings, default_idle_root, generate_dry_run_sheet, list_base_symbols
from .models import PreflightCheck, PreflightLevel, PreflightResult, SystemMode
from .transport import FluidNCTransport


class PreflightService:
    def __init__(
        self,
        *,
        supervisor_settings: OracleSupervisorSettings | None = None,
        plotter_settings: PlotterSettings | None = None,
        uploader_settings: UploaderSettings | None = None,
        firebase_settings: FirebaseSettings | None = None,
        fluidnc_checker: Callable[[float], tuple[bool, str]] | None = None,
    ) -> None:
        self.supervisor_settings = supervisor_settings or OracleSupervisorSettings()
        self.plotter_settings = plotter_settings or PlotterSettings()
        self.uploader_settings = uploader_settings or UploaderSettings()
        self.firebase_settings = firebase_settings or FirebaseSettings()
        self.fluidnc_checker = fluidnc_checker

    def run(self, *, mode: SystemMode, gui_settings: GuiSettings) -> PreflightResult:
        checks = [
            self._check_runtime_folder(),
            self._check_symbols(),
            self._check_idle_bank(),
            self._check_uploader_folder(),
            self._check_firebase(mode),
            self._check_fluidnc(mode),
            self._check_spool_write(),
            self._check_dry_run_generation(gui_settings),
        ]
        status = _aggregate_status(checks)
        return PreflightResult(status=status, checks=checks)

    def _check_runtime_folder(self) -> PreflightCheck:
        runtime_root = self.supervisor_settings.runtime_db_path.parent
        try:
            ensure_dir(runtime_root)
            _assert_writable(runtime_root)
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("runtime folder", PreflightLevel.CRITICAL, f"Runtime folder is not writable: {exc}")
        return PreflightCheck("runtime folder", PreflightLevel.OK, f"Runtime folder writable: {runtime_root}")

    def _check_symbols(self) -> PreflightCheck:
        symbols = list_base_symbols()
        if not symbols:
            return PreflightCheck("base symbols", PreflightLevel.CRITICAL, "No base SVG symbols found")
        return PreflightCheck("base symbols", PreflightLevel.OK, f"{len(symbols)} base symbol(s) available")

    def _check_idle_bank(self) -> PreflightCheck:
        idle_root = default_idle_root()
        idle_count = len(list(idle_root.glob("*.svg"))) if idle_root.exists() else 0
        if idle_count <= 0:
            return PreflightCheck("idle bank", PreflightLevel.WARNING, "Generated idle bank is empty; plotter can fall back to base symbols")
        return PreflightCheck("idle bank", PreflightLevel.OK, f"{idle_count} generated idle SVG(s) available")

    def _check_uploader_folder(self) -> PreflightCheck:
        root = self.uploader_settings.session_root
        if not root.exists():
            return PreflightCheck("uploader folder", PreflightLevel.WARNING, f"Uploader watched folder does not exist yet: {root}")
        if not root.is_dir():
            return PreflightCheck("uploader folder", PreflightLevel.CRITICAL, f"Uploader path is not a folder: {root}")
        return PreflightCheck("uploader folder", PreflightLevel.OK, f"Uploader watches {root}")

    def _check_firebase(self, mode: SystemMode) -> PreflightCheck:
        if self.firebase_settings.enabled:
            return PreflightCheck("firebase config", PreflightLevel.OK, f"Firebase configured: {self.firebase_settings.project_id}")
        level = PreflightLevel.WARNING if mode == SystemMode.TEST else PreflightLevel.CRITICAL
        return PreflightCheck("firebase config", level, "Firebase credentials/project/bucket are not fully configured")

    def _check_fluidnc(self, mode: SystemMode) -> PreflightCheck:
        if self.fluidnc_checker is not None:
            online, message = self.fluidnc_checker(1.5)
            detail = {}
        else:
            probe = FluidNCTransport(self.plotter_settings).probe(timeout_seconds=self.plotter_settings.fluidnc_connect_timeout_seconds)
            online = probe.online and probe.controller.is_idle
            message = probe.message
            detail = probe.to_dict()
            if probe.online and not probe.controller.is_idle:
                message = f"{probe.message}; controller must be Idle for real print"
        if online:
            return PreflightCheck("fluidnc", PreflightLevel.OK, message, detail=detail)
        level = PreflightLevel.CRITICAL if mode_policy(mode).real_fluidnc_required else PreflightLevel.WARNING
        return PreflightCheck("fluidnc", level, message, detail=detail)

    def _check_spool_write(self) -> PreflightCheck:
        try:
            ensure_dir(self.plotter_settings.spool_root)
            _assert_writable(self.plotter_settings.spool_root)
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("spool folder", PreflightLevel.CRITICAL, f"Spool folder is not writable: {exc}")
        return PreflightCheck("spool folder", PreflightLevel.OK, f"Spool folder writable: {self.plotter_settings.spool_root}")

    def _check_dry_run_generation(self, gui_settings: GuiSettings) -> PreflightCheck:
        try:
            output = generate_dry_run_sheet(gui_settings)
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("dry-run sheet", PreflightLevel.CRITICAL, f"Dry-run sheet failed: {exc}")
        return PreflightCheck("dry-run sheet", PreflightLevel.OK, f"Generated {Path(output['gcode']).name}")


def _assert_writable(path: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix=".neje_check_", dir=path, delete=True) as handle:
        handle.write(b"ok")


def _aggregate_status(checks: list[PreflightCheck]) -> PreflightLevel:
    if any(check.level == PreflightLevel.CRITICAL for check in checks):
        return PreflightLevel.CRITICAL
    if any(check.level == PreflightLevel.WARNING for check in checks):
        return PreflightLevel.WARNING
    return PreflightLevel.OK
