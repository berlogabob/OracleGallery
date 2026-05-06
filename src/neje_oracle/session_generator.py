from __future__ import annotations

import argparse
import csv
import json
import os
import random
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .config import UploaderSettings, _repo_root, ensure_dir
from .svg_normalizer import MARK_NAMES, normalize_svg_file

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

ORACLE_LINES = [
    "They crave certainty. Uncertainty fuels their fear.",
    "The signal bends where the voice refuses to break.",
    "A soft wound keeps its shape longer than a hard command.",
    "The mark remains after the question has left the room.",
    "What trembles most becomes the clearest line.",
]

THEME_BANK = [
    ["CERTAINTY", "FEAR", "DESIRE"],
    ["VOICE", "DOUBT", "CONTROL"],
    ["RITUAL", "SIGNAL", "BODY"],
    ["MEMORY", "PRESSURE", "TRACE"],
]


@dataclass(frozen=True)
class GeneratedSession:
    session_id: str
    session_dir: Path
    svg_file: Path
    receipt_file: Path
    base_symbol: Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate test Oracle session folders or idle SVG symbols.")
    parser.add_argument("--mode", choices=["user", "idle"], default="user")
    parser.add_argument("--count", type=int, default=None, help="Number to generate. Default: 1 for user, 8 for idle.")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=_repo_root() / "assets" / "symbols")
    parser.add_argument("--scale-config", type=Path, default=_repo_root() / "assets" / "symbols" / "symbol_scales.json")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--live", action="store_true", help="Generate repeatedly with a delay between sessions.")
    parser.add_argument("--interval-seconds", type=float, default=8.0)
    parser.add_argument("--jitter-px", type=float, default=4.0)
    args = parser.parse_args()

    if args.mode == "idle":
        count = args.count if args.count is not None else len(_load_source_symbols(args.source_root))
        output_root = args.output_root or (_repo_root() / "assets" / "generated_idle_symbols")
        generated = generate_idle_symbols(
            source_root=args.source_root,
            output_root=output_root,
            scale_config=args.scale_config,
            count=count,
            seed=args.seed,
            jitter_px=args.jitter_px,
        )
        print(f"Generated {len(generated)} idle SVG files in {output_root}")
        return

    count = args.count if args.count is not None else 1
    output_root = args.output_root or _default_user_output_root()

    total_generated = 0
    remaining = count
    while True:
        batch_count = 1 if args.live else count
        generated_sessions = generate_user_sessions(
            source_root=args.source_root,
            output_root=output_root,
            scale_config=args.scale_config,
            count=batch_count,
            seed=args.seed,
            jitter_px=args.jitter_px,
        )
        total_generated += len(generated_sessions)
        for session in generated_sessions:
            print(f"Generated user session {session.session_id}: {session.session_dir}")
        if not args.live:
            break
        if count > 0:
            remaining -= 1
            if remaining <= 0:
                break
        time.sleep(args.interval_seconds)
    print(f"Generated {total_generated} user session folder(s) in {output_root}")


