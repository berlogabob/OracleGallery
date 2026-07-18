from __future__ import annotations

import os
from pathlib import Path

from neje_oracle.shared.config import FirebaseSettings, UploaderSettings
from datetime import UTC, datetime

from neje_oracle.blocks.firebase.repository import FirebaseRemoteRepository
from neje_oracle.shared.models import PlotStatus, PublicationResult, PublicStatus, SessionRecord
from neje_oracle.blocks.macmini.session_uploader import SessionUploader
from neje_oracle.shared.store import UploaderStore


class FakeRemoteRepository:
    def __init__(self, *, fail_qr_download: bool = False) -> None:
        self.publish_calls: list[str] = []
        self.download_calls: list[tuple[str, Path]] = []
        self.fail_qr_download = fail_qr_download

    def publish_session(self, record, public_dir: Path) -> PublicationResult:
        self.publish_calls.append(record.session_id)
        assert (public_dir / "artwork.svg").exists()
        assert (public_dir / "artwork_raw.svg").exists()
        assert (public_dir / "receipt.txt").exists()
        assert (public_dir / "qr.png").exists()
        assert not (public_dir / "preview.png").exists()
        assert record.qr_url == f"https://example.github.io/gallery/#/session/{record.session_id}"
        return PublicationResult(
            public_status=PublicStatus.PUBLISHED,
            public_svg_path=f"sessions/{record.session_id}/artwork.svg",
            public_receipt_path=f"sessions/{record.session_id}/receipt.txt",
            public_qr_path=f"sessions/{record.session_id}/qr.png",
            public_manifest_path=f"sessions/{record.session_id}/manifest.json",
            public_svg_url=f"https://example.test/{record.session_id}/artwork.svg",
            public_receipt_url=f"https://example.test/{record.session_id}/receipt.txt",
            public_qr_url=f"https://example.test/{record.session_id}/qr.png",
        )

    def download_asset(self, storage_path: str, destination: Path) -> None:
        self.download_calls.append((storage_path, destination))
        if self.fail_qr_download:
            raise RuntimeError("QR download failed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(f"firebase:{storage_path}".encode("utf-8"))


class FakeBlob:
    def __init__(self, path: str) -> None:
        self.path = path
        self.uploads: list[tuple[str, str | None]] = []

    def upload_from_filename(self, filename: str, content_type: str | None = None) -> None:
        self.uploads.append((filename, content_type))

    def upload_from_string(self, payload: str, content_type: str | None = None) -> None:
        self.uploads.append((payload, content_type))

    def download_to_filename(self, filename: str) -> None:
        Path(filename).write_bytes(f"firebase:{self.path}".encode("utf-8"))


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, path: str) -> FakeBlob:
        self.blobs.setdefault(path, FakeBlob(path))
        return self.blobs[path]


class FakeDocRef:
    def __init__(self, doc_id: str) -> None:
        self.id = doc_id
        self.set_calls: list[dict] = []
        self.update_calls: list[dict] = []

    def set(self, payload: dict, merge: bool = False) -> None:
        self.set_calls.append(payload)

    def update(self, payload: dict) -> None:
        self.update_calls.append(payload)

    @property
    def reference(self):
        return self

    def to_dict(self) -> dict:
        payload: dict = {}
        for set_payload in self.set_calls:
            payload.update(set_payload)
        for update_payload in self.update_calls:
            payload.update(update_payload)
        return payload


class FakeQuery:
    def __init__(self, docs: list[FakeDocRef]) -> None:
        self.docs = docs
        self.filters: list[tuple[str, str, object]] = []
        self.order_field = ""
        self.limit_count: int | None = None

    def where(self, field: str, operator: str, value: object):
        self.filters.append((field, operator, value))
        return self

    def order_by(self, field: str):
        self.order_field = field
        return self

    def limit(self, count: int):
        self.limit_count = count
        return self

    def stream(self):
        docs = self.docs
        for field, operator, value in self.filters:
            assert operator == "=="
            docs = [doc for doc in docs if doc.to_dict().get(field) == value]
        if self.order_field:
            docs = sorted(docs, key=lambda doc: doc.to_dict().get(self.order_field, ""))
        if self.limit_count is not None:
            docs = docs[: self.limit_count]
        return docs


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, FakeDocRef] = {}

    def document(self, doc_id: str) -> FakeDocRef:
        self.docs.setdefault(doc_id, FakeDocRef(doc_id))
        return self.docs[doc_id]

    def where(self, field: str, operator: str, value: object):
        return FakeQuery(list(self.docs.values())).where(field, operator, value)

    def order_by(self, field: str):
        return FakeQuery(list(self.docs.values())).order_by(field)

    def limit(self, count: int):
        return FakeQuery(list(self.docs.values())).limit(count)


