from __future__ import annotations

import shutil
from pathlib import Path

from neje_oracle.firebase_svg_normalizer import normalize_firebase_sessions


class FakeFirebaseRepository:
    def __init__(self, svg_path: Path) -> None:
        self.svg_path = svg_path
        self.uploads: list[str] = []
        self.updates: list[str] = []

    def iter_sessions(self, *, limit: int | None = None, session_id: str | None = None):
        return [
            {
                "_id": "session_001",
                "sessionId": "session_001",
                "markName": "THE KIND SOUL",
                "assetPaths": {"svg": "sessions/session_001/artwork.svg"},
            }
        ]

    def download_asset(self, storage_path: str, destination: Path) -> None:
        shutil.copy2(self.svg_path, destination)

    def storage_asset_exists(self, storage_path: str) -> bool:
        return False

    def upload_asset(self, storage_path: str, source: Path, *, content_type: str) -> None:
        self.uploads.append(storage_path)

    def update_normalized_svg(
        self,
        session_id: str,
        *,
        svg_storage_path: str,
        raw_svg_storage_path: str,
        svg_version: str,
    ) -> str:
        self.updates.append(session_id)
        return "https://example.test/artwork.svg"


def test_firebase_normalizer_dry_run_does_not_upload(tmp_path: Path) -> None:
    svg_path = tmp_path / "artwork.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>",
        encoding="utf-8",
    )
    symbol_root = tmp_path / "symbols"
    symbol_root.mkdir()
    (symbol_root / "symbol_0.svg").write_text(svg_path.read_text(encoding="utf-8"), encoding="utf-8")
    repository = FakeFirebaseRepository(svg_path)

    changed = normalize_firebase_sessions(
        repository,  # type: ignore[arg-type]
        dry_run=True,
        limit=1,
        session_id=None,
        force=False,
        symbol_root=symbol_root,
        scale_config=tmp_path / "missing_scales.json",
    )

    assert changed == 1
    assert repository.uploads == []
    assert repository.updates == []
