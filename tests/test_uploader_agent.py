from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from neje_oracle.uploader_agent_service import UploaderAgentController


class FakeUploader:
    def __init__(self) -> None:
        self.scans = 0

    def scan_once(self) -> list[str]:
        self.scans += 1
        return [f"session_{self.scans:03d}"]


@dataclass
class FakeUploaderSettings:
    session_root: Path
    public_root: Path
    poll_seconds: float = 0.01


def test_uploader_agent_scan_once_updates_status(tmp_path: Path) -> None:
    controller = UploaderAgentController(
        FakeUploader(),  # type: ignore[arg-type]
        FakeUploaderSettings(session_root=tmp_path / "sessions", public_root=tmp_path / "public"),  # type: ignore[arg-type]
    )

    result = controller.scan_once()
    status = controller.status()

    assert result["imported"] == ["session_001"]
    assert status["imported_count"] == 1
    assert status["last_imported"] == ["session_001"]
    assert status["running"] is False
