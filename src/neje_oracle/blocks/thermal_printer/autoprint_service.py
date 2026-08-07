from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from ipaddress import ip_network
from pathlib import Path
from typing import Any

from ...shared.config import FirebaseSettings, firebase_enabled
from ..firebase.repository import FirebaseRemoteRepository, recorded_datetime

REPO_ROOT = Path(__file__).resolve().parents[4]
SEND_RECEIPT_SCRIPT = REPO_ROOT / "ESP32-BTN_Printer" / "tools" / "send_receipt.py"


def _load_dotenv_file() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv_file()


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


@dataclass(frozen=True)
class ThermalAutoprintSettings:
    macmini_agent_url: str = os.getenv("NEJE_MACMINI_AGENT_URL", "")
    esp32_url: str = os.getenv("NEJE_THERMAL_ESP32_URL", "http://10.28.8.56")
    firebase_limit: int = _env_int("NEJE_THERMAL_FIREBASE_LIMIT", 20)
    delay_seconds: float = _env_float("NEJE_THERMAL_DELAY_SECONDS", 60.0)
    poll_seconds: float = _env_float("NEJE_THERMAL_POLL_SECONDS", 10.0)
    retry_seconds: float = _env_float("NEJE_THERMAL_RETRY_SECONDS", 60.0)
    max_attempts: int = _env_int("NEJE_THERMAL_MAX_ATTEMPTS", 3)
    timeout_seconds: float = _env_float("NEJE_THERMAL_TIMEOUT_SECONDS", 90.0)
    state_path: Path = Path(os.getenv("NEJE_THERMAL_STATE_PATH", str(REPO_ROOT / "runtime" / "thermal_autoprint.json")))
    cache_root: Path = Path(os.getenv("NEJE_THERMAL_CACHE_ROOT", str(REPO_ROOT / "runtime" / "thermal_sessions")))
    repo_root: Path = REPO_ROOT