def generate_user_sessions(
    *,
    source_root: Path,
    output_root: Path,
    scale_config: Path,
    count: int,
    seed: int | None = None,
    jitter_px: float = 4.0,
    symbol_name: str | None = None,
    global_scale: float = 1.0,
    include_rings: bool = False,
    start_index: int = 0,
) -> list[GeneratedSession]:
    ensure_dir(output_root)
    symbols = _load_source_symbols(source_root)
    scales = _load_scales(scale_config, symbols)
    rng = random.Random(seed if seed is not None else time.time_ns())
    generated: list[GeneratedSession] = []

    for index in range(count):
        symbol_index = start_index + index
        base_symbol = _select_symbol(symbols, symbol_name, symbol_index)
        now = datetime.now(tz=UTC)
        session_id = _unique_session_id(output_root, now, index)
        session_dir = output_root / session_id
        ensure_dir(session_dir)

        mark_index = symbols.index(base_symbol) % len(MARK_NAMES)
        mark_name = MARK_NAMES[mark_index]
        oracle_text = rng.choice(ORACLE_LINES)
        themes = rng.choice(THEME_BANK)
        measures = _generate_measures(rng)
        scale = scales.get(base_symbol.name, 1.0) * global_scale

        svg_file = session_dir / f"{session_id}_plotter.svg"
        receipt_file = session_dir / f"{session_id}_receipt.txt"
        svg_file.write_text(
            build_variant_svg(
                base_symbol,
                marker_kind="user",
                scale=scale,
                rng=rng,
                jitter_px=jitter_px * max(measures["instability"], 0.2),
                include_rings=include_rings,
            ),
            encoding="utf-8",
        )
        receipt_file.write_text(_build_receipt_text(mark_name, oracle_text, themes), encoding="utf-8")
        (session_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "created_at": now.isoformat(),
                    "generatedBy": "neje-generate-sessions",
                    "baseSymbol": base_symbol.name,
                    "symbolScale": scale,
                    "kind": "test-user",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (session_dir / "READY").write_text("", encoding="utf-8")
        _append_session_log(output_root / "session_log.csv", session_id, now, mark_name, oracle_text, themes, measures)
        generated.append(
            GeneratedSession(
                session_id=session_id,
                session_dir=session_dir,
                svg_file=svg_file,
                receipt_file=receipt_file,
                base_symbol=base_symbol,
            )
        )
    return generated


def generate_idle_symbols(
    *,
    source_root: Path,
    output_root: Path,
    scale_config: Path,
    count: int,
    seed: int | None = None,
    jitter_px: float = 2.0,
    global_scale: float = 1.0,
    include_rings: bool = False,
    start_index: int = 0,
) -> list[Path]:
    ensure_dir(output_root)
    symbols = _load_source_symbols(source_root)
    scales = _load_scales(scale_config, symbols)
    rng = random.Random(seed if seed is not None else time.time_ns())
    generated: list[Path] = []
    for index in range(count):
        symbol_index = start_index + index
        base_symbol = symbols[symbol_index % len(symbols)]
        destination = output_root / f"idle_{index + 1:02d}_{base_symbol.stem}.svg"
        destination.write_text(
            build_variant_svg(
                base_symbol,
                marker_kind="idle",
                scale=scales.get(base_symbol.name, 1.0) * global_scale,
                rng=rng,
                jitter_px=jitter_px,
                include_rings=include_rings,
            ),
            encoding="utf-8",
        )
        generated.append(destination)
    return generated


def build_variant_svg(
    source_svg: Path,
    *,
    marker_kind: str,
    scale: float,
    rng: random.Random,
    jitter_px: float,
    include_rings: bool = False,
) -> str:
    return normalize_svg_file(
        source_svg,
        marker_kind=marker_kind,
        scale=scale,
        include_rings=include_rings,
        rng=rng,
        jitter_px=jitter_px,
    )


def _default_user_output_root() -> Path:
    if os.getenv("NEJE_UPLOADER_SESSION_ROOT"):
        return UploaderSettings().session_root
    assets_sessions = _repo_root() / "assets" / "sessions"
    if assets_sessions.exists():
        return assets_sessions
    return UploaderSettings().session_root


def _load_source_symbols(source_root: Path) -> list[Path]:
    symbols = sorted(path for path in source_root.glob("*.svg") if path.is_file())
    if not symbols:
        raise FileNotFoundError(f"No SVG symbols found in {source_root}")
    return symbols


def _select_symbol(symbols: list[Path], symbol_name: str | None, index: int) -> Path:
    if not symbol_name or symbol_name == "__cycle__":
        return symbols[index % len(symbols)]
    for symbol in symbols:
        if symbol.name == symbol_name or symbol.stem == symbol_name:
            return symbol
    raise FileNotFoundError(f"Requested symbol is not in the source bank: {symbol_name}")


def _load_scales(scale_config: Path, symbols: Iterable[Path]) -> dict[str, float]:
    if not scale_config.exists():
        return {symbol.name: 1.0 for symbol in symbols}
    payload = json.loads(scale_config.read_text(encoding="utf-8"))
    return {symbol.name: float(payload.get(symbol.name, 1.0)) for symbol in symbols}


def _unique_session_id(output_root: Path, now: datetime, index: int) -> str:
    base = now.strftime("test_%Y%m%d_%H%M%S")
    candidate = f"{base}_{index + 1:03d}"
    suffix = index + 1
    while (output_root / candidate).exists():
        suffix += 1
        candidate = f"{base}_{suffix:03d}"
    return candidate


def _generate_measures(rng: random.Random) -> dict[str, float]:
    return {
        "intensity": round(rng.uniform(0.35, 0.95), 2),
        "instability": round(rng.uniform(0.15, 0.85), 2),
        "confidence": round(rng.uniform(0.45, 0.92), 2),
    }


def _build_receipt_text(mark_name: str, oracle_text: str, themes: list[str]) -> str:
    return "\n".join(
        [
            oracle_text,
            f"Your symbol: {mark_name}",
            f"Themes: {', '.join(themes)}",
            "",
        ]
    )


def _append_session_log(
    csv_path: Path,
    session_id: str,
    created_at: datetime,
    mark_name: str,
    oracle_text: str,
    themes: list[str],
    measures: dict[str, float],
) -> None:
    fieldnames = [
        "session_id",
        "timestamp",
        "symbol",
        "reply_text",
        "keywords",
        "intensity",
        "instability",
        "confidence",
    ]
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "session_id": session_id,
                "timestamp": created_at.isoformat(),
                "symbol": mark_name,
                "reply_text": oracle_text,
                "keywords": json.dumps(themes),
                "intensity": measures["intensity"],
                "instability": measures["instability"],
                "confidence": measures["confidence"],
            }
        )


if __name__ == "__main__":
    main()
