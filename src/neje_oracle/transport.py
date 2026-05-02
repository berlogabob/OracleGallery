from __future__ import annotations

import socket
from pathlib import Path

from .config import PlotterSettings, ensure_dir


class FluidNCTransport:
    def __init__(self, settings: PlotterSettings) -> None:
        self.settings = settings
        ensure_dir(settings.spool_root)

    def send(self, *, gcode: str, sheet_id: str, dry_run: bool | None = None) -> Path:
        gcode_path = self.settings.spool_root / f"{sheet_id}.gcode"
        gcode_path.write_text(gcode, encoding="utf-8")

        effective_dry_run = self.settings.dry_run if dry_run is None else dry_run
        if effective_dry_run:
            return gcode_path

        with socket.create_connection((self.settings.fluidnc_host, self.settings.fluidnc_port), timeout=10.0) as conn:
            for line in gcode.splitlines():
                conn.sendall((line + "\n").encode("utf-8"))
        return gcode_path
