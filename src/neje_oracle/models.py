from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class PublicStatus(str, Enum):
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class PlotStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    PLOTTING = "plotting"
    PRINTED = "printed"
    FAILED = "failed"


class RuntimeStatus(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing_sheet"
    PRINTING = "printing"
    PAUSED = "paused_for_reload"
    ERROR = "error"


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class SessionRecord:
    session_id: str
    created_at: datetime
    title: str
    summary: str
    source_dir: Path
    svg_file: Path
    preview_file: Path
    qr_file: Path
    qr_url: str
    public_status: PublicStatus
    plot_status: PlotStatus
    priority: str = "user"
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    public_svg_path: str = ""
    public_preview_path: str = ""
    public_qr_path: str = ""
    public_svg_url: str = ""
    public_preview_url: str = ""
    public_qr_url: str = ""
    last_error: str = ""

    def to_manifest_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["source_dir"] = str(self.source_dir)
        payload["svg_file"] = str(self.svg_file)
        payload["preview_file"] = str(self.preview_file)
        payload["qr_file"] = str(self.qr_file)
        payload["public_status"] = self.public_status.value
        payload["plot_status"] = self.plot_status.value
        return payload


@dataclass
class PublicationResult:
    public_status: PublicStatus
    public_svg_path: str = ""
    public_preview_path: str = ""
    public_qr_path: str = ""
    public_svg_url: str = ""
    public_preview_url: str = ""
    public_qr_url: str = ""
    error: str = ""


@dataclass
class PlotJobLease:
    session_id: str
    title: str
    summary: str
    created_at: datetime
    priority: str
    svg_storage_path: str
    svg_url: str
    preview_url: str


@dataclass
class SheetPlacement:
    index: int
    center_x_mm: float
    center_y_mm: float
    diameter_mm: float


@dataclass
class SheetItem:
    source_kind: str
    session_id: str
    title: str
    svg_path: Path
    preview_url: str = ""


@dataclass
class PlotterRuntimeState:
    status: RuntimeStatus = RuntimeStatus.IDLE
    message: str = "Idle"
    current_sheet_id: str = ""
    last_sheet_path: str = ""
    placeholder_index: int = 0
    pending_reload: bool = False
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "current_sheet_id": self.current_sheet_id,
            "last_sheet_path": self.last_sheet_path,
            "placeholder_index": self.placeholder_index,
            "pending_reload": self.pending_reload,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlotterRuntimeState":
        return cls(
            status=RuntimeStatus(payload.get("status", RuntimeStatus.IDLE.value)),
            message=payload.get("message", "Idle"),
            current_sheet_id=payload.get("current_sheet_id", ""),
            last_sheet_path=payload.get("last_sheet_path", ""),
            placeholder_index=int(payload.get("placeholder_index", 0)),
            pending_reload=bool(payload.get("pending_reload", False)),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else utcnow(),
        )


class HealthResponse(BaseModel):
    ok: bool
    status: str
    detail: dict[str, Any]


class ReloadResponse(BaseModel):
    ok: bool
    status: str

