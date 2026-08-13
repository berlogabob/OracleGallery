"""Generative workspace: p5.js sketch capture and direct plotter print."""

from __future__ import annotations

import contextlib
import time

from nicegui import app, ui
from starlette.requests import Request
from starlette.responses import JSONResponse

from ....blocks.patterns import bank
from ....blocks.text import shx
from ....shared.gui_settings import GUI_DEFAULTS
from .. import ui as oracle
from ..context import GuiContext
from ..support import load_gui_settings
from ..ui import client_timer, helper_text, primary_action_button

STREAM: dict = {"enabled": False, "busy": False}
_ROUTES_REGISTERED = False


def should_send_frame(stream: dict) -> bool:
    """Whether the stream tick should pull a frame and plot it.

    It used to also require bytes in a shared capture buffer. That buffer is gone: the
    browser no longer pushes SVG at us, so there is nothing to check but our own state.
    """
    return bool(stream["enabled"]) and not bool(stream["busy"])


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

    app.add_api_route("/api/text/fonts", _handle_text_fonts, methods=["GET"])
    app.add_api_route("/api/text/paths", _handle_text_paths, methods=["GET"])
    app.add_api_route("/api/patterns/bank", _handle_pattern_bank, methods=["GET"])
    _ROUTES_REGISTERED = True


async def current_sketch_svg() -> bytes:
    """Read the frame the sketch has on screen, via the contract it exposes.

    The sketch used to POST its SVG into a process-global slot that the node editor also
    wrote to, so a texture could be plotted by the sketch's timer. Pulling on demand means
    there is one producer and no slot to confuse.
    """
    try:
        svg = await ui.run_javascript(
            "document.getElementById('generative-frame')?.contentWindow?.currentSvg?.() ?? ''",
            timeout=5.0,
        )
    except Exception as exc:  # noqa: BLE001 - no client, no iframe yet, or the call timed out
        raise ValueError("Could not read the sketch. Open the generative screen and let it draw.") from exc
    if not svg:
        raise ValueError("The sketch has not drawn a frame yet.")
    return str(svg).encode("utf-8")


def build(ctx: GuiContext) -> None:
    """Build the generative workspace UI."""
    with ui.column().classes("workspace-scroll gap-2"):
        with oracle.card("Generative sketch"):
            oracle.embedded_page("/generative/index.html", height_px=900, element_id="generative-frame")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Send to plotter").classes("text-sm font-bold")
            origin_label = ui.label("Origin X/Y: — / — mm (set on TESTS tab)").classes("text-xs text-[#8f4f2b]")

            def update_origin_label() -> None:
                origin_x = ctx.fields.get("direct_svg_origin_x_mm")
                origin_y = ctx.fields.get("direct_svg_origin_y_mm")
                if origin_x is not None and origin_y is not None:
                    origin_label.set_text(f"Origin X/Y: {origin_x.value} / {origin_y.value} mm (set on TESTS tab)")

            client_timer(1.0, update_origin_label)

            async def print_sketch(quiet: bool = False) -> None:
                # "Capture" is gone as a concept: there is nothing to capture into. The button
                # reads the frame that is on screen right now, which is what an operator
                # pressing PRINT expects it to mean.
                try:
                    svg_bytes = await current_sketch_svg()
                except ValueError as exc:
                    if not quiet:
                        ui.notify(str(exc), color="warning")
                    return
                await ctx.print_svg_payload(svg_bytes, f"generative_{time.strftime('%Y%m%d_%H%M%S')}.svg")

            with ui.row().classes("items-center gap-2"):
                primary_action_button("PRINT SKETCH", print_sketch)

            def push_stream_state() -> None:
                seconds = max(5, float(stream_interval.value or GUI_DEFAULTS["stream_interval_seconds"]))
                # Telling a browser that is not attached is a no-op, not a failure: this
                # runs from a once-timer at load and from headless tests with no client.
                with contextlib.suppress(Exception):
                    ui.run_javascript(
                        f"""const frame = document.getElementById('generative-frame');
                        frame?.contentWindow?.postMessage({{type: 'stream', enabled: {str(STREAM["enabled"]).lower()}, seconds: {seconds}}}, '*');"""
                    )

            def stream_toggled(event) -> None:
                STREAM["enabled"] = bool(event.value)
                ctx.settings.stream_enabled = STREAM["enabled"]
                ctx.save_settings()
                push_stream_state()
                if not STREAM["enabled"]:
                    ui.notify("Stream stopped", color="info")

            def interval_changed(_: object) -> None:
                ctx.settings.stream_interval_seconds = max(
                    5.0, float(stream_interval.value or GUI_DEFAULTS["stream_interval_seconds"])
                )
                ctx.save_settings()
                push_stream_state()

            # The switch renders from the persisted setting, so it has to start there too --
            # STREAM is a module global that outlives the page but not the process.
            STREAM["enabled"] = bool(ctx.settings.stream_enabled)
            with ui.row().classes("items-center gap-2"):
                ctx.fields["stream_enabled"] = ui.switch(
                    "Stream to plotter (auto-print each captured frame)",
                    value=STREAM["enabled"],
                    on_change=stream_toggled,
                )
                stream_interval = (
                    ui.number(
                        "Interval s",
                        value=ctx.settings.stream_interval_seconds,
                        min=5,
                        step=1,
                        on_change=interval_changed,
                    )
                    .props("dense outlined")
                    .classes("w-28")
                )
                ctx.fields["stream_interval_seconds"] = stream_interval

            # Tell the freshly-built iframe what the switch already says. Without this the
            # switch came back ON after a reload while nothing streamed: push_stream_state()
            # only ever ran from the change handlers, so the new iframe was never told, and
            # toggling off-then-on was the only way to start it.
            client_timer(2.0, push_stream_state, once=True)

            async def _stream_tick() -> None:
                if not should_send_frame(STREAM):
                    return
                STREAM["busy"] = True
                try:
                    # quiet=True matters here: with no browser attached the pull raises, and
                    # this runs every 3 seconds forever on an unattended machine. A toast per
                    # tick would bury the log the run is judged by.
                    await print_sketch(quiet=True)  # blocks (io_bound) while plotting
                finally:
                    STREAM["busy"] = False

            # ponytail: line-by-line ok-wait transport (~1 line/RTT) is the throughput ceiling; set NEJE_FLUIDNC_STREAMING=char_count for char-counting GRBL streaming if frames lag

            client_timer(3.0, _stream_tick)

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
