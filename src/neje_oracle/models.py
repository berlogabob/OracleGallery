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
    OPERATOR_PAUSED = "operator_paused"
    ERROR = "error"


class ComponentStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    OFFLINE = "offline"
    WARNING = "warning"
    ERROR = "error"


class SystemMode(str, Enum):
    TEST = "test"
    EXHIBITION_DRY = "exhibition_dry"
    EXHIBITION_REAL = "exhibition_real"


class PreflightLevel(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


class FluidNCState(str, Enum):
    IDLE = "Idle"
    RUN = "Run"
    HOLD = "Hold"
    ALARM = "Alarm"
    SLEEP = "Sleep"
    DOOR = "Door"
    JOG = "Jog"
    UNKNOWN = "Unknown"


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
    receipt_file: Path
    qr_file: Path
    qr_url: str
    public_status: PublicStatus
    plot_status: PlotStatus
    mark_name: str = ""
    oracle_text: str = ""
    themes: list[str] = field(default_factory=list)
    measures: dict[str, float] = field(default_factory=dict)
    priority: str = "user"
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    public_svg_path: str = ""
    public_receipt_path: str = ""
    public_qr_path: str = ""
    public_manifest_path: str = ""
    public_svg_url: str = ""
    public_receipt_url: str = ""
    public_qr_url: str = ""
    last_error: str = ""

    def to_manifest_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["source_dir"] = str(self.source_dir)
        payload["svg_file"] = str(self.svg_file)
        payload["receipt_file"] = str(self.receipt_file)
        payload["qr_file"] = str(self.qr_file)
        payload["public_status"] = self.public_status.value
        payload["plot_status"] = self.plot_status.value
        return payload


@dataclass
class PublicationResult:
    public_status: PublicStatus
    public_svg_path: str = ""
    public_receipt_path: str = ""
    public_qr_path: str = ""
    public_manifest_path: str = ""
    public_svg_url: str = ""
    public_receipt_url: str = ""
    public_qr_url: str = ""
    error: str = ""


@dataclass
class PlotJobLease:
    session_id: str
    title: str
    summary: str
    created_at: datetime
    priority: str
    queue: str
    svg_storage_path: str
    svg_url: str


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


@dataclass
class PlotterRuntimeState:
    status: RuntimeStatus = RuntimeStatus.IDLE
    message: str = "Idle"
    current_sheet_id: str = ""
    last_sheet_path: str = ""
    placeholder_index: int = 0
    pending_reload: bool = False
    gcode_lines_sent: int = 0
    gcode_lines_total: int = 0
    gcode_progress_percent: float = 0.0
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "current_sheet_id": self.current_sheet_id,
            "last_sheet_path": self.last_sheet_path,
            "placeholder_index": self.placeholder_index,
            "pending_reload": self.pending_reload,
            "gcode_lines_sent": self.gcode_lines_sent,
            "gcode_lines_total": self.gcode_lines_total,
            "gcode_progress_percent": self.gcode_progress_percent,
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
            gcode_lines_sent=int(payload.get("gcode_lines_sent", 0)),
            gcode_lines_total=int(payload.get("gcode_lines_total", 0)),
            gcode_progress_percent=float(payload.get("gcode_progress_percent", 0.0)),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else utcnow(),
        )


@dataclass
class PlotterControlState:
    print_enabled: bool = False
    operator_paused: bool = True
    run_mode: str = "exhibition"
    dry_run: bool = True
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "print_enabled": self.print_enabled,
            "operator_paused": self.operator_paused,
            "run_mode": self.run_mode,
            "dry_run": self.dry_run,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlotterControlState":
        return cls(
            print_enabled=bool(payload.get("print_enabled", False)),
            operator_paused=bool(payload.get("operator_paused", True)),
            run_mode=str(payload.get("run_mode", "exhibition")),
            dry_run=bool(payload.get("dry_run", True)),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else utcnow(),
        )


@dataclass
class ComponentState:
    component: str
    status: ComponentStatus = ComponentStatus.STOPPED
    message: str = ""
    last_error: str = ""
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "last_error": self.last_error,
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else "",
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ComponentState":
        return cls(
            component=str(payload.get("component", "")),
            status=ComponentStatus(payload.get("status", ComponentStatus.STOPPED.value)),
            message=str(payload.get("message", "")),
            last_error=str(payload.get("last_error", "")),
            heartbeat_at=_optional_datetime(payload.get("heartbeat_at")),
            started_at=_optional_datetime(payload.get("started_at")),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else utcnow(),
        )


