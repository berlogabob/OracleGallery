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
        return PublicationResult(
            public_status=PublicStatus.PUBLISHED,
            public_svg_path=f"sessions/{record.session_id}/artwork.svg",
            public_preview_path=f"sessions/{record.session_id}/preview.png",
            public_qr_path=f"sessions/{record.session_id}/qr.png",
            public_svg_url=f"https://example.test/{record.session_id}/artwork.svg",
            public_preview_url=f"https://example.test/{record.session_id}/preview.png",
            public_qr_url=f"https://example.test/{record.session_id}/qr.png",
        )


def _write_svg(path: Path) -> None:
    path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )


def _write_png_placeholder(path: Path) -> None:
    path.write_bytes(b"fake-png")


def test_session_dir_needs_stability_window_or_ready_marker(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_dir = session_root / "20260426_120000"
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / "artwork.svg")
    _write_png_placeholder(session_dir / "preview.png")

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


def test_published_session_is_not_imported_twice_after_restart(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions_raw"
    public_root = tmp_path / "sessions_public"
    session_dir = session_root / "20260426_130000"
    session_dir.mkdir(parents=True)
    _write_svg(session_dir / "artwork.svg")
    _write_png_placeholder(session_dir / "preview.png")
    past = 1_700_000_000
    os.utime(session_dir / "artwork.svg", (past, past))
    os.utime(session_dir / "preview.png", (past, past))
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

    manifest = (public_root / "20260426_130000" / "manifest.json").read_text(encoding="utf-8")
    assert '"public_status": "published"' in manifest
    assert '"plot_status": "pending"' in manifest