class FakeDB:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def collection(self, name: str) -> FakeCollection:
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


def _write_svg(path: Path) -> None:
    path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )


def _write_receipt(path: Path) -> None:
    path.write_text(
        """╔══════════════════════════╗
║      THE ORACLE SPEAKS   ║
╠══════════════════════════╣

  Your symbol: THE SKY EYE

  You seek certainty. Doubt is a constant companion.

  Themes: ['certainty', 'doubt', 'inquiry']

╚══════════════════════════╝
""",
        encoding="utf-8",
    )


def test_firebase_publish_separates_qr_deeplink_and_qr_image_url(tmp_path: Path) -> None:
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    _write_svg(public_dir / "artwork.svg")
    _write_svg(public_dir / "artwork_raw.svg")
    _write_receipt(public_dir / "receipt.txt")
    (public_dir / "tarot.jpg").write_bytes(b"jpg")
    (public_dir / "qr.png").write_bytes(b"png")

    record = SessionRecord(
        session_id="20260426_130000",
        created_at=datetime(2026, 4, 26, 13, 0, tzinfo=UTC),
        title="THE SKY EYE",
        summary="You seek certainty.",
        source_dir=tmp_path / "raw",
        svg_file=public_dir / "artwork.svg",
        receipt_file=public_dir / "receipt.txt",
        qr_file=public_dir / "qr.png",
        qr_url="https://berlogabob.github.io/OracleGallery/#/session/20260426_130000",
        public_status=PublicStatus.PUBLISHING,
        plot_status=PlotStatus.PENDING,
    )
    bucket = FakeBucket()
    db = FakeDB()
    repo = object.__new__(FirebaseRemoteRepository)
    repo.settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://berlogabob.github.io/OracleGallery",
    )
    repo._bucket = bucket
    repo._db = db

    publication = repo.publish_session(record, public_dir)

    session_doc = db.collection("sessions").document(record.session_id).set_calls[-1]
    expected_qr_image_url = "https://firebasestorage.googleapis.com/v0/b/demo.appspot.com/o/sessions%2F20260426_130000%2Fqr.png?alt=media"
    assert session_doc["sessionUrl"] == record.qr_url
    assert session_doc["qrUrl"] == record.qr_url
    assert session_doc["qrImageUrl"] == expected_qr_image_url
    assert session_doc["assetUrls"]["qr"] == expected_qr_image_url
    assert session_doc["assetUrls"]["tarot"] == "https://firebasestorage.googleapis.com/v0/b/demo.appspot.com/o/sessions%2F20260426_130000%2Ftarot.jpg?alt=media"
    assert session_doc["assetPaths"]["qr"] == "sessions/20260426_130000/qr.png"
    assert session_doc["assetPaths"]["tarot"] == "sessions/20260426_130000/tarot.jpg"
    assert session_doc["origin"] == "real_macmini"
    assert session_doc["tags"] == ["real", "oracle", "macmini"]
    assert session_doc["visibleInLibrary"] is True
    plot_job_doc = db.collection("plot_jobs").document(record.session_id).set_calls[-1]
    assert plot_job_doc["origin"] == "real_macmini"
    assert plot_job_doc["tags"] == ["real", "oracle", "macmini"]
    assert plot_job_doc["queue"] == "user"
    assert plot_job_doc["priority"] == "user"
    assert publication.public_qr_url == expected_qr_image_url


