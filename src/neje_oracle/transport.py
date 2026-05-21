from __future__ import annotations

import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from ipaddress import ip_network
from pathlib import Path
from typing import Callable

import httpx

from .config import PlotterSettings, ensure_dir
from .models import FluidNCCommandResult, FluidNCControllerState, FluidNCProbeResult, FluidNCState


STATUS_RE = re.compile(r"<([^|>]+)(?:\|([^>]*))?>")


def settings_for_fluidnc_host(settings: PlotterSettings, host: str) -> PlotterSettings:
    return replace(
        settings,
        fluidnc_http_url=f"http://{host}",
        fluidnc_telnet_host=host,
        fluidnc_host=host,
    )


def discover_fluidnc(
    settings: PlotterSettings,
    *,
    hosts: list[str] | None = None,
    timeout_seconds: float = 0.45,
    max_workers: int = 64,
) -> FluidNCProbeResult:
    candidates = hosts or _current_subnet_hosts()
    if not candidates:
        return FluidNCProbeResult(
            telnet_port=settings.fluidnc_telnet_port,
            message="FluidNC auto-discovery failed: no local IPv4 subnet found",
            last_error="no local IPv4 subnet found",
        )

    def try_host(host: str) -> FluidNCProbeResult | None:
        resolved_settings = settings_for_fluidnc_host(settings, host)
        try:
            with socket.create_connection((host, settings.fluidnc_telnet_port), timeout=timeout_seconds):
                pass
        except OSError:
            return None
        probe = FluidNCTransport(resolved_settings).probe(timeout_seconds=max(timeout_seconds, 0.75))
        return probe if probe.online else None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(try_host, host): host for host in candidates}
        for future in as_completed(futures):
            try:
                probe = future.result()
            except Exception:  # noqa: BLE001
                continue
            if probe and probe.online:
                for pending in futures:
                    pending.cancel()
                return probe

    return FluidNCProbeResult(
        telnet_port=settings.fluidnc_telnet_port,
        message=f"FluidNC auto-discovery found no controller on port {settings.fluidnc_telnet_port}",
        last_error="no FluidNC controller found",
    )


def _current_subnet_hosts() -> list[str]:
    local_ip = _local_ipv4()
    if not local_ip:
        return []
    network = ip_network(f"{local_ip}/24", strict=False)
    return [str(host) for host in network.hosts() if str(host) != local_ip]


def _local_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return ""


