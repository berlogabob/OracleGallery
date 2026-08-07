from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from ..blocks.fluidnc.transport import FluidNCTransport
from ..blocks.gcode.dry_run import generate_dry_run_sheet
from ..shared.config import FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings, ensure_dir
from ..shared.gui_settings import GuiSettings
from ..shared.models import SystemCheck, SystemCheckLevel, SystemCheckResult, SystemMode
from ..shared.modes import mode_policy
from ..shared.symbols import default_idle_root, list_base_symbols


class SystemCheckService:
    def __init__(
        self,
        *,
        supervisor_settings: OracleSupervisorSettings | None = None,
        plotter_settings: PlotterSettings | None = None,
        uploader_settings: UploaderSettings | None = None,
        firebase_settings: FirebaseSettings | None = None,
        fluidnc_checker: Callable[[float], tuple[bool, str]] | None = None,
        work_offset_provider: Callable[[], tuple[float, float, float] | None] | None = None,
        board_identity_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.supervisor_settings = supervisor_settings or OracleSupervisorSettings()
        self.plotter_settings = plotter_settings or PlotterSettings()
        self.uploader_settings = uploader_settings or UploaderSettings()
        self.firebase_settings = firebase_settings or FirebaseSettings()
        self.fluidnc_checker = fluidnc_checker
        self.work_offset_provider = work_offset_provider
        self.board_identity_provider = board_identity_provider

    def run(self, *, mode: SystemMode, gui_settings: GuiSettings) -> SystemCheckResult:
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
        return SystemCheckResult(status=status, checks=checks)

    def _check_runtime_folder(self) -> SystemCheck:
        runtime_root = self.supervisor_settings.runtime_db_path.parent
        try:
            ensure_dir(runtime_root)
            _assert_writable(runtime_root)
        except Exception as exc:  # noqa: BLE001
            return SystemCheck("runtime folder", SystemCheckLevel.CRITICAL, f"Runtime folder is not writable: {exc}")
        return SystemCheck("runtime folder", SystemCheckLevel.OK, f"Runtime folder writable: {runtime_root}")

    def _check_symbols(self) -> SystemCheck:
        symbols = list_base_symbols()
        if not symbols:
            return SystemCheck("base symbols", SystemCheckLevel.CRITICAL, "No base SVG symbols found")
        return SystemCheck("base symbols", SystemCheckLevel.OK, f"{len(symbols)} base symbol(s) available")

    def _check_idle_bank(self) -> SystemCheck:
        idle_root = default_idle_root()
        idle_count = len(list(idle_root.glob("*.svg"))) if idle_root.exists() else 0
        if idle_count <= 0:
            return SystemCheck(
                "local filler fallback",
                SystemCheckLevel.WARNING,
                "No legacy local filler SVGs found; production uses queue jobs or Generate next filler",
            )
        return SystemCheck(
            "local filler fallback",
            SystemCheckLevel.OK,
            f"{idle_count} legacy local filler SVG(s) available as fallback",
        )

    def _check_uploader_folder(self) -> SystemCheck:
        root = self.uploader_settings.session_root
        if not root.exists():
            return SystemCheck(
                "uploader folder", SystemCheckLevel.WARNING, f"Uploader watched folder does not exist yet: {root}"
            )
        if not root.is_dir():
            return SystemCheck("uploader folder", SystemCheckLevel.CRITICAL, f"Uploader path is not a folder: {root}")
        return SystemCheck("uploader folder", SystemCheckLevel.OK, f"Uploader watches {root}")

    def _check_firebase(self, mode: SystemMode) -> SystemCheck:
        if self.firebase_settings.enabled:
            return SystemCheck(
                "firebase config", SystemCheckLevel.OK, f"Firebase configured: {self.firebase_settings.project_id}"
            )
        level = SystemCheckLevel.CRITICAL if mode_policy(mode).firebase_required else SystemCheckLevel.WARNING
        return SystemCheck("firebase config", level, "Firebase credentials/project/bucket are not fully configured")

    def _check_tinybee_hardware(self, mode: SystemMode, gui_settings: GuiSettings) -> SystemCheck:
        config_path = self.plotter_settings.tinybee_config_path
        if not config_path.exists():
            level = SystemCheckLevel.CRITICAL if mode_policy(mode).real_output_required else SystemCheckLevel.WARNING
            return SystemCheck("tinybee hardware", level, f"TinyBee config JSON not found: {config_path}")
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return SystemCheck(
                "tinybee hardware", SystemCheckLevel.CRITICAL, f"TinyBee config JSON is unreadable: {exc}"
            )

        values = _flatten_tinybee_settings(payload)
        problems: list[str] = []
        warnings: list[str] = []

        board = str(values.get("/board", ""))
        if "TinyBee" not in board or "XXYYZ" not in board:
            problems.append(f"unexpected board {board or '<missing>'}; expected MKS TinyBee XXYYZ")

        # Everything above describes the checked-in JSON snapshot -- what the board *should*
        # be. Ask the controller what it is actually running. After a FluidNC panic it boots
        # a built-in fallback config with no motor pins and no limits, while every value in
        # the snapshot still looks perfect. Without this the check reports green on a machine
        # that cannot home.
        live_board = self.board_identity_provider() if self.board_identity_provider is not None else None
        if live_board is not None:
            if "TinyBee" not in live_board or "XXYYZ" not in live_board:
                problems.append(
                    f"controller is running config '{live_board or '<none>'}', not {board or 'the expected board'}; "
                    "FluidNC has most likely panicked into its built-in default -- power-cycle the board and "
                    "confirm $CD reports the real board before printing"
                )
            elif board and live_board != board:
                warnings.append(f"controller board '{live_board}' differs from {config_path.name} '{board}'")
        if values.get("Telnet/Enable") != "1":
            problems.append("Telnet/Enable must be 1")
        telnet_port = _float_value(values.get("Telnet/Port"), 0)
        if int(telnet_port) != self.plotter_settings.fluidnc_telnet_port:
            problems.append(
                f"Telnet port {int(telnet_port)} does not match sender port {self.plotter_settings.fluidnc_telnet_port}"
            )

        x_travel = _float_value(values.get("/axes/X/max_travel_mm"), 0)
        y_travel = _float_value(values.get("/axes/Y/max_travel_mm"), 0)
        z_travel = _float_value(values.get("/axes/Z/max_travel_mm"), 0)
        # Work zero consumes travel: a sheet starting at G54 (5, 5) has 5mm less room on
        # each axis. Comparing sheet size against raw travel passed a setup that would
        # have driven past the Y limit switch mid-sheet.
        offset_x, offset_y = 0.0, 0.0
        if self.work_offset_provider is not None:
            work_offset = self.work_offset_provider()
            if work_offset is not None:
                offset_x, offset_y = max(0.0, work_offset[0]), max(0.0, work_offset[1])
        usable_x = x_travel - offset_x
        usable_y = y_travel - offset_y
        offset_note_x = f" from work zero X{offset_x:.1f}" if offset_x else ""
        offset_note_y = f" from work zero Y{offset_y:.1f}" if offset_y else ""
        if usable_x < gui_settings.sheet_width_mm:
            problems.append(
                f"sheet width {gui_settings.sheet_width_mm:.1f}mm exceeds "
                f"{usable_x:.1f}mm of usable X travel{offset_note_x}"
            )
        if usable_y < gui_settings.sheet_height_mm:
            problems.append(
                f"sheet height {gui_settings.sheet_height_mm:.1f}mm exceeds "
                f"{usable_y:.1f}mm of usable Y travel{offset_note_y}"
            )
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
            return SystemCheck("tinybee hardware", SystemCheckLevel.CRITICAL, "; ".join(problems), detail=detail)
        if warnings:
            return SystemCheck("tinybee hardware", SystemCheckLevel.WARNING, "; ".join(warnings), detail=detail)
        return SystemCheck(
            "tinybee hardware",
            SystemCheckLevel.OK,
            f"{board}; travel X{x_travel:.0f} Y{y_travel:.0f} Z{z_travel:.0f}; single-axis homing enabled",
            detail=detail,
        )

    def _check_fluidnc(self, mode: SystemMode) -> SystemCheck:
        if self.fluidnc_checker is not None:
            online, message = self.fluidnc_checker(1.5)
            detail = {}
        else:
            probe = FluidNCTransport(self.plotter_settings).probe(
                timeout_seconds=self.plotter_settings.fluidnc_connect_timeout_seconds
            )
            online = probe.online and probe.controller.is_idle
            message = probe.message
            detail = probe.to_dict()
            if probe.online and not probe.controller.is_idle:
                message = f"{probe.message}; controller must be Idle for real print"
        if online:
            return SystemCheck("fluidnc", SystemCheckLevel.OK, message, detail=detail)
        level = SystemCheckLevel.CRITICAL if mode_policy(mode).real_output_required else SystemCheckLevel.WARNING
        return SystemCheck("fluidnc", level, message, detail=detail)

    def _check_spool_write(self) -> SystemCheck:
        try:
            ensure_dir(self.plotter_settings.spool_root)
            _assert_writable(self.plotter_settings.spool_root)
        except Exception as exc:  # noqa: BLE001
            return SystemCheck("spool folder", SystemCheckLevel.CRITICAL, f"Spool folder is not writable: {exc}")
        return SystemCheck(
            "spool folder", SystemCheckLevel.OK, f"Spool folder writable: {self.plotter_settings.spool_root}"
        )

    def _check_gcode_generation(self, gui_settings: GuiSettings) -> SystemCheck:
        try:
            output = generate_dry_run_sheet(gui_settings)
        except Exception as exc:  # noqa: BLE001
            return SystemCheck("g-code generation", SystemCheckLevel.CRITICAL, f"G-code generation failed: {exc}")
        return SystemCheck("g-code generation", SystemCheckLevel.OK, f"Generated {Path(output['gcode']).name}")


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


def _aggregate_status(checks: list[SystemCheck]) -> SystemCheckLevel:
    if any(check.level == SystemCheckLevel.CRITICAL for check in checks):
        return SystemCheckLevel.CRITICAL
    if any(check.level == SystemCheckLevel.WARNING for check in checks):
        return SystemCheckLevel.WARNING
    return SystemCheckLevel.OK