def test_firebase_publish_uses_filler_queue_metadata(tmp_path: Path) -> None:
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    _write_svg(public_dir / "artwork.svg")
    _write_svg(public_dir / "artwork_raw.svg")
    _write_receipt(public_dir / "receipt.txt")
    (public_dir / "qr.png").write_bytes(b"png")

    record = SessionRecord(
        session_id="filler_20260518_120000_001",
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
        title="Filler",
        summary="Local filler mark.",
        source_dir=tmp_path / "raw",
        svg_file=public_dir / "artwork.svg",
        receipt_file=public_dir / "receipt.txt",
        qr_file=public_dir / "qr.png",
        qr_url="https://berlogabob.github.io/OracleGallery/#/session/filler_20260518_120000_001",
        public_status=PublicStatus.PUBLISHING,
        plot_status=PlotStatus.PENDING,
        priority="filler",
        extra_metadata={
            "origin": "filler_macbook",
            "tags": ["filler", "local", "macbook"],
            "kind": "filler",
            "visibleInLibrary": False,
            "uploadToFirebase": True,
            "queue": "filler",
            "priority": "filler",
        },
    )
    bucket = FakeBucket()
    db = FakeDB()
    repo = object.__new__(FirebaseRemoteRepository)
    repo.settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://berlogabob.github.io/OracleGallery",
    )
    repo._bucket = bucket
    repo._db = db

    repo.publish_session(record, public_dir)

    session_doc = db.collection("sessions").document(record.session_id).set_calls[-1]
    plot_job_doc = db.collection("plot_jobs").document(record.session_id).set_calls[-1]
    assert session_doc["origin"] == "filler_macbook"
    assert session_doc["tags"] == ["filler", "local", "macbook"]
    assert session_doc["visibleInLibrary"] is False
    assert session_doc["priority"] == "filler"
    assert plot_job_doc["origin"] == "filler_macbook"
    assert plot_job_doc["tags"] == ["filler", "local", "macbook"]
    assert plot_job_doc["queue"] == "filler"
    assert plot_job_doc["priority"] == "filler"
    assert plot_job_doc["visibleInQueue"] is True


def test_claim_next_plot_job_prefers_real_user_queue_before_filler(tmp_path: Path) -> None:
    db = FakeDB()
    repo = object.__new__(FirebaseRemoteRepository)
    repo._db = db
    filler_doc = db.collection("plot_jobs").document("filler")
    filler_doc.set(
        {
            "sessionId": "filler",
            "title": "Filler",
            "summary": "",
            "createdAt": "2026-05-18T12:00:00+00:00",
            "status": PlotStatus.PENDING.value,
            "priority": "filler",
            "queue": "filler",
            "svgStoragePath": "sessions/filler/artwork.svg",
            "svgUrl": "",
            "origin": "filler_macbook",
            "tags": ["filler", "local", "macbook"],
            "visibleInQueue": True,
        }
    )
    user_doc = db.collection("plot_jobs").document("real")
    user_doc.set(
        {
            "sessionId": "real",
            "title": "Real",
            "summary": "",
            "createdAt": "2026-05-18T12:05:00+00:00",
            "status": PlotStatus.PENDING.value,
            "priority": "user",
            "queue": "user",
            "svgStoragePath": "sessions/real/artwork.svg",
            "svgUrl": "",
            "origin": "real_macmini",
            "tags": ["real", "oracle", "macmini"],
            "visibleInQueue": True,
        }
    )

    job = repo.claim_next_plot_job("plotter")

    assert job is not None
    assert job.session_id == "real"
    assert job.queue == "user"
    assert user_doc.update_calls[-1]["status"] == PlotStatus.LEASED.value
    assert not filler_doc.update_calls


def test_claim_next_plot_job_uses_filler_when_no_real_jobs(tmp_path: Path) -> None:
    db = FakeDB()
    repo = object.__new__(FirebaseRemoteRepository)
    repo._db = db
    filler_doc = db.collection("plot_jobs").document("filler")
    filler_doc.set(
        {
            "sessionId": "filler",
            "title": "Filler",
            "summary": "",
            "createdAt": "2026-05-18T12:00:00+00:00",
            "status": PlotStatus.PENDING.value,
            "priority": "filler",
            "queue": "filler",
            "svgStoragePath": "sessions/filler/artwork.svg",
            "svgUrl": "",
            "origin": "filler_macbook",
            "tags": ["filler", "local", "macbook"],
            "visibleInQueue": True,
        }
    )

    job = repo.claim_next_plot_job("plotter")

    assert job is not None
    assert job.session_id == "filler"
    assert job.queue == "filler"
    assert job.priority == "filler"
    assert filler_doc.update_calls[-1]["status"] == PlotStatus.LEASED.value


def test_session_dir_needs_stability_window_or_ready_marker(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_dir = session_root / "20260426_120000"
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / "20260426_120000_plotter.svg")
    _write_receipt(session_dir / "20260426_120000_receipt.txt")

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=60.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )
    store = UploaderStore(settings.db_path)
    remote = FakeRemoteRepository()
    uploader = SessionUploader(settings, firebase_settings, store, remote)

    assert uploader.scan_once() == []
    assert remote.publish_calls == []

    (session_dir / "READY").write_text("", encoding="utf-8")
    assert uploader.scan_once() == ["20260426_120000"]
    assert remote.publish_calls == ["20260426_120000"]
    assert (session_dir / "20260426_120000_qr.png").read_bytes() == b"firebase:sessions/20260426_120000/qr.png"
    assert remote.download_calls == [("sessions/20260426_120000/qr.png", session_dir / ".20260426_120000_qr.png.tmp")]


