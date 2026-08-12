"""Texture workspace: HTTP surface for the node editor, plus the card that prints a texture.

Separate from generative.py, which already owns the sketch's surface at 261 lines. Same shape:
a guarded register_routes() and a build(ctx) the generative workspace mounts.
"""

from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ....blocks.imaging import texture, texture_bank
from ....blocks.imaging.modes import MODES, polylines_to_svg, travel_length_mm, travel_preview_svg
from .. import ui as oracle
from ..context import GuiContext

# plot_minutes lives with the image workspace for historical reasons; it is generic, so it is
# imported rather than moved -- test_gui_workspaces imports it from there.
from .image import plot_minutes

# A graph is about a kilobyte of JSON. The 2 MB cap in generative.py is for SVG payloads; a body
# this size here is a bug or an attack, not a texture.
MAX_BODY_BYTES = 256_000

# The editor's thumbnail is a few hundred pixels; anything finer is bytes the operator cannot see.
# Clamped server-side so a browser cannot ask for a 4M-cell evaluation on every slider drag.
MAX_PREVIEW_CELLS = 512

_ROUTES_REGISTERED = False

# Handles for the render knobs, so number_control can offer double-click-to-reset. Deliberately
# not ctx.fields: nothing outside this card reads them back.
_CONTROLS: dict[str, Any] = {}

STATE: dict[str, Any] = {
    "graph": "",
    "mode": "hatch",
    "width_mm": 150.0,
    "height_mm": 150.0,
    "cell_mm": 0.8,
    "seed": 7,
    "svg": "",
}


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


