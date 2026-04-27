from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import firebase_admin
from firebase_admin import credentials, firestore, storage

from .config import FirebaseSettings
from .models import PlotJobLease, PlotStatus, PublicationResult, PublicStatus, SessionRecord


class FirebaseRemoteRepository:
    def __init__(self, settings: FirebaseSettings) -> None:
        if not settings.enabled:
            raise RuntimeError("Firebase is not configured. Check NEJE_FIREBASE_* environment variables.")
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
        preview_blob = self._bucket.blob(f"{remote_root}/preview.png")
        qr_blob = self._bucket.blob(f"{remote_root}/qr.png")
        manifest_blob = self._bucket.blob(f"{remote_root}/manifest.json")

        svg_blob.upload_from_filename(str(public_dir / "artwork.svg"), content_type="image/svg+xml")
        preview_blob.upload_from_filename(str(public_dir / "preview.png"), content_type="image/png")
        qr_blob.upload_from_filename(str(public_dir / "qr.png"), content_type="image/png")

        svg_url = self._public_storage_url(f"{remote_root}/artwork.svg")
        preview_url = self._public_storage_url(f"{remote_root}/preview.png")
        qr_url = self._public_storage_url(f"{remote_root}/qr.png")

        record.public_status = PublicStatus.PUBLISHED
        record.plot_status = PlotStatus.PENDING
        record.public_svg_path = f"{remote_root}/artwork.svg"
        record.public_preview_path = f"{remote_root}/preview.png"
        record.public_qr_path = f"{remote_root}/qr.png"
        record.public_svg_url = svg_url
        record.public_preview_url = preview_url
        record.public_qr_url = qr_url
        record.last_error = ""

        manifest_blob.upload_from_string(
            record_to_json(record),
            content_type="application/json",
        )

        self._db.collection("sessions").document(record.session_id).set(
            {
                "sessionId": record.session_id,
                "createdAt": record.created_at.isoformat(),
                "title": record.title,
                "summary": record.summary,
                "status": PublicStatus.PUBLISHED.value,
                "plotStatus": PlotStatus.PENDING.value,
                "priority": record.priority,
                "qrUrl": record.qr_url,
                "previewUrl": preview_url,
                "svgUrl": svg_url,
                "assetUrls": {
                    "preview": preview_url,
                    "svg": svg_url,
                    "qr": qr_url,
                },
                "assetPaths": {
                    "preview": f"{remote_root}/preview.png",
                    "svg": f"{remote_root}/artwork.svg",
                    "qr": f"{remote_root}/qr.png",
                    "manifest": f"{remote_root}/manifest.json",
                },
                "metadata": record.extra_metadata,
            },
            merge=True,
        )
        self._db.collection("plot_jobs").document(record.session_id).set(
            {
                "sessionId": record.session_id,
                "title": record.title,
                "summary": record.summary,
                "createdAt": record.created_at.isoformat(),
                "status": PlotStatus.PENDING.value,
                "priority": record.priority,
                "consumerId": "",
                "sheetId": "",
                "error": "",
                "svgStoragePath": f"{remote_root}/artwork.svg",
                "svgUrl": svg_url,
                "previewUrl": preview_url,
            },
            merge=True,
        )

        return PublicationResult(
            public_status=PublicStatus.PUBLISHED,
            public_svg_path=f"{remote_root}/artwork.svg",
            public_preview_path=f"{remote_root}/preview.png",
            public_qr_path=f"{remote_root}/qr.png",
            public_svg_url=svg_url,
            public_preview_url=preview_url,
            public_qr_url=qr_url,
        )

    def claim_next_plot_job(self, consumer_id: str) -> PlotJobLease | None:
        query = (
            self._db.collection("plot_jobs")
            .where("status", "==", PlotStatus.PENDING.value)
            .order_by("createdAt")
            .limit(1)
        )
        docs = list(query.stream())
        if not docs:
            return None
        doc = docs[0]
        payload = doc.to_dict()
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
            svg_storage_path=payload.get("svgStoragePath", ""),
            svg_url=payload.get("svgUrl", ""),
            preview_url=payload.get("previewUrl", ""),
        )

    def update_plot_job(self, session_id: str, status: PlotStatus, *, sheet_id: str = "", error: str = "") -> None:
        self._db.collection("plot_jobs").document(session_id).set(
            {
                "status": status.value,
                "sheetId": sheet_id,
                "error": error,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        self._db.collection("sessions").document(session_id).set(
            {
                "plotStatus": status.value,
            },
            merge=True,
        )

    def download_asset(self, storage_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._bucket.blob(storage_path).download_to_filename(str(destination))

    def _public_storage_url(self, storage_path: str) -> str:
        encoded_path = quote(storage_path, safe="")
        return f"https://firebasestorage.googleapis.com/v0/b/{self.settings.storage_bucket}/o/{encoded_path}?alt=media"


def recorded_datetime(value: str | None):
    from datetime import UTC, datetime

    if not value:
        return datetime.now(tz=UTC)
    return datetime.fromisoformat(value)


def record_to_json(record: SessionRecord) -> str:
    import json

    return json.dumps(record.to_manifest_dict(), ensure_ascii=False, indent=2)
