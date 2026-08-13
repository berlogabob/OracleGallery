from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest


def test_gui_entrypoint_and_workspace_modules_import() -> None:
    modules = [
        "neje_oracle.blocks.gui.context",
        "neje_oracle.blocks.gui.workspaces.motion",
        "neje_oracle.blocks.gui.workspaces.connection",
        "neje_oracle.blocks.gui.workspaces.calibration",
        "neje_oracle.blocks.gui.workspaces.tests",
        "neje_oracle.blocks.gui.workspaces.work",
        "neje_oracle.blocks.gui.service",
    ]

    for module in modules:
        importlib.import_module(module)

    # Every workspace exposes a single build(ctx) entry point.
    for name in ("connection", "calibration", "tests", "work"):
        workspace = importlib.import_module(f"neje_oracle.blocks.gui.workspaces.{name}")
        assert callable(workspace.build)


def test_gui_context_always_boots_with_preview_mode_even_if_store_has_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that GuiContext always starts with preview mode, ignoring persisted printing mode."""
    from neje_oracle.blocks.gui.context import GuiContext

    # Mock the runtime store to persist "printing" mode
    mock_store = MagicMock()
    mock_store.load_json.side_effect = lambda key, default: (
        {"mode": "printing"} if key == "gui_preview_mode" else default
    )

    mock_supervisor = MagicMock()
    mock_supervisor.runtime_store = mock_store
    mock_supervisor.settings = MagicMock()
    mock_supervisor.plotter_labels = {}
    mock_supervisor.queue_labels = {}

    # Mock the SupervisorService to return our mock
    monkeypatch.setattr("neje_oracle.blocks.gui.context.SupervisorService", lambda: mock_supervisor)

    # Mock load_gui_settings, load_symbol_scales, and list_base_symbols to avoid file I/O
    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda: MagicMock())
    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_symbol_scales", lambda: {})
    monkeypatch.setattr("neje_oracle.blocks.gui.context.list_base_symbols", lambda: [])

    # Create the context
    ctx = GuiContext()

    # Verify that preview_mode is always "preview" on boot, regardless of stored state
    assert ctx.preview_mode == {"value": "preview"}
    # Verify that the toggle can still read persisted value (this would be used by preview_mode_changed)
    assert mock_store.load_json.called
