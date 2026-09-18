"""Grid workspace: one picture, N x N cells, a mode per cell.

The mode comparison sheet used to be a throwaway script per session. The picture is the one
IMAGE holds (image.STATE), so uploading on either pane serves both. Every knob lives on
ctx.settings directly: there is no module state dict, and nothing here goes through
ctx.fields.

The canvas is the layout: an N x N editor filling the free space, whose tiles are each cell's
real render (the exact polylines the sheet prints, cached per cell). Clicking a tile picks its
mode. The 340 px panel holds only the grid-wide knobs; a 9x9 of dropdowns in
that track overflowed at 4x4.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from ....blocks.imaging.modes import MODES, Polylines, polylines_to_svg
from ....blocks.imaging.sheet import (
    GRID_LABEL_MM,
    GRID_SIZES,
    cell_art,
    grid_cells,
    grid_to_polylines,
    image_aspect,
    photo_filter,
)
from .. import ui as oracle
from ..context import GuiContext
from ..support import read_upload_event_payload
from ..ui import card, helper_text, safe_action_button, select, switch, toolbar
from .generative import sketch_canvas_mm
from .image import _PEN_AWARE_MODES, QUALITY_PRESETS, STATE, _mode_params, quality_cell_mm, quality_max_segments

TABLE = 9  # grid_cell_modes is a flat TABLE x TABLE table, row * TABLE + col
MODE_OPTIONS = {"": "empty", **{mode: mode for mode in MODES}}


def _modes_table(settings: Any) -> list[str]:
    table = list(settings.grid_cell_modes)[: TABLE * TABLE]
    return table + [""] * (TABLE * TABLE - len(table))


def active_modes(settings: Any) -> list[str]:
    """The modes of the current n x n grid, row-major."""
    n = int(settings.grid_size)
    table = _modes_table(settings)
    return [table[row * TABLE + col] for row in range(n) for col in range(n)]


def set_all_modes(settings: Any) -> None:
    """Every mode once, in the smallest square that holds them (11 modes -> 4x4)."""
    names = list(MODES)
    n = next(size for size in GRID_SIZES if size * size >= len(names))
    table = [""] * (TABLE * TABLE)
    for index, name in enumerate(names):
        table[(index // n) * TABLE + index % n] = name
    settings.grid_size = n
    settings.grid_cell_modes = table


def set_cell_mode(settings: Any, row: int, col: int, mode: str) -> None:
    table = _modes_table(settings)
    table[row * TABLE + col] = mode
    settings.grid_cell_modes = table


def build_section(ctx: GuiContext, *, preview_slot: Any = None) -> oracle.Section:
    settings = ctx.settings
    root = ui.column().classes("w-full gap-2")
    failures_box: dict[str, Any] = {}
    # Cell renders keyed by what changes them; a new picture (or filter flip) clears it.
    # ponytail: unbounded between pictures -- quality x sizes x modes is a few hundred entries.
    cache: dict[tuple[Any, ...], Polylines | str] = {}
    source: dict[str, Any] = {"key": None, "data": b"", "aspect": 1.0}

    def picture() -> tuple[bytes, float]:
        key = (hash(STATE["bytes"]), bool(settings.grid_photo_filter))
        if source["key"] != key:
            data = photo_filter(STATE["bytes"]) if settings.grid_photo_filter else STATE["bytes"]
            source.update(key=key, data=data, aspect=image_aspect(data))
            cache.clear()
        return source["data"], source["aspect"]

    def params_for(mode: str) -> dict[str, Any]:
        # The same set IMAGE's render_conversion builds, minus its per-mode extras (wave
        # orientation, flow dashes, lift budget), which stay at the mode defaults here.
        quality, pen = str(settings.grid_quality), float(settings.pen_width_mm)
        return {
            "cell_mm": quality_cell_mm(mode, quality, pen),
            "max_segments": quality_max_segments(quality),
            "min_stroke_mm": pen * 2.0,
            "autocontrast": not settings.grid_photo_filter,
            **({"pen_width_mm": pen} if mode in _PEN_AWARE_MODES else {}),
            **_mode_params(mode, 1.0, quality),
        }

    def art(mode: str, side_mm: float) -> Polylines:
        """cell_art through the cache. A refusal is cached too, and re-raised as ValueError."""
        data, aspect = picture()
        key = (mode, round(side_mm, 3), str(settings.grid_quality), float(settings.pen_width_mm))
        if key not in cache:
            try:
                cache[key] = cell_art(data, mode, side_mm, params_for(mode), aspect=aspect)
            except ValueError as exc:
                cache[key] = str(exc)
        hit = cache[key]
        if isinstance(hit, str):
            raise ValueError(hit)
        return hit

    def cells_now() -> list[tuple[float, float, float]]:
        width_mm, height_mm = sketch_canvas_mm(settings)
        label_mm = GRID_LABEL_MM if settings.grid_labels else 0.0
        return grid_cells(int(settings.grid_size), width_mm=width_mm, height_mm=height_mm, label_mm=label_mm)

    def update() -> None:
        editor.refresh()
        handle.refresh()

    def picker(row: int, col: int) -> Callable[[str], None]:
        def pick(mode: str) -> None:
            set_cell_mode(settings, row, col, mode)
            update()

        return pick

    @ui.refreshable
    def editor() -> None:
        n = int(settings.grid_size)
        side = cells_now()[0][2]
        table = _modes_table(settings)
        with oracle.tile_grid(n):
            for row in range(n):
                for col in range(n):
                    mode = table[row * TABLE + col]
                    svg, failed = "", ""
                    if mode and STATE["bytes"]:
                        try:
                            svg = polylines_to_svg(
                                art(mode, side), width_mm=side, height_mm=side, pen_width_mm=settings.pen_width_mm
                            )
                        except ValueError as exc:
                            failed = str(exc)
                    oracle.picture_tile(
                        f"{mode}: failed" if failed else (mode or "empty"),
                        svg,
                        MODE_OPTIONS,
                        picker(row, col),
                        empty=not mode,
                        failed=failed,
                    )

    host = preview_slot if preview_slot is not None else root
    with host:
        helper_text("Click a cell to choose its mode. Each cell shows exactly what it will print.")
        editor()
        # The tiles are the preview; the whole-sheet render still has to exist because it is
        # what PRINT sends, so render_card draws it into a container nobody sees.
        sheet_slot = ui.element("div")
        sheet_slot.set_visibility(False)

    with root, card("Mode grid", compact=True):
        helper_text("One picture in every cell, each cell drawn in its own mode. Shares the picture with IMAGE.")
        selected_label = helper_text("")

        def show_selected() -> None:
            selected_label.set_text(f"Selected: {STATE['name']}" if STATE["bytes"] else "No image selected")

        async def handle_upload(event: Any) -> None:
            try:
                name, data = await read_upload_event_payload(event)
            except Exception as exc:  # noqa: BLE001
                ui.notify(f"Image upload failed: {exc}", color="negative")
                return
            if not data:
                ui.notify("Image upload failed: file is empty", color="negative")
                return
            STATE["name"], STATE["bytes"] = name, data
            show_selected()
            update()

        oracle.file_upload("Drop a PNG/JPG here, or click + to choose", handle_upload)
        show_selected()

    def controls() -> None:
        def set_setting(key: str, value: Any) -> None:
            if getattr(settings, key) != value:
                setattr(settings, key, value)
                update()

        size_select = select(
            {size: f"{size} x {size}" for size in GRID_SIZES},
            value=int(settings.grid_size),
            label="Grid",
            on_change=lambda e: set_setting("grid_size", int(e.value)),
        )
        select(
            list(QUALITY_PRESETS),
            value=str(settings.grid_quality),
            label="Quality",
            on_change=lambda e: set_setting("grid_quality", str(e.value)),
        )
        switch(
            "Photo filter (crop bars + local contrast)",
            value=bool(settings.grid_photo_filter),
            on_change=lambda e: set_setting("grid_photo_filter", bool(e.value)),
        )
        switch(
            "Cell outlines and labels",
            value=bool(settings.grid_labels),
            on_change=lambda e: set_setting("grid_labels", bool(e.value)),
        )

        def all_modes() -> None:
            set_all_modes(settings)
            size_select.set_value(int(settings.grid_size))
            update()

        def clear() -> None:
            settings.grid_cell_modes = []
            update()

        with toolbar():
            safe_action_button("ALL MODES", all_modes)
            safe_action_button("CLEAR", clear)
        failures_box["label"] = helper_text("")

    def render() -> oracle.Render:
        failures_box["label"].set_text("")
        if not STATE["bytes"]:
            raise ValueError("Upload an image to see the grid.")
        modes = active_modes(settings)
        if not any(modes):
            raise ValueError("Click a cell to choose its mode, or press ALL MODES.")
        data, _aspect = picture()
        width_mm, height_mm = sketch_canvas_mm(settings)
        n = int(settings.grid_size)
        # ponytail: renders on the event loop like every render_card source. The cell cache
        # makes a re-render cheap; the first 9x9 at "max" can still freeze the tab. Move
        # render_card onto run.cpu_bound if that bites.
        polylines, failures = grid_to_polylines(
            data,
            modes,
            n=n,
            width_mm=width_mm,
            height_mm=height_mm,
            params_for=params_for,
            labels=bool(settings.grid_labels),
            art_for=art,
        )
        failures_box["label"].set_text("; ".join(failures))
        stem = str(STATE["name"] or "image").rsplit(".", 1)[0]
        return oracle.Render(polylines=polylines, width_mm=width_mm, height_mm=height_mm, name=f"{stem}_grid{n}x{n}")

    with root:
        handle = oracle.render_card(
            ctx,
            title="Sheet",
            controls=controls,
            render=render,
            travel_default=False,
            preview_slot=sheet_slot,
            actions=False,
        )

    def on_show() -> None:
        # IMAGE may have loaded a different picture while this pane was hidden.
        show_selected()
        update()

    return oracle.Section(
        root=root, refresh=handle.refresh, print=handle.print, print_label="PRINT GRID", on_show=on_show
    )
