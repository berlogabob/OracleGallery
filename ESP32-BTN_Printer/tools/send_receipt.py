#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import base64
import csv
import json
import math
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover - operator setup feedback
    raise SystemExit("Pillow is required. Run `uv sync --extra dev` from the repo root.") from exc


MARK_NAMES = [
    "THE KIND SOUL",
    "THE PITIFUL STORY",
    "THE SHRIEK",
    "THE THORNS",
    "THE SKY EYE",
    "THE BITTER ROOT",
    "THE STILL BLADE",
    "THE HOLLOW SUN",
]

GALLERY_BASE_URL = "https://berlogabob.github.io/OracleGallery"

def main() -> None:
    args = parse_args()
    session_dir = args.session_dir.expanduser().resolve()
    if not session_dir.exists():
        raise SystemExit(f"Session folder does not exist: {session_dir}")

    payload = build_payload(
        session_dir=session_dir,
        repo_root=args.repo_root.expanduser().resolve(),
        include_symbol=not args.no_symbol,
        printer_width=args.printer_width,
        symbol_size=args.symbol_size,
    )
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        args.output.expanduser().write_text(encoded + "\n", encoding="utf-8")

    if args.dry_run or not args.esp32:
        print(encoded)
        if not args.esp32:
            print("\nNo --esp32 URL supplied; not posting.", file=sys.stderr)
        return

    url = args.esp32.rstrip("/") + "/print"
    request = urllib.request.Request(
        url,
        data=encoded.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            print(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"ESP32 returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach ESP32 at {url}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Send an Oracle session receipt to the ESP32 printer bridge.")
    parser.add_argument(
        "session_dir",
        nargs="?",
        type=Path,
        default=repo_root / "assets" / "sessions" / "20260505_155503",
        help="Session folder containing *_receipt.txt and optional *_receipt.csv.",
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--esp32", help="ESP32 base URL, for example http://192.168.1.42")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true", help="Print JSON without posting to the ESP32.")
    parser.add_argument("--output", type=Path, help="Write the generated JSON payload to a file.")
    parser.add_argument("--no-symbol", action="store_true", help="Do not include ESC/POS raster symbol bytes.")
    parser.add_argument("--printer-width", type=int, default=384, help="Thermal printer raster width in dots.")
    parser.add_argument("--symbol-size", type=int, default=240, help="Square symbol render size in dots.")
    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def build_payload(
    *,
    session_dir: Path,
    repo_root: Path,
    include_symbol: bool,
    printer_width: int,
    symbol_size: int,
) -> dict[str, Any]:
    session_id = session_dir.name
    receipt_data = parse_receipt_txt(find_required(session_dir, f"{session_id}_receipt.txt", "*_receipt.txt"))
    csv_data = load_csv_data(session_dir)

    mark_name = first_non_empty(receipt_data.get("mark_name"), csv_data.get("mark_name"))
    oracle_text = first_non_empty(receipt_data.get("oracle_text"), csv_data.get("oracle_text"))
    themes = receipt_data.get("themes") or csv_data.get("themes") or []
    measures = csv_data.get("measures") or {}

    payload: dict[str, Any] = {
        "session_id": session_id,
        "mark_name": mark_name,
        "oracle_text": oracle_text,
        "themes": themes,
        "measures": measures,
        "session_url": f"{GALLERY_BASE_URL}/#/session/{session_id}",
        "symbol_escpos_base64": "",
    }

    if include_symbol:
        symbol_path = find_optional(session_dir, f"{session_id}_plotter.svg", "*_plotter.svg")
        if not symbol_path:
            symbol_path = symbol_for_mark(repo_root / "assets" / "symbols", mark_name)
        if symbol_path:
            payload["symbol_escpos_base64"] = base64.b64encode(
                render_svg_as_escpos(symbol_path, printer_width=printer_width, symbol_size=symbol_size)
            ).decode("ascii")
        else:
            print(f"No matching symbol SVG found for mark '{mark_name}'; sending text-only receipt.", file=sys.stderr)

    return payload


def find_required(session_dir: Path, preferred_name: str, pattern: str) -> Path:
    preferred = session_dir / preferred_name
    if preferred.exists():
        return preferred
    matches = sorted(session_dir.glob(pattern))
    if matches:
        return matches[0]
    raise SystemExit(f"Missing required file matching {pattern} in {session_dir}")


def find_optional(session_dir: Path, preferred_name: str, pattern: str) -> Path | None:
    preferred = session_dir / preferred_name
    if preferred.exists():
        return preferred
    matches = sorted(session_dir.glob(pattern))
    return matches[0] if matches else None


def parse_receipt_txt(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {"mark_name": "", "oracle_text": "", "themes": []}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("╔", "║", "╠", "╚")):
            continue
        lower = line.lower()
        if lower.startswith("your symbol:"):
            data["mark_name"] = line.split(":", 1)[1].strip()
            continue
        if lower.startswith("themes:"):
            data["themes"] = parse_themes(line.split(":", 1)[1].strip())
            continue
        if not data["oracle_text"]:
            data["oracle_text"] = line
    return data


def load_csv_data(session_dir: Path) -> dict[str, Any]:
    session_id = session_dir.name
    csv_candidates = sorted(session_dir.glob("*_receipt.csv"))
    root_log = session_dir.parent / "session_log.csv"
    if root_log.exists():
        csv_candidates.append(root_log)

    for path in csv_candidates:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("session_id") != session_id:
                    continue
                return {
                    "mark_name": first_non_empty(row.get("symbol"), row.get("mark_name")).upper(),
                    "oracle_text": first_non_empty(row.get("reply_text"), row.get("oracle_text")),
                    "themes": parse_themes(first_non_empty(row.get("keywords"), row.get("themes"))),
                    "measures": parse_measures(row),
                }
    return {}


def parse_themes(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    try:
        parsed = ast.literal_eval(str(raw))
    except (SyntaxError, ValueError):
        parsed = [part.strip() for part in str(raw).split(",")]
    if isinstance(parsed, list):
        return [str(item).strip().strip("'\"") for item in parsed if str(item).strip()]
    return [str(parsed).strip()]


def parse_measures(row: dict[str, str]) -> dict[str, float]:
    aliases = {
        "intensity": ("intensity", "voice_intensity"),
        "instability": ("instability",),
        "confidence": ("confidence",),
    }
    result: dict[str, float] = {}
    for output_key, input_keys in aliases.items():
        for input_key in input_keys:
            raw = row.get(input_key)
            if raw in (None, ""):
                continue
            try:
                result[output_key] = float(raw)
                break
            except ValueError:
                continue
    return result


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def symbol_for_mark(symbol_root: Path, mark_name: str) -> Path | None:
    symbols = sorted(path for path in symbol_root.glob("*.svg") if path.is_file())
    normalized_mark = normalize_name(mark_name)
    for index, symbol in enumerate(symbols):
        if index < len(MARK_NAMES) and normalize_name(MARK_NAMES[index]) == normalized_mark:
            return symbol
    for symbol in symbols:
        if normalize_name(symbol.stem).find(normalized_mark) >= 0 or normalized_mark.find(normalize_name(symbol.stem)) >= 0:
            return symbol
    return None


def normalize_name(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def render_svg_as_escpos(symbol_path: Path, *, printer_width: int, symbol_size: int) -> bytes:
    root = ET.fromstring(symbol_path.read_text(encoding="utf-8"))
    width = parse_svg_number(root.get("width")) or 800.0
    height = parse_svg_number(root.get("height")) or 800.0
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [float(part) for part in viewbox.replace(",", " ").split()]
        if len(parts) == 4:
            width, height = parts[2], parts[3]

    image = Image.new("L", (printer_width, symbol_size), 255)
    draw = ImageDraw.Draw(image)
    scale = min((printer_width * 0.78) / width, (symbol_size * 0.86) / height)
    offset_x = (printer_width - width * scale) / 2.0
    offset_y = (symbol_size - height * scale) / 2.0

    def transform(x: float, y: float) -> tuple[float, float]:
        return offset_x + x * scale, offset_y + y * scale

    for element in root.iter():
        tag = strip_ns(element.tag)
        stroke_width = max(1, int(round((parse_svg_number(element.get("stroke-width")) or 2.0) * scale)))
        if tag == "line":
            draw.line(
                [
                    transform(float_attr(element, "x1"), float_attr(element, "y1")),
                    transform(float_attr(element, "x2"), float_attr(element, "y2")),
                ],
                fill=0,
                width=stroke_width,
            )
        elif tag in {"polyline", "polygon"}:
            points = parse_points(element.get("points", ""))
            if len(points) >= 2:
                draw.line([transform(x, y) for x, y in points], fill=0, width=stroke_width, joint="curve")
        elif tag == "circle":
            cx = float_attr(element, "cx")
            cy = float_attr(element, "cy")
            radius = float_attr(element, "r") * scale
            x, y = transform(cx, cy)
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], outline=0, width=stroke_width)

    return escpos_raster(image)


def escpos_raster(image: Image.Image) -> bytes:
    width, height = image.size
    width_bytes = math.ceil(width / 8)
    payload = bytearray()
    payload.extend([0x1D, 0x76, 0x30, 0x00, width_bytes & 0xFF, (width_bytes >> 8) & 0xFF, height & 0xFF, (height >> 8) & 0xFF])

    pixels = image.load()
    for y in range(height):
        for byte_x in range(width_bytes):
            value = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < width and pixels[x, y] < 128:
                    value |= 0x80 >> bit
            payload.append(value)
    return bytes(payload)


def parse_points(raw: str) -> list[tuple[float, float]]:
    values = [float(part) for part in raw.replace(",", " ").split()]
    return list(zip(values[0::2], values[1::2], strict=False))


def float_attr(element: ET.Element, name: str) -> float:
    return parse_svg_number(element.get(name)) or 0.0


def parse_svg_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.strip().replace("px", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if tag.startswith("{") else tag


if __name__ == "__main__":
    main()
