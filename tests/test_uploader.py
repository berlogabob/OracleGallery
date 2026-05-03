from __future__ import annotations

import os
from pathlib import Path

from neje_oracle.config import FirebaseSettings, UploaderSettings
from neje_oracle.models import PlotStatus, PublicationResult, PublicStatus
from neje_oracle.session_uploader import SessionUploader
from neje_oracle.store import UploaderStore


class FakeRemoteRepository:
    def __init__(self) -> None:
        self.publish_calls: list[str] = []

    def publish_session(self, record, public_dir: Path) -> PublicationResult:
        self.publish_calls.append(record.session_id)
        assert (public_dir / "artwork.svg").exists()
        assert (public_dir / "artwork_raw.svg").exists()
        assert (public_dir / "receipt.txt").exists()
        assert not (public_dir / "preview.png").exists()
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
    assert '"transcript"' not in manifest


def test_touchdesigner_plotter_and_receipt_assets_are_imported_without_visitor_png(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_id = "20260427_115941"
    session_dir = session_root / session_id
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / f"{session_id}_plotter.svg")
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
    (session_root / "session_log.csv").write_text(
        "session_id,timestamp,transcript,reply_text,symbol,keywords,intensity,hesitation,confidence,warmth,instability\n"
        f"{session_id},2026-04-27 12:02:08,private words,You seek closure. Grief remains.,THE SKY EYE,"
        "\"['truth', 'illusion', 'crave']\",0.8,0.1,0.9,0.05,0.2\n",
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
    assert not (public_root / session_id / "preview.png").exists()
    assert 'data-neje-normalized="true"' in (public_root / session_id / "artwork.svg").read_text(encoding="utf-8")
    assert 'data-neje-normalized="true"' not in (public_root / session_id / "artwork_raw.svg").read_text(encoding="utf-8")

    row = store.get_session(session_id)
    assert row is not None
    assert row["mark_name"] == "THE SKY EYE"
    assert row["oracle_text"] == "You seek closure. Grief remains."
    assert '"truth"' in row["themes_json"]
    assert '"intensity": 0.8' in row["measures_json"]

    manifest = (public_root / session_id / "manifest.json").read_text(encoding="utf-8")
    assert "private words" not in manifest
    assert "visitor.png" not in manifest