async def _read_json(request: Request) -> dict[str, Any]:
    """Body -> dict, with the size and syntax guards that keep a bad POST a 400 rather than a 500."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise ValueError(f"request body too large (max {MAX_BODY_BYTES} bytes)")
    if not body:
        raise ValueError("empty request body")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError(f"body is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    return payload


def _extent(payload: dict[str, Any]) -> tuple[float, float, float, int | None]:
    try:
        width_mm = float(payload.get("width_mm", 150.0))
        height_mm = float(payload.get("height_mm", 150.0))
        cell_mm = float(payload.get("cell_mm", 1.0))
        raw_seed = payload.get("seed")
        seed = None if raw_seed is None else int(raw_seed)
    except (TypeError, ValueError) as error:
        raise ValueError(f"width_mm, height_mm, cell_mm and seed must be numbers: {error}") from error
    return width_mm, height_mm, cell_mm, seed


def _preview_cell_mm(width_mm: float, height_mm: float, cell_mm: float) -> float:
    """Never finer than MAX_PREVIEW_CELLS on the long side."""
    longest = max(width_mm, height_mm)
    return max(cell_mm, longest / MAX_PREVIEW_CELLS)


def _png_response(field, cell_mm: float) -> Response:
    rows, cols = field.shape
    return Response(
        content=texture.field_to_png(field),
        media_type="image/png",
        headers={
            "X-Texture-Cols": str(cols),
            "X-Texture-Rows": str(rows),
            "X-Texture-Cell-Mm": f"{cell_mm:.4f}",
            # The sketch re-requests per seed and the editor per edit; neither wants a stale frame.
            "Cache-Control": "no-store",
        },
    )


async def _handle_preview(request: Request) -> Response:
    """Evaluate a posted graph to a grayscale PNG.

    PNG rather than a JSON float array: the browser decodes it natively and it is ~1 byte per cell
    against ~9 for "0.123456," -- at 512x512 that is 260 KB against 2.4 MB, on every keystroke.
    """
    try:
        payload = await _read_json(request)
        width_mm, height_mm, cell_mm, seed = _extent(payload)
        cell_mm = _preview_cell_mm(width_mm, height_mm, cell_mm)
        field = texture.evaluate_field(
            payload.get("graph") or {}, width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm, seed=seed
        )
    except ValueError as error:
        return _error(str(error))
    return _png_response(field, cell_mm)


async def _handle_svg(request: Request) -> JSONResponse:
    """Render a graph through a mode, and report what it will cost before anyone prints it.

    JSON rather than raw SVG, matching _handle_text_paths: a texture is dark everywhere, unlike a
    photograph, so the cost line is the thing standing between an operator and a six-hour plot.
    """
    try:
        payload = await _read_json(request)
        width_mm, height_mm, cell_mm, seed = _extent(payload)
        mode = str(payload.get("mode", "hatch"))
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("'params' must be an object")
        polylines = texture.texture_to_polylines(
            payload.get("graph") or {},
            mode=mode,
            width_mm=width_mm,
            height_mm=height_mm,
            cell_mm=cell_mm,
            seed=seed,
            max_segments=int(payload.get("max_segments", 240_000)),
            min_stroke_mm=float(payload.get("min_stroke_mm", 0.0)),
            **params,
        )
    except ValueError as error:
        return _error(str(error))
    except TypeError as error:
        # A mode param that does not exist on that mode arrives as an unexpected keyword.
        return _error(f"bad params for mode: {error}")

    draw_mm, travel_mm = travel_length_mm(polylines)
    return JSONResponse(
        {
            "ok": True,
            "svg": polylines_to_svg(polylines, width_mm=width_mm, height_mm=height_mm),
            "strokes": len(polylines),
            "segments": sum(len(polyline) - 1 for polyline in polylines),
            "draw_mm": round(draw_mm, 1),
            "travel_mm": round(travel_mm, 1),
        }
    )


def _handle_graphs_get(request: Request) -> JSONResponse:
    """List the bank, or return one graph.

    Sync on purpose: this reads and parses every file in the folder, and Starlette runs a plain
    `def` handler in a threadpool. As `async def` that would block the event loop.
    """
    name = request.query_params.get("name")
    if not name:
        return JSONResponse({"ok": True, "graphs": texture_bank.list_graphs()})
    try:
        return JSONResponse({"ok": True, "name": name, "graph": texture_bank.load_graph(name)})
    except ValueError as error:
        return _error(str(error), status=404)


async def _handle_graphs_post(request: Request) -> JSONResponse:
    try:
        payload = await _read_json(request)
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("a name is required")
        # save_graph de-duplicates, so the caller is told the stem it actually got.
        saved = texture_bank.save_graph(name, payload.get("graph") or {})
    except ValueError as error:
        return _error(str(error))
    return JSONResponse({"ok": True, "name": saved.stem})


def _handle_kinds(request: Request) -> JSONResponse:
    """One source of truth for sockets, params and modes, so the editor's param panel is generated
    rather than hand-written -- which is exactly what _mode_params in the image workspace never had."""
    return JSONResponse(
        {
            "ok": True,
            "kinds": texture.kinds_schema(),
            "blends": sorted(texture.BLEND_MODES),
            "modes": sorted(MODES),
            "limits": {"max_nodes": texture.MAX_NODES, "max_evaluations": texture.MAX_EVALUATIONS},
        }
    )


def _handle_field(request: Request) -> Response:
    """A saved graph as a PNG, by GET.

    GET on purpose: the sketch hands this URL straight to `new Image()`, which keeps it same-origin
    (so getImageData does not taint the canvas) and cacheable.
    """
    params = request.query_params
    name = params.get("name", "")
    try:
        graph = texture_bank.load_graph(name)
        width_mm = float(params.get("width_mm", "200"))
        height_mm = float(params.get("height_mm", "200"))
        cell_mm = _preview_cell_mm(width_mm, height_mm, float(params.get("cell_mm", "1.0")))
        raw_seed = params.get("seed")
        seed = None if raw_seed is None else int(raw_seed)
        field = texture.evaluate_field(graph, width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm, seed=seed)
    except ValueError as error:
        return _error(str(error))
    return _png_response(field, cell_mm)


def register_routes() -> None:
    global _ROUTES_REGISTERED

    if _ROUTES_REGISTERED:
        return

    app.add_api_route("/api/texture/preview", _handle_preview, methods=["POST"])
    app.add_api_route("/api/texture/svg", _handle_svg, methods=["POST"])
    app.add_api_route("/api/texture/graphs", _handle_graphs_get, methods=["GET"])
    app.add_api_route("/api/texture/graphs", _handle_graphs_post, methods=["POST"])
    app.add_api_route("/api/texture/kinds", _handle_kinds, methods=["GET"])
    app.add_api_route("/api/texture/field", _handle_field, methods=["GET"])
    _ROUTES_REGISTERED = True


# ---------------------------------------------------------------------------
# The operator-facing card
# ---------------------------------------------------------------------------
def build(ctx: GuiContext) -> None:
    """Node editor iframe, plus render-and-print for a saved texture."""
    with oracle.card(
        "Texture nodes",
        "Noise, mixing and masking as a node graph. Save a texture to use it here and in the sketch.",
    ):
        oracle.embedded_page("/generative/nodes.html", height_px=760, element_id="texture-frame")

    with oracle.card("Print texture"):
        cost_label = oracle.metric_line()
        preview = oracle.preview_pane()

        def refresh() -> None:
            name = str(STATE["graph"] or "")
            if not name:
                STATE["svg"] = ""
                preview.content = ""
                cost_label.set_text("Save a texture in the editor above, then pick it here.")
                return
            try:
                graph = texture_bank.load_graph(name)
                polylines = texture.texture_to_polylines(
                    graph,
                    mode=str(STATE["mode"]),
                    width_mm=float(STATE["width_mm"]),
                    height_mm=float(STATE["height_mm"]),
                    cell_mm=float(STATE["cell_mm"]),
                    seed=int(STATE["seed"]),
                    max_segments=240_000,
                )
            except ValueError as error:
                # The segment cap and the cell-size cap both land here. A texture is dark
                # everywhere, unlike a photograph, so these are reachable by accident -- the
                # operator gets the advice rather than a blank preview.
                STATE["svg"] = ""
                preview.content = ""
                cost_label.set_text(str(error))
                return

            width_mm = float(STATE["width_mm"])
            height_mm = float(STATE["height_mm"])
            STATE["svg"] = polylines_to_svg(polylines, width_mm=width_mm, height_mm=height_mm)
            preview.content = travel_preview_svg(polylines, width_mm=width_mm, height_mm=height_mm)
            preview.update()

            draw_mm, travel_mm = travel_length_mm(polylines)
            xy_minutes, pen_minutes = plot_minutes(
                ctx.settings,
                strokes=len(polylines),
                draw_mm=draw_mm,
                travel_mm=travel_mm,
                use_z_servo=ctx.supervisor.plotter_settings.use_z_servo,
            )
            cost_label.set_text(
                f"{len(polylines)} strokes, {sum(len(p) - 1 for p in polylines)} segments, "
                f"{draw_mm / 1000:.1f} m drawn + {travel_mm / 1000:.1f} m travel, "
                f"~{xy_minutes + pen_minutes:.0f} min"
            )

        def set_field(key: str, value: Any) -> None:
            STATE[key] = value
            refresh()

        with oracle.toolbar(full_width=True):
            graph_select = oracle.select(
                texture_bank.list_graphs(),
                value=STATE["graph"] or None,
                label="Texture",
                on_change=lambda event: set_field("graph", event.value),
            )
            # Auto-populated from the MODES registry, like the image workspace: a mode added later
            # appears here for free.
            oracle.select(
                sorted(MODES),
                value=STATE["mode"],
                label="Mode",
                on_change=lambda event: set_field("mode", event.value),
            )

            def reload_graphs() -> None:
                # The editor saves through the API, not through this page, so the list goes stale
                # the moment an operator saves a new texture next door.
                graph_select.options = texture_bank.list_graphs()
                graph_select.update()
                ui.notify("Texture list reloaded", color="info")

            oracle.safe_action_button("RELOAD", reload_graphs)

        with oracle.toolbar(full_width=True):
            for key, label, step in (
                ("width_mm", "Width mm", 5.0),
                ("height_mm", "Height mm", 5.0),
                ("cell_mm", "Cell mm", 0.1),
                ("seed", "Seed", 1),
            ):
                # A module-local registry, not ctx.fields: these are per-texture render knobs like
                # the image workspace's, not machine calibration that other workspaces read back.
                # number_control still gives them double-click-to-reset for free.
                oracle.number_control(
                    _CONTROLS,
                    key,
                    label=label,
                    value=float(STATE[key]),
                    default=float(STATE[key]),
                    min_value=0.05 if key == "cell_mm" else 0.0,
                    step=step,
                    # number_control's on_change takes no arguments, so it cannot carry the value.
                    # The real handler is the chained on_value_change below.
                    on_change=lambda: None,
                ).on_value_change(lambda event, key=key: set_field(key, event.value))

        async def print_texture() -> None:
            if not STATE["svg"]:
                ui.notify("Nothing to print yet", color="warning")
                return
            await ctx.print_svg_payload(
                str(STATE["svg"]).encode("utf-8"), f"texture_{STATE['graph']}_{STATE['mode']}.svg"
            )

        with oracle.toolbar():
            oracle.primary_action_button("PRINT TEXTURE", lambda: print_texture())

        refresh()