def test_scan_continues_after_malformed_session_metadata(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_ids = ["20260426_120000", "20260426_120001", "20260426_120002"]
    for session_id in session_ids:
        session_dir = session_root / session_id
        session_dir.mkdir(parents=True)
        _write_svg(session_dir / f"{session_id}_plotter.svg")
        _write_receipt(session_dir / f"{session_id}_receipt.txt")
        (session_dir / "READY").write_text("", encoding="utf-8")
    (session_root / session_ids[1] / "metadata.json").write_text("{", encoding="utf-8")

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=0.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )
    store = UploaderStore(settings.db_path)
    remote = FakeRemoteRepository()
    uploader = SessionUploader(settings, firebase_settings, store, remote)

    assert uploader.scan_once() == [session_ids[0], session_ids[2]]


def test_qr_download_failure_does_not_mark_session_published(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_dir = session_root / "20260426_120500"
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / "20260426_120500_plotter.svg")
    _write_receipt(session_dir / "20260426_120500_receipt.txt")
    (session_dir / "READY").write_text("", encoding="utf-8")

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=0.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )
    store = UploaderStore(settings.db_path)
    remote = FakeRemoteRepository(fail_qr_download=True)
    uploader = SessionUploader(settings, firebase_settings, store, remote)

    assert uploader.scan_once() == ["20260426_120500"]
    assert not (session_dir / "20260426_120500_qr.png").exists()
    row = store.get_session("20260426_120500")
    assert row is not None
    assert row["public_status"] == PublicStatus.FAILED.value
    assert "QR download failed" in row["last_error"]

    remote.fail_qr_download = False
    assert uploader.scan_once() == ["20260426_120500"]
    row = store.get_session("20260426_120500")
    assert row is not None
    assert row["public_status"] == PublicStatus.PUBLISHED.value
    assert (session_dir / "20260426_120500_qr.png").read_bytes() == b"firebase:sessions/20260426_120500/qr.png"


def test_session_without_receipt_txt_is_ignored(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_dir = session_root / "20260426_121000"
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / "20260426_121000_plotter.svg")
    (session_dir / "READY").write_text("", encoding="utf-8")

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=0.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )
    store = UploaderStore(settings.db_path)
    remote = FakeRemoteRepository()
    uploader = SessionUploader(settings, firebase_settings, store, remote)

    assert uploader.scan_once() == []
    assert remote.publish_calls == []


def test_published_session_is_not_imported_twice_after_restart(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_dir = session_root / "20260426_130000"
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / "20260426_130000_plotter.svg")
    _write_receipt(session_dir / "20260426_130000_receipt.txt")
    past = 1_700_000_000
    os.utime(session_dir / "20260426_130000_plotter.svg", (past, past))
    os.utime(session_dir / "20260426_130000_receipt.txt", (past, past))
    os.utime(session_dir, (past, past))

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=0.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )

    remote = FakeRemoteRepository()
    first_store = UploaderStore(settings.db_path)
    first = SessionUploader(settings, firebase_settings, first_store, remote)
    assert first.scan_once() == ["20260426_130000"]

    second_store = UploaderStore(settings.db_path)
    second = SessionUploader(settings, firebase_settings, second_store, remote)
    assert second.scan_once() == []
    assert remote.publish_calls == ["20260426_130000"]

    row = second_store.get_session("20260426_130000")
    assert row is not None
    assert row["public_status"] == PublicStatus.PUBLISHED.value
    assert row["plot_status"] == PlotStatus.PENDING.value
    assert row["public_receipt_path"] == "sessions/20260426_130000/receipt.txt"

    manifest = (public_root / "20260426_130000" / "manifest.json").read_text(encoding="utf-8")
    assert '"public_status": "published"' in manifest
    assert '"plot_status": "pending"' in manifest
    assert '"sessionUrl": "https://example.github.io/gallery/#/session/20260426_130000"' in manifest
    assert '"qrImageUrl": "https://example.test/20260426_130000/qr.png"' in manifest
    assert '"transcript"' not in manifest


