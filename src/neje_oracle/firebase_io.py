from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import firebase_admin
from firebase_admin import credentials, firestore, storage

from .config import FirebaseSettings
from .models import PlotJobLease, PlotStatus, PublicationResult, PublicStatus, SessionRecord
from .origin_markers import classify_session_origin, normalize_origin, normalize_tags, origin_allowed


class FirebaseRemoteRepository:
    def __init__(self, settings: FirebaseSettings) -> None:
        if not settings.enabled:
            raise RuntimeError(
                "Firebase Admin is not configured. Set NEJE_FIREBASE_CREDENTIALS to a service account JSON. "
                "Project/bucket can come from NEJE_FIREBASE_* or FIREBASE_PROJECT_ID."
            )
        self.settings = settings
        app_name = f"neje-oracle-{settings.project_id}"
        try:
            self._app = firebase_admin.get_app(app_name)
        except ValueError:
            cred = credentials.Certificate(str(settings.credentials_path))
            self._app = firebase_admin.initialize_app(
                cred,
                {
                    "projectId": settings.project_id,
                    "storageBucket": settings.storage_bucket,
                },
                name=app_name,
            )
        self._db = firestore.client(app=self._app)
        self._bucket = storage.bucket(app=self._app)

    def publish_session(self, record: SessionRecord, public_dir: Path) -> PublicationResult:
        remote_root = f"sessions/{record.session_id}"
        svg_blob = self._bucket.blob(f"{remote_root}/artwork.svg")
        receipt_blob = self._bucket.blob(f"{remote_root}/receipt.txt")
        qr_blob = self._bucket.blob(f"{remote_root}/qr.png")
        manifest_blob = self._bucket.blob(f"{remote_root}/manifest.json")
        raw_svg_path = public_dir / "artwork_raw.svg"
        raw_svg_storage_path = f"{remote_root}/artwork_raw.svg"

        svg_blob.upload_from_filename(str(public_dir / "artwork.svg"), content_type="image/svg+xml")
        receipt_blob.upload_from_filename(str(public_dir / "receipt.txt"), content_type="text/plain; charset=utf-8")
        qr_blob.upload_from_filename(str(public_dir / "qr.png"), content_type="image/png")
        if raw_svg_path.exists():
            self._bucket.blob(raw_svg_storage_path).upload_from_filename(str(raw_svg_path), content_type="image/svg+xml")

        svg_version = _file_hash(public_dir / "artwork.svg")
        svg_url = self._public_storage_url(f"{remote_root}/artwork.svg", version=svg_version)
        receipt_url = self._public_storage_url(f"{remote_root}/receipt.txt")
        qr_image_url = self._public_storage_url(f"{remote_root}/qr.png")

        record.public_status = PublicStatus.PUBLISHED
        record.plot_status = PlotStatus.PENDING
        record.public_svg_path = f"{remote_root}/artwork.svg"
        record.public_receipt_path = f"{remote_root}/receipt.txt"
        record.public_qr_path = f"{remote_root}/qr.png"
        record.public_manifest_path = f"{remote_root}/manifest.json"
        record.public_svg_url = svg_url
        record.public_receipt_url = receipt_url
        record.public_qr_url = qr_image_url
        record.last_error = ""

        classification = classify_session_origin(record.extra_metadata)
        origin = classification.origin
        tags = classification.tags
        visible_in_library = classification.visible_in_library
        record.extra_metadata = {
            **record.extra_metadata,
            "origin": origin,
            "tags": tags,
            "visibleInLibrary": visible_in_library,
        }

        manifest_blob.upload_from_string(
            record_to_json(record),
            content_type="application/json",
        )

        session_ref = self._db.collection("sessions").document(record.session_id)
        session_ref.set(
            {
                "sessionId": record.session_id,
                "createdAt": record.created_at.isoformat(),
                "title": record.title,
                "summary": record.summary,
                "status": PublicStatus.PUBLISHED.value,
                "plotStatus": PlotStatus.PENDING.value,
                "priority": record.priority,
                "sessionUrl": record.qr_url,
                "qrUrl": record.qr_url,
                "qrImageUrl": qr_image_url,
                "svgUrl": svg_url,
                "receiptUrl": receipt_url,
                "markName": record.mark_name,
                "oracleText": record.oracle_text,
                "themes": record.themes,
                "measures": record.measures,
                "assetUrls": {
                    "svg": svg_url,
                    "qr": qr_image_url,
                    "receipt": receipt_url,
                },
                "assetPaths": {
                    "svg": f"{remote_root}/artwork.svg",
                    "qr": f"{remote_root}/qr.png",
                    "receipt": f"{remote_root}/receipt.txt",
                    "manifest": f"{remote_root}/manifest.json",
                    "rawSvg": raw_svg_storage_path if raw_svg_path.exists() else "",
                },
                "svgVersion": svg_version,
                "metadata": record.extra_metadata,
                "origin": origin,
                "tags": tags,
                "visibleInLibrary": visible_in_library,
            },
            merge=True,
        )
        session_ref.update(
            {
                "previewUrl": firestore.DELETE_FIELD,
                "assetUrls.preview": firestore.DELETE_FIELD,
                "assetPaths.preview": firestore.DELETE_FIELD,
            }
        )
        plot_job_ref = self._db.collection("plot_jobs").document(record.session_id)
        plot_job_ref.set(
            {
                "sessionId": record.session_id,
                "title": record.title,
                "summary": record.summary,
                "createdAt": record.created_at.isoformat(),
                "status": PlotStatus.PENDING.value,
                "priority": record.priority,
                "queue": "user",
                "consumerId": "",
                "sheetId": "",
                "sheetIndex": -1,
                "error": "",
                "svgStoragePath": f"{remote_root}/artwork.svg",
                "svgUrl": svg_url,
                "origin": origin,
                "tags": tags,
                "visibleInQueue": True,
            },
            merge=True,
        )
        plot_job_ref.update({"previewUrl": firestore.DELETE_FIELD})

        return PublicationResult(
            public_status=PublicStatus.PUBLISHED,
            public_svg_path=f"{remote_root}/artwork.svg",
            public_receipt_path=f"{remote_root}/receipt.txt",
            public_qr_path=f"{remote_root}/qr.png",
            public_manifest_path=f"{remote_root}/manifest.json",
            public_svg_url=svg_url,
            public_receipt_url=receipt_url,
            public_qr_url=qr_image_url,
        )

    def claim_next_plot_job(
        self,
        consumer_id: str,
        *,
        run_started_at: datetime | None = None,
        allowed_origins: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> PlotJobLease | None:
        query = (
            self._db.collection("plot_jobs")
            .where("status", "==", PlotStatus.PENDING.value)
            .order_by("createdAt")
            .limit(25)
        )
        docs = list(query.stream())
        if not docs:
            return None
        doc = None
        payload = None
        for candidate in docs:
            candidate_payload = candidate.to_dict()
            if candidate_payload.get("visibleInQueue") is False:
                continue
            if run_started_at is not None and recorded_datetime(candidate_payload.get("createdAt")) < run_started_at:
                self._mark_plot_job_skipped(candidate, candidate_payload, reason="before_run_started_at")
                continue
            candidate_origin = normalize_origin(candidate_payload.get("origin"))
            if not origin_allowed(candidate_origin, allowed_origins):
                continue
            doc = candidate
            payload = candidate_payload
            break
        if doc is None or payload is None:
            return None
        doc.reference.update(
            {
                "status": PlotStatus.LEASED.value,
                "consumerId": consumer_id,
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "error": "",
            }
        )
        self._db.collection("sessions").document(doc.id).set(
            {
                "plotStatus": PlotStatus.LEASED.value,
            },
            merge=True,
        )
        return PlotJobLease(
            session_id=payload["sessionId"],
            title=payload.get("title", payload["sessionId"]),
            summary=payload.get("summary", ""),
            created_at=recorded_datetime(payload.get("createdAt")),
            priority=payload.get("priority", "user"),
            queue=payload.get("queue", "user"),
            svg_storage_path=payload.get("svgStoragePath", ""),
            svg_url=payload.get("svgUrl", ""),
            origin=normalize_origin(payload.get("origin")),
            tags=normalize_tags(payload.get("tags")),
            visible_in_queue=payload.get("visibleInQueue") is not False,
        )

    def skip_pending_before(self, cutoff: datetime, *, reason: str = "before_run_started_at") -> int:
        query = (
            self._db.collection("plot_jobs")
            .where("status", "==", PlotStatus.PENDING.value)
            .order_by("createdAt")
            .limit(500)
        )
        skipped = 0
        for doc in query.stream():
            payload = doc.to_dict()
            if recorded_datetime(payload.get("createdAt")) >= cutoff:
                continue
            self._mark_plot_job_skipped(doc, payload, reason=reason)
            skipped += 1
        return skipped

    def get_plot_job_counts(self, *, run_started_at: datetime | None = None, limit: int = 500) -> dict[str, int | str | bool]:
        docs = list(self._db.collection("plot_jobs").limit(limit).stream())
        return summarize_plot_job_counts(
            [doc.to_dict() or {} for doc in docs],
            run_started_at=run_started_at,
            limited_to=limit,
        )

    def _mark_plot_job_skipped(self, doc, payload: dict, *, reason: str) -> None:
        tags = list(payload.get("tags") or [])
        if "baseline_skipped" not in tags:
            tags.append("baseline_skipped")
        doc.reference.set(
            {
                "status": PlotStatus.SKIPPED.value,
                "tags": tags,
                "skipReason": reason,
                "visibleInQueue": False,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        self._db.collection("sessions").document(doc.id).set(
            {
                "plotStatus": PlotStatus.SKIPPED.value,
                "tags": tags,
                "skipReason": reason,
                "visibleInQueue": False,
            },
            merge=True,
        )

    def update_plot_job(
        self,
        session_id: str,
        status: PlotStatus,
        *,
        sheet_id: str = "",
        sheet_index: int | None = None,
        error: str = "",
    ) -> None:
        update_payload = {
            "status": status.value,
            "sheetId": sheet_id,
            "error": error,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
        session_payload = {
            "plotStatus": status.value,
        }
        if sheet_index is not None:
            update_payload["sheetIndex"] = sheet_index
            session_payload["sheetIndex"] = sheet_index
        if sheet_id:
            session_payload["sheetId"] = sheet_id
        self._db.collection("plot_jobs").document(session_id).set(
            update_payload,
            merge=True,
        )
        self._db.collection("sessions").document(session_id).set(
            session_payload,
            merge=True,
        )

    def download_asset(self, storage_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._bucket.blob(storage_path).download_to_filename(str(destination))

    def upload_asset(self, storage_path: str, source: Path, *, content_type: str) -> None:
        self._bucket.blob(storage_path).upload_from_filename(str(source), content_type=content_type)

    def storage_asset_exists(self, storage_path: str) -> bool:
        return self._bucket.blob(storage_path).exists()

    def iter_sessions(self, *, limit: int | None = None, session_id: str | None = None):
        if session_id:
            doc = self._db.collection("sessions").document(session_id).get()
            if not doc.exists:
                return []
            payload = doc.to_dict() or {}
            payload["_id"] = doc.id
            return [payload]
        query = self._db.collection("sessions").order_by("createdAt")
        if limit:
            query = query.limit(limit)
        rows = []
        for doc in query.stream():
            payload = doc.to_dict() or {}
            payload["_id"] = doc.id
            rows.append(payload)
        return rows

    def update_normalized_svg(
        self,
        session_id: str,
        *,
        svg_storage_path: str,
        raw_svg_storage_path: str,
        svg_version: str,
    ) -> str:
        svg_url = self._public_storage_url(svg_storage_path, version=svg_version)
        self._db.collection("sessions").document(session_id).set(
            {
                "svgUrl": svg_url,
                "assetUrls": {"svg": svg_url},
                "assetPaths": {"svg": svg_storage_path, "rawSvg": raw_svg_storage_path},
                "svgVersion": svg_version,
                "metadata": {"svgNormalized": True},
            },
            merge=True,
        )
        self._db.collection("plot_jobs").document(session_id).set(
            {
                "svgStoragePath": svg_storage_path,
                "svgUrl": svg_url,
            },
            merge=True,
        )
        return svg_url

    def public_storage_url(self, storage_path: str, *, version: str | None = None) -> str:
        return self._public_storage_url(storage_path, version=version)

    def _public_storage_url(self, storage_path: str, *, version: str | None = None) -> str:
        encoded_path = quote(storage_path, safe="")
        url = f"https://firebasestorage.googleapis.com/v0/b/{self.settings.storage_bucket}/o/{encoded_path}?alt=media"
        if version:
            return f"{url}&v={quote(version, safe='')}"
        return url


def recorded_datetime(value):
    from datetime import UTC, datetime

    if not value:
        return datetime.now(tz=UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if hasattr(value, "isoformat"):
        raw = value.isoformat()
    else:
        raw = str(value)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def summarize_plot_job_counts(
    payloads: list[dict],
    *,
    run_started_at: datetime | None = None,
    limited_to: int | None = None,
) -> dict[str, int | str | bool]:
    counts: dict[str, int | str | bool] = {
        "online": True,
        "total": len(payloads),
        "limitedTo": limited_to or 0,
        "pending": 0,
        "pendingAfterBaseline": 0,
        "pendingBeforeBaseline": 0,
        "leased": 0,
        "plotting": 0,
        "printed": 0,
        "failed": 0,
        "skipped": 0,
        "hidden": 0,
        "unknown": 0,
        "message": "Queue counts loaded",
    }
    known_statuses = {status.value for status in PlotStatus}
    for payload in payloads:
        status = str(payload.get("status") or "unknown")
        if status not in known_statuses:
            status = "unknown"
        counts[status] = int(counts.get(status, 0)) + 1
        visible = payload.get("visibleInQueue") is not False
        if not visible:
            counts["hidden"] = int(counts["hidden"]) + 1
        if status == PlotStatus.PENDING.value:
            created_at = recorded_datetime(payload.get("createdAt"))
            if run_started_at is not None and created_at < run_started_at:
                counts["pendingBeforeBaseline"] = int(counts["pendingBeforeBaseline"]) + 1
            elif visible:
                counts["pendingAfterBaseline"] = int(counts["pendingAfterBaseline"]) + 1
    return counts


def record_to_json(record: SessionRecord) -> str:
    import json

    return json.dumps(record.to_manifest_dict(), ensure_ascii=False, indent=2)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]
