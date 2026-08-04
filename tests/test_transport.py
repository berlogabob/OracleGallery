from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from neje_oracle.shared.config import PlotterSettings
from neje_oracle.shared.models import FluidNCState
from neje_oracle.blocks.fluidnc.transport import (
    RX_BUFFER,
    FluidNCTransport,
    discover_fluidnc,
    parse_status_response,
    settings_for_fluidnc_host,
)


class FakeFluidNCServer:
    def __init__(
        self,
        *,
        error_command: str = "",
        suppress_ok_command: str = "",
        close_command: str = "",
        status_states: list[str] | None = None,
    ) -> None:
        self.error_command = error_command
        self.suppress_ok_command = suppress_ok_command
        self.close_command = close_command
        self.status_states = status_states or ["Idle"]
        self.status_queries = 0
        self._status_lock = threading.Lock()
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
                while b"?" in data:
                    conn.sendall(self._next_status_response())
                    data = data.replace(b"?", b"", 1)
                buffer += data
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    command = raw.decode("utf-8", "replace").strip()
                    if not command:
                        continue
                    self.commands.append(command)
                    if command == self.close_command:
                        return
                    if command == self.suppress_ok_command:
                        continue
                    if command == self.error_command:
                        conn.sendall(b"error:2\r\n")
                    elif command == "$G":
                        conn.sendall(b"[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]\r\nok\r\n")
                    else:
                        conn.sendall(b"ok\r\n")

    def _next_status_response(self) -> bytes:
        with self._status_lock:
            index = min(self.status_queries, len(self.status_states) - 1)
            state = self.status_states[index]
            self.status_queries += 1
        return f"<{state}|MPos:1.000,2.000,3.000|FS:0,0|Ov:100,100,100>\r\n".encode("utf-8")


def _settings(
    tmp_path: Path,
    server: FakeFluidNCServer,
    *,
    idle_timeout_seconds: float = 0.5,
    streaming: str = "ok_wait",
    ack_timeout_seconds: float = 0.5,
) -> PlotterSettings:
    return PlotterSettings(
        spool_root=tmp_path / "spool",
        fluidnc_http_url="",
        fluidnc_telnet_host=server.host,
        fluidnc_telnet_port=server.port,
        fluidnc_connect_timeout_seconds=0.5,
        fluidnc_ack_timeout_seconds=ack_timeout_seconds,
        fluidnc_idle_timeout_seconds=idle_timeout_seconds,
        fluidnc_streaming=streaming,
        dry_run=False,
    )


class FakeCharCountServer:
    """Minimal FluidNC-like server for exercising GRBL character-counting
    streaming: acks lag behind sends (one ack per short delay) so more than
    one line ends up outstanding at once, and it tracks the outstanding byte
    count the client is allowed to hold so tests can assert it stays within
    RX_BUFFER.
    """

    def __init__(self, *, ack_delay_seconds: float = 0.02, error_on_command: str = "") -> None:
        self.ack_delay_seconds = ack_delay_seconds
        self.error_on_command = error_on_command
        self.commands: list[str] = []
        self.max_outstanding_bytes = 0
        self.max_outstanding_lines = 0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.host = "127.0.0.1"
        self.port = 0

    def __enter__(self) -> "FakeCharCountServer":
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
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(0.05)
        buffer = b""
        pending: list[str] = []
        outstanding_bytes = 0
        with conn:
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    while b"?" in data:
                        conn.sendall(b"<Idle|MPos:0.000,0.000,0.000|FS:0,0|Ov:100,100,100>\r\n")
                        data = data.replace(b"?", b"", 1)
                    buffer += data
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        command = raw.decode("utf-8", "replace").strip()
                        if not command:
                            continue
                        if command == "$G":
                            # Probe's modal-state query; answer immediately, it is
                            # not part of the char-counting g-code stream.
                            conn.sendall(b"[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]\r\nok\r\n")
                            continue
                        self.commands.append(command)
                        pending.append(command)
                        outstanding_bytes += len(command) + 1
                        self.max_outstanding_bytes = max(self.max_outstanding_bytes, outstanding_bytes)
                        self.max_outstanding_lines = max(self.max_outstanding_lines, len(pending))
                except socket.timeout:
                    pass

                if pending:
                    time.sleep(self.ack_delay_seconds)
                    command = pending.pop(0)
                    outstanding_bytes -= len(command) + 1
                    if command == self.error_on_command:
                        conn.sendall(b"error:9\r\n")
                        return
                    conn.sendall(b"ok\r\n")


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


def test_probe_accepts_status_when_modal_query_times_out(tmp_path: Path) -> None:
    with FakeFluidNCServer(suppress_ok_command="$G") as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        probe = transport.probe()

    assert probe.online
    assert probe.controller.state == FluidNCState.IDLE
    assert "Timed out waiting for ok after $G" in probe.last_error


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


def test_send_waits_for_idle_after_final_ack(tmp_path: Path) -> None:
    with FakeFluidNCServer(status_states=["Idle", "Run", "Run", "Idle"]) as server:
        transport = FluidNCTransport(_settings(tmp_path, server, idle_timeout_seconds=1.0))
        gcode_path = transport.send(gcode="G1 X1\n", sheet_id="sheet", dry_run=False)

    assert gcode_path.exists()
    assert server.status_queries >= 4


