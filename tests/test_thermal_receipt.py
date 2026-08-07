from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEND_RECEIPT_PATH = REPO_ROOT / "ESP32-BTN_Printer" / "tools" / "send_receipt.py"

# Synthetic and tracked. Real sessions live under assets/sessions/, which is gitignored
# because it holds visitor PII (photo, voice recordings) — pointing tests there made them
# pass locally and fail in CI forever.
SESSION_ID = "20260101_000000"
FIXTURE_SESSION = REPO_ROOT / "tests" / "fixtures" / "thermal_session" / SESSION_ID


def load_send_receipt_module():
    spec = importlib.util.spec_from_file_location("send_receipt", SEND_RECEIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_session_carries_no_visitor_media() -> None:
    """The fixture must never grow real visitor audio or full-size imagery."""
    assert FIXTURE_SESSION.is_dir(), f"missing tracked fixture: {FIXTURE_SESSION}"
    assert not list(FIXTURE_SESSION.glob("*.wav")), "visitor audio must not be committed"
    for image in FIXTURE_SESSION.glob("*.png"):
        assert image.stat().st_size < 10_000, f"{image.name} is too large to be synthetic"


def test_thermal_payload_from_real_session_has_mandatory_contract() -> None:
    send_receipt = load_send_receipt_module()
    payload = send_receipt.build_payload(
        session_dir=FIXTURE_SESSION,
        repo_root=REPO_ROOT,
        include_symbol=True,
        printer_width=384,
        ilabel_width=576,
        symbol_size=168,
    )

    assert payload["receipt_title"] == "ORACLE"
    assert payload["subtitle"] == "THE ORACLE THAT WEARS US"
    assert payload["symbol_label"]
    assert payload["qr_required"] is True
    assert payload["persona_image_allowed"] is False
    assert not any(key.startswith("persona_") and key != "persona_image_allowed" for key in payload)
    assert payload["session_url"].endswith(f"/#/session/{SESSION_ID}")
    assert payload["qr_escpos_base64"]
    assert payload["receipt_raster_rle_base64"]
    assert payload["ilabel_width_dots"] == 576
    assert payload["ilabel_height_dots"] > 300


def test_missing_measures_and_themes_degrade_gracefully(tmp_path: Path) -> None:
    send_receipt = load_send_receipt_module()
    session_dir = tmp_path / "20260520_101010"
    session_dir.mkdir()
    (session_dir / "20260520_101010_receipt.txt").write_text(
        "Your symbol: THE HORIZON\nA long oracle text that should still render even without CSV measures or themes.\n",
        encoding="utf-8",
    )
    (session_dir / "20260520_101010_plotter.svg").write_text(
        '<svg width="100" height="100" viewBox="0 0 100 100"><line x1="10" y1="10" x2="90" y2="90" stroke="black" stroke-width="6"/></svg>',
        encoding="utf-8",
    )

    payload = send_receipt.build_payload(
        session_dir=session_dir,
        repo_root=REPO_ROOT,
        include_symbol=True,
        printer_width=384,
        ilabel_width=576,
        symbol_size=120,
    )

    assert payload["themes"] == []
    assert payload["measures"] == {}
    assert payload["symbol_label"] == "THE HORIZON"
    assert payload["symbol_escpos_base64"]
    assert base64.b64decode(payload["receipt_raster_rle_base64"])


def test_printer_connect_receipt_dry_run_outputs_payload_and_preview(tmp_path: Path) -> None:
    preview = tmp_path / "preview.png"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ESP32-BTN_Printer" / "tools" / "printer_connect.py"),
            "receipt",
            str(FIXTURE_SESSION),
            "--dry-run",
            "--preview-png",
            str(preview),
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload["qr_required"] is True
    assert payload["persona_image_allowed"] is False
    assert payload["receipt_raster_rle_base64"]
    assert preview.exists()
