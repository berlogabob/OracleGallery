#!/bin/zsh

set -e
setopt pipefail

SCRIPT_DIR="${0:A:h}"
CONFIG_FILE="$SCRIPT_DIR/macmini_uploader.env"
RUNTIME_DIR="$SCRIPT_DIR/.macmini_uploader_runtime"
APP_FILE="$RUNTIME_DIR/standalone_uploader.py"
VENV_DIR="$RUNTIME_DIR/venv"
EMBEDDED_FIREBASE_SERVICE_ACCOUNT_JSON_B64=""

pause() {
  echo
  read '?Press Enter to close...'
}

fail() {
  echo
  echo "ERROR: $1"
  pause
  exit 1
}

find_python() {
  local candidate
  local -a candidates=(
    "${PYTHON_BIN:-}"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
    "$(command -v python3 2>/dev/null || true)"
  )
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

create_default_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    return 0
  fi
  cat > "$CONFIG_FILE" <<EOF
# Mac mini standalone uploader settings.
# The folder containing START_ORACLE_UPLOADER.command is watched for session folders.
NEJE_FIREBASE_PROJECT_ID=oraclegallery
NEJE_FIREBASE_STORAGE_BUCKET=oraclegallery.firebasestorage.app
NEJE_FIREBASE_CREDENTIALS="$SCRIPT_DIR/firebase-service-account.json"
NEJE_GALLERY_BASE_URL=https://berlogabob.github.io/OracleGallery
NEJE_UPLOADER_READY_MARKER=READY
NEJE_UPLOADER_REQUIRE_READY_MARKER=false
NEJE_UPLOADER_STABILITY_SECONDS=8
NEJE_UPLOADER_POLL_SECONDS=2
NEJE_UPLOADER_AGENT_HOST=0.0.0.0
NEJE_UPLOADER_AGENT_PORT=8790
EOF
}

