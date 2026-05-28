from __future__ import annotations

import importlib


def test_gui_entrypoint_and_workspace_modules_import() -> None:
    modules = [
        "neje_oracle.gui_components.components.status",
        "neje_oracle.gui_workspaces.connection",
        "neje_oracle.gui_workspaces.calibration",
        "neje_oracle.gui_workspaces.tests",
        "neje_oracle.gui_workspaces.work",
        "neje_oracle.gui_workspaces.exhibition",
        "neje_oracle.gui_service",
        "neje_oracle.blocks.gui.components.components.status",
        "neje_oracle.blocks.gui.workspaces.connection",
        "neje_oracle.blocks.gui.workspaces.calibration",
        "neje_oracle.blocks.gui.workspaces.tests",
        "neje_oracle.blocks.gui.workspaces.work",
        "neje_oracle.blocks.gui.workspaces.exhibition",
        "neje_oracle.blocks.gui.service",
    ]

    for module in modules:
        importlib.import_module(module)
