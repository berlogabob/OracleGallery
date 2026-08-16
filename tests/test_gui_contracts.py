"""The ctx key registries are load-bearing; this makes breaking them a red test.

`refresh_status()` writes to registered label handles by key, and
`pull_settings_from_fields()` reads ~40 `ctx.fields` keys unguarded. Removing a widget
without also removing its key used to surface as a crash in the 2-second poll loop, in
the gallery, mid-exhibition. Here it surfaces at commit time instead: all three screens
are built under one real GuiContext -- exactly how service.build_page composes them --
and then both contract surfaces are exercised.
"""

from __future__ import annotations

import pytest
from nicegui import ui

from neje_oracle.blocks.gui import screens
from neje_oracle.blocks.gui.context import GuiContext
from neje_oracle.shared.gui_settings import GuiSettings


def test_ctx_contracts_survive_a_full_page_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda *a, **k: GuiSettings())
    ctx = GuiContext()
    with ui.column():
        screens.build_print(ctx)
        screens.build_create(ctx)
        screens.build_setup(ctx)

    # Both raise KeyError/AttributeError if a screen dropped a widget but kept its consumer.
    ctx.pull_settings_from_fields()
    ctx.refresh_status()
