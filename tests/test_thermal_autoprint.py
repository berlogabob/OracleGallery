from __future__ import annotations

from pathlib import Path

from neje_oracle.thermal_autoprint_service import ThermalAutoprintService, ThermalAutoprintSettings


def make_session(root: Path, session_id: str) -> Path:
    session_dir = root / session_id
    session_dir.mkdir(parents=True)
    (session_dir / f"{session_id}_receipt.txt").write_text("Your symbol: THE KIND SOUL\nA receipt.\n", encoding="utf-8")
    (session_dir / f"{session_id}_plotter.svg").write_text(
        '<svg width="100" height="100" viewBox="0 0 100 100"><line x1="0" y1="0" x2="100" y2="100"/></svg>',
        encoding="utf-8",
    )
    return session_dir


def make_service(
    tmp_path: Path,
    *,
    now_value: list[float],
    status: dict[str, object],
    printed: list[Path],
    delay_seconds: float = 60.0,
    retry_seconds: float = 60.0,
    max_attempts: int = 3,
    print_results: list[dict[str, object]] | None = None,
) -> ThermalAutoprintService:
    settings = ThermalAutoprintSettings(
        macmini_agent_url="http://macmini.local:8790",
        esp32_url="http://10.28.8.56",
        delay_seconds=delay_seconds,
        poll_seconds=10.0,
        retry_seconds=retry_seconds,
        max_attempts=max_attempts,
        timeout_seconds=1.0,
        state_path=tmp_path / "thermal_autoprint.json",
        repo_root=tmp_path,
    )

    def http_get_json(url: str, timeout: float) -> dict[str, object]:
        assert url == "http://macmini.local:8790/status"
        assert timeout == 1.0
        return status

    def print_receipt(session_dir: Path) -> dict[str, object]:
        printed.append(session_dir)
        if print_results:
            return print_results.pop(0)
        return {"ok": True, "printed": True}

    return ThermalAutoprintService(
        settings,
        http_get_json=http_get_json,
        print_receipt=print_receipt,
        firebase_sessions=lambda: [],
        now=lambda: now_value[0],
    )


