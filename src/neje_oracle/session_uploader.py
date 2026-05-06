from __future__ import annotations

import ast
import csv
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import qrcode

from .config import FirebaseSettings, UploaderSettings, _repo_root, ensure_dir
from .firebase_io import FirebaseRemoteRepository, record_to_json
from .models import PlotStatus, PublicStatus, SessionRecord
from .store import UploaderStore
from .svg_normalizer import normalize_svg_file, scale_for_mark_name


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
            if row and row["public_status"] == PublicStatus.PUBLISHED.value and row["public_receipt_path"]:
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
            staged_record.public_receipt_path = publication.public_receipt_path
            staged_record.public_qr_path = publication.public_qr_path
            staged_record.public_manifest_path = publication.public_manifest_path
            staged_record.public_svg_url = publication.public_svg_url
            staged_record.public_receipt_url = publication.public_receipt_url
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
        return self._resolve_svg_source(session_dir) is not None and self._resolve_receipt_source(session_dir) is not None

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

        svg_source = self._resolve_svg_source(session_dir)
        receipt_source = self._resolve_receipt_source(session_dir)
        if svg_source is None or receipt_source is None:
            raise FileNotFoundError(f"Missing SVG or receipt TXT asset in {session_dir}")

        receipt_data = self._parse_receipt_txt(receipt_source)
        csv_data = self._load_csv_metadata(session_id)
        safe_metadata = self._safe_metadata(metadata, receipt_data, csv_data)
        created_at = self._resolve_created_at(session_dir, safe_metadata)
        mark_name = receipt_data.get("mark_name") or csv_data.get("mark_name") or ""
        oracle_text = receipt_data.get("oracle_text") or csv_data.get("oracle_text") or ""
        themes = self._resolve_themes(receipt_data, csv_data)
        measures = self._resolve_measures(csv_data)

        raw_svg_target = public_dir / "artwork_raw.svg"
        svg_target = public_dir / "artwork.svg"
        receipt_target = public_dir / "receipt.txt"
        shutil.copy2(svg_source, raw_svg_target)
        svg_scale = scale_for_mark_name(
            mark_name,
            _repo_root() / "assets" / "symbols",
            _repo_root() / "assets" / "symbols" / "symbol_scales.json",
        )
        svg_target.write_text(
            normalize_svg_file(svg_source, marker_kind="user", scale=svg_scale, include_rings=False),
            encoding="utf-8",
        )
        shutil.copy2(receipt_source, receipt_target)
        safe_metadata.update(
            {
                "svgNormalized": True,
                "svgScale": svg_scale,
                "rawSvgFile": raw_svg_target.name,
            }
        )

        qr_url = f"{self.firebase_settings.gallery_base_url.rstrip('/')}/#/session/{quote(session_id)}"
        qr_target = public_dir / "qr.png"
        qrcode.make(qr_url).save(qr_target)
        record = SessionRecord(
            session_id=session_id,
            created_at=created_at,
            title=mark_name or safe_metadata.get("title") or session_id.replace("_", " "),
            summary=oracle_text or safe_metadata.get("summary") or "",
            source_dir=session_dir,
            svg_file=svg_target,
            receipt_file=receipt_target,
            qr_file=qr_target,
            qr_url=qr_url,
            public_status=PublicStatus.PUBLISHING,
            plot_status=PlotStatus.PENDING,
            mark_name=mark_name,
            oracle_text=oracle_text,
            themes=themes,
            measures=measures,
            extra_metadata=safe_metadata,
        )
        self._write_manifest(record)
        return record

    def _resolve_svg_source(self, session_dir: Path) -> Path | None:
        candidates = [
            session_dir / f"{session_dir.name}_plotter.svg",
        ]
        candidates.extend(sorted(session_dir.glob("*_plotter.svg")))
        return next((path for path in candidates if path.exists()), None)

    def _resolve_receipt_source(self, session_dir: Path) -> Path | None:
        candidates = [
            session_dir / f"{session_dir.name}_receipt.txt",
        ]
        candidates.extend(sorted(session_dir.glob("*_receipt.txt")))
        return next((path for path in candidates if path.exists()), None)

    def _resolve_created_at(self, session_dir: Path, metadata: dict[str, Any]) -> datetime:
        raw = metadata.get("created_at") or metadata.get("timestamp")
        if raw:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return datetime.fromtimestamp(session_dir.stat().st_mtime, tz=UTC)

    def _write_manifest(self, record: SessionRecord) -> None:
        (record.qr_file.parent / "manifest.json").write_text(
            record_to_json(record),
            encoding="utf-8",
        )

    def _parse_receipt_txt(self, receipt_path: Path) -> dict[str, Any]:
        data: dict[str, Any] = {"mark_name": "", "oracle_text": "", "themes": []}
        for raw_line in receipt_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("╔", "║", "╠", "╚")):
                continue
            if line.lower().startswith("your symbol:"):
                data["mark_name"] = line.split(":", 1)[1].strip()
                continue
            if line.lower().startswith("themes:"):
                data["themes"] = self._parse_themes(line.split(":", 1)[1].strip())
                continue
            if not data["oracle_text"]:
                data["oracle_text"] = line
        return data

    def _load_csv_metadata(self, session_id: str) -> dict[str, Any]:
        csv_path = self.settings.session_root / "session_log.csv"
        if not csv_path.exists():
            return {}
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("session_id") == session_id:
                    return {
                        "timestamp": row.get("timestamp", ""),
                        "mark_name": (row.get("symbol") or "").strip().upper(),
                        "oracle_text": (row.get("reply_text") or "").strip(),
                        "themes": self._parse_themes(row.get("keywords", "")),
                        "intensity": row.get("intensity", ""),
                        "instability": row.get("instability", ""),
                        "confidence": row.get("confidence", ""),
                    }
        return {}

    def _safe_metadata(
        self,
        metadata: dict[str, Any],
        receipt_data: dict[str, Any],
        csv_data: dict[str, Any],
    ) -> dict[str, Any]:
        safe = {
            key: value
            for key, value in metadata.items()
            if key not in {"transcript", "visitor", "audio", "visitor_image", "visitor_photo"}
        }
        safe.update(
            {
                "markName": receipt_data.get("mark_name") or csv_data.get("mark_name", ""),
                "oracleText": receipt_data.get("oracle_text") or csv_data.get("oracle_text", ""),
                "themes": self._resolve_themes(receipt_data, csv_data),
                "measures": self._resolve_measures(csv_data),
            }
        )
        if csv_data.get("timestamp"):
            safe["timestamp"] = csv_data["timestamp"]
        return safe

    def _resolve_themes(self, receipt_data: dict[str, Any], csv_data: dict[str, Any]) -> list[str]:
        themes = receipt_data.get("themes") or csv_data.get("themes") or []
        return [str(theme).strip() for theme in themes if str(theme).strip()]

    def _resolve_measures(self, csv_data: dict[str, Any]) -> dict[str, float]:
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

    def _parse_themes(self, raw: Any) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        try:
            parsed = ast.literal_eval(str(raw))
        except (SyntaxError, ValueError):
            parsed = [part.strip() for part in str(raw).split(",")]
        if isinstance(parsed, list):
            return [str(item).strip().strip("'\"") for item in parsed if str(item).strip()]
        return [str(parsed).strip()]
