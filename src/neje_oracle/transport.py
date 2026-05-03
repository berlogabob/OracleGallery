from __future__ import annotations

import socket
from pathlib import Path
from typing import Callable

from .config import PlotterSettings, ensure_dir


class FluidNCTransport:
    def __init__(self, settings: PlotterSettings) -> None:
        self.settings = settings
        ensure_dir(settings.spool_root)

    def check_connection(self, *, timeout_seconds: float = 2.0) -> tuple[bool, str]:
        try:
            with socket.create_connection(
                (self.settings.fluidnc_host, self.settings.fluidnc_port),
                timeout=timeout_seconds,
            ):
                return True, f"online: {self.settings.fluidnc_host}:{self.settings.fluidnc_port}"
        except OSError as exc:
            return False, f"offline: {self.settings.fluidnc_host}:{self.settings.fluidnc_port} ({exc})"

    def send(
        self,
        *,
        gcode: str,
        sheet_id: str,
        dry_run: bool | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        gcode_path = self.settings.spool_root / f"{sheet_id}.gcode"
        gcode_path.write_text(gcode, encoding="utf-8")
        lines = gcode.splitlines()
        total_lines = len(lines)

        effective_dry_run = self.settings.dry_run if dry_run is None else dry_run
        if effective_dry_run:
            if progress_callback:
                progress_callback(total_lines, total_lines)
            return gcode_path

        with socket.create_connection((self.settings.fluidnc_host, self.settings.fluidnc_port), timeout=10.0) as conn:
            for index, line in enumerate(lines, start=1):
                conn.sendall((line + "\n").encode("utf-8"))
                if progress_callback and (index == total_lines or index % 10 == 0):
                    progress_callback(index, total_lines)
        return gcode_path
