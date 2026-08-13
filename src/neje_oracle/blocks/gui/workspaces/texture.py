"""Texture workspace: HTTP surface for the node editor, plus the card that prints a texture.

Separate from generative.py, which already owns the sketch's surface at 261 lines. Same shape:
a guarded register_routes() and a build(ctx) the generative workspace mounts.
"""

from __future__ import annotations

import json
from typing import Any

from nicegui import app
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ....blocks.imaging import texture, texture_bank
from ....blocks.imaging.modes import MODES, polylines_to_svg, travel_length_mm
from .. import ui as oracle
from ..context import GuiContext

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
    """Legacy stacked form, kept for tests that build this workspace alone."""
    build_canvas()
    build_controls(ctx)


def build_canvas() -> None:
    """The node editor itself. No card: on the CREATE screen the editor is the canvas."""
    oracle.embedded_page("/generative/nodes.html", element_id="texture-frame")


def build_controls(ctx: GuiContext, *, actions: bool = True) -> tuple[Any, Any]:
    """Render-and-print for a saved texture.

    Returns (card handle, reload-graph-list closure). The CREATE screen calls the reload
    whenever this pane becomes visible -- which is what buried the RELOAD button: the list
    went stale only because the editor saves through the API, not through this page.
    """
    # render_card builds the knobs itself, but every knob's handler already calls refresh().
    # Handing the name a handle once the card exists keeps those call sites unaware of it.
    card_handle: dict[str, Any] = {}
    hooks: dict[str, Any] = {}

    def refresh() -> None:
        handle = card_handle.get("handle")
        if handle is not None:
            handle.refresh()

    def set_field(key: str, value: Any) -> None:
        STATE[key] = value
        refresh()

    def texture_controls() -> None:
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
                # Quiet: this runs on every switch to the TEXTURE pane, not on a button press.
                graph_select.options = texture_bank.list_graphs()
                graph_select.update()

            hooks["reload"] = reload_graphs

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

    def render_texture() -> oracle.Render:
        name = str(STATE["graph"] or "")
        if not name:
            raise ValueError("Save a texture in the editor, then pick it here.")
        # load_graph, the segment cap and the cell-size cap all raise ValueError, and render_card
        # puts the message in the cost line. A texture is dark everywhere, unlike a photograph,
        # so the caps are reachable by accident -- the operator gets the advice, not a traceback.
        polylines = texture.texture_to_polylines(
            texture_bank.load_graph(name),
            mode=str(STATE["mode"]),
            width_mm=float(STATE["width_mm"]),
            height_mm=float(STATE["height_mm"]),
            cell_mm=float(STATE["cell_mm"]),
            seed=int(STATE["seed"]),
            max_segments=240_000,
        )
        return oracle.Render(
            polylines=polylines,
            width_mm=float(STATE["width_mm"]),
            height_mm=float(STATE["height_mm"]),
            name=f"texture_{name}_{STATE['mode']}",
        )

    card_handle["handle"] = oracle.render_card(
        ctx,
        title="Print texture",
        helper="Render a saved graph through a plotter mode, then send it to the machine.",
        controls=texture_controls,
        render=render_texture,
        button_label="PRINT TEXTURE",
        # Anything that already knows this module by its state dict keeps reading the
        # printable bytes off STATE -- tests/test_gui_workspaces.py among them.
        on_render=lambda svg: STATE.__setitem__("svg", svg),
        actions=actions,
    )

    refresh()
    return card_handle["handle"], hooks["reload"]
