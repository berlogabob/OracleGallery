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
    SKIPPED = "skipped"


class RuntimeStatus(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing_sheet"
    PRINTING = "printing"
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
    EXHIBITION = "exhibition"

    @classmethod
    def _missing_(cls, value: object) -> SystemMode | None:
        if str(value) in {"exhibition_dry", "exhibition_real"}:
            return cls.EXHIBITION
        return None


class SystemCheckLevel(str, Enum):
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
        payload["sessionUrl"] = self.qr_url
        payload["qrImageUrl"] = self.public_qr_url
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
    origin: str = "unknown"
    tags: list[str] = field(default_factory=list)
    visible_in_queue: bool = True


@dataclass
class SheetPlacement:
    index: int
    center_x_mm: float
    center_y_mm: float
    diameter_mm: float
    rotation_deg: float = 0.0
    symbol_scale: float = 1.0
    row_y_mm: float | None = None


@dataclass
class SheetItem:
    source_kind: str
    session_id: str
    title: str
    svg_path: Path
    origin: str = "unknown"
    tags: list[str] = field(default_factory=list)
    marker_position: str = ""


@dataclass
class PlotterRuntimeState:
    status: RuntimeStatus = RuntimeStatus.IDLE
    message: str = "Idle"
    current_sheet_id: str = ""
    last_sheet_path: str = ""
    placeholder_index: int = 0
    gcode_lines_sent: int = 0
    gcode_lines_total: int = 0
    gcode_progress_percent: float = 0.0
    current_row_index: int = 0
    row_count: int = 0
    current_cell_index: int = 0
    current_cell_in_row: int = 0
    row_cell_count: int = 0
    cells_completed: int = 0
    rows_completed: int = 0
    sheet_progress_percent: float = 0.0
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "current_sheet_id": self.current_sheet_id,
            "last_sheet_path": self.last_sheet_path,
            "placeholder_index": self.placeholder_index,
            "gcode_lines_sent": self.gcode_lines_sent,
            "gcode_lines_total": self.gcode_lines_total,
            "gcode_progress_percent": self.gcode_progress_percent,
            "current_row_index": self.current_row_index,
            "row_count": self.row_count,
            "current_cell_index": self.current_cell_index,
            "current_cell_in_row": self.current_cell_in_row,
            "row_cell_count": self.row_cell_count,
            "cells_completed": self.cells_completed,
            "rows_completed": self.rows_completed,
            "sheet_progress_percent": self.sheet_progress_percent,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PlotterRuntimeState:
        raw_status = payload.get("status", RuntimeStatus.IDLE.value)
        try:
            status = RuntimeStatus(raw_status)
        except ValueError:
            status = RuntimeStatus.OPERATOR_PAUSED
        return cls(
            status=status,
            message=payload.get("message", "Idle"),
            current_sheet_id=payload.get("current_sheet_id", ""),
            last_sheet_path=payload.get("last_sheet_path", ""),
            placeholder_index=int(payload.get("placeholder_index", 0)),
            gcode_lines_sent=int(payload.get("gcode_lines_sent", 0)),
            gcode_lines_total=int(payload.get("gcode_lines_total", 0)),
            gcode_progress_percent=float(payload.get("gcode_progress_percent", 0.0)),
            current_row_index=int(payload.get("current_row_index", 0)),
            row_count=int(payload.get("row_count", 0)),
            current_cell_index=int(payload.get("current_cell_index", 0)),
            current_cell_in_row=int(payload.get("current_cell_in_row", 0)),
            row_cell_count=int(payload.get("row_cell_count", 0)),
            cells_completed=int(payload.get("cells_completed", 0)),
            rows_completed=int(payload.get("rows_completed", 0)),
            sheet_progress_percent=float(payload.get("sheet_progress_percent", 0.0)),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else utcnow(),
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
    def from_dict(cls, payload: dict[str, Any]) -> PlotterControlState:
        return cls(
            print_enabled=bool(payload.get("print_enabled", False)),
            operator_paused=bool(payload.get("operator_paused", True)),
            run_mode=str(payload.get("run_mode", "exhibition")),
            dry_run=bool(payload.get("dry_run", True)),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else utcnow(),
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
    def from_dict(cls, payload: dict[str, Any]) -> ComponentState:
        return cls(
            component=str(payload.get("component", "")),
            status=ComponentStatus(payload.get("status", ComponentStatus.STOPPED.value)),
            message=str(payload.get("message", "")),
            last_error=str(payload.get("last_error", "")),
            heartbeat_at=_optional_datetime(payload.get("heartbeat_at")),
            started_at=_optional_datetime(payload.get("started_at")),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else utcnow(),
        )


@dataclass
class FluidNCControllerState:
    state: FluidNCState = FluidNCState.UNKNOWN
    machine_position: tuple[float, float, float] | None = None
    feed_rate: float | None = None
    spindle_speed: float | None = None
    overrides: tuple[int, int, int] | None = None
    pins: str = ""
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
            "pins": self.controller.pins,
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
    organic_enabled: bool = False
    organic_cell_size_mm: float = 18.0
    organic_rotation_ramp: float = 0.0
    organic_scale_ramp: float = 0.0
    organic_seed: int = 1007
    run_mode: str = "exhibition"
    dry_run: bool = True
    include_rings: bool = True
    include_markers: bool = True
    marker_diameter_mm: float = 1.5
    travel_rate: float = 5000.0
    draw_rate: float = 1800.0
    xy_acceleration_mm_s2: float = 1000.0
    use_z_servo: bool = True
    z_down_mm: float = -25.0
    z_up_mm: float = 0.0
    z_feed_mm_min: float = 1000.0
    work_zero_command: str = "G10 L20 P1 X0 Y0"
    # G-code optimisation
    sample_step_mm: float = 1.0
    sample_reference_cell_mm: float = 80.0
    sample_density_exponent: float = 1.0
    sample_min_step_mm: float = 0.25
    sample_max_step_mm: float = 3.0
    streaming_mode: str = "row"
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_mode": self.layout_mode,
            "sheet_width_mm": self.sheet_width_mm,
            "sheet_height_mm": self.sheet_height_mm,
            "sheet_margin_mm": self.sheet_margin_mm,
            "cell_diameter_mm": self.cell_diameter_mm,
            "gap_mm": self.gap_mm,
            "organic_enabled": self.organic_enabled,
            "organic_cell_size_mm": self.organic_cell_size_mm,
            "organic_rotation_ramp": self.organic_rotation_ramp,
            "organic_scale_ramp": self.organic_scale_ramp,
            "organic_seed": self.organic_seed,
            "run_mode": self.run_mode,
            "dry_run": self.dry_run,
            "include_rings": self.include_rings,
            "include_markers": self.include_markers,
            "marker_diameter_mm": self.marker_diameter_mm,
            "travel_rate": self.travel_rate,
            "draw_rate": self.draw_rate,
            "xy_acceleration_mm_s2": self.xy_acceleration_mm_s2,
            "use_z_servo": self.use_z_servo,
            "z_down_mm": self.z_down_mm,
            "z_up_mm": self.z_up_mm,
            "z_feed_mm_min": self.z_feed_mm_min,
            "work_zero_command": self.work_zero_command,
            "sample_step_mm": self.sample_step_mm,
            "sample_reference_cell_mm": self.sample_reference_cell_mm,
            "sample_density_exponent": self.sample_density_exponent,
            "sample_min_step_mm": self.sample_min_step_mm,
            "sample_max_step_mm": self.sample_max_step_mm,
            "streaming_mode": self.streaming_mode,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PlotterRuntimeConfig:
        return cls(
            layout_mode=str(payload.get("layout_mode", "hex")),
            sheet_width_mm=float(payload.get("sheet_width_mm", 250.0)),
            sheet_height_mm=float(payload.get("sheet_height_mm", 440.0)),
            sheet_margin_mm=float(payload.get("sheet_margin_mm", 0.0)),
            cell_diameter_mm=float(payload.get("cell_diameter_mm", 80.0)),
            gap_mm=float(payload.get("gap_mm", 0.0)),
            organic_enabled=bool(payload.get("organic_enabled", False)),
            organic_cell_size_mm=float(payload.get("organic_cell_size_mm", 18.0)),
            organic_rotation_ramp=float(payload.get("organic_rotation_ramp", 0.0)),
            organic_scale_ramp=float(payload.get("organic_scale_ramp", 0.0)),
            organic_seed=int(payload.get("organic_seed", 1007)),
            run_mode=str(payload.get("run_mode", "exhibition")),
            dry_run=bool(payload.get("dry_run", True)),
            include_rings=bool(payload.get("include_rings", True)),
            include_markers=bool(payload.get("include_markers", True)),
            marker_diameter_mm=float(payload.get("marker_diameter_mm", 1.5)),
            travel_rate=float(payload.get("travel_rate", 5000.0)),
            draw_rate=float(payload.get("draw_rate", 1800.0)),
            xy_acceleration_mm_s2=float(payload.get("xy_acceleration_mm_s2", 1000.0)),
            use_z_servo=bool(payload.get("use_z_servo", True)),
            z_down_mm=float(payload.get("z_down_mm", -25.0)),
            z_up_mm=float(payload.get("z_up_mm", 0.0)),
            z_feed_mm_min=float(payload.get("z_feed_mm_min", 1000.0)),
            work_zero_command=str(payload.get("work_zero_command", "G10 L20 P1 X0 Y0")),
            sample_step_mm=float(payload.get("sample_step_mm", 1.0)),
            sample_reference_cell_mm=float(payload.get("sample_reference_cell_mm", 80.0)),
            sample_density_exponent=float(payload.get("sample_density_exponent", 1.0)),
            sample_min_step_mm=float(payload.get("sample_min_step_mm", 0.25)),
            sample_max_step_mm=float(payload.get("sample_max_step_mm", 3.0)),
            streaming_mode=str(payload.get("streaming_mode", "row")),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else utcnow(),
        )


@dataclass
class PlotterReadinessState:
    work_zero_set: bool = False
    plotter_ready: bool = False
    message: str = "Not ready"
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_zero_set": self.work_zero_set,
            "plotter_ready": self.plotter_ready,
            "message": self.message,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PlotterReadinessState:
        return cls(
            work_zero_set=bool(payload.get("work_zero_set", False)),
            plotter_ready=bool(payload.get("plotter_ready", False)),
            message=str(payload.get("message", "Not ready")),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else utcnow(),
        )


@dataclass
class SystemCheck:
    name: str
    level: SystemCheckLevel
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
    def from_dict(cls, payload: dict[str, Any]) -> SystemCheck:
        return cls(
            name=str(payload.get("name", "")),
            level=SystemCheckLevel(payload.get("level", SystemCheckLevel.WARNING.value)),
            message=str(payload.get("message", "")),
            detail=dict(payload.get("detail", {})),
        )


@dataclass
class SystemCheckResult:
    status: SystemCheckLevel
    checks: list[SystemCheck]
    generated_at: datetime = field(default_factory=utcnow)

    @property
    def has_critical(self) -> bool:
        return any(check.level == SystemCheckLevel.CRITICAL for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SystemCheckResult:
        checks = [SystemCheck.from_dict(item) for item in payload.get("checks", [])]
        return cls(
            status=SystemCheckLevel(payload.get("status", SystemCheckLevel.WARNING.value)),
            checks=checks,
            generated_at=datetime.fromisoformat(payload["generated_at"]) if payload.get("generated_at") else utcnow(),
        )


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))


class HealthResponse(BaseModel):
    ok: bool
    status: str
    detail: dict[str, Any]


class OperatorResponse(BaseModel):
    ok: bool
    status: str
