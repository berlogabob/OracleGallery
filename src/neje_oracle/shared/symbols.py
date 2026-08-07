from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .config import _repo_root, ensure_parent


def default_scale_config_path() -> Path:
    return _repo_root() / "assets" / "symbols" / "symbol_scales.json"


def default_symbol_root() -> Path:
    return _repo_root() / "assets" / "symbols"


def default_idle_root() -> Path:
    return _repo_root() / "assets" / "generated_idle_symbols"


def list_base_symbols(symbol_root: Path | None = None) -> list[Path]:
    root = symbol_root or default_symbol_root()
    return sorted(path for path in root.glob("*.svg") if path.is_file())


def load_symbol_scales(scale_path: Path | None = None, symbol_root: Path | None = None) -> dict[str, float]:
    symbols = list_base_symbols(symbol_root)
    path = scale_path or default_scale_config_path()
    payload: dict[str, str | int | float] = {}
    if path.exists():
        payload = cast(dict[str, str | int | float], json.loads(path.read_text(encoding="utf-8")))
    return {symbol.name: float(payload.get(symbol.name, 1.0)) for symbol in symbols}


def save_symbol_scales(
    scales: dict[str, float],
    scale_path: Path | None = None,
    symbol_root: Path | None = None,
) -> None:
    symbols = list_base_symbols(symbol_root)
    payload = {symbol.name: float(scales.get(symbol.name, 1.0)) for symbol in symbols}
    path = scale_path or default_scale_config_path()
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
