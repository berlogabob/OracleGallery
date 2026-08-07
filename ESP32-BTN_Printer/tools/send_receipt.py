#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import base64
import csv
import json
import math
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - operator setup feedback
    raise SystemExit("Pillow and qrcode are required. Run `uv sync --extra dev` from the repo root.") from exc


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
RECEIPT_TITLE = "ORACLE"
RECEIPT_SUBTITLE = "THE ORACLE THAT WEARS US"


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
        ilabel_width=args.ilabel_width,
        preview_png=args.preview_png.expanduser().resolve() if args.preview_png else None,
    )
    encoded = json.dumps(payload, ensure_ascii=True, indent=2)
    post_payload = payload_for_protocol(payload, args.protocol)
    post_encoded = json.dumps(post_payload, ensure_ascii=True, separators=(",", ":"))

    if args.output:
        args.output.expanduser().write_text(encoded + "\n", encoding="utf-8")

    if args.dry_run or not args.esp32:
        print(encoded)
        if not args.esp32:
            print("\nNo --esp32 URL supplied; not posting.", file=sys.stderr)
        return

    path = "/print"
    if args.protocol:
        path += "?" + urllib.parse.urlencode({"protocol": args.protocol})
    url = args.esp32.rstrip("/") + path
    if args.protocol == "ilabel" and "receipt_raster_rle_base64" in post_payload:
        print_json(post_ilabel_raster_chunks(args.esp32, post_payload, timeout=args.timeout))
        return

    request = urllib.request.Request(
        url,
        data=post_encoded.encode("utf-8"),
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
    parser = argparse.ArgumentParser(description="Build or send an Oracle thermal receipt to the ESP32 printer bridge.")
    parser.add_argument(
        "session_dir",
        nargs="?",
        type=Path,
        default=repo_root / "assets" / "sessions" / "20260518_154452",
        help="Session folder containing *_receipt.txt and optional *_receipt.csv.",
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--esp32", help="ESP32 base URL, for example http://192.168.1.42")
    parser.add_argument(
        "--protocol", default="ilabel", choices=("ilabel", "escpos"), help="ESP32 /print protocol query."
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true", help="Print JSON without posting to the ESP32.")
    parser.add_argument("--output", type=Path, help="Write the generated JSON payload to a file.")
    parser.add_argument("--preview-png", type=Path, help="Write a local black-on-white thermal preview PNG.")
    parser.add_argument("--no-symbol", action="store_true", help="Do not include the simplified symbol bitmap.")
    parser.add_argument("--printer-width", type=int, default=384, help="ESC/POS thermal printer raster width in dots.")
    parser.add_argument("--ilabel-width", type=int, default=576, help="iLabel thermal printer raster width in dots.")
    parser.add_argument("--symbol-size", type=int, default=168, help="Square symbol render size in dots.")
    return parser


def payload_for_protocol(payload: dict[str, Any], protocol: str) -> dict[str, Any]:
    if protocol != "ilabel":
        return payload
    trimmed = dict(payload)
    trimmed.pop("symbol_escpos_base64", None)
    trimmed.pop("qr_escpos_base64", None)
    return trimmed


def post_ilabel_raster_chunks(base_url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    base = base_url.rstrip("/")
    raster = str(payload["receipt_raster_rle_base64"])
    width = int(payload["ilabel_width_dots"])
    height = int(payload["ilabel_height_dots"])
    post_json(
        base,
        "/ilabel-raster-begin?"
        + urllib.parse.urlencode({"width": str(width), "height": str(height), "length": str(len(raster))}),
        None,
        timeout=timeout,
    )
    chunk_size = 900
    for offset in range(0, len(raster), chunk_size):
        chunk = raster[offset : offset + chunk_size]
        post_json(base, "/ilabel-raster-chunk?" + urllib.parse.urlencode({"data": chunk}), None, timeout=timeout)
    return post_json(base, "/ilabel-raster-print", None, timeout=timeout)


def post_json(base_url: str, path: str, payload: dict[str, Any] | None, *, timeout: float) -> dict[str, Any]:
    data = b"" if payload is None else json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
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


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def build_payload(
    *,
    session_dir: Path,
    repo_root: Path,
    include_symbol: bool,
    printer_width: int,
    symbol_size: int,
    ilabel_width: int | None = 576,
    preview_png: Path | None = None,
) -> dict[str, Any]:
    session_id = session_dir.name
    receipt_data = parse_receipt_txt(find_required(session_dir, f"{session_id}_receipt.txt", "*_receipt.txt"))
    csv_data = load_csv_data(session_dir)

    mark_name = first_non_empty(receipt_data.get("mark_name"), csv_data.get("mark_name"))
    symbol_label = normalize_display_name(mark_name)
    oracle_text = first_non_empty(receipt_data.get("oracle_text"), csv_data.get("oracle_text"))
    themes = receipt_data.get("themes") or csv_data.get("themes") or []
    measures = csv_data.get("measures") or {}
    session_url = f"{GALLERY_BASE_URL}/#/session/{session_id}"
    symbol_path = find_symbol_path(session_dir, repo_root, session_id, mark_name) if include_symbol else None
    qr_image = build_qr_image(session_url, min(220, max(160, printer_width - 96)))

    escpos_symbol = b""
    if symbol_path:
        symbol_image = render_svg_symbol_image(symbol_path, width=printer_width, height=symbol_size)
        escpos_symbol = escpos_raster(symbol_image)
    elif include_symbol:
        print(
            f"No matching symbol SVG found for mark '{mark_name}'; sending receipt without symbol bitmap.",
            file=sys.stderr,
        )

    qr_escpos = escpos_raster(center_on_width(qr_image, printer_width))
    ilabel_image = render_thermal_receipt(
        session_id=session_id,
        symbol_label=symbol_label,
        oracle_text=oracle_text,
        themes=themes,
        measures=measures,
        session_url=session_url,
        symbol_path=symbol_path,
        width=ilabel_width or 576,
    )
    if preview_png:
        preview_png.parent.mkdir(parents=True, exist_ok=True)
        ilabel_image.save(preview_png)

    ilabel_raster = raster_bytes(ilabel_image)
    payload: dict[str, Any] = {
        "session_id": session_id,
        "mark_name": mark_name,
        "oracle_text": sanitize_ascii(oracle_text),
        "themes": [sanitize_ascii(str(theme)) for theme in themes],
        "measures": measures,
        "session_url": session_url,
        "receipt_title": RECEIPT_TITLE,
        "subtitle": RECEIPT_SUBTITLE,
        "symbol_label": symbol_label,
        "qr_required": True,
        "persona_image_allowed": False,
        "thermal_width_dots": printer_width,
        "ilabel_width_dots": ilabel_image.width,
        "ilabel_height_dots": ilabel_image.height,
        "receipt_raster_rle_base64": base64.b64encode(rle_encode(ilabel_raster)).decode("ascii"),
        "qr_escpos_base64": base64.b64encode(qr_escpos).decode("ascii"),
        "symbol_escpos_base64": base64.b64encode(escpos_symbol).decode("ascii") if escpos_symbol else "",
    }
    return payload


def find_symbol_path(session_dir: Path, repo_root: Path, session_id: str, mark_name: str) -> Path | None:
    symbol_path = find_optional(session_dir, f"{session_id}_plotter.svg", "*_plotter.svg")
    if symbol_path:
        return symbol_path
    return symbol_for_mark(repo_root / "assets" / "symbols", mark_name)


def render_thermal_receipt(
    *,
    session_id: str,
    symbol_label: str,
    oracle_text: str,
    themes: list[str],
    measures: dict[str, float],
    session_url: str,
    symbol_path: Path | None,
    width: int,
) -> Image.Image:
    fonts = load_fonts()
    margin = 24 if width >= 576 else 16
    content_width = width - margin * 2
    blocks: list[Image.Image] = []

    blocks.append(text_block(RECEIPT_TITLE, fonts["title"], width, align="center", top=8, bottom=2))
    blocks.append(text_block(RECEIPT_SUBTITLE, fonts["small"], width, align="center", bottom=14))
    blocks.append(text_block(f"SESSION {session_id}", fonts["small"], width, align="center", bottom=16))

    if symbol_path:
        symbol_size = min(176, content_width)
        symbol = render_svg_symbol_image(symbol_path, width=symbol_size, height=symbol_size)
        blocks.append(center_on_width(symbol, width, top=4, bottom=6))

    blocks.append(text_block(symbol_label or "UNKNOWN SYMBOL", fonts["section"], width, align="center", bottom=18))
    blocks.append(rule_block(width, margin))
    blocks.append(
        text_block("WHAT THE ORACLE PERCEIVED", fonts["section"], width, align="left", margin=margin, top=12, bottom=6)
    )
    blocks.append(
        wrapped_text_block(sanitize_ascii(oracle_text), fonts["body"], width, content_width, margin, bottom=18)
    )
    blocks.append(
        text_block("WHAT THE SYSTEM MEASURED", fonts["section"], width, align="left", margin=margin, bottom=6)
    )
    measure_lines = [
        f"INTENSITY   {format_measure(measures.get('intensity'))}",
        f"INSTABILITY {format_measure(measures.get('instability'))}",
        f"CONFIDENCE  {format_measure(measures.get('confidence'))}",
    ]
    blocks.append(wrapped_text_block("\n".join(measure_lines), fonts["body"], width, content_width, margin, bottom=18))
    blocks.append(text_block("THEMES", fonts["section"], width, align="left", margin=margin, bottom=6))
    blocks.append(
        wrapped_text_block(
            ", ".join(sanitize_ascii(str(theme)).upper() for theme in themes) or "NONE",
            fonts["body"],
            width,
            content_width,
            margin,
            bottom=18,
        )
    )
    blocks.append(rule_block(width, margin))
    blocks.append(text_block("VIEW YOUR MARK ONLINE", fonts["section"], width, align="center", top=12, bottom=10))
    qr_size = min(248 if width >= 576 else 200, content_width)
    blocks.append(center_on_width(build_qr_image(session_url, qr_size), width, bottom=8))
    blocks.append(text_block(session_id, fonts["small"], width, align="center", bottom=16))

    height = sum(block.height for block in blocks) + 12
    image = Image.new("L", (width, height), 255)
    y = 0
    for block in blocks:
        image.paste(block, (0, y))
        y += block.height
    return image.point(lambda pixel: 0 if pixel < 180 else 255, mode="L")


def load_fonts() -> dict[str, ImageFont.ImageFont]:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]

    def font(size: int) -> ImageFont.ImageFont:
        for candidate in candidates:
            path = Path(candidate)
            if path.exists():
                return ImageFont.truetype(str(path), size=size)
        return ImageFont.load_default()

    return {
        "title": font(42),
        "section": font(22),
        "body": font(22),
        "small": font(17),
    }


def text_block(
    text: str,
    font: ImageFont.ImageFont,
    width: int,
    *,
    align: str,
    margin: int = 0,
    top: int = 0,
    bottom: int = 0,
) -> Image.Image:
    text = sanitize_ascii(text)
    bbox = font.getbbox(text or " ")
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    image = Image.new("L", (width, max(1, top + text_height + bottom)), 255)
    draw = ImageDraw.Draw(image)
    x = max(0, (width - text_width) // 2) if align == "center" else margin
    draw.text((x, top - bbox[1]), text, fill=0, font=font)
    return image


def wrapped_text_block(
    text: str,
    font: ImageFont.ImageFont,
    width: int,
    content_width: int,
    margin: int,
    *,
    bottom: int = 0,
) -> Image.Image:
    lines: list[str] = []
    for paragraph in sanitize_ascii(text).splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue
        approx_chars = max(12, content_width // max(8, int(font.getlength("M"))))
        for line in textwrap.wrap(paragraph, width=approx_chars, break_long_words=False) or [""]:
            while font.getlength(line) > content_width and len(line) > 8:
                split_at = max(8, len(line) - 4)
                lines.append(line[:split_at].rstrip())
                line = line[split_at:].lstrip()
            lines.append(line)

    line_height = max(18, font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + 6)
    image = Image.new("L", (width, max(1, len(lines) * line_height + bottom)), 255)
    draw = ImageDraw.Draw(image)
    y = 0
    for line in lines:
        draw.text((margin, y), line, fill=0, font=font)
        y += line_height
    return image


def rule_block(width: int, margin: int) -> Image.Image:
    image = Image.new("L", (width, 10), 255)
    draw = ImageDraw.Draw(image)
    draw.line([(margin, 5), (width - margin, 5)], fill=0, width=2)
    return image


def center_on_width(image: Image.Image, width: int, *, top: int = 0, bottom: int = 0) -> Image.Image:
    out = Image.new("L", (width, image.height + top + bottom), 255)
    out.paste(image.convert("L"), ((width - image.width) // 2, top))
    return out


def build_qr_image(data: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("L")
    return image.resize((size, size), Image.Resampling.NEAREST)


def render_svg_symbol_image(symbol_path: Path, *, width: int, height: int) -> Image.Image:
    root = ET.fromstring(symbol_path.read_text(encoding="utf-8"))
    source_width = parse_svg_number(root.get("width")) or 800.0
    source_height = parse_svg_number(root.get("height")) or 800.0
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [float(part) for part in viewbox.replace(",", " ").split()]
        if len(parts) == 4:
            source_width, source_height = parts[2], parts[3]

    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    scale = min((width * 0.82) / source_width, (height * 0.82) / source_height)
    offset_x = (width - source_width * scale) / 2.0
    offset_y = (height - source_height * scale) / 2.0

    def transform(x: float, y: float) -> tuple[float, float]:
        return offset_x + x * scale, offset_y + y * scale

    for element in root.iter():
        tag = strip_ns(element.tag)
        stroke_width = max(2, int(round((parse_svg_number(element.get("stroke-width")) or 2.0) * scale)))
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
    return image.point(lambda pixel: 0 if pixel < 180 else 255, mode="L")


def raster_bytes(image: Image.Image) -> bytes:
    image = image.convert("L").point(lambda pixel: 0 if pixel < 180 else 255, mode="L")
    width, height = image.size
    width_bytes = math.ceil(width / 8)
    pixels = image.load()
    payload = bytearray()
    for y in range(height):
        for byte_x in range(width_bytes):
            value = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < width and pixels[x, y] < 128:
                    value |= 0x80 >> bit
            payload.append(value)
    return bytes(payload)


def rle_encode(data: bytes) -> bytes:
    if not data:
        return b""
    encoded = bytearray()
    run_value = data[0]
    run_length = 1
    for value in data[1:]:
        if value == run_value and run_length < 255:
            run_length += 1
            continue
        encoded.extend((run_length, run_value))
        run_value = value
        run_length = 1
    encoded.extend((run_length, run_value))
    return bytes(encoded)


def escpos_raster(image: Image.Image) -> bytes:
    image = image.convert("L").point(lambda pixel: 0 if pixel < 180 else 255, mode="L")
    width, height = image.size
    width_bytes = math.ceil(width / 8)
    payload = bytearray()
    payload.extend(
        [0x1D, 0x76, 0x30, 0x00, width_bytes & 0xFF, (width_bytes >> 8) & 0xFF, height & 0xFF, (height >> 8) & 0xFF]
    )
    payload.extend(raster_bytes(image))
    return bytes(payload)


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
    candidates: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = strip_box_art(raw_line)
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("your symbol:"):
            data["mark_name"] = line.split(":", 1)[1].strip()
            continue
        if lower.startswith("themes:"):
            data["themes"] = parse_themes(line.split(":", 1)[1].strip())
            continue
        if not lower.startswith(("oracle", "session", "timestamp")):
            candidates.append(line)
    data["oracle_text"] = " ".join(candidates[:3]).strip()
    return data


def strip_box_art(raw_line: str) -> str:
    line = raw_line.strip().strip("║│|")
    line = re.sub(r"[╔╗╚╝╠╣═─]+", "", line).strip()
    return line


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
        return [sanitize_ascii(str(item)).strip() for item in raw if str(item).strip()]
    try:
        parsed = ast.literal_eval(str(raw))
    except (SyntaxError, ValueError):
        parsed = [part.strip() for part in str(raw).split(",")]
    if isinstance(parsed, list):
        return [sanitize_ascii(str(item)).strip().strip("'\"") for item in parsed if str(item).strip()]
    return [sanitize_ascii(str(parsed)).strip()]


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
        if (
            normalize_name(symbol.stem).find(normalized_mark) >= 0
            or normalized_mark.find(normalize_name(symbol.stem)) >= 0
        ):
            return symbol
    return None


def normalize_display_name(value: str) -> str:
    cleaned = sanitize_ascii(value).upper()
    cleaned = re.sub(r"[^A-Z0-9 ]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_name(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def sanitize_ascii(value: str) -> str:
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
    text = str(value)
    for source, target in replacements.items():
        text = text.replace(source, target)
    return "".join(ch if ch == "\n" or 32 <= ord(ch) < 127 else "?" for ch in text)


def format_measure(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{round(float(value) * 100):>3}%"


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
