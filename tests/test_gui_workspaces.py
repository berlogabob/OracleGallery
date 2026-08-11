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

import inspect
import io

import pytest
from nicegui import ui
from PIL import Image, ImageDraw

from neje_oracle.blocks.gui.context import GuiContext
from neje_oracle.blocks.gui.workspaces import calibration, connection, exhibition, generative, work
from neje_oracle.blocks.gui.workspaces import image as image_workspace
from neje_oracle.blocks.gui.workspaces import tests as tests_workspace
from neje_oracle.blocks.imaging.modes import MODES, image_to_polylines, polylines_to_svg
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


def test_travel_toggle_changes_only_the_view() -> None:
    """Hiding travel lines must change the picture on screen and nothing else.

    The switch selects between two serializers, and one of them emits red <line> elements
    that svg_gcode would gladly draw. If the toggle ever reached the print path, turning it
    on would make the pen trace every pen-up move.
    """
    polylines = [[(0.0, 0.0), (10.0, 0.0)], [(30.0, 30.0), (40.0, 30.0)]]
    try:
        image_workspace.STATE["show_travel"] = True
        with_travel = image_workspace.preview_svg(polylines, width_mm=50, height_mm=50)
        image_workspace.STATE["show_travel"] = False
        without = image_workspace.preview_svg(polylines, width_mm=50, height_mm=50)
    finally:
        image_workspace.STATE["show_travel"] = True

    assert "<line" in with_travel
    assert "<line" not in without
    # Travel hidden, the preview IS the printed geometry — same serializer, same output.
    assert without == polylines_to_svg(polylines, width_mm=50, height_mm=50)
    assert with_travel.count("<polyline") == without.count("<polyline")


def test_mode_params_are_accepted_by_every_mode() -> None:
    """Every key the GUI emits must be a real keyword of the mode it is aimed at.

    The old version of this test hardcoded four modes and so proved nothing about the two
    added since; a bad key only surfaces as a TypeError once an operator picks that mode.
    """
    for name, function in MODES.items():
        accepted = set(inspect.signature(function).parameters)
        for quality in image_workspace.QUALITY_PRESETS:
            produced = image_workspace._mode_params(name, 1.0, quality)
            assert set(produced) <= accepted, f"{name}/{quality} passes {set(produced) - accepted}"


def test_every_quality_preset_converts_without_dead_ending() -> None:
    """A preset the operator can select must never hand them a blank preview.

    This is the shipped-defaults bug in general form: halftone at cell 1.5 used to raise on
    every real image, and the first cut of the fader put `fine` past the skeleton cap. Both
    budgets rise with the preset precisely so the slow end stays reachable.

    The fixture has to be busy and full-size — an earlier version used a 256 px swatch on an
    80 mm frame, which is far too small to reach either cap and so proved nothing.
    """
    data = _dense_line_art_png()

    for name in MODES:
        for quality in image_workspace.QUALITY_PRESETS:
            image_to_polylines(
                data,
                mode=name,
                width_mm=150.0,
                height_mm=150.0,
                cell_mm=image_workspace.quality_cell_mm(name, quality),
                max_segments=image_workspace.quality_max_segments(quality),
                **image_workspace._mode_params(name, 1.0, quality),
            )


def test_quality_fader_buys_detail_monotonically() -> None:
    """Pushing the fader up must actually add strokes, or the label is lying about the cost."""
    strokes = []
    for quality in image_workspace.QUALITY_PRESETS:
        polylines = image_to_polylines(
            _line_art_png(),
            mode="trace",
            width_mm=100.0,
            height_mm=100.0,
            # A hair-thin pen, so this measures the fader and only the fader. quality_cell_mm
            # now floors trace's grid at half the pen width, and with a real nib that floor
            # binds hard enough to flatten the top presets into each other — which is correct
            # behaviour, and is asserted separately by test_pen_width_floors_the_fader.
            cell_mm=image_workspace.quality_cell_mm("trace", quality, 0.05),
            max_segments=image_workspace.quality_max_segments(quality),
            **image_workspace._mode_params("trace", 1.0, quality),
        )
        strokes.append(sum(len(p) - 1 for p in polylines))
    # Deliberately not asserting step-by-step monotonicity on segment count, because that
    # is not monotonic and should not be: a coarser grid blurs neighbouring strokes into
    # one thicker stroke, which then earns more weight passes. Measured, draft can emit
    # more segments than fast while resolving strictly less.
    #
    # Fidelity is the property that really is ordered, and it is verified against the real
    # folders by the sweep recorded next to _TYPICAL_MINUTES (draft 0.881 -> max 0.947).
    # What this test can cheaply guarantee is that the fader's range is worth having.
    assert strokes[-1] > strokes[0] * 2, f"max barely differs from draft: {strokes}"
    assert strokes[-1] == max(strokes), f"max was not the most detailed preset: {strokes}"


