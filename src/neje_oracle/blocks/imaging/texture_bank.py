"""Texture bank: JSON node graphs on disk become named textures for the editor and the sketch.

Deliberately shaped like blocks/patterns/bank.py, which is the repo's one proven zero-code
extension point: curation is which files are in the folder, and adding a texture is adding a file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ...shared.config import _repo_root
from .texture import TextureGraph

BANK_DIR = _repo_root() / "assets" / "textures"


def list_graphs(bank_dir: Path | None = None) -> list[str]:
    """Names of the graphs in the bank, sorted."""
    directory = bank_dir or BANK_DIR
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def load_graph(name: str, bank_dir: Path | None = None) -> dict[str, Any]:
    """Load and validate one graph."""
    directory = bank_dir or BANK_DIR
    matches = [path for path in directory.glob("*.json") if path.stem == name] if directory.is_dir() else []
    if not matches:
        known = ", ".join(list_graphs(directory)[:5])
        raise ValueError(f"unknown texture {name!r}; bank contains: {known or '(empty)'}")
    try:
        data = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"texture {name!r} is not readable JSON: {error}") from error
    return TextureGraph.from_dict(data).to_dict()


def load_bank(bank_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Every graph in the bank. Unreadable or invalid files are skipped, not fatal -- a hand-edited
    JSON with one bad node must not take the whole editor down mid-session."""
    directory = bank_dir or BANK_DIR
    graphs: dict[str, dict[str, Any]] = {}
    for name in list_graphs(directory):
        try:
            graphs[name] = load_graph(name, directory)
        except ValueError:
            continue
    return graphs


def save_graph(name: str, graph: dict[str, Any], *, bank_dir: Path | None = None) -> Path:
    """Write a graph into the bank under a safe name, and prove it loads back.

    load_bank() deliberately swallows invalid files, so an unvalidated save would fail silently:
    the file sits in the folder and the texture simply never appears in the picker.
    """
    directory = bank_dir or BANK_DIR

    # Validate BEFORE creating the directory or touching disk, so a bad graph leaves nothing behind.
    validated = TextureGraph.from_dict(graph).to_dict()
    directory.mkdir(parents=True, exist_ok=True)

    # Deliberately NOT Path(name).stem: this is a typed-in label, not a path, and .stem would
    # silently throw away everything before a slash -- "clouds 2026/08/12" arrives as "12".
    # Sanitizing the whole string keeps the name and still cannot escape the directory, since the
    # result has no separators left. Same character class as save_motif in patterns/bank.py.
    raw = name.strip()
    if raw.lower().endswith(".json"):
        raw = raw[:-5]
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("._-") or "texture"

    # Suffix rather than timestamp: the stem is user-facing and appears in the sketch's picker.
    target = directory / f"{safe}.json"
    counter = 2
    while target.exists():
        target = directory / f"{safe}-{counter}.json"
        counter += 1

    target.write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")
    try:
        load_graph(target.stem, directory)
    except ValueError as error:
        target.unlink(missing_ok=True)
        raise ValueError(f"texture {target.stem!r} does not load back: {error}") from error
    return target
