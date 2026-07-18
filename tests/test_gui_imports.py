from __future__ import annotations

import importlib


def test_gui_entrypoint_and_workspace_modules_import() -> None:
    modules = [
        "neje_oracle.blocks.gui.context",
        "neje_oracle.blocks.gui.workspaces.motion",
        "neje_oracle.blocks.gui.workspaces.connection",
        "neje_oracle.blocks.gui.workspaces.calibration",
        "neje_oracle.blocks.gui.workspaces.tests",
        "neje_oracle.blocks.gui.workspaces.work",
        "neje_oracle.blocks.gui.workspaces.exhibition",
        "neje_oracle.blocks.gui.service",
    ]

    for module in modules:
        importlib.import_module(module)

    # Every workspace exposes a single build(ctx) entry point.
    for name in ("connection", "calibration", "tests", "work", "exhibition"):
        workspace = importlib.import_module(f"neje_oracle.blocks.gui.workspaces.{name}")
        assert callable(workspace.build)