class ThermalAutoprintService:
    def __init__(
        self,
        settings: ThermalAutoprintSettings,
        *,
        http_get_json: Callable[[str, float], dict[str, Any]] | None = None,
        print_receipt: Callable[[Path], dict[str, Any]] | None = None,
        firebase_sessions: Callable[[], list[dict[str, Any]]] | None = None,
        download_asset: Callable[[str, Path], None] | None = None,
        remote_factory: Callable[[], FirebaseRemoteRepository] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings
        self.http_get_json = http_get_json or get_json
        self.print_receipt = print_receipt or self._print_receipt
        self.firebase_sessions = firebase_sessions or self._firebase_sessions
        self.download_asset = download_asset or self._download_firebase_asset
        self.remote_factory = remote_factory or (lambda: FirebaseRemoteRepository(FirebaseSettings()))
        self.now = now or time.time
        self.macmini_agent_url = settings.macmini_agent_url.rstrip("/")
        self.state = self._load_state()

    def run_once(self) -> dict[str, Any]:
        agent_error = ""
        imported: list[str] = []
        if not self.macmini_agent_url:
            self.macmini_agent_url = discover_macmini_uploader_url(timeout_seconds=0.25)

        if self.macmini_agent_url:
            try:
                status = self.http_get_json(f"{self.macmini_agent_url}/status", self.settings.timeout_seconds)
                watched_folder = Path(str(status.get("watched_folder") or "")).expanduser()
                imported = [
                    str(session_id) for session_id in status.get("last_imported", []) if str(session_id).strip()
                ]
            except Exception as exc:  # noqa: BLE001
                agent_error = str(exc)
                imported = []
        else:
            agent_error = "Mac mini uploader agent was not found"

        for session_id in imported:
            self._observe_session(session_id, watched_folder)

        firebase_imported = [] if imported else self._observe_firebase_sessions()
        result = self._process_pending()
        self._save_state()
        return {
            "ok": True,
            "macmini_agent_url": self.macmini_agent_url,
            "agent_error": agent_error,
            "observed": imported + firebase_imported,
            "observed_agent": imported,
            "observed_firebase": firebase_imported,
            **result,
        }

    def _observe_session(self, session_id: str, watched_folder: Path) -> None:
        sessions = self.state.setdefault("sessions", {})
        record = sessions.get(session_id)
        if record and record.get("status") == "printed":
            return
        now_iso = iso_from_epoch(self.now())
        session_dir = watched_folder / session_id if watched_folder else Path(session_id)
        if not record:
            record = {
                "status": "pending",
                "detected_at": now_iso,
                "attempts": 0,
                "last_attempt_at": "",
                "last_error": "",
            }
            sessions[session_id] = record
        record["session_dir"] = str(session_dir)
        record.setdefault("detected_at", now_iso)
        record.setdefault("source", "macmini_agent")

    def _observe_firebase_sessions(self) -> list[str]:
        try:
            payloads = self.firebase_sessions()
        except Exception:  # noqa: BLE001
            return []

        candidates = [payload for payload in payloads if firebase_session_printable(payload)]
        if not candidates:
            return []

        latest_seen = epoch_from_iso(str(self.state.get("firebase_latest_created_at") or ""))
        if not latest_seen:
            latest_seen = self._latest_firebase_record_epoch()
        if latest_seen:
            candidates = [
                payload
                for payload in candidates
                if recorded_datetime(payload.get("createdAt")).timestamp() > latest_seen
            ]
        if not candidates:
            self.state["firebase_observed_at"] = iso_from_epoch(self.now())
            return []

        first_firebase_scan = not self.state.get("firebase_observed_at")
        if first_firebase_scan:
            candidates = candidates[:1]
        self.state["firebase_observed_at"] = iso_from_epoch(self.now())

        observed: list[str] = []
        processed_epochs: list[float] = []
        for payload in candidates:
            session_id = str(payload.get("sessionId") or payload.get("_id") or "").strip()
            if not session_id:
                continue
            created_at = recorded_datetime(payload.get("createdAt")).timestamp()
            sessions = self.state.setdefault("sessions", {})
            record = sessions.get(session_id)
            if record and record.get("status") == "printed":
                processed_epochs.append(created_at)
                continue
            try:
                session_dir = self._materialize_firebase_session(payload)
            except Exception:  # noqa: BLE001
                continue
            if session_dir is None:
                continue
            detected_at = min(created_at, self.now()) if created_at else self.now()
            if not record:
                record = {
                    "status": "pending",
                    "detected_at": iso_from_epoch(detected_at),
                    "firebase_created_at": payload.get("createdAt", ""),
                    "attempts": 0,
                    "last_attempt_at": "",
                    "last_error": "",
                    "source": "firebase",
                }
                sessions[session_id] = record
            record["session_dir"] = str(session_dir)
            record["firebase_created_at"] = payload.get("createdAt", "")
            record.setdefault("detected_at", iso_from_epoch(detected_at))
            record.setdefault("source", "firebase")
            observed.append(session_id)
            processed_epochs.append(created_at)
        if processed_epochs:
            self.state["firebase_latest_created_at"] = iso_from_epoch(max(max(processed_epochs), latest_seen))
        return observed

    def _latest_firebase_record_epoch(self) -> float:
        values: list[float] = []
        for session_id, record in self.state.get("sessions", {}).items():
            if not isinstance(record, dict) or record.get("source") != "firebase":
                continue
            created_at = epoch_from_iso(str(record.get("firebase_created_at") or ""))
            if not created_at:
                created_at = epoch_from_session_id(str(session_id))
            if not created_at:
                created_at = epoch_from_iso(str(record.get("detected_at") or ""))
            values.append(created_at)
        return max(values) if values else 0.0

    def _materialize_firebase_session(self, payload: dict[str, Any]) -> Path | None:
        session_id = str(payload.get("sessionId") or payload.get("_id") or "").strip()
        if not session_id:
            return None
        asset_paths = payload.get("assetPaths")
        if not isinstance(asset_paths, dict):
            asset_paths = {}
        receipt_path = str(asset_paths.get("receipt") or "")
        svg_path = str(asset_paths.get("svg") or "")
        if not receipt_path or not svg_path:
            return None

        session_dir = self.settings.cache_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        local_receipt = session_dir / f"{session_id}_receipt.txt"
        local_svg = session_dir / f"{session_id}_plotter.svg"
        if not local_receipt.exists():
            self.download_asset(receipt_path, local_receipt)
        if not local_svg.exists():
            self.download_asset(svg_path, local_svg)
        self._write_firebase_csv(payload, session_dir)
        return session_dir

    def _write_firebase_csv(self, payload: dict[str, Any], session_dir: Path) -> None:
        session_id = str(payload.get("sessionId") or payload.get("_id") or session_dir.name)
        measures = payload.get("measures")
        if not isinstance(measures, dict):
            measures = {}
        themes = payload.get("themes") if isinstance(payload.get("themes"), list) else []
        csv_path = session_dir / f"{session_id}_receipt.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "session_id",
                    "date",
                    "symbol",
                    "reply_text",
                    "keywords",
                    "intensity",
                    "instability",
                    "confidence",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "session_id": session_id,
                    "date": payload.get("createdAt", ""),
                    "symbol": payload.get("markName", ""),
                    "reply_text": payload.get("oracleText", ""),
                    "keywords": repr(themes),
                    "intensity": measures.get("intensity", ""),
                    "instability": measures.get("instability", ""),
                    "confidence": measures.get("confidence", ""),
                }
            )

    def _process_pending(self) -> dict[str, Any]:
        printed: list[str] = []
        waiting: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        now_value = self.now()

        for session_id, record in sorted(self.state.get("sessions", {}).items()):
            status = str(record.get("status") or "pending")
            if status == "printed":
                continue
            if status == "failed" and int(record.get("attempts") or 0) >= self.settings.max_attempts:
                failed.append(session_id)
                continue

            detected_at = epoch_from_iso(str(record.get("detected_at") or "")) or now_value
            if now_value - detected_at < self.settings.delay_seconds:
                waiting.append(session_id)
                continue

            last_attempt_at = epoch_from_iso(str(record.get("last_attempt_at") or ""))
            if last_attempt_at and now_value - last_attempt_at < self.settings.retry_seconds:
                waiting.append(session_id)
                continue

            session_dir = Path(str(record.get("session_dir") or session_id)).expanduser()
            ready, reason = printable_session(session_dir)
            if not ready:
                record["status"] = "pending"
                record["last_error"] = reason
                skipped.append(session_id)
                continue

            record["attempts"] = int(record.get("attempts") or 0) + 1
            record["last_attempt_at"] = iso_from_epoch(now_value)
            try:
                response = self.print_receipt(session_dir)
            except Exception as exc:  # noqa: BLE001
                response = {"ok": False, "error": str(exc)}

            if response.get("ok") and response.get("printed"):
                record["status"] = "printed"
                record["printed_at"] = iso_from_epoch(self.now())
                record["last_error"] = ""
                printed.append(session_id)
                continue

            record["last_error"] = str(response.get("error") or response)
            if int(record.get("attempts") or 0) >= self.settings.max_attempts:
                record["status"] = "failed"
                failed.append(session_id)
            else:
                record["status"] = "pending"
                waiting.append(session_id)

        return {"printed": printed, "waiting": waiting, "failed": failed, "skipped": skipped}

    def _print_receipt(self, session_dir: Path) -> dict[str, Any]:
        preview_path = self.settings.repo_root / "reports" / f"thermal_autoprint_{session_dir.name}.png"
        command = [
            sys.executable,
            str(SEND_RECEIPT_SCRIPT),
            str(session_dir),
            "--repo-root",
            str(self.settings.repo_root),
            "--esp32",
            self.settings.esp32_url.rstrip("/"),
            "--protocol",
            "ilabel",
            "--preview-png",
            str(preview_path),
            "--timeout",
            str(self.settings.timeout_seconds),
        ]
        result = subprocess.run(
            command,
            cwd=self.settings.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return {"ok": False, "error": (result.stderr or result.stdout).strip()}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error": result.stdout.strip() or "Printer command returned no JSON"}

    def _load_state(self) -> dict[str, Any]:
        if not self.settings.state_path.exists():
            return {"sessions": {}}
        try:
            data = json.loads(self.settings.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"sessions": {}}
        if not isinstance(data, dict):
            return {"sessions": {}}
        data.setdefault("sessions", {})
        return data

    def _save_state(self) -> None:
        self.settings.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.state_path.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @cached_property
    def firebase_remote(self) -> FirebaseRemoteRepository:
        return self.remote_factory()

    def _firebase_sessions(self) -> list[dict[str, Any]]:
        if not firebase_enabled():
            return []
        return self.firebase_remote.iter_recent_sessions(limit=self.settings.firebase_limit)

    def _download_firebase_asset(self, storage_path: str, destination: Path) -> None:
        self.firebase_remote.download_asset(storage_path, destination)


def printable_session(session_dir: Path) -> tuple[bool, str]:
    if not session_dir.exists():
        return False, f"session folder does not exist: {session_dir}"
    if not list(session_dir.glob("*_receipt.txt")):
        return False, f"missing *_receipt.txt in {session_dir}"
    if not list(session_dir.glob("*_plotter.svg")):
        return False, f"missing *_plotter.svg in {session_dir}"
    return True, ""


def firebase_session_printable(payload: dict[str, Any]) -> bool:
    if str(payload.get("status") or "") != "published":
        return False
    if str(payload.get("origin") or "") != "real_macmini":
        return False
    asset_paths = payload.get("assetPaths")
    if not isinstance(asset_paths, dict):
        return False
    return bool(asset_paths.get("receipt") and asset_paths.get("svg"))


def get_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc


def discover_macmini_uploader_url(*, timeout_seconds: float) -> str:
    configured = os.getenv("NEJE_MACMINI_AGENT_URL", "").strip().rstrip("/")
    if configured and probe_uploader_url(configured, timeout_seconds=timeout_seconds):
        return configured

    hosts = scan_lan_hosts()
    candidates = [f"http://{host}:8790" for host in hosts]
    if not candidates:
        return ""
    with ThreadPoolExecutor(max_workers=min(64, len(candidates))) as executor:
        futures = {executor.submit(probe_uploader_url, url, timeout_seconds=timeout_seconds): url for url in candidates}
        for future in as_completed(futures):
            try:
                if future.result():
                    return futures[future]
            except Exception:
                continue
    return ""


def probe_uploader_url(url: str, *, timeout_seconds: float) -> bool:
    try:
        payload = get_json(f"{url.rstrip('/')}/health", timeout_seconds)
    except Exception:
        return False
    return str(payload.get("service") or "") in {"standalone-macmini-uploader", "neje-uploader-agent"}


def scan_lan_hosts() -> list[str]:
    local_ip = local_ipv4()
    if not local_ip:
        return []
    network = ip_network(f"{local_ip}/24", strict=False)
    return [str(host) for host in network.hosts() if str(host) != local_ip]


def local_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return ""


def iso_from_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def epoch_from_iso(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def epoch_from_session_id(value: str) -> float:
    try:
        return datetime.strptime(value, "%Y%m%d_%H%M%S").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch the Mac mini uploader and autoprint new thermal receipts.")
    parser.add_argument("--watch", action="store_true", help="Keep polling for new imported sessions.")
    parser.add_argument("--once", action="store_true", help="Run one poll/process pass and exit.")
    parser.add_argument("--macmini-agent-url", default=os.getenv("NEJE_MACMINI_AGENT_URL", ""))
    parser.add_argument("--esp32", default=os.getenv("NEJE_THERMAL_ESP32_URL", "http://10.28.8.56"))
    parser.add_argument("--firebase-limit", type=int, default=_env_int("NEJE_THERMAL_FIREBASE_LIMIT", 20))
    parser.add_argument("--delay-seconds", type=float, default=_env_float("NEJE_THERMAL_DELAY_SECONDS", 60.0))
    parser.add_argument("--poll-seconds", type=float, default=_env_float("NEJE_THERMAL_POLL_SECONDS", 10.0))
    parser.add_argument("--retry-seconds", type=float, default=_env_float("NEJE_THERMAL_RETRY_SECONDS", 60.0))
    parser.add_argument("--max-attempts", type=int, default=_env_int("NEJE_THERMAL_MAX_ATTEMPTS", 3))
    parser.add_argument("--timeout", type=float, default=_env_float("NEJE_THERMAL_TIMEOUT_SECONDS", 90.0))
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path(os.getenv("NEJE_THERMAL_STATE_PATH", str(REPO_ROOT / "runtime" / "thermal_autoprint.json"))),
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(os.getenv("NEJE_THERMAL_CACHE_ROOT", str(REPO_ROOT / "runtime" / "thermal_sessions"))),
    )
    return parser


def settings_from_args(args: argparse.Namespace) -> ThermalAutoprintSettings:
    return ThermalAutoprintSettings(
        macmini_agent_url=args.macmini_agent_url,
        esp32_url=args.esp32,
        firebase_limit=args.firebase_limit,
        delay_seconds=args.delay_seconds,
        poll_seconds=args.poll_seconds,
        retry_seconds=args.retry_seconds,
        max_attempts=args.max_attempts,
        timeout_seconds=args.timeout,
        state_path=args.state_path.expanduser(),
        cache_root=args.cache_root.expanduser(),
        repo_root=REPO_ROOT,
    )


def main() -> None:
    args = build_parser().parse_args()
    settings = settings_from_args(args)
    service = ThermalAutoprintService(settings)

    if args.watch:
        try:
            while True:
                print(json.dumps(service.run_once(), sort_keys=True))
                time.sleep(settings.poll_seconds)
        except KeyboardInterrupt:
            print("Thermal autoprint stopped.")
        return

    print(json.dumps(service.run_once(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
