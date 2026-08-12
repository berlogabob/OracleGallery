"""Generative workspace: p5.js sketch capture and direct plotter print."""

from __future__ import annotations

import time

from nicegui import app, ui
from starlette.requests import Request
from starlette.responses import JSONResponse

from ....blocks.patterns import bank
from ....blocks.text import shx
from .. import ui as oracle
from ..context import GuiContext
from ..support import load_gui_settings
from ..ui import helper_text, primary_action_button

LATEST: dict = {"name": "", "bytes": b""}
STREAM: dict = {"enabled": False, "busy": False}
_ROUTES_REGISTERED = False


def should_send_frame(stream: dict, latest: dict) -> bool:
    """Whether the stream tick should hand the current LATEST frame to the plotter."""
    return stream["enabled"] and not stream["busy"] and bool(latest["bytes"])


async def _handle_generative_svg(request: Request) -> JSONResponse:
    """Handle SVG upload from generative sketch."""
    body = await request.body()

    if not body:
        return JSONResponse({"ok": False, "error": "Empty request body"}, status_code=400)

    if len(body) > 2_000_000:
        return JSONResponse({"ok": False, "error": "File too large (max 2MB)"}, status_code=400)

    # Check if it's a valid SVG
    trimmed = body.lstrip()
    if not trimmed.startswith(b"<svg") and not trimmed.startswith(b"<?xml"):
        return JSONResponse({"ok": False, "error": "Not a valid SVG file"}, status_code=400)

    LATEST["name"] = f"generative_{time.strftime('%Y%m%d_%H%M%S')}.svg"
    LATEST["bytes"] = body

    return JSONResponse({"ok": True, "name": LATEST["name"]})


async def _handle_text_fonts(request: Request) -> JSONResponse:
    """List the SHX fonts that actually load, for the sketch's font picker."""
    return JSONResponse({"fonts": shx.list_fonts()})


async def _handle_text_paths(request: Request) -> JSONResponse:
    """Render text to mm polylines so the sketch can draw it as a layer."""
    params = request.query_params
    text = params.get("text", "")
    font = params.get("font", "")
    if not font:
        fonts = shx.list_fonts()
        if not fonts:
            return JSONResponse({"ok": False, "error": "No usable SHX fonts installed"}, status_code=500)
        font = fonts[0]
    try:
        cap_height = float(params.get("h", "10"))
        polylines = shx.text_polylines(text, font=font, cap_height_mm=cap_height)
        width_mm, height_mm = shx.text_extents(text, font=font, cap_height_mm=cap_height)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse(
        {
            "ok": True,
            "polylines": [[[round(x, 3), round(y, 3)] for x, y in line] for line in polylines],
            "width_mm": round(width_mm, 3),
            "height_mm": round(height_mm, 3),
        }
    )


def sketch_canvas_mm(settings) -> tuple[float, float]:
    """Drawable extent for the sketch, in mm.

    The direct-SVG path offsets the whole drawing by the origin
    (blocks/gcode/direct_svg.py), so a canvas the full width of the sheet would
    run off the bed by exactly that origin. Subtract it here rather than let
    generate_absolute_svg_gcode clamp the overhang away.
    """
    width = float(settings.sheet_width_mm) - float(settings.direct_svg_origin_x_mm)
    height = float(settings.sheet_height_mm) - float(settings.direct_svg_origin_y_mm)
    return max(10.0, width), max(10.0, height)


def _handle_pattern_bank(request: Request) -> JSONResponse:
    """Serve the SVG motif bank plus the canvas extent the sketch should use.

    Sync on purpose: load_bank() parses every SVG in the folder, and Starlette runs a
    plain `def` handler in a threadpool. As `async def` that parsing would block the
    event loop for every connected client.
    """
    width_mm, height_mm = sketch_canvas_mm(load_gui_settings())
    motifs = bank.load_bank()
    return JSONResponse(
        {
            "ok": True,
            "canvas": {"width_mm": round(width_mm, 3), "height_mm": round(height_mm, 3)},
            "motifs": {
                name: [[[round(x, 4), round(y, 4)] for x, y in line] for line in polylines]
                for name, polylines in motifs.items()
            },
        }
    )


def register_routes() -> None:
    """Register the generative SVG API endpoint."""
    global _ROUTES_REGISTERED

    if _ROUTES_REGISTERED:
        return

    app.add_api_route("/api/generative/svg", _handle_generative_svg, methods=["POST"])
    app.add_api_route("/api/text/fonts", _handle_text_fonts, methods=["GET"])
    app.add_api_route("/api/text/paths", _handle_text_paths, methods=["GET"])
    app.add_api_route("/api/patterns/bank", _handle_pattern_bank, methods=["GET"])
    _ROUTES_REGISTERED = True