def test_send_times_out_waiting_for_idle_after_final_ack(tmp_path: Path) -> None:
    with FakeFluidNCServer(status_states=["Idle", "Run"]) as server:
        transport = FluidNCTransport(_settings(tmp_path, server, idle_timeout_seconds=0.15))
        with pytest.raises(RuntimeError, match="Timed out waiting for motion to complete"):
            transport.send(gcode="G1 X1\n", sheet_id="sheet", dry_run=False)


def test_send_fails_fast_when_fluidnc_holds_after_final_ack(tmp_path: Path) -> None:
    with FakeFluidNCServer(status_states=["Idle", "Hold"]) as server:
        transport = FluidNCTransport(_settings(tmp_path, server, idle_timeout_seconds=1.0))
        with pytest.raises(RuntimeError, match="entered Hold while waiting for motion to complete"):
            transport.send(gcode="G1 X1\n", sheet_id="sheet", dry_run=False)


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
        assert transport.home("XY").ok
        assert transport.unlock_alarm().ok
        assert transport.jog("X", 1, 1000).ok
        assert transport.feed_hold().ok
        assert transport.cycle_start().ok
        assert transport.soft_reset().ok
        time.sleep(0.1)

    assert "$H" in server.commands
    assert "$H=XY" in server.commands
    assert "$X" in server.commands
    assert "$J=G91 G21 X1.000 F1000" in server.commands
    assert b"!" in server.realtime
    assert b"~" in server.realtime
    assert b"\x18" in server.realtime


def test_home_returns_quickly_when_fluidnc_closes_connection(tmp_path: Path) -> None:
    with FakeFluidNCServer(close_command="$H") as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        result = transport.home()

    assert result.ok is False
    assert "$H" in server.commands
    assert "closed" in result.message.lower()


def test_send_commands_uses_one_connection_for_modal_preamble(tmp_path: Path) -> None:
    with FakeFluidNCServer() as server:
        transport = FluidNCTransport(_settings(tmp_path, server))
        result = transport.send_commands(["G21", "G90", "G54", "G0 Z-25"])

    assert result.ok
    assert server.commands[-4:] == ["G21", "G90", "G54", "G0 Z-25"]


def test_char_count_streaming_uses_sliding_window_within_rx_buffer(tmp_path: Path) -> None:
    with FakeCharCountServer(ack_delay_seconds=0.02) as server:
        transport = FluidNCTransport(_settings(tmp_path, server, streaming="char_count"))
        progress: list[tuple[int, int]] = []
        gcode = "\n".join(f"G0 X{i}" for i in range(40)) + "\n"
        transport.send(
            gcode=gcode,
            sheet_id="sheet",
            dry_run=False,
            progress_callback=lambda acked, total: progress.append((acked, total)),
        )

    assert len(server.commands) == 40
    # Window must hold more than one unacked line in flight (character-count
    # streaming, not one-at-a-time), but the buffer cap must have been hit
    # too -- otherwise this would just be "send everything up front".
    assert server.max_outstanding_lines > 1
    assert server.max_outstanding_lines < 40
    assert server.max_outstanding_bytes <= RX_BUFFER
    assert progress[-1] == (40, 40)
    assert [acked for acked, _ in progress] == sorted(acked for acked, _ in progress)


def test_char_count_streaming_never_exceeds_rx_buffer(tmp_path: Path) -> None:
    with FakeCharCountServer(ack_delay_seconds=0.03) as server:
        transport = FluidNCTransport(_settings(tmp_path, server, streaming="char_count"))
        gcode = "\n".join(f"G1 X{i} Y{i} F1000" for i in range(30)) + "\n"
        transport.send(gcode=gcode, sheet_id="sheet", dry_run=False)

    assert len(server.commands) == 30
    assert server.max_outstanding_bytes <= RX_BUFFER


def test_char_count_streaming_raises_on_mid_stream_error_naming_line_index(tmp_path: Path) -> None:
    with FakeCharCountServer(ack_delay_seconds=0.01, error_on_command="G0 X5") as server:
        transport = FluidNCTransport(_settings(tmp_path, server, streaming="char_count"))
        gcode = "\n".join(f"G0 X{i}" for i in range(10)) + "\n"
        with pytest.raises(RuntimeError, match=r"rejected line 6: G0 X5 :: error:9"):
            transport.send(gcode=gcode, sheet_id="sheet", dry_run=False)


def test_char_count_streaming_times_out_like_ok_wait(tmp_path: Path) -> None:
    with FakeFluidNCServer(suppress_ok_command="G1 X1") as server:
        transport = FluidNCTransport(_settings(tmp_path, server, streaming="char_count", ack_timeout_seconds=0.3))
        with pytest.raises(RuntimeError, match="rejected line 1: G1 X1 :: Timed out waiting for ok after G1 X1"):
            transport.send(gcode="G1 X1\n", sheet_id="sheet", dry_run=False)
