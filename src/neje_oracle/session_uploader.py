from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import qrcode

from .config import FirebaseSettings, UploaderSettings, ensure_dir
from .firebase_io import FirebaseRemoteRepository, record_to_json
from .models import PlotStatus, PublicStatus, SessionRecord
from .store import UploaderStore


class SessionUploader:
    def __init__(
        self,
        settings: UploaderSettings,
        firebase_settings: FirebaseSettings,
        store: UploaderStore,
        remote: FirebaseRemoteRepository,
    ) -> None:
        self.settings = settings
        self.firebase_settings = firebase_settings
        self.store = store
        self.remote = remote
        ensure_dir(self.settings.session_root)
        ensure_dir(self.settings.public_root)

    def scan_once(self) -> list[str]:
        imported: list[str] = []
        for session_dir in sorted(path for path in self.settings.session_root.iterdir() if path.is_dir()):
            row = self.store.get_session_by_source(session_dir)
            if row and row["public_status"] == PublicStatus.PUBLISHED.value:
                continue
            if not self._is_ready(session_dir):
                continue
            imported.append(self.process_session(session_dir))
        return imported

    def process_session(self, session_dir: Path) -> str:
        session_id = session_dir.name
        metadata = self._load_metadata(session_dir)
        staged_record = self._stage_public_assets(session_dir, metadata)
        try:
            publication = self.remote.publish_session(staged_record, staged_record.qr_file.parent)
            staged_record.public_status = publication.public_status
            staged_record.public_svg_path = publication.public_svg_path
            staged_record.public_preview_path = publication.public_preview_path
            staged_record.public_qr_path = publication.public_qr_path
            staged_record.public_svg_url = publication.public_svg_url
            staged_record.public_preview_url = publication.public_preview_url
            staged_record.public_qr_url = publication.public_qr_url
            staged_record.plot_status = PlotStatus.PENDING
            staged_record.last_error = ""
        except Exception as exc:  # noqa: BLE001
            staged_record.public_status = PublicStatus.FAILED
            staged_record.last_error = str(exc)
        self._write_manifest(staged_record)
        self.store.upsert_session(staged_record)
        return session_id

    def _is_ready(self, session_dir: Path) -> bool:
        ready_marker = session_dir / self.settings.ready_marker_name
        if ready_marker.exists():
            return self._has_required_assets(session_dir)
        if self.settings.require_ready_marker:
            return False
        if not self._has_required_assets(session_dir):
            return False
        newest_mtime = max(path.stat().st_mtime for path in session_dir.rglob("*") if path.is_file())
        return (time.time() - newest_mtime) >= self.settings.stability_seconds

    def _has_required_assets(self, session_dir: Path) -> bool:
        return (session_dir / "artwork.svg").exists() and (session_dir / "preview.png").exists()

    def _load_metadata(self, session_dir: Path) -> dict[str, Any]:
        for candidate in ("metadata.json", "session.json"):
            path = session_dir / candidate
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _stage_public_assets(self, session_dir: Path, metadata: dict[str, Any]) -> SessionRecord:
        session_id = session_dir.name
        public_dir = self.settings.public_root / session_id
        ensure_dir(public_dir)

        svg_source = session_dir / "artwork.svg"
        preview_source = session_dir / "preview.png"
        svg_target = public_dir / "artwork.svg"
        preview_target = public_dir / "preview.png"
        shutil.copy2(svg_source, svg_target)
        shutil.copy2(preview_source, preview_target)

        qr_url = f"{self.firebase_settings.gallery_base_url.rstrip('/')}/#/session/{quote(session_id)}"
        qr_target = public_dir / "qr.png"
        qrcode.make(qr_url).save(qr_target)

        created_at = self._resolve_created_at(session_dir, metadata)
        record = SessionRecord(
            session_id=session_id,
            created_at=created_at,
            title=metadata.get("title") or session_id.replace("_", " "),
            summary=metadata.get("summary") or "",
            source_dir=session_dir,
            svg_file=svg_target,
            preview_file=preview_target,
            qr_file=qr_target,
            qr_url=qr_url,
            public_status=PublicStatus.PUBLISHING,
            plot_status=PlotStatus.PENDING,
            extra_metadata=metadata,
        )
        self._write_manifest(record)
        return record

    def _resolve_created_at(self, session_dir: Path, metadata: dict[str, Any]) -> datetime:
        raw = metadata.get("created_at")
        if raw:
            return datetime.fromisoformat(raw)
        return datetime.fromtimestamp(session_dir.stat().st_mtime, tz=UTC)

    def _write_manifest(self, record: SessionRecord) -> None:
        (record.qr_file.parent / "manifest.json").write_text(
            record_to_json(record),
            encoding="utf-8",
        )