repair_firebase_credentials_config() {
  local default_credentials="$SCRIPT_DIR/firebase-service-account.json"
  local raw_credentials="${NEJE_FIREBASE_CREDENTIALS:-}"
  local expanded_credentials="${raw_credentials/#\~/$HOME}"
  local resolved_script_dir="${SCRIPT_DIR:A}"
  local resolved_credentials="${expanded_credentials:A}"

  if [[ -z "$raw_credentials" ]]; then
    export NEJE_FIREBASE_CREDENTIALS="$default_credentials"
    return 0
  fi

  if [[ "$resolved_credentials" == /Users/berloga/* ]]; then
    :
  elif [[ "$resolved_credentials" == "$resolved_script_dir"/* ]]; then
    return 0
  else
    :
  fi

  export NEJE_FIREBASE_CREDENTIALS="$default_credentials"

  local tmp_file="$CONFIG_FILE.tmp.$$"
  local replaced=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == NEJE_FIREBASE_CREDENTIALS=* ]]; then
      printf 'NEJE_FIREBASE_CREDENTIALS="%s"\n' "$default_credentials" >> "$tmp_file"
      replaced=1
    else
      printf '%s\n' "$line" >> "$tmp_file"
    fi
  done < "$CONFIG_FILE"
  if [[ $replaced -eq 0 ]]; then
    printf 'NEJE_FIREBASE_CREDENTIALS="%s"\n' "$default_credentials" >> "$tmp_file"
  fi
  mv "$tmp_file" "$CONFIG_FILE"
}

ensure_firebase_credentials() {
  if [[ -f "$NEJE_FIREBASE_CREDENTIALS" ]]; then
    return 0
  fi

  if [[ -n "$EMBEDDED_FIREBASE_SERVICE_ACCOUNT_JSON_B64" ]]; then
    mkdir -p "${NEJE_FIREBASE_CREDENTIALS:h}"
    FIREBASE_JSON_B64="$EMBEDDED_FIREBASE_SERVICE_ACCOUNT_JSON_B64" "$PYTHON_BIN" - "$NEJE_FIREBASE_CREDENTIALS" <<'PY'
import base64
import json
import os
import sys

payload = base64.b64decode(os.environ["FIREBASE_JSON_B64"])
json.loads(payload.decode("utf-8"))
with open(sys.argv[1], "wb") as handle:
    handle.write(payload)
PY
    chmod 600 "$NEJE_FIREBASE_CREDENTIALS" || true
    echo "Created Firebase service account JSON from embedded private key:"
    echo "$NEJE_FIREBASE_CREDENTIALS"
    return 0
  fi

  echo
  echo "Firebase service account JSON was not found:"
  echo "$NEJE_FIREBASE_CREDENTIALS"
  echo
  echo "Drag the Firebase service account JSON file into this Terminal window, then press Enter."
  echo "Press Enter without a file path to stop."
  echo
  local source_path
  read '?Firebase JSON path: ' source_path
  source_path="${source_path/#\\~/$HOME}"
  source_path="${source_path//\\ / }"
  source_path="${source_path%\"}"
  source_path="${source_path#\"}"
  source_path="${source_path%\'}"
  source_path="${source_path#\'}"

  [[ -n "$source_path" ]] || fail "Firebase service account JSON is required for upload."
  [[ -f "$source_path" ]] || fail "File not found: $source_path"

  mkdir -p "${NEJE_FIREBASE_CREDENTIALS:h}"
  cp "$source_path" "$NEJE_FIREBASE_CREDENTIALS" || fail "Could not copy Firebase service account JSON."
  chmod 600 "$NEJE_FIREBASE_CREDENTIALS" || true
  echo "Saved Firebase service account JSON to:"
  echo "$NEJE_FIREBASE_CREDENTIALS"
}

write_python_app() {
  mkdir -p "$RUNTIME_DIR"
  cat > "$APP_FILE" <<'PY'
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote

import firebase_admin
import qrcode
from firebase_admin import credentials, firestore, storage


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


@dataclass(frozen=True)
class Settings:
    session_root: Path
    runtime_dir: Path
    project_id: str
    storage_bucket: str
    credentials_path: Path
    gallery_base_url: str
    ready_marker_name: str = "READY"
    require_ready_marker: bool = False
    stability_seconds: float = 8.0
    poll_seconds: float = 2.0


@dataclass
class Publication:
    session_id: str
    created_at: datetime
    title: str
    summary: str
    mark_name: str
    oracle_text: str
    themes: list[str] = field(default_factory=list)
    measures: dict[str, float] = field(default_factory=dict)
    qr_url: str = ""
    svg_url: str = ""
    receipt_url: str = ""
    qr_image_url: str = ""
    tarot_url: str = ""
    public_dir: Path | None = None


class JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"published": {}, "run_started_at": ""}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.path.with_suffix(".broken.json")
            shutil.copy2(self.path, backup)
            return {"published": {}, "run_started_at": ""}

    def save(self, payload: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def run_started_at(self) -> datetime | None:
        raw = self.load().get("run_started_at") or ""
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def set_run_started_at(self, value: datetime) -> None:
        with self.lock:
            payload = self.load()
            payload["run_started_at"] = value.isoformat()
            self.save(payload)

    def is_published(self, session_id: str) -> bool:
        return bool(self.load().get("published", {}).get(session_id))

    def mark_published(self, session_id: str, payload: dict[str, Any]) -> None:
        with self.lock:
            state = self.load()
            published = dict(state.get("published") or {})
            published[session_id] = payload
            state["published"] = published
            self.save(state)


class FirebasePublisher:
    def __init__(self, settings: Settings) -> None:
        if not settings.credentials_path.exists():
            raise RuntimeError(f"Firebase service account JSON does not exist: {settings.credentials_path}")
        app_name = f"macmini-standalone-uploader-{settings.project_id}"
        try:
            self.app = firebase_admin.get_app(app_name)
        except ValueError:
            cred = credentials.Certificate(str(settings.credentials_path))
            self.app = firebase_admin.initialize_app(
                cred,
                {"projectId": settings.project_id, "storageBucket": settings.storage_bucket},
                name=app_name,
            )
        self.settings = settings
        self.db = firestore.client(app=self.app)
        self.bucket = storage.bucket(app=self.app)

    def publish(self, publication: Publication) -> None:
        assert publication.public_dir is not None
        remote_root = f"sessions/{publication.session_id}"
        svg_path = f"{remote_root}/artwork.svg"
        raw_svg_path = f"{remote_root}/artwork_raw.svg"
        receipt_path = f"{remote_root}/receipt.txt"
        qr_path = f"{remote_root}/qr.png"
        tarot_path = f"{remote_root}/tarot.jpg"
        manifest_path = f"{remote_root}/manifest.json"

        self._upload(publication.public_dir / "artwork.svg", svg_path, "image/svg+xml")
        self._upload(publication.public_dir / "artwork_raw.svg", raw_svg_path, "image/svg+xml")
        self._upload(publication.public_dir / "receipt.txt", receipt_path, "text/plain; charset=utf-8")
        self._upload(publication.public_dir / "qr.png", qr_path, "image/png")
        if (publication.public_dir / "tarot.jpg").exists():
            self._upload(publication.public_dir / "tarot.jpg", tarot_path, "image/jpeg")

        publication.svg_url = self.public_storage_url(svg_path, version=file_hash(publication.public_dir / "artwork.svg"))
        publication.receipt_url = self.public_storage_url(receipt_path)
        publication.qr_image_url = self.public_storage_url(qr_path)
        publication.tarot_url = self.public_storage_url(tarot_path) if (publication.public_dir / "tarot.jpg").exists() else ""

        manifest = self._manifest_payload(publication, svg_path, raw_svg_path, receipt_path, qr_path, tarot_path, manifest_path)
        self.bucket.blob(manifest_path).upload_from_string(
            json.dumps(manifest, indent=2, sort_keys=True),
            content_type="application/json",
        )

        session_payload = {
            "sessionId": publication.session_id,
            "createdAt": publication.created_at.isoformat(),
            "title": publication.title,
            "summary": publication.summary,
            "status": "published",
            "plotStatus": "pending",
            "priority": "user",
            "sessionUrl": publication.qr_url,
            "qrUrl": publication.qr_url,
            "qrImageUrl": publication.qr_image_url,
            "tarotUrl": publication.tarot_url,
            "svgUrl": publication.svg_url,
            "receiptUrl": publication.receipt_url,
            "markName": publication.mark_name,
            "oracleText": publication.oracle_text,
            "themes": publication.themes,
            "measures": publication.measures,
            "assetUrls": {
                "svg": publication.svg_url,
                "qr": publication.qr_image_url,
                "receipt": publication.receipt_url,
                "tarot": publication.tarot_url,
            },
            "assetPaths": {
                "svg": svg_path,
                "rawSvg": raw_svg_path,
                "qr": qr_path,
                "receipt": receipt_path,
                "tarot": tarot_path if publication.tarot_url else "",
                "manifest": manifest_path,
            },
            "metadata": {
                "origin": "real_macmini",
                "tags": ["real", "oracle", "macmini"],
                "visibleInLibrary": True,
                "standaloneUploader": True,
            },
            "origin": "real_macmini",
            "tags": ["real", "oracle", "macmini"],
            "visibleInLibrary": True,
        }
        self.db.collection("sessions").document(publication.session_id).set(session_payload, merge=True)
        self.db.collection("sessions").document(publication.session_id).update(
            {
                "previewUrl": firestore.DELETE_FIELD,
                "assetUrls.preview": firestore.DELETE_FIELD,
                "assetPaths.preview": firestore.DELETE_FIELD,
            }
        )
        self.db.collection("plot_jobs").document(publication.session_id).set(
            {
                "sessionId": publication.session_id,
                "title": publication.title,
                "summary": publication.summary,
                "createdAt": publication.created_at.isoformat(),
                "status": "pending",
                "priority": "user",
                "queue": "user",
                "consumerId": "",
                "sheetId": "",
                "sheetIndex": -1,
                "error": "",
                "svgStoragePath": svg_path,
                "svgUrl": publication.svg_url,
                "origin": "real_macmini",
                "tags": ["real", "oracle", "macmini"],
                "visibleInQueue": True,
            },
            merge=True,
        )
        self.db.collection("plot_jobs").document(publication.session_id).update(
            {"previewUrl": firestore.DELETE_FIELD}
        )

    def _manifest_payload(
        self,
        publication: Publication,
        svg_path: str,
        raw_svg_path: str,
        receipt_path: str,
        qr_path: str,
        tarot_path: str,
        manifest_path: str,
    ) -> dict[str, Any]:
        return {
            "session_id": publication.session_id,
            "created_at": publication.created_at.isoformat(),
            "title": publication.title,
            "summary": publication.summary,
            "mark_name": publication.mark_name,
            "oracle_text": publication.oracle_text,
            "themes": publication.themes,
            "measures": publication.measures,
            "public_status": "published",
            "plot_status": "pending",
            "sessionUrl": publication.qr_url,
            "qrImageUrl": publication.qr_image_url,
            "tarotUrl": publication.tarot_url,
            "public_svg_path": svg_path,
            "public_receipt_path": receipt_path,
            "public_qr_path": qr_path,
            "public_manifest_path": manifest_path,
            "assetPaths": {
                "svg": svg_path,
                "rawSvg": raw_svg_path,
                "qr": qr_path,
                "receipt": receipt_path,
                "tarot": tarot_path if publication.tarot_url else "",
                "manifest": manifest_path,
            },
            "origin": "real_macmini",
            "tags": ["real", "oracle", "macmini"],
            "visibleInLibrary": True,
        }

    def _upload(self, source: Path, storage_path: str, content_type: str) -> None:
        self.bucket.blob(storage_path).upload_from_filename(str(source), content_type=content_type)

    def download(self, storage_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.bucket.blob(storage_path).download_to_filename(str(destination))

    def public_storage_url(self, storage_path: str, *, version: str | None = None) -> str:
        url = (
            f"https://firebasestorage.googleapis.com/v0/b/{self.settings.storage_bucket}/o/"
            f"{quote(storage_path, safe='')}?alt=media"
        )
        if version:
            return f"{url}&v={quote(version, safe='')}"
        return url


class Uploader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = JsonStore(settings.runtime_dir / "state.json")
        self.publisher = FirebasePublisher(settings)
        self.public_root = settings.runtime_dir / "public"
        self.public_root.mkdir(parents=True, exist_ok=True)

    def scan_once(self) -> list[str]:
        imported: list[str] = []
        baseline = self.store.run_started_at()
        for session_dir in sorted(path for path in self.settings.session_root.iterdir() if path.is_dir()):
            if session_dir == self.settings.runtime_dir or session_dir.name.startswith("."):
                continue
            session_id = session_dir.name
            if self.store.is_published(session_id):
                continue
            if baseline is not None and self.session_timestamp(session_dir) < baseline:
                continue
            if not self.is_ready(session_dir):
                continue
            self.process_session(session_dir)
            imported.append(session_id)
        return imported

    def is_ready(self, session_dir: Path) -> bool:
        if self.has_ready_marker(session_dir):
            return self.resolve_svg(session_dir) is not None and self.resolve_receipt(session_dir) is not None
        if self.settings.require_ready_marker:
            return False
        if self.resolve_svg(session_dir) is None or self.resolve_receipt(session_dir) is None:
            return False
        file_mtimes = [path.stat().st_mtime for path in session_dir.rglob("*") if path.is_file()]
        if not file_mtimes:
            return False
        return (time.time() - max(file_mtimes)) >= self.settings.stability_seconds

    def process_session(self, session_dir: Path) -> None:
        session_id = session_dir.name
        svg_source = self.resolve_svg(session_dir)
        receipt_source = self.resolve_receipt(session_dir)
        tarot_source = self.resolve_tarot(session_dir)
        if svg_source is None or receipt_source is None:
            raise FileNotFoundError(f"Missing plotter SVG or receipt TXT in {session_dir}")

        public_dir = self.public_root / session_id
        public_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(svg_source, public_dir / "artwork_raw.svg")
        shutil.copy2(svg_source, public_dir / "artwork.svg")
        shutil.copy2(receipt_source, public_dir / "receipt.txt")
        if tarot_source is not None:
            shutil.copy2(tarot_source, public_dir / "tarot.jpg")

        receipt_data = parse_receipt(receipt_source)
        csv_data = parse_session_csv(session_dir)
        created_at = resolve_created_at(session_dir, csv_data)
        mark_name = receipt_data.get("mark_name") or csv_data.get("mark_name", "")
        oracle_text = receipt_data.get("oracle_text") or csv_data.get("oracle_text", "")
        title = mark_name or session_id.replace("_", " ")
        qr_url = f"{self.settings.gallery_base_url.rstrip('/')}/#/session/{quote(session_id)}"
        qrcode.make(qr_url).save(public_dir / "qr.png")

        publication = Publication(
            session_id=session_id,
            created_at=created_at,
            title=title,
            summary=oracle_text,
            mark_name=mark_name,
            oracle_text=oracle_text,
            themes=receipt_data.get("themes") or csv_data.get("themes", []),
            measures=resolve_measures(csv_data),
            qr_url=qr_url,
            public_dir=public_dir,
        )
        self.publisher.publish(publication)
        local_qr_path = self.download_published_qr(publication, session_dir)
        self.store.mark_published(
            session_id,
            {
                "published_at": datetime.now(tz=UTC).isoformat(),
                "source_dir": str(session_dir),
                "localQrPath": str(local_qr_path),
                "sessionUrl": publication.qr_url,
                "svgUrl": publication.svg_url,
                "receiptUrl": publication.receipt_url,
                "qrImageUrl": publication.qr_image_url,
                "tarotUrl": publication.tarot_url,
            },
        )

    def download_published_qr(self, publication: Publication, session_dir: Path) -> Path:
        qr_path = f"sessions/{publication.session_id}/qr.png"
        destination = session_dir / f"{publication.session_id}_qr.png"
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            self.publisher.download(qr_path, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def has_ready_marker(self, session_dir: Path) -> bool:
        candidates = [
            session_dir / self.settings.ready_marker_name,
            session_dir / f"{session_dir.name}_tarot_ready.txt",
        ]
        candidates.extend(sorted(session_dir.glob("*_ready.txt")))
        return any(path.exists() for path in candidates)

    def resolve_svg(self, session_dir: Path) -> Path | None:
        candidates = [session_dir / f"{session_dir.name}_plotter.svg"]
        candidates.extend(sorted(session_dir.glob("*_plotter.svg")))
        return next((path for path in candidates if path.exists()), None)

    def resolve_receipt(self, session_dir: Path) -> Path | None:
        candidates = [session_dir / f"{session_dir.name}_receipt.txt"]
        candidates.extend(sorted(session_dir.glob("*_receipt.txt")))
        return next((path for path in candidates if path.exists()), None)

    def resolve_tarot(self, session_dir: Path) -> Path | None:
        candidates = [session_dir / f"{session_dir.name}_tarot.jpg"]
        candidates.extend(sorted(session_dir.glob("*_tarot.jpg")))
        return next((path for path in candidates if path.exists()), None)

    def session_timestamp(self, session_dir: Path) -> datetime:
        mtimes = [session_dir.stat().st_mtime]
        mtimes.extend(path.stat().st_mtime for path in session_dir.rglob("*") if path.is_file())
        return datetime.fromtimestamp(max(mtimes), tz=UTC)


class Controller:
    def __init__(self, uploader: Uploader, settings: Settings) -> None:
        self.uploader = uploader
        self.settings = settings
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.imported_count = 0
        self.last_imported: list[str] = []
        self.last_error = ""
        self.started_at: datetime | None = None
        self.heartbeat_at: datetime | None = None

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return self.status("already running")
            self.stop_event.clear()
            self.started_at = datetime.now(tz=UTC)
            self.uploader.store.set_run_started_at(self.started_at)
            self.thread = threading.Thread(target=self.loop, daemon=True)
            self.thread.start()
        return self.status("started")

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self.stop_event.set()
            thread = self.thread
        if thread:
            thread.join(timeout=max(self.settings.poll_seconds * 2, 2.0))
        return self.status("stopped")

    def restart(self) -> dict[str, Any]:
        self.stop()
        return self.start()

    def scan_once(self) -> dict[str, Any]:
        try:
            imported = self.uploader.scan_once()
            self.record_imported(imported)
            self.last_error = ""
            return {**self.status("scan complete"), "imported": imported}
        except Exception as exc:
            self.last_error = str(exc)
            return {**self.status("scan failed"), "imported": []}

    def loop(self) -> None:
        while not self.stop_event.is_set():
            self.scan_once()
            self.heartbeat_at = datetime.now(tz=UTC)
            self.stop_event.wait(self.settings.poll_seconds)

    def record_imported(self, imported: list[str]) -> None:
        if imported:
            self.imported_count += len(imported)
            self.last_imported = imported[-5:]

    def status(self, message: str = "") -> dict[str, Any]:
        running = bool(self.thread and self.thread.is_alive())
        return {
            "running": running,
            "message": message or ("running" if running else "stopped"),
            "watched_folder": str(self.settings.session_root),
            "runtime_folder": str(self.settings.runtime_dir),
            "firebase_project": self.settings.project_id,
            "storage_bucket": self.settings.storage_bucket,
            "imported_count": self.imported_count,
            "last_imported": self.last_imported,
            "last_error": self.last_error,
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else "",
        }


def parse_receipt(receipt_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {"mark_name": "", "oracle_text": "", "themes": []}
    for raw_line in receipt_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line[0] in {"\u2554", "\u2551", "\u2560", "\u255a"}:
            continue
        lower = line.lower()
        if lower.startswith("your symbol:"):
            data["mark_name"] = line.split(":", 1)[1].strip()
            continue
        if lower.startswith("themes:"):
            data["themes"] = parse_themes(line.split(":", 1)[1].strip())
            continue
        if not data["oracle_text"]:
            data["oracle_text"] = line
    return data


def parse_themes(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        parsed = ast.literal_eval(str(raw))
    except (SyntaxError, ValueError):
        parsed = [part.strip() for part in str(raw).split(",")]
    if isinstance(parsed, list):
        return [str(item).strip().strip("'\"") for item in parsed if str(item).strip()]
    return [str(parsed).strip()]


def parse_session_csv(session_dir: Path) -> dict[str, Any]:
    csv_path = session_dir / f"{session_dir.name}_receipt.csv"
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle), None)
    if not row:
        return {}
    return {
        "timestamp": row.get("date", ""),
        "mark_name": (row.get("symbol") or "").strip().upper(),
        "mark_type": row.get("mark_type", ""),
        "oracle_text": (row.get("reply_text") or "").strip(),
        "themes": parse_themes(row.get("keywords", "")),
        "intensity": row.get("intensity") or row.get("voice_intensity") or "",
        "instability": row.get("instability", ""),
        "confidence": row.get("confidence", ""),
    }


def resolve_created_at(session_dir: Path, csv_data: dict[str, Any]) -> datetime:
    raw = csv_data.get("timestamp")
    if raw:
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.fromtimestamp(session_dir.stat().st_mtime, tz=UTC)


def resolve_measures(csv_data: dict[str, Any]) -> dict[str, float]:
    measures: dict[str, float] = {}
    for key in ("intensity", "instability", "confidence"):
        value = csv_data.get(key)
        if value in (None, ""):
            continue
        try:
            measures[key] = float(value)
        except ValueError:
            continue
    return measures


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


class Handler(BaseHTTPRequestHandler):
    controller: Controller

    def do_GET(self) -> None:
        if self.path in {"/", "/status"}:
            self.respond(self.controller.status())
            return
        if self.path == "/health":
            self.respond({"ok": True, "service": "standalone-macmini-uploader", **self.controller.status()})
            return
        self.respond({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path == "/control/start":
            self.respond(self.controller.start())
            return
        if self.path == "/control/stop":
            self.respond(self.controller.stop())
            return
        if self.path == "/control/restart":
            self.respond(self.controller.restart())
            return
        if self.path == "/scan-once":
            self.respond(self.controller.scan_once())
            return
        self.respond({"error": "not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} {format % args}")

    def respond(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Oracle Mac mini Firebase uploader.")
    parser.add_argument("--session-root", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--host", default=os.getenv("NEJE_UPLOADER_AGENT_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NEJE_UPLOADER_AGENT_PORT", "8790")))
    args = parser.parse_args()

    settings = Settings(
        session_root=Path(args.session_root).expanduser().resolve(),
        runtime_dir=Path(args.runtime_dir).expanduser().resolve(),
        project_id=os.environ["NEJE_FIREBASE_PROJECT_ID"],
        storage_bucket=os.environ["NEJE_FIREBASE_STORAGE_BUCKET"],
        credentials_path=Path(os.environ["NEJE_FIREBASE_CREDENTIALS"]).expanduser().resolve(),
        gallery_base_url=os.getenv("NEJE_GALLERY_BASE_URL", "https://berlogabob.github.io/OracleGallery"),
        ready_marker_name=os.getenv("NEJE_UPLOADER_READY_MARKER", "READY"),
        require_ready_marker=env_bool("NEJE_UPLOADER_REQUIRE_READY_MARKER", False),
        stability_seconds=env_float("NEJE_UPLOADER_STABILITY_SECONDS", 8.0),
        poll_seconds=env_float("NEJE_UPLOADER_POLL_SECONDS", 2.0),
    )
    controller = Controller(Uploader(settings), settings)
    controller.started_at = datetime.now(tz=UTC)
    controller.uploader.store.set_run_started_at(controller.started_at)
    Handler.controller = controller
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Standalone Mac mini uploader agent: http://{args.host}:{args.port}/")
    print(f"Watching session folder: {settings.session_root}")
    print(f"Firebase project: {settings.project_id}")
    print(f"Launch baseline: {controller.started_at.isoformat()}")
    print("Waiting for NEJE GUI /control/start or manual /scan-once.")
    server.serve_forever()


if __name__ == "__main__":
    main()
PY
}

create_default_config
set -a
source "$CONFIG_FILE"
set +a
repair_firebase_credentials_config

PYTHON_BIN="$(find_python)" || fail "python3 was not found. Install Python 3 first."
[[ -n "${NEJE_FIREBASE_PROJECT_ID:-}" ]] || fail "NEJE_FIREBASE_PROJECT_ID is empty in $CONFIG_FILE"
[[ -n "${NEJE_FIREBASE_STORAGE_BUCKET:-}" ]] || fail "NEJE_FIREBASE_STORAGE_BUCKET is empty in $CONFIG_FILE"
[[ -n "${NEJE_FIREBASE_CREDENTIALS:-}" ]] || fail "NEJE_FIREBASE_CREDENTIALS is empty in $CONFIG_FILE"
ensure_firebase_credentials

mkdir -p "$RUNTIME_DIR"
write_python_app

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Could not create private Python environment."
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null || fail "Could not upgrade pip."
"$VENV_DIR/bin/python" -m pip install "firebase-admin>=6.7.0" "qrcode[pil]>=8.0" >/dev/null || fail "Could not install uploader dependencies."

clear || true
echo "========================================"
echo "  Standalone Oracle Mac mini Uploader"
echo "========================================"
echo "Sessions folder: $SCRIPT_DIR"
echo "Runtime folder:  $RUNTIME_DIR"
echo "Config file:     $CONFIG_FILE"
echo "Firebase:        $NEJE_FIREBASE_PROJECT_ID / $NEJE_FIREBASE_STORAGE_BUCKET"
echo "Agent:           http://${NEJE_UPLOADER_AGENT_HOST:-0.0.0.0}:${NEJE_UPLOADER_AGENT_PORT:-8790}/"
echo
echo "Leave this window open."
echo "The uploader starts scanning when NEJE GUI sends Start, or when /scan-once is called."
echo

"$VENV_DIR/bin/python" "$APP_FILE" \
  --session-root "$SCRIPT_DIR" \
  --runtime-dir "$RUNTIME_DIR" \
  --host "${NEJE_UPLOADER_AGENT_HOST:-0.0.0.0}" \
  --port "${NEJE_UPLOADER_AGENT_PORT:-8790}"

exit_code=$?
echo
echo "Standalone Mac mini uploader stopped with exit code $exit_code."
pause
exit "$exit_code"
