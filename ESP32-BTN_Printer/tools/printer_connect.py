#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import ip_network
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PAYLOAD = REPO_ROOT / "ESP32-BTN_Printer" / "examples" / "receipt_payload.json"


def main() -> None:
    args = parse_args()
    if args.dry_run and args.action in {"sample", "receipt"}:
        if args.action == "sample":
            print_json(build_receipt_payload(args))
            return
        print_json(build_receipt_payload(args))
        return

    base_url = resolve_base_url(args)
    print(f"ESP32 printer bridge: {base_url}")

    if args.action == "status":
        print_json(get_json(base_url, "/status", timeout=args.timeout))
        return

    if args.action == "connect":
        print_json(post_json(base_url, "/connect", None, timeout=args.timeout))
        return

    if args.action == "wake":
        print_json(post_json(base_url, "/wake", None, timeout=args.timeout))
        return

    if args.action == "test":
        params = {"protocol": args.protocol}
        if args.message:
            params["message"] = args.message
        if args.write_response:
            params["response"] = "1"
        if args.characteristic:
            params["char"] = args.characteristic
        print_json(post_json(base_url, query_path("/test-print", params), None, timeout=args.timeout))
        return

    if args.action == "raw":
        payload = {"hex": args.hex}
        if args.write_response:
            payload["response"] = True
        if args.characteristic:
            payload["char"] = args.characteristic
        print_json(post_json(base_url, "/raw", payload, timeout=args.timeout))
        return

    if args.action == "probe":
        print_json(post_json(base_url, "/probe-print", None, timeout=args.timeout))
        return

    if args.action == "sample":
        payload = build_receipt_payload(args)
        payload = payload_for_protocol(payload, args.protocol)
        if args.protocol == "ilabel" and "receipt_raster_rle_base64" in payload:
            print_json(post_ilabel_raster_chunks(base_url, payload, timeout=args.timeout))
            return
        print_json(post_json(base_url, query_path("/print", {"protocol": args.protocol}), payload, timeout=args.timeout))
        return

    if args.action == "receipt":
        payload = build_receipt_payload(args)
        payload = payload_for_protocol(payload, args.protocol)
        if args.protocol == "ilabel" and "receipt_raster_rle_base64" in payload:
            print_json(post_ilabel_raster_chunks(base_url, payload, timeout=args.timeout))
            return
        print_json(post_json(base_url, query_path("/print", {"protocol": args.protocol}), payload, timeout=args.timeout))
        return

    raise SystemExit(f"Unsupported action: {args.action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover the ESP32 printer bridge on a changing hotspot IP and send test commands.",
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=("status", "connect", "wake", "test", "raw", "probe", "sample", "receipt"),
        default="status",
        help="Command to run after discovery.",
    )
    parser.add_argument(
        "session_dir_arg",
        nargs="?",
        type=Path,
        help="Optional session folder for action=receipt.",
    )
    parser.add_argument("--esp32", help="Known ESP32 base URL, for example http://10.60.149.56")
    parser.add_argument("--host", help="Known ESP32 host/IP without http://")
    parser.add_argument("--subnet", help="Subnet to scan, for example 10.60.149.0/24. Defaults to this Mac's /24.")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--scan-timeout", type=float, default=0.6)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=96)
    parser.add_argument(
        "--protocol",
        default="ilabel",
        choices=(
            "raw",
            "escpos",
            "tspl",
            "cpcl",
            "zpl",
            "catstate",
            "catfeed",
            "catblack",
            "ilabel",
            "ilabel-status",
            "ilabel-info",
            "ilabel-cancel",
            "ilabel-text",
            "ilabel-roll",
            "ilabel-black",
        ),
    )
    parser.add_argument("--message", help="Text to print for action=test.")
    parser.add_argument("--write-response", action="store_true", help="Use BLE write-with-response for action=test.")
    parser.add_argument("--characteristic", help="BLE characteristic UUID to use for action=test.")
    parser.add_argument("--hex", help="Hex bytes for action=raw, for example '1b 40 0a'.")
    parser.add_argument("--dry-run", action="store_true", help="Build sample/receipt JSON without posting to the ESP32.")
    parser.add_argument("--preview-png", type=Path, help="Write a local thermal preview PNG for action=receipt.")
    parser.add_argument(
        "--session-dir",
        type=Path,
        default=REPO_ROOT / "assets" / "sessions" / "20260518_154452",
        help="Session folder for action=receipt.",
    )
    parser.add_argument("--no-symbol", action="store_true", help="Do not include symbol bitmap for action=receipt.")
    parser.add_argument("--printer-width", type=int, default=384)
    parser.add_argument("--ilabel-width", type=int, default=576)
    parser.add_argument("--symbol-size", type=int, default=240)
    return parser


