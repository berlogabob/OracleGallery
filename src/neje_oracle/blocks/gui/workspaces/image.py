"""Image workspace: raster image -> single-pen line art -> plotter."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ....blocks.imaging.modes import (
    MODES,
    image_to_polylines,
    polylines_to_svg,
    travel_length_mm,
)
from ..context import GuiContext
from ..support import read_upload_event_payload
from ..ui import helper_text, primary_action_button, safe_action_button

# ponytail: image knobs stay in-module, not in GUI_DEFAULTS/GuiSettings — they are
# per-image choices, not machine calibration. Promote them if operators ask for sticky values.
STATE: dict[str, Any] = {
    "name": "",
    "bytes": b"",
    "svg": "",
    "mode": "halftone",
    "width_mm": 150.0,
    "height_mm": 150.0,
    "cell_mm": 1.5,
    "gamma": 1.0,
    "invert": False,
    "detail": 1.0,
}

MODE_HELP = {
    "halftone": "Dots grow with darkness. Shortest plot, reads best from a distance.",
    "hatch": "Parallel lines drawn only where the image is dark. Detail = line spacing in mm.",
    "dither": "Floyd-Steinberg dots. Highest fidelity, longest plot.",
    "contour": "Threshold-band outlines. Detail = number of bands.",
}


def _mode_params(mode: str, detail: float) -> dict[str, Any]:
    if mode == "hatch":
        return {"line_spacing_mm": max(0.2, detail), "angle_deg": 45.0}
    if mode == "contour":
        return {"bands": max(2, int(round(detail)))}
    return {}


def build(ctx: GuiContext) -> None:
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Image to line art").classes("text-sm font-bold")
            helper_text(
                "A single pen cannot print grey. Each mode turns tone into geometry the plotter can actually draw."
            )
            selected_label = ui.label("No image selected").classes("path-label text-xs")

            async def handle_upload(event: Any) -> None:
                try:
                    name, data = await read_upload_event_payload(event)
                except Exception as exc:  # noqa: BLE001
                    ui.notify(f"Image upload failed: {exc}", color="negative")
                    return
                if not data:
                    ui.notify("Image upload failed: file is empty", color="negative")
                    return
                STATE["name"] = name
                STATE["bytes"] = data
                selected_label.set_text(f"Selected: {name}")
                refresh_preview()

            ui.upload(on_upload=handle_upload).props(
                "accept=.png,.jpg,.jpeg,.bmp,.webp,.gif max-files=1 auto-upload"
            ).classes("w-full")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Conversion").classes("text-sm font-bold")
            mode_help = ui.label(MODE_HELP[STATE["mode"]]).classes("text-xs text-[#8f4f2b]")

            def set_field(key: str, value: Any) -> None:
                STATE[key] = value
                if key == "mode":
                    mode_help.set_text(MODE_HELP.get(str(value), ""))
                refresh_preview()

            with ui.row().classes("gap-2 w-full items-center"):
                ui.select(
                    sorted(MODES),
                    value=STATE["mode"],
                    label="Mode",
                    on_change=lambda e: set_field("mode", e.value),
                ).props("dense outlined").classes("w-36")
                ui.number(
                    "Width mm",
                    value=STATE["width_mm"],
                    min=5,
                    step=5,
                    on_change=lambda e: set_field("width_mm", float(e.value or 150.0)),
                ).props("dense outlined").classes("w-28")
                ui.number(
                    "Height mm",
                    value=STATE["height_mm"],
                    min=5,
                    step=5,
                    on_change=lambda e: set_field("height_mm", float(e.value or 150.0)),
                ).props("dense outlined").classes("w-28")

            with ui.row().classes("gap-2 w-full items-center"):
                ui.number(
                    "Cell mm",
                    value=STATE["cell_mm"],
                    min=0.2,
                    step=0.1,
                    on_change=lambda e: set_field("cell_mm", float(e.value or 1.5)),
                ).props("dense outlined").classes("w-28").tooltip(
                    "Sampling resolution. Smaller = more detail and a much longer plot."
                )
                ui.number(
                    "Detail",
                    value=STATE["detail"],
                    min=0.2,
                    step=0.2,
                    on_change=lambda e: set_field("detail", float(e.value or 1.0)),
                ).props("dense outlined").classes("w-28").tooltip(
                    "Hatch: line spacing mm. Contour: band count. Ignored by halftone/dither."
                )
                ui.number(
                    "Gamma",
                    value=STATE["gamma"],
                    min=0.2,
                    max=4.0,
                    step=0.1,
                    on_change=lambda e: set_field("gamma", float(e.value or 1.0)),
                ).props("dense outlined").classes("w-24").tooltip("Above 1 lightens midtones, below 1 darkens them.")
                ui.switch(
                    "Invert",
                    value=STATE["invert"],
                    on_change=lambda e: set_field("invert", bool(e.value)),
                )

            cost_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
            preview = ui.html().classes("preview-frame w-full")

            with ui.row().classes("items-center gap-2"):
                safe_action_button("REFRESH PREVIEW", lambda: refresh_preview())
                primary_action_button("PRINT IMAGE", lambda: print_image())

    def refresh_preview() -> None:
        if not STATE["bytes"]:
            preview.content = ""
            cost_label.set_text("Upload an image to see the preview.")
            STATE["svg"] = ""
            return
        try:
            polylines = image_to_polylines(
                STATE["bytes"],
                mode=str(STATE["mode"]),
                width_mm=float(STATE["width_mm"]),
                height_mm=float(STATE["height_mm"]),
                cell_mm=float(STATE["cell_mm"]),
                gamma=float(STATE["gamma"]),
                invert=bool(STATE["invert"]),
                **_mode_params(str(STATE["mode"]), float(STATE["detail"])),
            )
        except ValueError as exc:
            preview.content = ""
            STATE["svg"] = ""
            cost_label.set_text(str(exc))
            ui.notify(str(exc), color="warning")
            return
        svg = polylines_to_svg(
            polylines,
            width_mm=float(STATE["width_mm"]),
            height_mm=float(STATE["height_mm"]),
        )
        STATE["svg"] = svg
        preview.content = svg
        preview.update()
        draw_mm, travel_mm = travel_length_mm(polylines)
        segments = sum(max(0, len(p) - 1) for p in polylines)
        minutes = (draw_mm / max(ctx.settings.draw_rate, 1.0)) + (travel_mm / max(ctx.settings.travel_rate, 1.0))
        cost_label.set_text(
            f"{len(polylines)} strokes, {segments} segments, "
            f"{draw_mm / 1000:.1f} m drawn + {travel_mm / 1000:.1f} m travel, "
            f"~{minutes:.0f} min at current feeds"
        )

    async def print_image() -> None:
        if not STATE["svg"]:
            refresh_preview()
        if not STATE["svg"]:
            ui.notify("Upload an image and refresh the preview first", color="warning")
            return
        stem = str(STATE["name"] or "image").rsplit(".", 1)[0]
        await ctx.print_svg_payload(STATE["svg"].encode("utf-8"), f"{stem}_{STATE['mode']}.svg")

    refresh_preview()
