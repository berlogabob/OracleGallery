from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "neje_oracle"


def _import_targets(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            targets.append(f"{'.' * node.level}{module}")
    return targets


def test_shared_layer_does_not_import_app_or_blocks() -> None:
    for path in (ROOT / "shared").rglob("*.py"):
        targets = _import_targets(path)
        assert not any("neje_oracle.blocks" in target for target in targets), path
        assert not any("neje_oracle.app" in target for target in targets), path
        assert not any(target.startswith("..blocks") for target in targets), path
        assert not any(target.startswith("..app") for target in targets), path


def test_non_gui_blocks_do_not_import_gui_block() -> None:
    for path in (ROOT / "blocks").rglob("*.py"):
        if "blocks/gui/" in path.as_posix():
            continue
        targets = _import_targets(path)
        assert not any("neje_oracle.blocks.gui" in target for target in targets), path
        assert not any(target.startswith("..gui") for target in targets), path


def test_app_layer_does_not_import_gui_block() -> None:
    for path in (ROOT / "app").rglob("*.py"):
        targets = _import_targets(path)
        assert not any("neje_oracle.blocks.gui" in target for target in targets), path
        assert not any(target.startswith("..blocks.gui") for target in targets), path
        assert not any(target.startswith(".blocks.gui") for target in targets), path
