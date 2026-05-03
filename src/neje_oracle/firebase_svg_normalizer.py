from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from .config import FirebaseSettings, _repo_root
from .firebase_io import FirebaseRemoteRepository, _file_hash
from .svg_normalizer import is_normalized_svg, normalize_svg_file, scale_for_mark_name


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize existing Firebase session SVG assets in place.")
    parser.add_argument("--dry-run", action="store_true", help="Only report planned changes; do not upload.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of sessions to inspect.")
    parser.add_argument("--session-id", default=None, help="Normalize one session only.")
    parser.add_argument("--force", action="store_true", help="Re-normalize already normalized artwork.svg files.")
    parser.add_argument("--symbol-root", type=Path, default=_repo_root() / "assets" / "symbols")
    parser.add_argument("--scale-config", type=Path, default=_repo_root() / "assets" / "symbols" / "symbol_scales.json")
    args = parser.parse_args()

    repository = FirebaseRemoteRepository(FirebaseSettings())
    changed = normalize_firebase_sessions(
        repository,
        dry_run=args.dry_run,
        limit=args.limit,
        session_id=args.session_id,
        force=args.force,
        symbol_root=args.symbol_root,
        scale_config=args.scale_config,
    )
    verb = "Would normalize" if args.dry_run else "Normalized"
    print(f"{verb} {changed} Firebase session SVG asset(s).")


def normalize_firebase_sessions(
    repository: FirebaseRemoteRepository,
    *,
    dry_run: bool,
    limit: int | None,
    session_id: str | None,
    force: bool,
    symbol_root: Path,
    scale_config: Path,
) -> int:
    changed = 0
    with tempfile.TemporaryDirectory(prefix="neje-firebase-normalize-") as tmp:
        tmp_root = Path(tmp)
        for document in repository.iter_sessions(limit=limit, session_id=session_id):
            resolved_session_id = str(document.get("sessionId") or document.get("_id") or "")
            if not resolved_session_id:
                continue
            asset_paths = document.get("assetPaths") or {}
            svg_storage_path = asset_paths.get("svg") or f"sessions/{resolved_session_id}/artwork.svg"
            raw_svg_storage_path = asset_paths.get("rawSvg") or f"sessions/{resolved_session_id}/artwork_raw.svg"
            if not svg_storage_path:
                continue

            source_path = tmp_root / f"{resolved_session_id}_artwork.svg"
            normalized_path = tmp_root / f"{resolved_session_id}_normalized.svg"
            repository.download_asset(svg_storage_path, source_path)
            if is_normalized_svg(source_path) and not force:
                print(f"skip {resolved_session_id}: already normalized")
                continue

            mark_name = str(document.get("markName") or "")
            scale = scale_for_mark_name(mark_name, symbol_root, scale_config)
            normalized_path.write_text(
                normalize_svg_file(source_path, marker_kind="user", scale=scale, include_rings=True),
                encoding="utf-8",
            )
            svg_version = _file_hash(normalized_path)

            print(
                f"{'dry-run ' if dry_run else ''}normalize {resolved_session_id}: "
                f"scale={scale:.3f} storage={svg_storage_path}"
            )
            changed += 1
            if dry_run:
                continue

            if force or not repository.storage_asset_exists(raw_svg_storage_path):
                repository.upload_asset(raw_svg_storage_path, source_path, content_type="image/svg+xml")
            repository.upload_asset(svg_storage_path, normalized_path, content_type="image/svg+xml")
            repository.update_normalized_svg(
                resolved_session_id,
                svg_storage_path=svg_storage_path,
                raw_svg_storage_path=raw_svg_storage_path,
                svg_version=svg_version,
            )
    return changed


if __name__ == "__main__":
    main()