@dataclass
class FluidNCControllerState:
    state: FluidNCState = FluidNCState.UNKNOWN
    machine_position: tuple[float, float, float] | None = None
    feed_rate: float | None = None
    spindle_speed: float | None = None
    overrides: tuple[int, int, int] | None = None
    raw_status: str = ""
    modal_state: str = ""

    @property
    def is_idle(self) -> bool:
        return self.state == FluidNCState.IDLE

    @property
    def is_alarm(self) -> bool:
        return self.state == FluidNCState.ALARM

    @property
    def is_hold(self) -> bool:
        return self.state == FluidNCState.HOLD


@dataclass
class FluidNCProbeResult:
    http_online: bool = False
    telnet_online: bool = False
    ok: bool = False
    message: str = ""
    http_url: str = ""
    telnet_host: str = ""
    telnet_port: int = 23
    controller: FluidNCControllerState = field(default_factory=FluidNCControllerState)
    last_response: str = ""
    last_error: str = ""

    @property
    def online(self) -> bool:
        return self.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_online": self.http_online,
            "telnet_online": self.telnet_online,
            "ok": self.ok,
            "message": self.message,
            "http_url": self.http_url,
            "telnet_host": self.telnet_host,
            "telnet_port": self.telnet_port,
            "controller_state": self.controller.state.value,
            "machine_position": self.controller.machine_position,
            "feed_rate": self.controller.feed_rate,
            "spindle_speed": self.controller.spindle_speed,
            "overrides": self.controller.overrides,
            "raw_status": self.controller.raw_status,
            "modal_state": self.controller.modal_state,
            "last_response": self.last_response,
            "last_error": self.last_error,
        }


@dataclass
class FluidNCCommandResult:
    ok: bool
    command: str
    response_lines: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def message(self) -> str:
        if self.ok:
            return "\n".join(self.response_lines) or "ok"
        return self.error or "\n".join(self.response_lines) or "failed"


@dataclass
class PlotterRuntimeConfig:
    layout_mode: str = "hex"
    sheet_width_mm: float = 250.0
    sheet_height_mm: float = 440.0
    sheet_margin_mm: float = 0.0
    cell_diameter_mm: float = 80.0
    gap_mm: float = 0.0
    run_mode: str = "exhibition"
    dry_run: bool = True
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_mode": self.layout_mode,
            "sheet_width_mm": self.sheet_width_mm,
            "sheet_height_mm": self.sheet_height_mm,
            "sheet_margin_mm": self.sheet_margin_mm,
            "cell_diameter_mm": self.cell_diameter_mm,
            "gap_mm": self.gap_mm,
            "run_mode": self.run_mode,
            "dry_run": self.dry_run,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlotterRuntimeConfig":
        return cls(
            layout_mode=str(payload.get("layout_mode", "hex")),
            sheet_width_mm=float(payload.get("sheet_width_mm", 250.0)),
            sheet_height_mm=float(payload.get("sheet_height_mm", 440.0)),
            sheet_margin_mm=float(payload.get("sheet_margin_mm", 0.0)),
            cell_diameter_mm=float(payload.get("cell_diameter_mm", 80.0)),
            gap_mm=float(payload.get("gap_mm", 0.0)),
            run_mode=str(payload.get("run_mode", "exhibition")),
            dry_run=bool(payload.get("dry_run", True)),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else utcnow(),
        )


@dataclass
class PreflightCheck:
    name: str
    level: PreflightLevel
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "message": self.message,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreflightCheck":
        return cls(
            name=str(payload.get("name", "")),
            level=PreflightLevel(payload.get("level", PreflightLevel.WARNING.value)),
            message=str(payload.get("message", "")),
            detail=dict(payload.get("detail", {})),
        )


@dataclass
class PreflightResult:
    status: PreflightLevel
    checks: list[PreflightCheck]
    generated_at: datetime = field(default_factory=utcnow)

    @property
    def has_critical(self) -> bool:
        return any(check.level == PreflightLevel.CRITICAL for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreflightResult":
        checks = [PreflightCheck.from_dict(item) for item in payload.get("checks", [])]
        return cls(
            status=PreflightLevel(payload.get("status", PreflightLevel.WARNING.value)),
            checks=checks,
            generated_at=datetime.fromisoformat(payload["generated_at"])
            if payload.get("generated_at")
            else utcnow(),
        )


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))


class HealthResponse(BaseModel):
    ok: bool
    status: str
    detail: dict[str, Any]


class ReloadResponse(BaseModel):
    ok: bool
    status: str
