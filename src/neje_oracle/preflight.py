from __future__ import annotations

import json
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
            self._check_tinybee_hardware(mode, gui_settings),
            self._check_fluidnc(mode),
            self._check_spool_write(),
            self._check_gcode_generation(gui_settings),
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
            return PreflightCheck("local filler fallback", PreflightLevel.WARNING, "No legacy local filler SVGs found; production uses queue jobs or Generate next filler")
        return PreflightCheck("local filler fallback", PreflightLevel.OK, f"{idle_count} legacy local filler SVG(s) available as fallback")

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
        level = PreflightLevel.CRITICAL if mode_policy(mode).firebase_required else PreflightLevel.WARNING
        return PreflightCheck("firebase config", level, "Firebase credentials/project/bucket are not fully configured")

    def _check_tinybee_hardware(self, mode: SystemMode, gui_settings: GuiSettings) -> PreflightCheck:
        config_path = self.plotter_settings.tinybee_config_path
        if not config_path.exists():
            level = PreflightLevel.CRITICAL if mode_policy(mode).real_output_required else PreflightLevel.WARNING
            return PreflightCheck("tinybee hardware", level, f"TinyBee config JSON not found: {config_path}")
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("tinybee hardware", PreflightLevel.CRITICAL, f"TinyBee config JSON is unreadable: {exc}")

        values = _flatten_tinybee_settings(payload)
        problems: list[str] = []
        warnings: list[str] = []

        board = str(values.get("/board", ""))
        if "TinyBee" not in board or "XXYYZ" not in board:
            problems.append(f"unexpected board {board or '<missing>'}; expected MKS TinyBee XXYYZ")
        if values.get("Telnet/Enable") != "1":
            problems.append("Telnet/Enable must be 1")
        telnet_port = _float_value(values.get("Telnet/Port"), 0)
        if int(telnet_port) != self.plotter_settings.fluidnc_telnet_port:
            problems.append(f"Telnet port {int(telnet_port)} does not match sender port {self.plotter_settings.fluidnc_telnet_port}")

        x_travel = _float_value(values.get("/axes/X/max_travel_mm"), 0)
        y_travel = _float_value(values.get("/axes/Y/max_travel_mm"), 0)
        z_travel = _float_value(values.get("/axes/Z/max_travel_mm"), 0)
        if x_travel < gui_settings.sheet_width_mm:
            problems.append(f"sheet width {gui_settings.sheet_width_mm:.1f}mm exceeds X travel {x_travel:.1f}mm")
        if y_travel < gui_settings.sheet_height_mm:
            problems.append(f"sheet height {gui_settings.sheet_height_mm:.1f}mm exceeds Y travel {y_travel:.1f}mm")
        if abs(z_travel - 25.0) > 0.5:
            warnings.append(f"Z travel is {z_travel:.1f}mm; expected 25mm servo travel")
        for axis in ("X", "Y", "Z"):
            if values.get(f"/axes/{axis}/homing/allow_single_axis") != "1":
                problems.append(f"{axis} single-axis homing is disabled")
        if values.get("/axes/Z/motor0/rc_servo/pwm_hz") in {None, ""}:
            problems.append("Z rc_servo config is missing")

        detail = {
            "config_path": str(config_path),
            "board": board,
            "telnet_port": int(telnet_port),
            "x_travel_mm": x_travel,
            "y_travel_mm": y_travel,
            "z_travel_mm": z_travel,
            "problems": problems,
            "warnings": warnings,
        }
        if problems:
            return PreflightCheck("tinybee hardware", PreflightLevel.CRITICAL, "; ".join(problems), detail=detail)
        if warnings:
            return PreflightCheck("tinybee hardware", PreflightLevel.WARNING, "; ".join(warnings), detail=detail)
        return PreflightCheck(
            "tinybee hardware",
            PreflightLevel.OK,
            f"{board}; travel X{x_travel:.0f} Y{y_travel:.0f} Z{z_travel:.0f}; single-axis homing enabled",
            detail=detail,
        )

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
        level = PreflightLevel.CRITICAL if mode_policy(mode).real_output_required else PreflightLevel.WARNING
        return PreflightCheck("fluidnc", level, message, detail=detail)

    def _check_spool_write(self) -> PreflightCheck:
        try:
            ensure_dir(self.plotter_settings.spool_root)
            _assert_writable(self.plotter_settings.spool_root)
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("spool folder", PreflightLevel.CRITICAL, f"Spool folder is not writable: {exc}")
        return PreflightCheck("spool folder", PreflightLevel.OK, f"Spool folder writable: {self.plotter_settings.spool_root}")

    def _check_gcode_generation(self, gui_settings: GuiSettings) -> PreflightCheck:
        try:
            output = generate_dry_run_sheet(gui_settings)
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("g-code generation", PreflightLevel.CRITICAL, f"G-code generation failed: {exc}")
        return PreflightCheck("g-code generation", PreflightLevel.OK, f"Generated {Path(output['gcode']).name}")


def _assert_writable(path: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix=".neje_check_", dir=path, delete=True) as handle:
        handle.write(b"ok")


def _flatten_tinybee_settings(payload: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for section_value in payload.values():
        if not isinstance(section_value, dict):
            continue
        for items in section_value.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = item.get("id")
                if key is None:
                    continue
                values[str(key)] = str(item.get("value", ""))
    return values


def _float_value(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _aggregate_status(checks: list[PreflightCheck]) -> PreflightLevel:
    if any(check.level == PreflightLevel.CRITICAL for check in checks):
        return PreflightLevel.CRITICAL
    if any(check.level == PreflightLevel.WARNING for check in checks):
        return PreflightLevel.WARNING
    return PreflightLevel.OK
