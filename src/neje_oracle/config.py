from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SYMBOL_FIT_RATIO = 0.86


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_dotenv_file() -> None:
    env_path = _repo_root() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv_file()


def _firebase_project_id() -> str:
    return os.getenv("NEJE_FIREBASE_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID", "")


def _firebase_storage_bucket() -> str:
    explicit = os.getenv("NEJE_FIREBASE_STORAGE_BUCKET") or os.getenv("FIREBASE_STORAGE_BUCKET", "")
    if explicit:
        return explicit
    project_id = _firebase_project_id()
    return f"{project_id}.firebasestorage.app" if project_id else ""


def _firebase_credentials_path() -> Path:
    explicit = os.getenv("NEJE_FIREBASE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if explicit:
        return Path(explicit).expanduser()
    return _repo_root() / "firebase" / "serviceAccountKey.json"


@dataclass(frozen=True)
class FirebaseSettings:
    project_id: str = _firebase_project_id()
    storage_bucket: str = _firebase_storage_bucket()
    credentials_path: Path = _firebase_credentials_path()
    gallery_base_url: str = os.getenv(
        "NEJE_GALLERY_BASE_URL",
        "https://example.github.io/neje-oracle-gallery",
    )

    @property
    def enabled(self) -> bool:
        return bool(self.project_id and self.storage_bucket and self.credentials_path.exists())


@dataclass(frozen=True)
class UploaderSettings:
    session_root: Path = Path(os.getenv("NEJE_UPLOADER_SESSION_ROOT", str(_repo_root() / "sessions_raw")))
    public_root: Path = Path(os.getenv("NEJE_UPLOADER_PUBLIC_ROOT", str(_repo_root() / "sessions_public")))
    db_path: Path = Path(os.getenv("NEJE_UPLOADER_DB_PATH", str(_repo_root() / "runtime" / "uploader.sqlite3")))
    poll_seconds: float = _env_float("NEJE_UPLOADER_POLL_SECONDS", 2.0)
    stability_seconds: float = _env_float("NEJE_UPLOADER_STABILITY_SECONDS", 8.0)
    ready_marker_name: str = os.getenv("NEJE_UPLOADER_READY_MARKER", "READY")
    require_ready_marker: bool = _env_bool("NEJE_UPLOADER_REQUIRE_READY_MARKER", False)


@dataclass(frozen=True)
class PlotterSettings:
    db_path: Path = Path(os.getenv("NEJE_PLOTTER_DB_PATH", str(_repo_root() / "runtime" / "plotter.sqlite3")))
    placeholder_root: Path = Path(os.getenv("NEJE_PLOTTER_PLACEHOLDER_ROOT", str(_repo_root() / "assets" / "symbols")))
    spool_root: Path = Path(os.getenv("NEJE_PLOTTER_SPOOL_ROOT", str(_repo_root() / "spool")))
    poll_seconds: float = _env_float("NEJE_PLOTTER_POLL_SECONDS", 4.0)
    sheet_width_mm: float = _env_float("NEJE_PLOTTER_SHEET_WIDTH_MM", 250.0)
    sheet_height_mm: float = _env_float("NEJE_PLOTTER_SHEET_HEIGHT_MM", 440.0)
    sheet_margin_mm: float = _env_float("NEJE_PLOTTER_SHEET_MARGIN_MM", 0.0)
    cell_diameter_mm: float = _env_float("NEJE_PLOTTER_CELL_DIAMETER_MM", 80.0)
    cell_gap_mm: float = _env_float("NEJE_PLOTTER_CELL_GAP_MM", 0.0)
    layout_mode: str = os.getenv("NEJE_PLOTTER_LAYOUT_MODE", "hex")
    sample_step_mm: float = _env_float("NEJE_PLOTTER_SAMPLE_STEP_MM", 1.0)
    travel_rate: float = _env_float("NEJE_PLOTTER_TRAVEL_RATE", 5000.0)
    draw_rate: float = _env_float("NEJE_PLOTTER_DRAW_RATE", 1800.0)
    pen_up_command: str = os.getenv("NEJE_PLOTTER_PEN_UP", "M5")
    pen_down_command: str = os.getenv("NEJE_PLOTTER_PEN_DOWN", "M3 S15")
    # TinyBee touch connector exposes the PWM servo as FluidNC Z axis.
    use_z_servo: bool = _env_bool("NEJE_PLOTTER_USE_Z_SERVO", True)
    z_down_mm: float = _env_float("NEJE_PLOTTER_Z_DOWN_MM", -25.0)
    z_up_mm: float = _env_float("NEJE_PLOTTER_Z_UP_MM", 0.0)
    z_feed_mm_min: float = _env_float("NEJE_PLOTTER_Z_FEED_MM_MIN", 1000.0)
    work_zero_command: str = os.getenv("NEJE_PLOTTER_WORK_ZERO_COMMAND", "G10 L20 P1 X0 Y0")
    tinybee_config_path: Path = Path(os.getenv("NEJE_PLOTTER_TINYBEE_CONFIG_PATH", str(_repo_root() / "assets" / "tinybee.json")))
    dry_run: bool = _env_bool("NEJE_PLOTTER_DRY_RUN", True)
    include_markers: bool = _env_bool("NEJE_PLOTTER_INCLUDE_MARKERS", True)
    marker_diameter_mm: float = _env_float("NEJE_PLOTTER_MARKER_DIAMETER_MM", 1.5)
    fluidnc_http_url: str = os.getenv("NEJE_PLOTTER_FLUIDNC_HTTP_URL", "")
    fluidnc_telnet_host: str = os.getenv(
        "NEJE_PLOTTER_FLUIDNC_TELNET_HOST",
        os.getenv("NEJE_PLOTTER_FLUIDNC_HOST", ""),
    )
    fluidnc_telnet_port: int = _env_int(
        "NEJE_PLOTTER_FLUIDNC_TELNET_PORT",
        _env_int("NEJE_PLOTTER_FLUIDNC_PORT", 23),
    )
    fluidnc_connect_timeout_seconds: float = _env_float("NEJE_PLOTTER_FLUIDNC_CONNECT_TIMEOUT_SECONDS", 3.0)
    fluidnc_ack_timeout_seconds: float = _env_float("NEJE_PLOTTER_FLUIDNC_ACK_TIMEOUT_SECONDS", 10.0)
    fluidnc_host: str = fluidnc_telnet_host
    fluidnc_port: int = fluidnc_telnet_port
    operator_host: str = os.getenv("NEJE_PLOTTER_OPERATOR_HOST", "0.0.0.0")
    operator_port: int = _env_int("NEJE_PLOTTER_OPERATOR_PORT", 8765)


@dataclass(frozen=True)
class OracleSupervisorSettings:
    runtime_db_path: Path = Path(
        os.getenv("NEJE_ORACLE_RUNTIME_DB_PATH", str(_repo_root() / "runtime" / "oracle_runtime.sqlite3"))
    )
    logs_root: Path = Path(os.getenv("NEJE_ORACLE_LOGS_ROOT", str(_repo_root() / "logs")))
    macmini_agent_url: str = os.getenv("NEJE_MACMINI_AGENT_URL", "")
    macmini_agent_timeout_seconds: float = _env_float("NEJE_MACMINI_AGENT_TIMEOUT_SECONDS", 2.0)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