def build(ctx: GuiContext) -> None:
    """Build the generative workspace UI."""
    with ui.column().classes("workspace-scroll gap-2"):
        with oracle.card("Generative sketch"):
            oracle.embedded_page("/generative/index.html", height_px=900, element_id="generative-frame")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Send to plotter").classes("text-sm font-bold")
            origin_label = ui.label("Origin X/Y: — / — mm (set on TESTS tab)").classes("text-xs text-[#8f4f2b]")

            captured_label = ui.label("No capture yet").classes("path-label text-xs")

            def update_capture_label() -> None:
                if LATEST["name"]:
                    captured_label.set_text(f"Captured: {LATEST['name']}")
                else:
                    captured_label.set_text("No capture yet")
                origin_x = ctx.fields.get("direct_svg_origin_x_mm")
                origin_y = ctx.fields.get("direct_svg_origin_y_mm")
                if origin_x is not None and origin_y is not None:
                    origin_label.set_text(f"Origin X/Y: {origin_x.value} / {origin_y.value} mm (set on TESTS tab)")

            ui.timer(1.0, update_capture_label)

            with ui.row().classes("items-center gap-2"):
                primary_action_button("PRINT CAPTURED SVG", lambda: ctx.print_generative_svg())

            def push_stream_state() -> None:
                seconds = max(5, float(stream_interval.value or 15))
                ui.run_javascript(
                    f"""const frame = document.getElementById('generative-frame');
                    frame?.contentWindow?.postMessage({{type: 'stream', enabled: {str(STREAM["enabled"]).lower()}, seconds: {seconds}}}, '*');"""
                )

            def stream_toggled(event) -> None:
                STREAM["enabled"] = bool(event.value)
                push_stream_state()
                if not STREAM["enabled"]:
                    ui.notify("Stream stopped", color="info")

            with ui.row().classes("items-center gap-2"):
                ui.switch(
                    "Stream to plotter (auto-print each captured frame)",
                    value=STREAM["enabled"],
                    on_change=stream_toggled,
                )
                stream_interval = (
                    ui.number(
                        "Interval s",
                        value=15,
                        min=5,
                        step=1,
                        on_change=lambda _: push_stream_state(),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                )

            async def _stream_tick() -> None:
                if not should_send_frame(STREAM, LATEST):
                    return
                STREAM["busy"] = True
                try:
                    await ctx.print_generative_svg(
                        quiet=True
                    )  # pops LATEST on success; blocks (io_bound) while plotting
                finally:
                    STREAM["busy"] = False

            # ponytail: line-by-line ok-wait transport (~1 line/RTT) is the throughput ceiling; set NEJE_FLUIDNC_STREAMING=char_count for char-counting GRBL streaming if frames lag

            ui.timer(3.0, _stream_tick)

        _build_line_text_card(ctx)
        # A texture is a generative source, so it lives in this workspace rather than a tab of its
        # own. Imported here rather than at module scope: workspaces.texture imports from .image,
        # and a top-level import would drag the image workspace into every generative-only test.
        from . import texture as texture_workspace

        texture_workspace.build(ctx)


def _build_line_text_card(ctx: GuiContext) -> None:
    """Single-stroke SHX text: preview, then print through the direct-SVG path."""
    fonts = shx.list_fonts()

    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Line text").classes("text-sm font-bold")
        if not fonts:
            helper_text("No usable SHX fonts found in assets/fonts/shx.")
            return
        helper_text("Single-stroke engraving fonts. One pen pass per letter, no outlines to fill.")

        with ui.row().classes("gap-2 w-full items-center"):
            font_select = ui.select(fonts, value=fonts[0], label="Font").props("dense outlined").classes("w-48")
            cap_height = ui.number("Cap height mm", value=10.0, min=1, step=1).props("dense outlined").classes("w-32")
        text_input = ui.textarea("Text", value="NEJE\nORACLE").props("dense outlined autogrow").classes("w-full")

        extent_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
        preview = ui.html().classes("preview-frame w-full")

        def build_svg() -> str:
            return shx.text_svg(
                str(text_input.value or ""),
                font=str(font_select.value),
                cap_height_mm=float(cap_height.value or 10.0),
            )

        def refresh() -> None:
            try:
                svg = build_svg()
                width_mm, height_mm = shx.text_extents(
                    str(text_input.value or ""),
                    font=str(font_select.value),
                    cap_height_mm=float(cap_height.value or 10.0),
                )
            except ValueError as exc:
                preview.content = ""
                extent_label.set_text(str(exc))
                return
            preview.content = svg
            preview.update()
            extent_label.set_text(f"{width_mm:.1f} x {height_mm:.1f} mm")

        for control in (font_select, cap_height, text_input):
            control.on_value_change(lambda _: refresh())

        async def print_text() -> None:
            text = str(text_input.value or "").strip()
            if not text:
                ui.notify("Type something to print", color="warning")
                return
            await ctx.print_svg_payload(build_svg().encode("utf-8"), f"text_{font_select.value}.svg")

        with ui.row().classes("items-center gap-2"):
            primary_action_button("PRINT TEXT", lambda: print_text())

        refresh()