class FluidNCTransport:
    def __init__(self, settings: PlotterSettings) -> None:
        self.settings = settings
        ensure_dir(settings.spool_root)

    @property
    def host(self) -> str:
        return self.settings.fluidnc_telnet_host

    @property
    def port(self) -> int:
        return self.settings.fluidnc_telnet_port

    def probe(self, *, timeout_seconds: float | None = None) -> FluidNCProbeResult:
        timeout = timeout_seconds or self.settings.fluidnc_connect_timeout_seconds
        result = FluidNCProbeResult(
            http_url=self.settings.fluidnc_http_url,
            telnet_host=self.host,
            telnet_port=self.port,
        )

        result.http_online = self._check_http(timeout)
        try:
            with self._connect(timeout) as conn:
                result.telnet_online = True
                self._drain(conn, timeout_seconds=0.3)
                status_response = self._query_status(conn, timeout_seconds=timeout)
                modal = self._send_regular_command_on_connection(conn, "$G", timeout_seconds=timeout)
        except OSError as exc:
            result.last_error = str(exc)
            result.message = self._probe_message(result)
            return result

        controller = parse_status_response(status_response)
        controller.modal_state = "\n".join(modal.response_lines)
        result.controller = controller
        result.last_response = "\n".join(line for line in [status_response, *modal.response_lines] if line)
        result.last_error = "" if modal.ok else modal.message
        result.ok = result.telnet_online and controller.state != FluidNCState.UNKNOWN
        result.message = self._probe_message(result)
        return result

    def check_connection(self, *, timeout_seconds: float = 2.0) -> tuple[bool, str]:
        probe = self.probe(timeout_seconds=timeout_seconds)
        return probe.online, probe.message

    def send_command(self, command: str, *, wait_for_ok: bool = True, timeout_seconds: float | None = None) -> FluidNCCommandResult:
        timeout = timeout_seconds or self.settings.fluidnc_ack_timeout_seconds
        try:
            with self._connect(self.settings.fluidnc_connect_timeout_seconds) as conn:
                self._drain(conn, timeout_seconds=0.2)
                if wait_for_ok:
                    return self._send_regular_command_on_connection(conn, command, timeout_seconds=timeout)
                conn.sendall((command + "\n").encode("utf-8"))
                return FluidNCCommandResult(ok=True, command=command, response_lines=[])
        except OSError as exc:
            return FluidNCCommandResult(ok=False, command=command, error=str(exc))

    def send_commands(self, commands: list[str], *, timeout_seconds: float | None = None) -> FluidNCCommandResult:
        timeout = timeout_seconds or self.settings.fluidnc_ack_timeout_seconds
        response_lines: list[str] = []
        command_label = " ; ".join(commands)
        try:
            with self._connect(self.settings.fluidnc_connect_timeout_seconds) as conn:
                self._drain(conn, timeout_seconds=0.2)
                for command in commands:
                    result = self._send_regular_command_on_connection(conn, command, timeout_seconds=timeout)
                    response_lines.extend(result.response_lines)
                    if not result.ok:
                        return FluidNCCommandResult(
                            ok=False,
                            command=command_label,
                            response_lines=response_lines,
                            error=f"{command}: {result.message}",
                        )
                return FluidNCCommandResult(ok=True, command=command_label, response_lines=response_lines)
        except OSError as exc:
            return FluidNCCommandResult(ok=False, command=command_label, response_lines=response_lines, error=str(exc))

    def send_realtime(self, byte_command: str | bytes) -> FluidNCCommandResult:
        payload = byte_command.encode("latin1") if isinstance(byte_command, str) else byte_command
        try:
            with self._connect(self.settings.fluidnc_connect_timeout_seconds) as conn:
                conn.sendall(payload)
                return FluidNCCommandResult(ok=True, command=repr(payload), response_lines=["sent"])
        except OSError as exc:
            return FluidNCCommandResult(ok=False, command=repr(payload), error=str(exc))

    def home(self, axis: str | None = None) -> FluidNCCommandResult:
        command = "$H" if not axis else f"$H={axis.upper()}"
        return self.send_command(command, wait_for_ok=True, timeout_seconds=max(self.settings.fluidnc_ack_timeout_seconds, 60.0))

    def unlock_alarm(self) -> FluidNCCommandResult:
        return self.send_command("$X", wait_for_ok=True)

    def jog(self, axis: str, distance_mm: float, feed_mm_min: float) -> FluidNCCommandResult:
        axis_name = axis.upper()
        if axis_name not in {"X", "Y", "Z"}:
            return FluidNCCommandResult(ok=False, command="", error=f"Unsupported jog axis: {axis}")
        command = f"$J=G91 G21 {axis_name}{distance_mm:.3f} F{feed_mm_min:.0f}"
        return self.send_command(command, wait_for_ok=True)

    def pen_up(self) -> FluidNCCommandResult:
        return self.send_command(self.settings.pen_up_command, wait_for_ok=True)

    def pen_down(self) -> FluidNCCommandResult:
        return self.send_command(self.settings.pen_down_command, wait_for_ok=True)

    def feed_hold(self) -> FluidNCCommandResult:
        return self.send_realtime("!")

    def cycle_start(self) -> FluidNCCommandResult:
        return self.send_realtime("~")

    def soft_reset(self) -> FluidNCCommandResult:
        return self.send_realtime(b"\x18")

    def send(
        self,
        *,
        gcode: str,
        sheet_id: str,
        dry_run: bool | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        gcode_path = self.settings.spool_root / f"{sheet_id}.gcode"
        gcode_path.write_text(gcode, encoding="utf-8")
        all_lines = gcode.splitlines()
        commands = [line.strip() for line in all_lines if _should_send_line(line)]

        effective_dry_run = self.settings.dry_run if dry_run is None else dry_run
        if effective_dry_run:
            if progress_callback:
                progress_callback(len(all_lines), len(all_lines))
            return gcode_path

        probe = self.probe(timeout_seconds=self.settings.fluidnc_connect_timeout_seconds)
        if not probe.online:
            raise RuntimeError(f"FluidNC is not ready: {probe.message}")
        if not probe.controller.is_idle:
            raise RuntimeError(f"FluidNC is not idle: {probe.controller.state.value}")

        with self._connect(self.settings.fluidnc_connect_timeout_seconds) as conn:
            self._drain(conn, timeout_seconds=0.2)
            total = len(commands)
            for index, line in enumerate(commands, start=1):
                result = self._send_regular_command_on_connection(
                    conn,
                    line,
                    timeout_seconds=self.settings.fluidnc_ack_timeout_seconds,
                )
                if not result.ok:
                    raise RuntimeError(f"FluidNC rejected line {index}: {line} :: {result.message}")
                if progress_callback:
                    progress_callback(index, total)
            if commands:
                self._wait_until_idle(conn, sheet_id=sheet_id)
        return gcode_path

    def _wait_until_idle(self, conn: socket.socket, *, sheet_id: str) -> None:
        timeout = self.settings.fluidnc_idle_timeout_seconds
        deadline = time.monotonic() + timeout
        last_state = "unknown"
        last_status = ""
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                status_response = self._query_status(
                    conn,
                    timeout_seconds=max(0.1, min(0.5, remaining)),
                )
            except TimeoutError:
                time.sleep(min(0.2, max(0.0, remaining)))
                continue
            except OSError as exc:
                raise RuntimeError(
                    f"FluidNC connection closed while waiting for motion to complete after streaming {sheet_id}: {exc}"
                ) from exc

            controller = parse_status_response(status_response)
            last_state = controller.state.value
            last_status = controller.raw_status
            if controller.is_idle:
                return
            if controller.is_alarm or controller.is_hold:
                raise RuntimeError(
                    f"FluidNC entered {controller.state.value} while waiting for motion to complete after streaming {sheet_id}: {last_status}"
                )
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))

        raise RuntimeError(
            f"Timed out waiting for motion to complete after streaming {sheet_id}; FluidNC last state {last_state}"
        )

    def _check_http(self, timeout_seconds: float) -> bool:
        if not self.settings.fluidnc_http_url:
            return False
        try:
            response = httpx.get(self.settings.fluidnc_http_url, timeout=timeout_seconds, follow_redirects=True)
            return response.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    def _connect(self, timeout_seconds: float) -> socket.socket:
        conn = socket.create_connection((self.host, self.port), timeout=timeout_seconds)
        conn.settimeout(timeout_seconds)
        return conn

    def _query_status(self, conn: socket.socket, *, timeout_seconds: float) -> str:
        conn.sendall(b"?")
        deadline = time.monotonic() + timeout_seconds
        buffer = ""
        while time.monotonic() < deadline:
            buffer += self._recv_text(conn, timeout_seconds=max(0.1, min(0.5, deadline - time.monotonic())))
            match = STATUS_RE.search(buffer)
            if match:
                return match.group(0)
        raise TimeoutError("Timed out waiting for FluidNC status response")

    def _send_regular_command_on_connection(self, conn: socket.socket, command: str, *, timeout_seconds: float) -> FluidNCCommandResult:
        conn.sendall((command.rstrip() + "\n").encode("utf-8"))
        lines: list[str] = []
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            chunk = self._recv_text(conn, timeout_seconds=max(0.1, min(0.5, deadline - time.monotonic())))
            if not chunk:
                continue
            for raw_line in chunk.replace("\r", "\n").split("\n"):
                line = raw_line.strip()
                if not line:
                    continue
                lines.append(line)
                lower = line.lower()
                if lower == "ok":
                    return FluidNCCommandResult(ok=True, command=command, response_lines=lines)
                if lower.startswith("error") or "alarm" in lower:
                    return FluidNCCommandResult(ok=False, command=command, response_lines=lines, error=line)
        return FluidNCCommandResult(ok=False, command=command, response_lines=lines, error=f"Timed out waiting for ok after {command}")

    def _drain(self, conn: socket.socket, *, timeout_seconds: float) -> str:
        previous_timeout = conn.gettimeout()
        conn.settimeout(timeout_seconds)
        chunks: list[str] = []
        try:
            while True:
                text = self._recv_text(conn, timeout_seconds=timeout_seconds)
                if not text:
                    break
                chunks.append(text)
        except OSError:
            pass
        finally:
            conn.settimeout(previous_timeout)
        return "".join(chunks)

    def _recv_text(self, conn: socket.socket, *, timeout_seconds: float) -> str:
        previous_timeout = conn.gettimeout()
        conn.settimeout(timeout_seconds)
        try:
            try:
                data = conn.recv(4096)
                if not data:
                    raise ConnectionAbortedError("Connection closed by FluidNC")
                return data.decode("utf-8", "replace")
            except socket.timeout:
                return ""
        finally:
            conn.settimeout(previous_timeout)

    def _probe_message(self, probe: FluidNCProbeResult) -> str:
        if probe.ok:
            return (
                f"FluidNC online: HTTP {'online' if probe.http_online else 'offline'}, "
                f"Telnet online, state {probe.controller.state.value}, "
                f"MPos {_format_position(probe.controller.machine_position)}"
            )
        if not probe.telnet_online:
            return (
                f"FluidNC Telnet offline: {probe.telnet_host}:{probe.telnet_port}; "
                f"HTTP {'online' if probe.http_online else 'offline'}"
                + (f" ({probe.last_error})" if probe.last_error else "")
            )
        return f"FluidNC Telnet online but status probe failed: {probe.last_error or probe.last_response or 'unknown response'}"