def test_waits_sixty_seconds_before_printing_new_import(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions"
    make_session(session_root, "session_001")
    status = {"watched_folder": str(session_root), "last_imported": ["session_001"]}
    now_value = [100.0]
    printed: list[Path] = []
    service = make_service(tmp_path, now_value=now_value, status=status, printed=printed)

    first = service.run_once()
    assert first["printed"] == []
    assert first["waiting"] == ["session_001"]
    assert printed == []

    now_value[0] = 159.0
    second = service.run_once()
    assert second["printed"] == []
    assert printed == []

    now_value[0] = 160.0
    third = service.run_once()
    assert third["printed"] == ["session_001"]
    assert printed == [session_root / "session_001"]


def test_persisted_print_state_prevents_duplicate_after_restart(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions"
    make_session(session_root, "session_001")
    status = {"watched_folder": str(session_root), "last_imported": ["session_001"]}
    now_value = [100.0]
    printed: list[Path] = []
    service = make_service(tmp_path, now_value=now_value, status=status, printed=printed, delay_seconds=0.0)

    assert service.run_once()["printed"] == ["session_001"]
    assert len(printed) == 1

    now_value[0] = 1000.0
    restarted = make_service(tmp_path, now_value=now_value, status=status, printed=printed, delay_seconds=0.0)
    assert restarted.run_once()["printed"] == []
    assert len(printed) == 1


def test_missing_required_session_files_stays_pending_without_attempt(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions"
    (session_root / "session_001").mkdir(parents=True)
    status = {"watched_folder": str(session_root), "last_imported": ["session_001"]}
    now_value = [100.0]
    printed: list[Path] = []
    service = make_service(tmp_path, now_value=now_value, status=status, printed=printed, delay_seconds=0.0)

    result = service.run_once()

    assert result["printed"] == []
    assert result["skipped"] == ["session_001"]
    assert printed == []
    assert service.state["sessions"]["session_001"]["attempts"] == 0


def test_failed_print_retries_after_retry_window(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions"
    make_session(session_root, "session_001")
    status = {"watched_folder": str(session_root), "last_imported": ["session_001"]}
    now_value = [100.0]
    printed: list[Path] = []
    service = make_service(
        tmp_path,
        now_value=now_value,
        status=status,
        printed=printed,
        delay_seconds=0.0,
        retry_seconds=60.0,
        print_results=[
            {"ok": False, "error": "printer busy"},
            {"ok": True, "printed": True},
        ],
    )

    first = service.run_once()
    assert first["printed"] == []
    assert first["waiting"] == ["session_001"]
    assert len(printed) == 1

    now_value[0] = 159.0
    second = service.run_once()
    assert second["printed"] == []
    assert len(printed) == 1

    now_value[0] = 160.0
    third = service.run_once()
    assert third["printed"] == ["session_001"]
    assert len(printed) == 2


def test_firebase_fallback_materializes_latest_session_when_agent_missing(tmp_path: Path) -> None:
    now_value = [200.0]
    printed: list[Path] = []
    downloads: list[tuple[str, Path]] = []
    firebase_rows = [
        {
            "sessionId": "session_002",
            "createdAt": "1970-01-01T00:02:00+00:00",
            "status": "published",
            "origin": "real_macmini",
            "markName": "THE SHRIEK",
            "oracleText": "A receipt from Firebase.",
            "themes": ["echo"],
            "measures": {"intensity": 0.8, "instability": 0.3, "confidence": 0.9},
            "assetPaths": {
                "receipt": "sessions/session_002/receipt.txt",
                "svg": "sessions/session_002/artwork.svg",
            },
        },
        {
            "sessionId": "session_001",
            "createdAt": "1970-01-01T00:01:00+00:00",
            "status": "published",
            "origin": "real_macmini",
            "assetPaths": {
                "receipt": "sessions/session_001/receipt.txt",
                "svg": "sessions/session_001/artwork.svg",
            },
        },
    ]
    settings = ThermalAutoprintSettings(
        macmini_agent_url="",
        esp32_url="http://10.28.8.56",
        delay_seconds=0.0,
        timeout_seconds=1.0,
        state_path=tmp_path / "thermal_autoprint.json",
        cache_root=tmp_path / "thermal_sessions",
        repo_root=tmp_path,
    )

    def download_asset(storage_path: str, destination: Path) -> None:
        downloads.append((storage_path, destination))
        if storage_path.endswith("receipt.txt"):
            destination.write_text("Your symbol: THE SHRIEK\nA receipt from Firebase.\n", encoding="utf-8")
        else:
            destination.write_text(
                '<svg width="100" height="100" viewBox="0 0 100 100"><line x1="0" y1="0" x2="100" y2="100"/></svg>',
                encoding="utf-8",
            )

    def print_receipt(session_dir: Path) -> dict[str, object]:
        printed.append(session_dir)
        return {"ok": True, "printed": True}

    service = ThermalAutoprintService(
        settings,
        http_get_json=lambda _url, _timeout: (_ for _ in ()).throw(RuntimeError("offline")),
        print_receipt=print_receipt,
        firebase_sessions=lambda: firebase_rows,
        download_asset=download_asset,
        now=lambda: now_value[0],
    )

    result = service.run_once()

    assert result["observed_firebase"] == ["session_002"]
    assert result["printed"] == ["session_002"]
    assert printed == [tmp_path / "thermal_sessions" / "session_002"]
    assert (tmp_path / "thermal_sessions" / "session_002" / "session_002_receipt.txt").exists()
    assert (tmp_path / "thermal_sessions" / "session_002" / "session_002_plotter.svg").exists()
    assert [path for _, path in downloads] == [
        tmp_path / "thermal_sessions" / "session_002" / "session_002_receipt.txt",
        tmp_path / "thermal_sessions" / "session_002" / "session_002_plotter.svg",
    ]

    restarted = ThermalAutoprintService(
        settings,
        http_get_json=lambda _url, _timeout: (_ for _ in ()).throw(RuntimeError("offline")),
        print_receipt=print_receipt,
        firebase_sessions=lambda: firebase_rows,
        download_asset=download_asset,
        now=lambda: now_value[0],
    )
    second = restarted.run_once()

    assert second["observed_firebase"] == []
    assert second["printed"] == []
    assert len(printed) == 1


def test_firebase_fallback_retries_when_asset_download_fails(tmp_path: Path) -> None:
    now_value = [200.0]
    firebase_rows = [
        {
            "sessionId": "session_003",
            "createdAt": "1970-01-01T00:03:00+00:00",
            "status": "published",
            "origin": "real_macmini",
            "markName": "THE SHRIEK",
            "oracleText": "A receipt from Firebase.",
            "assetPaths": {
                "receipt": "sessions/session_003/receipt.txt",
                "svg": "sessions/session_003/artwork.svg",
            },
        }
    ]
    settings = ThermalAutoprintSettings(
        macmini_agent_url="",
        esp32_url="http://10.28.8.56",
        delay_seconds=0.0,
        timeout_seconds=1.0,
        state_path=tmp_path / "thermal_autoprint.json",
        cache_root=tmp_path / "thermal_sessions",
        repo_root=tmp_path,
    )
    calls = [0]
    printed: list[Path] = []

    def download_asset(storage_path: str, destination: Path) -> None:
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("temporary storage failure")
        if storage_path.endswith("receipt.txt"):
            destination.write_text("Your symbol: THE SHRIEK\nA receipt from Firebase.\n", encoding="utf-8")
        else:
            destination.write_text(
                '<svg width="100" height="100" viewBox="0 0 100 100"><line x1="0" y1="0" x2="100" y2="100"/></svg>',
                encoding="utf-8",
            )

    service = ThermalAutoprintService(
        settings,
        http_get_json=lambda _url, _timeout: (_ for _ in ()).throw(RuntimeError("offline")),
        print_receipt=lambda session_dir: printed.append(session_dir) or {"ok": True, "printed": True},
        firebase_sessions=lambda: firebase_rows,
        download_asset=download_asset,
        now=lambda: now_value[0],
    )

    first = service.run_once()
    assert first["observed_firebase"] == []
    assert "firebase_latest_created_at" not in service.state

    restarted = ThermalAutoprintService(
        settings,
        http_get_json=lambda _url, _timeout: (_ for _ in ()).throw(RuntimeError("offline")),
        print_receipt=lambda session_dir: printed.append(session_dir) or {"ok": True, "printed": True},
        firebase_sessions=lambda: firebase_rows,
        download_asset=download_asset,
        now=lambda: now_value[0],
    )
    second = restarted.run_once()

    assert second["observed_firebase"] == ["session_003"]
    assert second["printed"] == ["session_003"]
    assert printed == [tmp_path / "thermal_sessions" / "session_003"]
