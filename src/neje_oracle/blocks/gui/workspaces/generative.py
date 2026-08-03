"""Generative workspace: p5.js sketch capture and direct plotter print."""

from __future__ import annotations

import time

from nicegui import app, ui
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..context import GuiContext


LATEST: dict = {"name": "", "bytes": b""}
_ROUTES_REGISTERED = False


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


def register_routes() -> None:
    """Register the generative SVG API endpoint."""
    global _ROUTES_REGISTERED

    if _ROUTES_REGISTERED:
        return

    app.add_api_route("/api/generative/svg", _handle_generative_svg, methods=["POST"])
    _ROUTES_REGISTERED = True


def build(ctx: GuiContext) -> None:
    """Build the generative workspace UI."""
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Generative sketch").classes("text-sm font-bold")
            ui.element("iframe").props('src="/generative/"').style("width:100%; height:640px; border:0; background:#1a1a1a; border-radius:10px;")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Send to plotter").classes("text-sm font-bold")
            ui.label("SVG X0/Y0 origin controls are on the TESTS tab.").classes("text-xs text-[#8f4f2b]")

            captured_label = ui.label("No capture yet").classes("path-label text-xs")

            def update_capture_label() -> None:
                if LATEST["name"]:
                    captured_label.set_text(f"Captured: {LATEST['name']}")
                else:
                    captured_label.set_text("No capture yet")

            ui.timer(1.0, update_capture_label)

            with ui.row().classes("items-center gap-2"):
                ui.button("START PRINT", on_click=ctx.print_generative_svg).props("dense color=positive")
