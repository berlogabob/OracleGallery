from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from neje_oracle.config import PlotterSettings
from neje_oracle.models import FluidNCState
from neje_oracle.transport import FluidNCTransport, discover_fluidnc, parse_status_response, settings_for_fluidnc_host


class FakeFluidNCServer:
    def __init__(self, *, error_command: str = "", suppress_ok_command: str = "") -> None:
        self.error_command = error_command
        self.suppress_ok_command = suppress_ok_command
        self.commands: list[str] = []
        self.realtime: list[bytes] = []
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.host = "127.0.0.1"
        self.port = 0

    def __enter__(self) -> "FakeFluidNCServer":
        self._thread.start()
        assert self._ready.wait(timeout=2)
        return self

    def __exit__(self, *args: object) -> None:
        self._stop.set()
        try:
            with socket.create_connection((self.host, self.port), timeout=0.2):
                pass
        except OSError:
            pass
        self._thread.join(timeout=2)

    def _run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, 0))
            server.listen()
            server.settimeout(0.2)
            self.port = int(server.getsockname()[1])
            self._ready.set()
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(0.2)
            buffer = b""
            while not self._stop.is_set():
                try:
                    data = conn.recv(1024)
                except socket.timeout:
                    continue
                if not data:
                    break
                if b"!" in data:
                    self.realtime.append(b"!")
                if b"~" in data:
                    self.realtime.append(b"~")
                if b"\x18" in data:
                    self.realtime.append(b"\x18")
                if b"?" in data:
                    conn.sendall(b"<Idle|MPos:1.000,2.000,3.000|FS:0,0|Ov:100,100,100>\r\n")
                    data = data.replace(b"?", b"")
                buffer += data
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    command = raw.decode("utf-8", "replace").strip()
                    if not command:
                        continue
                    self.commands.append(command)
                    if command == self.suppress_ok_command:
                        continue
                    if command == self.error_command:
                        conn.sendall(b"error:2\r\n")
                    elif command == "$G":
                        conn.sendall(b"[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]\r\nok\r\n")
                    else:
                        conn.sendall(b"ok\r\n")


def _settings(tmp_path: Path, server: FakeFluidNCServer) -> PlotterSettings:
    return PlotterSettings(
        spool_root=tmp_path / "spool",
        fluidnc_http_url="",
        fluidnc_telnet_host=server.host,
        fluidnc_telnet_port=server.port,
        fluidnc_connect_timeout_seconds=0.5,
        fluidnc_ack_timeout_seconds=0.5,
        dry_run=False,
    )


def test_parse_status_response() -> None:
    state = parse_status_response("<Idle|MPos:1.000,2.000,3.000|FS:4,5|Ov:100,90,80>")

    assert state.state == FluidNCState.IDLE
    assert state.machine_position == (1.0, 2.0, 3.0)
    assert state.feed_rate == 4.0
    assert state.spindle_speed == 5.0
    assert state.overrides == (100, 90, 80)


def test_probe_parses_status_and_modal_state(tmp_path: Path) -> None:
    with FakeFluidNCServer() as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        probe = transport.probe()

    assert probe.online
    assert probe.telnet_online
    assert probe.controller.state == FluidNCState.IDLE
    assert probe.controller.machine_position == (1.0, 2.0, 3.0)
    assert "G90" in probe.controller.modal_state


def test_discover_fluidnc_finds_controller_on_candidate_host(tmp_path: Path) -> None:
    with FakeFluidNCServer() as server:
        probe = discover_fluidnc(
            _settings(tmp_path, server),
            hosts=[server.host],
            timeout_seconds=0.2,
            max_workers=1,
        )

    assert probe.online
    assert probe.telnet_host == server.host
    assert probe.telnet_port == server.port


def test_settings_for_fluidnc_host_updates_http_and_telnet(tmp_path: Path) -> None:
    with FakeFluidNCServer() as server:
        settings = settings_for_fluidnc_host(_settings(tmp_path, server), "10.60.149.74")

    assert settings.fluidnc_http_url == "http://10.60.149.74"
    assert settings.fluidnc_telnet_host == "10.60.149.74"
    assert settings.fluidnc_host == "10.60.149.74"


def test_send_waits_for_ok_for_each_line(tmp_path: Path) -> None:
    with FakeFluidNCServer() as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        progress: list[tuple[int, int]] = []
        transport.send(
            gcode="; comment\nG0 X0\nG1 X1\n",
            sheet_id="sheet",
            dry_run=False,
            progress_callback=lambda sent, total: progress.append((sent, total)),
        )

    assert "G0 X0" in server.commands
    assert "G1 X1" in server.commands
    assert "; comment" not in server.commands
    assert progress[-1] == (2, 2)


def test_send_fails_on_fluidnc_error(tmp_path: Path) -> None:
    with FakeFluidNCServer(error_command="G1 X1") as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        with pytest.raises(RuntimeError, match="rejected line"):
            transport.send(gcode="G1 X1\n", sheet_id="sheet", dry_run=False)


def test_send_fails_on_ack_timeout(tmp_path: Path) -> None:
    with FakeFluidNCServer(suppress_ok_command="G1 X1") as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        with pytest.raises(RuntimeError, match="Timed out waiting for ok"):
            transport.send(gcode="G1 X1\n", sheet_id="sheet", dry_run=False)


def test_control_commands_send_expected_payloads(tmp_path: Path) -> None:
    with FakeFluidNCServer() as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        assert transport.home().ok
        assert transport.unlock_alarm().ok
        assert transport.jog("X", 1, 1000).ok
        assert transport.feed_hold().ok
        assert transport.cycle_start().ok
        assert transport.soft_reset().ok
        time.sleep(0.1)

    assert "$H" in server.commands
    assert "$X" in server.commands
    assert "$J=G91 G21 X1.000 F1000" in server.commands
    assert b"!" in server.realtime
    assert b"~" in server.realtime
    assert b"\x18" in server.realtime
