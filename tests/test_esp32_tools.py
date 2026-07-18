from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_PATH = REPO_ROOT / "ESP32-BTN_Printer" / "tools"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS_PATH / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


printer_connect = load_module("printer_connect")
send_receipt = load_module("send_receipt")


def test_printer_connect_get_json_rejects_invalid_response() -> None:
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b"<html>not json</html>"
        with pytest.raises(SystemExit) as exc:
            printer_connect.get_json("http://esp32", "/status", timeout=1)

    assert "invalid response" in str(exc.value)


def test_printer_connect_post_json_rejects_invalid_response() -> None:
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b"<html>not json</html>"
        with pytest.raises(SystemExit) as exc:
            printer_connect.post_json("http://esp32", "/print", None, timeout=1)

    assert "invalid response" in str(exc.value)


def test_send_receipt_post_json_rejects_invalid_response() -> None:
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b"<html>not json</html>"
        with pytest.raises(SystemExit) as exc:
            send_receipt.post_json("http://esp32", "/print", None, timeout=1)

    assert "invalid response" in str(exc.value)
