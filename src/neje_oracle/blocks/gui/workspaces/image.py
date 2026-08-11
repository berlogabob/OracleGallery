"""Image workspace: raster image -> single-pen line art -> plotter."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from nicegui import ui

from ....blocks.imaging.modes import (
    MODES,
    PEN_WIDTH_MM_DEFAULT,
    image_to_polylines,
    polylines_to_svg,
    travel_length_mm,
    travel_preview_svg,
)
from ....blocks.imaging.sheet import SHAPES, frame_grid_capacity, images_to_sheet_polylines
from ....shared.gui_settings import GuiSettings
from ..context import GuiContext
from ..support import read_upload_event_payload
from ..ui import helper_text, primary_action_button, safe_action_button

# ponytail: image knobs stay in-module, not in GUI_DEFAULTS/GuiSettings — they are
# per-image choices, not machine calibration. Promote them if operators ask for sticky values.
STATE: dict[str, Any] = {
    "name": "",
    "bytes": b"",
    "svg": "",
    "mode": "trace",
    "quality": "fine",
    "width_mm": 150.0,
    "height_mm": 150.0,
    "cell_mm": 0.10,
    "gamma": 1.0,
    "invert": False,
    "show_travel": True,
    "detail": 1.0,
}

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")

# Cell size is in frame terms, not pixels: set it to the wooden frame's aperture. gap_mm 0
# butts the cells so one cut serves two prints; gap_mm > 0 leaves a cutting alley.
SHEET_STATE: dict[str, Any] = {
    "folder": "",
    "cell_w": 40.0,
    "cell_h": 60.0,
    "gap": 5.0,
    "padding": 2.0,
    "shape": "rect",
    "sheet_index": 0,
    "svg": "",
}

MODE_HELP = {
    "trace": "Follows the drawing's own lines, filling bold strokes to weight. For ink drawings and line art.",
    "halftone": "Dots grow with darkness. Shortest plot, reads best from a distance.",
    "hatch": "Parallel lines drawn only where the image is dark. Detail = line spacing in mm.",
    "dither": "Floyd-Steinberg dots. Highest fidelity, longest plot.",
    "contour": "Threshold-band outlines. Detail = number of bands.",
    "crosshatch": "Layered hatching at four angles. Graphic and even; good for flat tone.",
    "flow": "Hatching that follows the form, so shading wraps around shapes. Best for photographs.",
    "spiral": "One spiral out from the centre, wobbling harder where the image is dark. Fewest pen lifts of any mode.",
    "wave": "Rows that ripple wider and faster with darkness. Graphic, continuous, no dropped lines.",
    "stipple": "Density-weighted dots, chained into rows to cut pen lifts. Grainy, organic tone.",
    "squiggle": "One continuous meandering line, packing tighter where the image is dark. Wandering, few pen lifts.",
}


# The quality fader, slowest last. Every row below is indexed by the same position, so a
# preset is one number that moves resolution, spacing and the segment budget together.
QUALITY_PRESETS = ("draft", "fast", "balanced", "fine", "max")

# cell_mm means something different per mode, so one shared table cannot serve all of them.
# For trace it is the resolution the drawing is followed at, and it wants to sit at or below
# the source's own pixel size — 0.2 mm resamples a 1024 px source down to 750 and blurs thin
# strokes away before thinning runs, which cost 19% of the drawing.
# Stops at 0.10, not finer. Walking the skeleton is a Python loop and its cost roughly
# doubles per step: on the densest real folder, 0.146 takes 1.3 s, 0.10 takes 8.6 s and
# 0.07 takes 43 s — for +0.01 F over 0.10. A 43 s frozen preview is not worth that.
_TRACE_CELL_MM = (0.30, 0.20, 0.146, 0.12, 0.10)
# For halftone it is dot pitch: 10 000 dots on a 150 mm frame blows the segment cap before
# the first vertex is placed, so it stays far coarser than the line modes.
_HALFTONE_CELL_MM = (4.0, 3.5, 3.0, 2.5, 2.0)
_TONE_CELL_MM = (1.5, 1.0, 0.7, 0.5, 0.4)
_SPACING_MM = (2.5, 2.0, 1.6, 1.2, 1.0)
# One grid cell, at every preset. Expressed in cells this tracks resolution for free, and
# it stops the top presets emitting vertices finer than the machine can act on: at cell 0.10
# a 0.8-cell tolerance is 0.08 mm, against a 0.3 mm pen and a 1.0 mm G-code sample step.
_SIMPLIFY_PX = (1.0, 1.0, 1.0, 1.0, 1.0)
# Photo work is impossible at the shipped 40k: a shaded render needs 49k segments for dither
# and 125k for halftone. The budget has to move with the fader or the top presets dead-end.
# From measurement, ~25% over the worst real image at each preset. The top presets are
# genuinely large: `max` can reach ~500k segments, which is a multi-MB G-code file, and at
# ok_wait streaming that upload becomes the slow part rather than the drawing.
_MAX_SEGMENTS = (40_000, 60_000, 90_000, 240_000, 640_000)
# Same story for the skeleton guard: the measured worst real image needs 195 000 px at the
# top preset, so a flat 150 000 made `fine` unselectable. Roughly 2x headroom over measured
# worst, which still refuses noise (a 1500-grid noise field skeletonises to ~950 000).
_MAX_SKELETON_PX = (60_000, 90_000, 130_000, 260_000, 420_000)
# Measured medians over one sample from each of the nine boats/collections folders at
# 150 mm and the shipped feeds — not guesses. Advisory only: the cost line under the preview
# is computed from the actual geometry and corrects this for the image in hand.
# Fidelity at the same points, scored against the source at 1 px:
#   draft 0.895 | fast 0.921 | balanced 0.937 | fine 0.947 | max 0.960
_TYPICAL_MINUTES = (22, 31, 45, 61, 87)

# Taste constants, deliberately not on the fader — they are about how the drawing should
# look, not how long it may take, so moving the quality slider must not change them.
# Below this darkness the paper is left alone. At the shipped 0.05 nothing was ever white,
# which is most of why the tone modes read as an even grey field rather than a photograph.
WHITE_POINT = 0.18
# Free on tone content: identical tone correlation, 622 -> 287 strokes, 40 -> 28 min. Kept
# near 1.2 mm because past ~2 mm it starts bridging the gaps that encode tone and adds ink.
CROSSHATCH_STITCH_MM = 1.2
# Every dither dot is otherwise its own pen lift: a photo came to 77 129 strokes, ~41 hours.
# Chaining them into rows trades some tonal precision (0.992 -> 0.908) for ~6x the speed.
DITHER_CHAIN_GAP_MM = 1.6


def quality_index(quality: str) -> int:
    return QUALITY_PRESETS.index(quality) if quality in QUALITY_PRESETS else QUALITY_PRESETS.index("balanced")


# What the pen can actually resolve, measured on paper with a 0.5 mm fineliner: a 0.5 mm line
# pair merged into one line, 1.0 mm barely separated, 2.0 mm was clean. Both floors below come
# from that single measurement.
#   - a dot lattice finer than two pen widths fills in instead of reading as tone. At the
#     shipped balanced cell of 0.7 mm, dither's dot_mm defaults to 0.42 mm — smaller than the
#     pen itself — and the dark end printed as solid bands.
#   - sampling a drawing finer than half a pen width traces detail that cannot print. Merging
#     it in the raster, before _thin runs, turns two sub-pen strokes into one clean skeleton
#     line; leaving it produced congested mud at the biplane's engine.
_DOT_PITCH_MODES = frozenset({"dither", "halftone"})
# Modes that need to know the pen to be correct: trace sizes its weight passes off it, and
# halftone fills its dots rather than ringing them once they are wider than the nib.
_PEN_AWARE_MODES = frozenset({"trace", "halftone"})


def quality_cell_mm(mode: str, quality: str, pen_width_mm: float = PEN_WIDTH_MM_DEFAULT) -> float:
    step = quality_index(quality)
    if mode == "trace":
        return max(_TRACE_CELL_MM[step], pen_width_mm / 2.0)
    if mode == "halftone":
        return max(_HALFTONE_CELL_MM[step], pen_width_mm * 2.0)
    if mode in _DOT_PITCH_MODES:
        return max(_TONE_CELL_MM[step], pen_width_mm * 2.0)
    return _TONE_CELL_MM[step]


def quality_max_segments(quality: str) -> int:
    return _MAX_SEGMENTS[quality_index(quality)]


def plot_minutes(
    settings: GuiSettings,
    *,
    strokes: int,
    draw_mm: float,
    travel_mm: float,
    use_z_servo: bool,
) -> tuple[float, float]:
    """Split the plot into (xy_minutes, pen_minutes).

    Every stroke costs a Z round trip, and at the shipped -25 mm throw / 1000 mm/min that
    is ~1.8 s of pen for ~0.2 s of ink. Counting only XY under-reported a 488-stroke
    halftone as 1.7 min when the machine actually spent ~18. Legs are costed the way
    svg_gcode emits them: down is a G1 at z_feed_mm_min, up is a G0 under the file's
    G0 F<travel_rate>.
    """
    xy_minutes = draw_mm / max(settings.draw_rate, 1.0) + travel_mm / max(settings.travel_rate, 1.0)
    if not use_z_servo:
        return xy_minutes, 0.0
    throw_mm = abs(settings.z_down_mm - settings.z_up_mm)
    per_cycle = throw_mm / max(settings.z_feed_mm_min, 1.0) + throw_mm / max(settings.travel_rate, 1.0)
    return xy_minutes, strokes * per_cycle


def preview_svg(polylines: list[list[tuple[float, float]]], *, width_mm: float, height_mm: float) -> str:
    """What the operator sees. With travel lines off this is the printed geometry exactly,
    so the preview doubles as a proof of what lands on paper."""
    render = travel_preview_svg if STATE["show_travel"] else polylines_to_svg
    return render(polylines, width_mm=width_mm, height_mm=height_mm)


def _mode_params(mode: str, detail: float, quality: str = "balanced") -> dict[str, Any]:
    """Mode keywords for a quality preset. `detail` is the operator's fine adjustment on top."""
    step = quality_index(quality)
    scale = max(0.2, detail)
    if mode == "hatch":
        return {
            "line_spacing_mm": max(0.2, _SPACING_MM[step] / scale),
            "angle_deg": 45.0,
            "min_darkness": WHITE_POINT,
        }
    if mode == "crosshatch":
        return {
            "line_spacing_mm": max(0.3, _SPACING_MM[step] / scale),
            "min_darkness": WHITE_POINT,
            "stitch_mm": CROSSHATCH_STITCH_MM,
        }
    if mode == "flow":
        # Two spacings, not one: tone comes from how far apart the streamlines sit, so the
        # fader has to move the dark end and the light end together.
        return {
            "min_spacing_mm": max(0.3, _SPACING_MM[step] * 0.5 / scale),
            "max_spacing_mm": max(0.6, _SPACING_MM[step] * 2.2 / scale),
            "white_point": WHITE_POINT,
        }
    if mode == "spiral":
        return {
            "pitch_mm": max(1.0, _SPACING_MM[step] / scale),
            "min_darkness": WHITE_POINT,
        }
    if mode == "wave":
        # Amplitude is capped inside the mode to 45% of the row pitch so neighbouring rows
        # cannot cross; asking for more than that here would silently do nothing.
        return {
            "row_pitch_mm": max(1.0, _SPACING_MM[step] * 1.25 / scale),
            "min_darkness": WHITE_POINT,
        }
    if mode == "stipple":
        # Both floored at 1.0: the measured pen-and-paper spacing where two lines still
        # read as two, not one. Below that this mode would just be a slower, chained dither.
        return {
            "row_pitch_mm": max(1.0, _SPACING_MM[step] / scale),
            "min_spacing_mm": max(1.0, _SPACING_MM[step] / scale),
            "min_darkness": WHITE_POINT,
        }
    if mode == "squiggle":
        return {
            "min_row_pitch_mm": max(1.0, _SPACING_MM[step] / scale),
            "min_darkness": WHITE_POINT,
        }
    if mode == "dither":
        return {"chain_gap_mm": DITHER_CHAIN_GAP_MM}
    if mode == "halftone":
        # halftone's own min_ink_mm is a size floor, not a tone floor, and expressed in tone it
        # weakens as the dot pitch grows -- 1% darkness at the shipped 3 mm pitch, so the whole
        # sheet got dots. The white point is what actually leaves paper as paper.
        return {"min_darkness": WHITE_POINT}
    if mode == "contour":
        # Two, not four. Every band traces the same edge on near-binary art, so the extra two
        # only stack ink on top of ink: measured on a line drawing, 4 bands laid 1649 mm of ink
        # against 883 mm at 2 and 504 mm at 1, and the hull printed as a solid mass. Detail
        # still scales up from here for a photograph, which is the subject that earns bands.
        return {"bands": max(2, int(round(2 * scale)))}
    if mode == "trace":
        # Only simplification is a per-image choice. Stitching and despeckling are left at
        # their swept values: more stitching is free, and any despeckling costs fidelity.
        # Weight passes come from the pen width, so there is no knob for them either.
        return {
            "simplify_px": _SIMPLIFY_PX[step] / scale,
            "max_skeleton_px": _MAX_SKELETON_PX[step],
            # shade_spacing_mm is deliberately NOT set here. Hatching the uninked mid-tones
            # looked worthwhile until weight passes existed; measured against all nine
            # folders afterwards it is negative or neutral on every one (worst: boats02,
            # F 0.949 -> 0.883), because filling bold strokes already covers what the
            # shading was aimed at. trace() still accepts it for flat-colour sources.
        }
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

            # Unlabelled, a QUploader renders as a black "0.0B / 0.00%" strip and reads as a
            # progress bar, not a file picker — operators could not find the feature.
            ui.upload(label="Drop a PNG/JPG here, or click + to choose", on_upload=handle_upload).props(
                "accept=.png,.jpg,.jpeg,.bmp,.webp,.gif max-files=1 auto-upload"
            ).classes("w-full")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Conversion").classes("text-sm font-bold")
            mode_help = ui.label(MODE_HELP[STATE["mode"]]).classes("text-xs text-[#8f4f2b]")

            def set_field(key: str, value: Any) -> None:
                STATE[key] = value
                if key in ("mode", "quality"):
                    mode_help.set_text(MODE_HELP.get(str(STATE["mode"]), ""))
                    STATE["cell_mm"] = quality_cell_mm(
                        str(STATE["mode"]), str(STATE["quality"]), ctx.settings.pen_width_mm
                    )
                    cell_field.set_value(STATE["cell_mm"])
                    quality_label.set_text(_quality_text())
                refresh_preview()

            def _quality_text() -> str:
                step = quality_index(str(STATE["quality"]))
                return (
                    f"Quality: {QUALITY_PRESETS[step].upper()} — about {_TYPICAL_MINUTES[step]} min "
                    f"for a 150 mm drawing. Slower presets trace finer and allow more segments."
                )

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

            quality_label = ui.label("").classes("text-xs text-[#8f4f2b]")
            ui.slider(
                min=0,
                max=len(QUALITY_PRESETS) - 1,
                step=1,
                value=quality_index(str(STATE["quality"])),
                on_change=lambda e: set_field("quality", QUALITY_PRESETS[int(e.value)]),
            ).props(
                "label-always markers snap :label-value=\"['draft','fast','balanced','fine','max'][value]\""
            ).classes("w-full tight-slider")

            with ui.row().classes("gap-2 w-full items-center"):
                cell_field = (
                    ui.number(
                        "Cell mm",
                        value=STATE["cell_mm"],
                        min=0.2,
                        step=0.1,
                        on_change=lambda e: set_field(
                            "cell_mm",
                            float(
                                e.value
                                or quality_cell_mm(
                                    str(STATE["mode"]), str(STATE["quality"]), ctx.settings.pen_width_mm
                                )
                            ),
                        ),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                    .tooltip(
                        "Trace: the resolution the drawing is followed at. Tone modes: sampling pitch, "
                        "where smaller means more detail and a much longer plot. Switching mode resets it."
                    )
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
                ui.switch(
                    "Travel lines",
                    value=STATE["show_travel"],
                    on_change=lambda e: set_field("show_travel", bool(e.value)),
                ).tooltip("Off shows the drawing alone, as it will appear on paper. Never affects what is printed.")

            cost_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
            preview = ui.html().classes("preview-frame w-full")

            with ui.row().classes("items-center gap-2"):
                safe_action_button("REFRESH PREVIEW", lambda: refresh_preview())
                primary_action_button("PRINT IMAGE", lambda: print_image())

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Frame sheet").classes("text-sm font-bold")
            helper_text(
                "Fill one sheet from a folder, using the mode and tone settings above. "
                "Set the cell to your wooden frame's aperture; gap 0 butts the cells so one cut serves two prints."
            )

            def set_sheet(key: str, value: Any) -> None:
                SHEET_STATE[key] = value
                refresh_sheet_capacity()

            ui.input(
                "Image folder",
                value=SHEET_STATE["folder"],
                placeholder="/Users/you/Documents/ComfyUI/output/boats01",
                on_change=lambda e: set_sheet("folder", str(e.value or "")),
            ).props("dense outlined clearable").classes("w-full")

            with ui.row().classes("gap-2 w-full items-center"):
                ui.number(
                    "Cell width mm",
                    value=SHEET_STATE["cell_w"],
                    min=5,
                    step=5,
                    on_change=lambda e: set_sheet("cell_w", float(e.value or 40.0)),
                ).props("dense outlined").classes("w-32")
                ui.number(
                    "Cell height mm",
                    value=SHEET_STATE["cell_h"],
                    min=5,
                    step=5,
                    on_change=lambda e: set_sheet("cell_h", float(e.value or 60.0)),
                ).props("dense outlined").classes("w-32")
                ui.number(
                    "Gap mm",
                    value=SHEET_STATE["gap"],
                    min=0,
                    step=1,
                    on_change=lambda e: set_sheet("gap", float(e.value or 0.0)),
                ).props("dense outlined").classes("w-24").tooltip("0 = cells butt together. Above 0 = alley to cut in.")
                ui.number(
                    "Padding mm",
                    value=SHEET_STATE["padding"],
                    min=0,
                    step=0.5,
                    on_change=lambda e: set_sheet("padding", float(e.value or 0.0)),
                ).props("dense outlined").classes("w-28").tooltip("Blank border between the cut line and the art.")

            with ui.row().classes("gap-2 w-full items-center"):
                ui.select(
                    list(SHAPES),
                    value=SHEET_STATE["shape"],
                    label="Cut line",
                    on_change=lambda e: set_sheet("shape", str(e.value)),
                ).props("dense outlined").classes("w-32")
                ui.number(
                    "Sheet #",
                    value=SHEET_STATE["sheet_index"],
                    min=0,
                    step=1,
                    on_change=lambda e: set_sheet("sheet_index", int(e.value or 0)),
                ).props("dense outlined").classes("w-24").tooltip("0 = first sheet of the folder, 1 = next, ...")

            sheet_info = ui.label("-").classes("text-xs text-[#8f4f2b]")
            sheet_cost = ui.label("").classes("text-xs text-[#8f4f2b]")
            sheet_preview = ui.html().classes("preview-frame w-full")

            with ui.row().classes("items-center gap-2"):
                safe_action_button("BUILD SHEET", lambda: build_sheet())
                primary_action_button("PRINT SHEET", lambda: print_sheet())

    def _sheet_files() -> list[Path]:
        folder = Path(SHEET_STATE["folder"]).expanduser()
        if not SHEET_STATE["folder"] or not folder.is_dir():
            return []
        return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)

    def _sheet_capacity() -> int:
        return frame_grid_capacity(
            sheet_width_mm=ctx.settings.sheet_width_mm,
            sheet_height_mm=ctx.settings.sheet_height_mm,
            margin_mm=ctx.settings.sheet_margin_mm,
            cell_width_mm=float(SHEET_STATE["cell_w"]),
            cell_height_mm=float(SHEET_STATE["cell_h"]),
            gap_mm=float(SHEET_STATE["gap"]),
        )

    def refresh_sheet_capacity() -> None:
        SHEET_STATE["svg"] = ""
        sheet_preview.content = ""
        sheet_cost.set_text("")
        capacity = _sheet_capacity()
        sheet = ctx.settings
        if capacity <= 0:
            sheet_info.set_text(
                f"No cell fits: {SHEET_STATE['cell_w']:g}x{SHEET_STATE['cell_h']:g} mm on a "
                f"{sheet.sheet_width_mm:g}x{sheet.sheet_height_mm:g} mm sheet with a {sheet.sheet_margin_mm:g} mm margin."
            )
            return
        files = _sheet_files()
        if not files:
            sheet_info.set_text(f"{capacity} per sheet. Point 'Image folder' at a folder of images.")
            return
        total_sheets = math.ceil(len(files) / capacity)
        index = min(int(SHEET_STATE["sheet_index"]), total_sheets - 1)
        sheet_info.set_text(
            f"{len(files)} images, {capacity} per sheet -> {total_sheets} sheets. "
            f"Showing sheet {index + 1} of {total_sheets}."
        )

    def build_sheet() -> None:
        capacity = _sheet_capacity()
        files = _sheet_files()
        if capacity <= 0 or not files:
            refresh_sheet_capacity()
            ui.notify("Set a folder and a cell size that fits the sheet first", color="warning")
            return
        start = int(SHEET_STATE["sheet_index"]) * capacity
        batch = files[start : start + capacity]
        if not batch:
            ui.notify(f"Sheet {SHEET_STATE['sheet_index']} is past the end of the folder", color="warning")
            return
        try:
            polylines, placed = images_to_sheet_polylines(
                [path.read_bytes() for path in batch],
                sheet_width_mm=ctx.settings.sheet_width_mm,
                sheet_height_mm=ctx.settings.sheet_height_mm,
                margin_mm=ctx.settings.sheet_margin_mm,
                cell_width_mm=float(SHEET_STATE["cell_w"]),
                cell_height_mm=float(SHEET_STATE["cell_h"]),
                gap_mm=float(SHEET_STATE["gap"]),
                padding_mm=float(SHEET_STATE["padding"]),
                shape=str(SHEET_STATE["shape"]),
                mode=str(STATE["mode"]),
                cell_mm=float(STATE["cell_mm"]),
                **({"pen_width_mm": ctx.settings.pen_width_mm} if STATE["mode"] in _PEN_AWARE_MODES else {}),
                gamma=float(STATE["gamma"]),
                invert=bool(STATE["invert"]),
                max_segments=quality_max_segments(str(STATE["quality"])),
                min_stroke_mm=ctx.settings.pen_width_mm * 2.0,
                **_mode_params(str(STATE["mode"]), float(STATE["detail"]), str(STATE["quality"])),
            )
        except (ValueError, OSError) as exc:
            SHEET_STATE["svg"] = ""
            sheet_preview.content = ""
            sheet_cost.set_text(str(exc))
            ui.notify(str(exc), color="warning")
            return
        svg = polylines_to_svg(
            polylines,
            width_mm=ctx.settings.sheet_width_mm,
            height_mm=ctx.settings.sheet_height_mm,
            pen_width_mm=ctx.settings.pen_width_mm,
        )
        SHEET_STATE["svg"] = svg
        # The plotter gets `svg`; the operator sees the travel overlay on top of it.
        sheet_preview.content = preview_svg(
            polylines,
            width_mm=ctx.settings.sheet_width_mm,
            height_mm=ctx.settings.sheet_height_mm,
        )
        sheet_preview.update()
        draw_mm, travel_mm = travel_length_mm(polylines)
        xy_minutes, pen_minutes = plot_minutes(
            ctx.settings,
            strokes=len(polylines),
            draw_mm=draw_mm,
            travel_mm=travel_mm,
            use_z_servo=ctx.supervisor.plotter_settings.use_z_servo,
        )
        total = xy_minutes + pen_minutes
        sheet_cost.set_text(
            f"{placed} images, {len(polylines)} strokes, ~{total:.0f} min "
            f"({xy_minutes:.0f} min moving + {pen_minutes:.0f} min pen lifts), "
            f"~{total / max(placed, 1):.0f} min per image"
        )

    async def print_sheet() -> None:
        if not SHEET_STATE["svg"]:
            build_sheet()
        if not SHEET_STATE["svg"]:
            ui.notify("Build the sheet first", color="warning")
            return
        stem = Path(SHEET_STATE["folder"]).name or "sheet"
        await ctx.print_svg_payload(
            SHEET_STATE["svg"].encode("utf-8"),
            f"{stem}_sheet{int(SHEET_STATE['sheet_index'])}.svg",
        )

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
                max_segments=quality_max_segments(str(STATE["quality"])),
                min_stroke_mm=ctx.settings.pen_width_mm * 2.0,
                **({"pen_width_mm": ctx.settings.pen_width_mm} if STATE["mode"] in _PEN_AWARE_MODES else {}),
                **_mode_params(str(STATE["mode"]), float(STATE["detail"]), str(STATE["quality"])),
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
            pen_width_mm=ctx.settings.pen_width_mm,
        )
        STATE["svg"] = svg
        preview.content = preview_svg(
            polylines,
            width_mm=float(STATE["width_mm"]),
            height_mm=float(STATE["height_mm"]),
        )
        preview.update()
        draw_mm, travel_mm = travel_length_mm(polylines)
        segments = sum(max(0, len(p) - 1) for p in polylines)
        xy_minutes, pen_minutes = plot_minutes(
            ctx.settings,
            strokes=len(polylines),
            draw_mm=draw_mm,
            travel_mm=travel_mm,
            use_z_servo=ctx.supervisor.plotter_settings.use_z_servo,
        )
        pen_note = f" + {pen_minutes:.0f} min pen lifts" if pen_minutes >= 0.5 else ""
        cost_label.set_text(
            f"{len(polylines)} strokes, {segments} segments, "
            f"{draw_mm / 1000:.1f} m drawn + {travel_mm / 1000:.1f} m travel, "
            f"~{xy_minutes + pen_minutes:.0f} min at current feeds "
            f"({xy_minutes:.0f} min moving{pen_note})"
        )

    async def print_image() -> None:
        if not STATE["svg"]:
            refresh_preview()
        if not STATE["svg"]:
            ui.notify("Upload an image and refresh the preview first", color="warning")
            return
        stem = str(STATE["name"] or "image").rsplit(".", 1)[0]
        await ctx.print_svg_payload(STATE["svg"].encode("utf-8"), f"{stem}_{STATE['mode']}.svg")

    quality_label.set_text(_quality_text())
    refresh_preview()
    refresh_sheet_capacity()