def parse_status_response(response: str) -> FluidNCControllerState:
    match = STATUS_RE.search(response.strip())
    if not match:
        return FluidNCControllerState(raw_status=response.strip())

    raw_state = match.group(1).strip()
    fields = (match.group(2) or "").split("|")
    state = _parse_state(raw_state)
    machine_position: tuple[float, float, float] | None = None
    feed_rate: float | None = None
    spindle_speed: float | None = None
    overrides: tuple[int, int, int] | None = None
    pins = ""

    for field in fields:
        if field.startswith("MPos:"):
            machine_position = _parse_float_tuple(field.removeprefix("MPos:"), 3)
        elif field.startswith("FS:"):
            values = _parse_float_tuple(field.removeprefix("FS:"), 2)
            if values is not None:
                feed_rate, spindle_speed = values
        elif field.startswith("Ov:"):
            values = _parse_int_tuple(field.removeprefix("Ov:"), 3)
            if values is not None:
                overrides = values
        elif field.startswith("Pn:"):
            pins = field.removeprefix("Pn:")

    return FluidNCControllerState(
        state=state,
        machine_position=machine_position,
        feed_rate=feed_rate,
        spindle_speed=spindle_speed,
        overrides=overrides,
        pins=pins,
        raw_status=match.group(0),
    )


def _parse_state(value: str) -> FluidNCState:
    for state in FluidNCState:
        if value.startswith(state.value):
            return state
    return FluidNCState.UNKNOWN


def _parse_float_tuple(value: str, expected: int) -> tuple[float, ...] | None:
    parts = value.split(",")
    if len(parts) < expected:
        return None
    try:
        return tuple(float(part) for part in parts[:expected])
    except ValueError:
        return None


def _parse_int_tuple(value: str, expected: int) -> tuple[int, ...] | None:
    parts = value.split(",")
    if len(parts) < expected:
        return None
    try:
        return tuple(int(float(part)) for part in parts[:expected])
    except ValueError:
        return None


def _format_position(position: tuple[float, float, float] | None) -> str:
    if position is None:
        return "-"
    return ",".join(f"{axis:.3f}" for axis in position)


def _should_send_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith(";"))