def parse_args() -> argparse.Namespace:
    args = build_parser().parse_args()
    if args.action == "raw" and not args.hex:
        raise SystemExit("action=raw requires --hex, for example --hex '51 78 a1 00 01 00 50 b9 ff'")
    return args


def resolve_base_url(args: argparse.Namespace) -> str:
    if args.esp32:
        return args.esp32.rstrip("/")
    if args.host:
        host = args.host.strip()
        if host.startswith(("http://", "https://")):
            return host.rstrip("/")
        suffix = "" if args.port == 80 else f":{args.port}"
        return f"http://{host}{suffix}"

    bridge = discover_bridge(subnet=args.subnet, port=args.port, timeout=args.scan_timeout, workers=args.workers)
    if bridge:
        return bridge
    raise SystemExit("No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.")


def discover_bridge(*, subnet: str | None, port: int, timeout: float, workers: int) -> str | None:
    hosts = scan_hosts(subnet)
    if not hosts:
        return None

    print(f"Scanning {len(hosts)} host(s) for ESP32 printer bridge on port {port}...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(probe_host, host, port, timeout): host for host in hosts}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:
                continue
            if result:
                for pending in futures:
                    pending.cancel()
                return result
    return None


def scan_hosts(subnet: str | None) -> list[str]:
    local_ip = local_ipv4()
    if subnet:
        network = ip_network(subnet, strict=False)
    elif local_ip:
        network = ip_network(f"{local_ip}/24", strict=False)
    else:
        return []
    return [str(host) for host in network.hosts() if str(host) != local_ip]


def local_ipv4() -> str:
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(str(sock.getsockname()[0]))
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                candidates.append(ip)
    except OSError:
        pass

    return candidates[0] if candidates else ""


def probe_host(host: str, port: int, timeout: float) -> str | None:
    base_url = f"http://{host}:{port}" if port != 80 else f"http://{host}"
    try:
        status = get_json(base_url, "/status", timeout=timeout)
    except Exception:
        return None
    if {"wifi", "printer"}.issubset(status) and (
        "button_pin" in status or "transport" in status or "default_protocol" in status
    ):
        return base_url
    return None


def get_json(base_url: str, path: str, *, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"ESP32 returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach ESP32 at {base_url.rstrip('/') + path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ESP32 returned an invalid response: {exc}") from exc


def post_json(base_url: str, path: str, payload: dict[str, Any] | None, *, timeout: float) -> dict[str, Any]:
    data = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"ESP32 returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach ESP32 at {base_url.rstrip('/') + path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ESP32 returned an invalid response: {exc}") from exc


def query_path(path: str, params: dict[str, str | None]) -> str:
    filtered = {key: value for key, value in params.items() if value}
    if not filtered:
        return path
    return f"{path}?{urllib.parse.urlencode(filtered)}"


def payload_for_protocol(payload: dict[str, Any], protocol: str) -> dict[str, Any]:
    if protocol != "ilabel":
        return payload
    trimmed = dict(payload)
    trimmed.pop("symbol_escpos_base64", None)
    trimmed.pop("qr_escpos_base64", None)
    return trimmed


def post_ilabel_raster_chunks(base_url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    raster = str(payload["receipt_raster_rle_base64"])
    width = str(int(payload["ilabel_width_dots"]))
    height = str(int(payload["ilabel_height_dots"]))
    post_json(
        base_url,
        query_path("/ilabel-raster-begin", {"width": width, "height": height, "length": str(len(raster))}),
        None,
        timeout=timeout,
    )
    chunk_size = 900
    for offset in range(0, len(raster), chunk_size):
        post_json(
            base_url,
            query_path("/ilabel-raster-chunk", {"data": raster[offset : offset + chunk_size]}),
            None,
            timeout=timeout,
        )
    return post_json(base_url, "/ilabel-raster-print", None, timeout=timeout)


def build_receipt_payload(args: argparse.Namespace) -> dict[str, Any]:
    import send_receipt

    return send_receipt.build_payload(
        session_dir=(args.session_dir_arg or args.session_dir).expanduser().resolve(),
        repo_root=REPO_ROOT,
        include_symbol=not args.no_symbol,
        printer_width=args.printer_width,
        ilabel_width=args.ilabel_width,
        symbol_size=args.symbol_size,
        preview_png=args.preview_png.expanduser().resolve() if args.preview_png else None,
    )


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
