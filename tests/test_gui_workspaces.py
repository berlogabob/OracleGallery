"""Headless regression coverage for the NiceGUI operator workspaces.

Each workspace exposes `build(ctx: GuiContext) -> None`, called from
`blocks/gui/service.py` inside a `ui.tab_panel`. NiceGUI elements attach to an
implicit default page context even without a running server (verified: plain
`with ui.column(): ui.label(...)` works with no `ui.run()`), so `build(ctx)` can be
exercised directly under a `ui.column()` wrapper without starting a real server or
event loop.

`GuiContext()` is constructed for real (not mocked) so a workspace referencing a
renamed/removed `ctx` attribute or shared helper fails loudly here, exactly like it
would in the running app. The one exception is `load_gui_settings`, which is
monkeypatched to return fresh `GuiSettings()` defaults instead of reading the
developer's real `runtime/gui_settings.json` (that file lives outside the
`conftest.py` sandbox and its contents are not test-controlled). Every other root
`GuiContext()` touches -- the runtime store, spool, uploader session roots -- is
already sandboxed by `conftest.py`. `assets/symbols` is deliberately real per that
same sandbox: it is a read-only bundled asset root.
"""

from __future__ import annotations

import io

import pytest
from nicegui import ui
from PIL import Image

from neje_oracle.blocks.gui.context import GuiContext
from neje_oracle.blocks.gui.workspaces import calibration, connection, exhibition, generative, work
from neje_oracle.blocks.gui.workspaces import image as image_workspace
from neje_oracle.blocks.gui.workspaces import tests as tests_workspace
from neje_oracle.shared.gui_settings import GuiSettings
from neje_oracle.shared.origin_markers import ALL_ORIGINS


def _new_ctx(monkeypatch: pytest.MonkeyPatch) -> GuiContext:
    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda *a, **k: GuiSettings())
    return GuiContext()


def test_connection_workspace_builds_and_populates_fluidnc_and_jog_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        connection.build(ctx)

    assert {"jog_step", "jog_feed"} <= ctx.fields.keys()
    assert {"webui", "telnet", "state", "mpos", "pins", "modal", "message", "target"} <= ctx.fluidnc_labels.keys()


def test_calibration_workspace_builds_and_populates_layout_and_scale_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        calibration.build(ctx)

    expected_fields = {
        "layout_mode",
        "cell_diameter_mm",
        "gap_mm",
        "sheet_width_mm",
        "sheet_height_mm",
        "sheet_margin_mm",
        "marker_diameter_mm",
        "include_rings",
        "include_markers",
        "organic_enabled",
        "organic_cell_size_mm",
        "organic_seed",
        "organic_rotation_ramp",
        "organic_scale_ramp",
        "sample_step_mm",
        "sample_density_exponent",
        "sample_min_step_mm",
        "sample_max_step_mm",
        "streaming_mode",
        "randomness",
        "randomness_fine",
        "global_scale",
        "travel_rate",
        "draw_rate",
        "xy_acceleration_mm_s2",
        "z_up_mm",
        "z_down_mm",
        "z_feed_mm_min",
        # from the shared motion panel
        "jog_step",
        "jog_feed",
    }
    assert expected_fields <= ctx.fields.keys()

    # One scale slider per bundled base symbol, one origin checkbox pair per origin --
    # asserted by count (not hardcoded names) since the bundled symbol set can grow.
    scale_keys = [key for key in ctx.fields if key.startswith("scale:")]
    show_origin_keys = [key for key in ctx.fields if key.startswith("show_origin:")]
    print_origin_keys = [key for key in ctx.fields if key.startswith("print_origin:")]
    assert len(scale_keys) == len(ctx.symbols)
    assert len(show_origin_keys) == len(ALL_ORIGINS)
    assert len(print_origin_keys) == len(ALL_ORIGINS)

    assert {"effective", "points", "load", "limits"} <= ctx.gcode_labels.keys()
    assert ctx.capacity_label is not None


def test_tests_workspace_builds_and_populates_direct_svg_origin_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        tests_workspace.build(ctx)

    assert {"direct_svg_origin_x_mm", "direct_svg_origin_y_mm"} <= ctx.fields.keys()
    assert ctx.uploaded_svg_label is not None


def test_work_workspace_builds_and_populates_thermal_queue_and_log_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        work.build(ctx)

    assert {"thermal_printer_url", "thermal_session_dir", "log_filter"} <= ctx.fields.keys()
    assert {"state", "pending", "active", "failed", "message"} <= ctx.queue_labels.keys()
    assert "message" in ctx.thermal_printer_labels
    assert ctx.system_check_label is not None
    assert ctx.logs_view is not None


def test_exhibition_workspace_builds_minimal_live_print_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        exhibition.build(ctx)

    assert ctx.start_print_button is not None
    assert {"sheet", "cells", "message"} <= ctx.plotter_labels.keys()
    assert ctx.progress is not None


def test_generative_workspace_builds_sketch_and_line_text_cards_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        generative.build(ctx)

    # Generative doesn't register anything on ctx.fields/labels -- reaching this
    # point without raising is the regression signal (catches a renamed ctx
    # attribute, e.g. print_generative_svg or a shx.list_fonts() break).
    assert ctx.fields == {}


def test_image_workspace_generates_real_preview_svg_for_uploaded_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """build() unconditionally calls the module's refresh_preview() once at the end;
    pre-seeding STATE with real image bytes before build() makes that call exercise
    the actual image -> polylines -> svg pipeline, not just the empty-state branch.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), color=(120, 120, 120)).save(buffer, format="PNG")
    image_workspace.STATE.update(
        {
            "name": "swatch.png",
            "bytes": buffer.getvalue(),
            "mode": "halftone",
            "width_mm": 40.0,
            "height_mm": 40.0,
            "cell_mm": 5.0,
            "gamma": 1.0,
            "invert": False,
            "detail": 1.0,
        }
    )
    ctx = _new_ctx(monkeypatch)

    with ui.column():
        image_workspace.build(ctx)

    assert "<svg" in image_workspace.STATE["svg"]


@pytest.mark.parametrize(
    ("mode", "detail", "expected"),
    [
        ("halftone", 1.0, {}),
        ("hatch", 2.0, {"line_spacing_mm": 2.0, "angle_deg": 45.0}),
        ("dither", 1.0, {}),
        ("contour", 3.7, {"bands": 4}),
    ],
)
def test_mode_params_covers_every_image_mode(mode: str, detail: float, expected: dict) -> None:
    assert image_workspace._mode_params(mode, detail) == expected