def test_uploader_baseline_skips_old_session_folders(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    old_dir = session_root / "20260426_130000"
    old_dir.mkdir(parents=True)
    _write_svg(old_dir / "20260426_130000_plotter.svg")
    _write_receipt(old_dir / "20260426_130000_receipt.txt")
    (old_dir / "READY").write_text("", encoding="utf-8")

    old_timestamp = 1_700_000_000
    for path in [old_dir, *old_dir.iterdir()]:
        os.utime(path, (old_timestamp, old_timestamp))

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=0.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )
    store = UploaderStore(settings.db_path)
    store.save_run_started_at(datetime(2026, 4, 26, 13, 0, tzinfo=UTC))
    remote = FakeRemoteRepository()
    uploader = SessionUploader(settings, firebase_settings, store, remote)

    assert uploader.scan_once() == []
    assert remote.publish_calls == []

    new_dir = session_root / "20260426_130001"
    new_dir.mkdir()
    _write_svg(new_dir / "20260426_130001_plotter.svg")
    _write_receipt(new_dir / "20260426_130001_receipt.txt")
    (new_dir / "READY").write_text("", encoding="utf-8")

    assert uploader.scan_once() == ["20260426_130001"]
    assert remote.publish_calls == ["20260426_130001"]


def test_touchdesigner_plotter_and_receipt_assets_are_imported_without_visitor_png(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_id = "20260427_115941"
    session_dir = session_root / session_id
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / f"{session_id}_plotter.svg")
    (session_dir / f"{session_id}_tarot.jpg").write_bytes(b"public-tarot")
    (session_dir / f"{session_id}_tarot_ready.txt").write_text(
        f"/Volumes/CreativeSSD/Interactive_Projects/Oracle/sessions/{session_id}/{session_id}_tarot.jpg",
        encoding="utf-8",
    )
    (session_dir / f"{session_id}_receipt.txt").write_text(
        """╔══════════════════════════╗
║      THE ORACLE SPEAKS   ║
╠══════════════════════════╣

  Your symbol: THE SKY EYE

  You seek closure. Grief remains.

  Themes: ['truth', 'illusion', 'crave']

╚══════════════════════════╝
""",
        encoding="utf-8",
    )
    (session_dir / f"{session_id}_visitor.png").write_bytes(b"private-photo")
    (session_dir / f"{session_id}_receipt.csv").write_text(
        "session_id,date,symbol,mark_type,reply_text,keywords,voice_intensity,instability,confidence\n"
        f"{session_id},2026-04-27 12:02,THE SKY EYE,the_sky_eye,You seek closure. Grief remains.,"
        "\"['truth', 'illusion', 'crave']\",0.8,0.2,0.9\n",
        encoding="utf-8",
    )

    settings = UploaderSettings(
        session_root=session_root,
        public_root=public_root,
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        poll_seconds=0.0,
        stability_seconds=0.0,
        ready_marker_name="READY",
        require_ready_marker=False,
    )
    firebase_settings = FirebaseSettings(
        project_id="demo",
        storage_bucket="demo.appspot.com",
        credentials_path=tmp_path / "missing.json",
        gallery_base_url="https://example.github.io/gallery",
    )
    store = UploaderStore(settings.db_path)
    remote = FakeRemoteRepository()
    uploader = SessionUploader(settings, firebase_settings, store, remote)

    assert uploader.scan_once() == [session_id]
    assert (public_root / session_id / "artwork.svg").exists()
    assert (public_root / session_id / "artwork_raw.svg").exists()
    assert (public_root / session_id / "receipt.txt").exists()
    assert (public_root / session_id / "tarot.jpg").read_bytes() == b"public-tarot"
    assert not (public_root / session_id / "preview.png").exists()
    assert 'data-neje-normalized="true"' in (public_root / session_id / "artwork.svg").read_text(encoding="utf-8")
    assert 'data-neje-normalized="true"' not in (public_root / session_id / "artwork_raw.svg").read_text(encoding="utf-8")

    row = store.get_session(session_id)
    assert row is not None
    assert row["mark_name"] == "THE SKY EYE"
    assert row["oracle_text"] == "You seek closure. Grief remains."
    assert '"truth"' in row["themes_json"]
    assert '"intensity": 0.8' in row["measures_json"]
    assert '"instability": 0.2' in row["measures_json"]

    manifest = (public_root / session_id / "manifest.json").read_text(encoding="utf-8")
    assert "private words" not in manifest
    assert "visitor.png" not in manifest
    assert '"tarotImageFile": "tarot.jpg"' in manifest
