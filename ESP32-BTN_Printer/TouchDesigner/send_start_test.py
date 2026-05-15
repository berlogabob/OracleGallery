#!/usr/bin/env python3
"""Send a local START packet to the TouchDesigner UDP listener."""

from __future__ import annotations

import argparse
import socket


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7000)
    parser.add_argument("--message", default="START")
    args = parser.parse_args()

    payload = args.message.encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, (args.host, args.port))

    print(f"sent {args.message!r} to {args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
