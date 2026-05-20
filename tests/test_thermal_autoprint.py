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