def test_pen_width_floors_the_fader() -> None:
    """A preset may not ask for detail the pen cannot draw.

    Measured on paper with a 0.5 mm fineliner: a 0.5 mm line pair merged into one line. So
    tracing at the shipped 0.10 mm grid resolves strokes three deep inside one nib width, and
    the biplane's engine printed as mud. The floor merges that detail in the raster instead,
    before thinning runs, which is both truthful and faster.
    """
    for quality in image_workspace.QUALITY_PRESETS:
        assert image_workspace.quality_cell_mm("trace", quality, 0.5) >= 0.25
        # Dot pitch goes the other way: a lattice finer than two nib widths fills in solid.
        # dither at balanced shipped 0.7 mm with a 0.42 mm dot, and printed as solid bands.
        assert image_workspace.quality_cell_mm("dither", quality, 0.5) >= 1.0
        assert image_workspace.quality_cell_mm("halftone", quality, 0.5) >= 1.0
    # A fine nib must not be penalised by a floor meant for a fat one.
    assert image_workspace.quality_cell_mm("trace", "max", 0.05) == 0.10
    assert image_workspace.quality_cell_mm("dither", "max", 0.05) == 0.40


def test_plot_estimate_counts_pen_lift_time() -> None:
    """The estimate used to count XY only and under-reported dot modes by ~10x."""
    settings = GuiSettings(draw_rate=1800.0, travel_rate=5000.0, z_down_mm=-25.0, z_up_mm=0.0, z_feed_mm_min=1000.0)
    kwargs = {"strokes": 488, "draw_mm": 2000.0, "travel_mm": 2700.0}

    xy, pen = image_workspace.plot_minutes(settings, use_z_servo=True, **kwargs)
    assert xy == pytest.approx(1.65, abs=0.05)
    # 488 strokes x (25 mm down at 1000 + 25 mm up at 5000). This term was missing entirely.
    assert pen == pytest.approx(14.6, abs=0.1)

    # A laser-style M3/M5 pen has no Z round trip, so the old number was right there.
    assert image_workspace.plot_minutes(settings, use_z_servo=False, **kwargs) == (xy, 0.0)


def test_tab_switch_does_not_change_system_mode_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Navigation must never mutate machine state.

    Regression: workspace_changed() flipped the system mode on every tab switch, and
    set_system_mode() writes print_enabled=False -- so merely looking at another tab
    silently aborted the sheet mid-print.
    """
    ctx = _new_ctx(monkeypatch)
    changed: list[object] = []
    monkeypatch.setattr(ctx, "set_system_mode", lambda *a, **k: changed.append(a))
    monkeypatch.setattr(ctx.supervisor, "is_printing", lambda: True)

    ctx.workspace_changed("tests")

    assert changed == []
    assert ctx.active_workspace["value"] == "tests"


def test_tab_switch_still_sets_system_mode_when_not_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _new_ctx(monkeypatch)
    changed: list[object] = []
    monkeypatch.setattr(ctx, "set_system_mode", lambda *a, **k: changed.append(a))
    monkeypatch.setattr(ctx.supervisor, "is_printing", lambda: False)

    ctx.workspace_changed("tests")

    assert changed, "tab-linked mode default should still apply when idle"


def _line_art_png(size: int = 600) -> bytes:
    """Strokes of mixed weight — what the fader has to resolve more of as it rises."""
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle([80, 100, 520, 380], outline=0, width=6)
    draw.ellipse([160, 150, 440, 330], outline=0, width=2)
    for x in range(100, 500, 14):
        draw.line([x, 400, x + 30, 470], fill=0, width=1)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _dense_line_art_png(size: int = 1024) -> bytes:
    """A busy full-size drawing: outlines, dense hatching, fine detail.

    Sized and populated to reach the segment and skeleton caps at the top presets, which is
    the only way this fixture can prove a preset is selectable.
    """
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle([60, 80, 960, 700], outline=0, width=8)
    draw.ellipse([180, 160, 840, 620], outline=0, width=3)
    for x in range(80, 950, 9):
        draw.line([x, 90, x + 40, 690], fill=0, width=1)
    for y in range(720, 1000, 7):
        draw.line([70, y, 950, y + 12], fill=0, width=1)
    return _to_png(image)


def _to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
