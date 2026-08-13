"""Image workspace: raster image -> single-pen line art -> plotter."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from nicegui import ui

from ....blocks.imaging.modes import (
    AI_LINE_ART_TRACE,
    MODES,
    PEN_WIDTH_MM_DEFAULT,
    image_to_polylines,
    polylines_to_svg,
    travel_preview_svg,
)
from ....blocks.imaging.sheet import SHAPES, frame_grid_capacity, images_to_sheet_polylines
from ....blocks.patterns import bank
from ....blocks.patterns.ingest import DEFAULT_MODE as DEFAULT_MOTIF_MODE
from ....blocks.patterns.ingest import CropBox, image_to_motif_polylines, motif_svg
from ....shared.gui_settings import GuiSettings
from .. import ui as oracle
from ..context import GuiContext
from ..support import read_upload_event_payload
from ..ui import helper_text, primary_action_button, safe_action_button

# These dicts are still the workspace's working state, but the tune-once knobs are no longer
# only here: operators asked for sticky values, so they are mirrored to GuiSettings (see
# _PERSISTED_* below). What stays purely in-module is per-picture — bytes, names, the crop box,
# the folder and the sheet index — because carrying those across a restart is a bug, not a
# preference.
STATE: dict[str, Any] = {
    "name": "",
    "bytes": b"",
    "svg": "",
    "mode": "trace",
    "quality": "fine",
    "source": "scan",
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

# Separate from STATE: the print path wants a whole picture at sheet scale, the bank wants
# one cropped glyph normalized to a unit box. Sharing knobs would fight over both.
MOTIF_STATE: dict[str, Any] = {
    "name": "",
    "bytes": b"",
    "svg": "",
    "mode": DEFAULT_MOTIF_MODE,
    "crop_left": 0.0,
    "crop_top": 0.0,
    "crop_width": 100.0,
    "crop_height": 100.0,
    "cell_mm": 0.8,
    "gamma": 1.0,
    "autocontrast": True,
    "invert": False,
    "despeckle_mm": 1.5,
    "simplify_mm": 0.4,
    "motif_name": "",
}

# in-module key -> GuiSettings field. Only the sticky ones appear here; anything missing is
# per-picture and is meant to reset. The same names are registered into ctx.fields below, which
# is what makes GuiContext.pull_settings_from_fields read them back.
_PERSISTED_IMAGE_KEYS = {
    "mode": "image_mode",
    "quality": "image_quality",
    "source": "image_source",
    "width_mm": "image_width_mm",
    "height_mm": "image_height_mm",
    "cell_mm": "image_cell_mm",
    "detail": "image_detail",
    "gamma": "image_gamma",
    "invert": "image_invert",
    "show_travel": "image_show_travel",
}
_PERSISTED_SHEET_KEYS = {
    "cell_w": "sheet_cell_width_mm",
    "cell_h": "sheet_cell_height_mm",
    "gap": "sheet_gap_mm",
    "padding": "sheet_padding_mm",
    "shape": "sheet_shape",
}
_PERSISTED_MOTIF_KEYS = {
    "mode": "motif_mode",
    "cell_mm": "motif_cell_mm",
    "gamma": "motif_gamma",
    "autocontrast": "motif_autocontrast",
    "invert": "motif_invert",
    "despeckle_mm": "motif_despeckle_mm",
    "simplify_mm": "motif_simplify_mm",
}


def seed_state_from_settings(settings: GuiSettings) -> None:
    """Restore what the operator last chose, so a process restart is not a reset.

    The module dicts survive a browser reload but not a restart, and they are shared by
    every browser session; GuiSettings is the thing that is actually written to disk.
    """
    for state, mapping in (
        (STATE, _PERSISTED_IMAGE_KEYS),
        (SHEET_STATE, _PERSISTED_SHEET_KEYS),
        (MOTIF_STATE, _PERSISTED_MOTIF_KEYS),
    ):
        for key, field_name in mapping.items():
            state[key] = getattr(settings, field_name)


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

# What the drawing came from. Only trace reads it, and the overrides themselves live with
# trace() in the imaging layer — see AI_LINE_ART_TRACE for what they cost and buy.
SOURCE_PROFILES = ("scan", "ai line art")

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


def preview_svg(polylines: list[list[tuple[float, float]]], *, width_mm: float, height_mm: float) -> str:
    """What the operator sees. With travel lines off this is the printed geometry exactly,
    so the preview doubles as a proof of what lands on paper."""
    render = travel_preview_svg if STATE["show_travel"] else polylines_to_svg
    return render(polylines, width_mm=width_mm, height_mm=height_mm)


def _mode_params(mode: str, detail: float, quality: str = "balanced", source: str = "scan") -> dict[str, Any]:
    """Mode keywords for a quality preset. `detail` is the operator's fine adjustment on top.

    `source` is what the picture came from; only trace reads it, and only to swap in the
    _AI_LINE_ART_TRACE overrides.
    """
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
        # Only simplification is a per-image choice of the fader. Stitching stays at its
        # swept value — more of it is free. Despeckling and weight passes are not knobs
        # either, but they DO depend on where the picture came from, so the source profile
        # overrides them; see _AI_LINE_ART_TRACE for what that costs and buys.
        return {
            "simplify_px": _SIMPLIFY_PX[step] / scale,
            "max_skeleton_px": _MAX_SKELETON_PX[step],
            **(AI_LINE_ART_TRACE if source == "ai line art" else {}),
            # shade_spacing_mm is deliberately NOT set here. Hatching the uninked mid-tones
            # looked worthwhile until weight passes existed; measured against all nine
            # folders afterwards it is negative or neutral on every one (worst: boats02,
            # F 0.949 -> 0.883), because filling bold strokes already covers what the
            # shading was aimed at. trace() still accepts it for flat-colour sources.
        }
    return {}


def build(ctx: GuiContext) -> None:
    # Before a single widget is created: every control below reads its initial value from
    # these dicts, so the restore has to land first or the page renders last session's
    # defaults and then writes them back.
    seed_state_from_settings(ctx.settings)

    # The conversion card is built partway down this function, but the upload handler and
    # every knob above it already call refresh_preview(). Keeping the name and handing it a
    # handle once the card exists means none of those call sites has to know the difference.
    card_handle: dict[str, Any] = {}

    def refresh_preview() -> None:
        handle = card_handle.get("handle")
        if handle is not None:
            handle.refresh()

    # Same shape for the frame sheet: sheet_controls() builds the knobs and the capacity
    # label, render_sheet() builds the geometry, and render_card wires them together. The
    # capacity label and the card handle live here because refresh_sheet_capacity (below,
    # called by every knob) needs both before/after the card exists.
    sheet_info: Any = None
    sheet_card_handle: dict[str, Any] = {}

    with ui.column().classes("w-full gap-2"):
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

        def conversion_controls() -> None:
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
                if key == "quality":
                    # The only sticky knob whose widget value is not the stored value: the
                    # fader holds a preset index, not "fine". Mirrored here rather than
                    # registered in ctx.fields, because pull_settings_from_fields would
                    # otherwise persist the string "3".
                    ctx.settings.image_quality = str(value)
                refresh_preview()

            def _quality_text() -> str:
                step = quality_index(str(STATE["quality"]))
                return (
                    f"Quality: {QUALITY_PRESETS[step].upper()} — about {_TYPICAL_MINUTES[step]} min "
                    f"for a 150 mm drawing. Slower presets trace finer and allow more segments."
                )

            with ui.row().classes("gap-2 w-full items-center"):
                # Registered under their GuiSettings names so pull_settings_from_fields sees
                # them; without that a control is silently inert however well it renders.
                ctx.fields["image_mode"] = (
                    ui.select(
                        sorted(MODES),
                        value=STATE["mode"],
                        label="Mode",
                        on_change=lambda e: set_field("mode", e.value),
                    )
                    .props("dense outlined")
                    .classes("w-36")
                )
                ctx.fields["image_source"] = (
                    ui.select(
                        list(SOURCE_PROFILES),
                        value=STATE["source"],
                        label="Source",
                        on_change=lambda e: set_field("source", e.value),
                    )
                    .props("dense outlined")
                    .classes("w-32")
                    .tooltip(
                        "Trace only. 'ai line art' drops the weight passes and despeckles, which "
                        "plots a diffusion render ~6x faster at one nib width throughout."
                    )
                )
                ctx.fields["image_width_mm"] = (
                    ui.number(
                        "Width mm",
                        value=STATE["width_mm"],
                        min=5,
                        step=5,
                        on_change=lambda e: set_field("width_mm", float(e.value or 150.0)),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                )
                ctx.fields["image_height_mm"] = (
                    ui.number(
                        "Height mm",
                        value=STATE["height_mm"],
                        min=5,
                        step=5,
                        on_change=lambda e: set_field("height_mm", float(e.value or 150.0)),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                )

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
                                or quality_cell_mm(str(STATE["mode"]), str(STATE["quality"]), ctx.settings.pen_width_mm)
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
                ctx.fields["image_cell_mm"] = cell_field
                ctx.fields["image_detail"] = (
                    ui.number(
                        "Detail",
                        value=STATE["detail"],
                        min=0.2,
                        step=0.2,
                        on_change=lambda e: set_field("detail", float(e.value or 1.0)),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                    .tooltip("Hatch: line spacing mm. Contour: band count. Ignored by halftone/dither.")
                )
                ctx.fields["image_gamma"] = (
                    ui.number(
                        "Gamma",
                        value=STATE["gamma"],
                        min=0.2,
                        max=4.0,
                        step=0.1,
                        on_change=lambda e: set_field("gamma", float(e.value or 1.0)),
                    )
                    .props("dense outlined")
                    .classes("w-24")
                    .tooltip("Above 1 lightens midtones, below 1 darkens them.")
                )
                ctx.fields["image_invert"] = ui.switch(
                    "Invert",
                    value=STATE["invert"],
                    on_change=lambda e: set_field("invert", bool(e.value)),
                )

            quality_label.set_text(_quality_text())

        def render_conversion() -> oracle.Render:
            if not STATE["bytes"]:
                raise ValueError("Upload an image to see the preview.")
            # Typed dict[str, Any], not inferred: a bare {"pen_width_mm": float} splat narrows to
            # dict[str, float], which mypy then reads as able to collide with image_to_polylines'
            # levels: int | None and autocontrast: bool.
            pen_param: dict[str, Any] = (
                {"pen_width_mm": ctx.settings.pen_width_mm} if STATE["mode"] in _PEN_AWARE_MODES else {}
            )
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
                **pen_param,
                **_mode_params(str(STATE["mode"]), float(STATE["detail"]), str(STATE["quality"]), str(STATE["source"])),
            )
            stem = str(STATE["name"] or "image").rsplit(".", 1)[0]
            return oracle.Render(
                polylines=polylines,
                width_mm=float(STATE["width_mm"]),
                height_mm=float(STATE["height_mm"]),
                name=f"{stem}_{STATE['mode']}",
            )

        conversion = oracle.render_card(
            ctx,
            title="Conversion",
            controls=conversion_controls,
            render=render_conversion,
            button_label="PRINT IMAGE",
            travel_default=bool(STATE["show_travel"]),
            # tests/test_gui_workspaces.py reads the printable bytes back off STATE, and so does
            # anything else that already knows this module by its state dict.
            on_render=lambda svg: STATE.__setitem__("svg", svg),
        )
        card_handle["handle"] = conversion
        # render_card owns the "Travel lines" switch, so register the one it built rather than
        # a second switch of our own. Without this the setting could be restored on load but
        # never recorded when the operator changed it.
        ctx.fields["image_show_travel"] = conversion.travel

        def set_sheet(key: str, value: Any) -> None:
            SHEET_STATE[key] = value
            refresh_sheet_capacity()

        def sheet_controls() -> None:
            nonlocal sheet_info

            ui.input(
                "Image folder",
                value=SHEET_STATE["folder"],
                placeholder="/Users/you/Documents/ComfyUI/output/boats01",
                on_change=lambda e: set_sheet("folder", str(e.value or "")),
            ).props("dense outlined clearable").classes("w-full")

            with ui.row().classes("gap-2 w-full items-center"):
                ctx.fields["sheet_cell_width_mm"] = (
                    ui.number(
                        "Cell width mm",
                        value=SHEET_STATE["cell_w"],
                        min=5,
                        step=5,
                        on_change=lambda e: set_sheet("cell_w", float(e.value or 40.0)),
                    )
                    .props("dense outlined")
                    .classes("w-32")
                )
                ctx.fields["sheet_cell_height_mm"] = (
                    ui.number(
                        "Cell height mm",
                        value=SHEET_STATE["cell_h"],
                        min=5,
                        step=5,
                        on_change=lambda e: set_sheet("cell_h", float(e.value or 60.0)),
                    )
                    .props("dense outlined")
                    .classes("w-32")
                )
                ctx.fields["sheet_gap_mm"] = (
                    ui.number(
                        "Gap mm",
                        value=SHEET_STATE["gap"],
                        min=0,
                        step=1,
                        on_change=lambda e: set_sheet("gap", float(e.value or 0.0)),
                    )
                    .props("dense outlined")
                    .classes("w-24")
                    .tooltip("0 = cells butt together. Above 0 = alley to cut in.")
                )
                ctx.fields["sheet_padding_mm"] = (
                    ui.number(
                        "Padding mm",
                        value=SHEET_STATE["padding"],
                        min=0,
                        step=0.5,
                        on_change=lambda e: set_sheet("padding", float(e.value or 0.0)),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                    .tooltip("Blank border between the cut line and the art.")
                )

            with ui.row().classes("gap-2 w-full items-center"):
                ctx.fields["sheet_shape"] = (
                    ui.select(
                        list(SHAPES),
                        value=SHEET_STATE["shape"],
                        label="Cut line",
                        on_change=lambda e: set_sheet("shape", str(e.value)),
                    )
                    .props("dense outlined")
                    .classes("w-32")
                )
                ui.number(
                    "Sheet #",
                    value=SHEET_STATE["sheet_index"],
                    min=0,
                    step=1,
                    on_change=lambda e: set_sheet("sheet_index", int(e.value or 0)),
                ).props("dense outlined").classes("w-24").tooltip("0 = first sheet of the folder, 1 = next, ...")

            sheet_info = ui.label("-").classes("text-xs text-[#8f4f2b]")

        def render_sheet() -> oracle.Render:
            capacity = _sheet_capacity()
            files = _sheet_files()
            if capacity <= 0 or not files:
                raise ValueError("Set a folder and a cell size that fits the sheet first")
            start = int(SHEET_STATE["sheet_index"]) * capacity
            batch = files[start : start + capacity]
            if not batch:
                raise ValueError(f"Sheet {SHEET_STATE['sheet_index']} is past the end of the folder")
            polylines, _placed = images_to_sheet_polylines(
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
                **_mode_params(str(STATE["mode"]), float(STATE["detail"]), str(STATE["quality"]), str(STATE["source"])),
            )
            stem = Path(SHEET_STATE["folder"]).name or "sheet"
            return oracle.Render(
                polylines=polylines,
                width_mm=ctx.settings.sheet_width_mm,
                height_mm=ctx.settings.sheet_height_mm,
                name=f"{stem}_sheet{int(SHEET_STATE['sheet_index'])}",
            )

        sheet_card_handle["handle"] = oracle.render_card(
            ctx,
            title="Frame sheet",
            helper=(
                "Fill one sheet from a folder, using the mode and tone settings above. "
                "Set the cell to your wooden frame's aperture; gap 0 butts the cells so one cut serves two prints."
            ),
            controls=sheet_controls,
            render=render_sheet,
            button_label="PRINT SHEET",
            # tests/test_gui_workspaces.py and anything else that knows this module by its
            # state dicts read the printable sheet back off SHEET_STATE.
            on_render=lambda svg: SHEET_STATE.__setitem__("svg", svg),
        )

        _build_motif_import_card(ctx)

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
        # A knob change invalidates the built sheet, exactly as the old BUILD SHEET flow
        # did: PRINT SHEET must re-render with the current knobs, never send the geometry
        # of the previous ones.
        SHEET_STATE["svg"] = ""
        handle = sheet_card_handle.get("handle")
        if handle is not None:
            handle.svg = ""
            handle.preview.content = ""
            handle.preview.update()
        if sheet_info is None:
            return
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

    refresh_preview()
    refresh_sheet_capacity()


def motif_crop() -> CropBox:
    return CropBox(
        left=float(MOTIF_STATE["crop_left"]),
        top=float(MOTIF_STATE["crop_top"]),
        width=float(MOTIF_STATE["crop_width"]),
        height=float(MOTIF_STATE["crop_height"]),
    )


def build_motif_svg() -> tuple[str, int, int]:
    """Trace the current picture into a motif SVG. Returns (svg, strokes, points)."""
    polylines = image_to_motif_polylines(
        MOTIF_STATE["bytes"],
        mode=str(MOTIF_STATE["mode"]),
        crop=motif_crop(),
        cell_mm=float(MOTIF_STATE["cell_mm"]),
        gamma=float(MOTIF_STATE["gamma"]),
        invert=bool(MOTIF_STATE["invert"]),
        autocontrast=bool(MOTIF_STATE["autocontrast"]),
        despeckle_mm=float(MOTIF_STATE["despeckle_mm"]),
        simplify_mm=float(MOTIF_STATE["simplify_mm"]),
    )
    return motif_svg(polylines), len(polylines), sum(len(p) for p in polylines)


def _build_motif_import_card(ctx: GuiContext) -> None:
    """Picture -> cropped, traced, optimised motif -> assets/patterns/.

    Takes `ctx` only so its sticky knobs can register into ctx.fields; the crop box and the
    motif name stay per-picture and are deliberately not registered.
    """
    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Import motif from picture").classes("text-sm font-bold")
        helper_text(
            "Crop to ONE motif, then save it into the pattern bank. "
            "Contour at 1 band gives a single outline; more bands double every stroke. "
            "Autocontrast off is usually better for fabric photos — it lifts weave texture into ink."
        )
        selected_label = ui.label("No picture selected").classes("path-label text-xs")
        status_label = ui.label("-").classes("text-xs text-[#8f4f2b]")
        preview = ui.html().classes("preview-frame w-full")

        def refresh() -> None:
            # Cleared up front, never only inside the handler: whatever goes wrong
            # below, SAVE TO BANK must not be left holding the previous motif and
            # write it under the new name.
            MOTIF_STATE["svg"] = ""
            if not MOTIF_STATE["bytes"]:
                preview.content = ""
                preview.update()
                status_label.set_text("Upload a picture to begin")
                return
            try:
                svg, strokes, points = build_motif_svg()
            except Exception as exc:  # noqa: BLE001
                # Deliberately broad. Segment and skeleton caps raise ValueError and trip
                # routinely when the crop is too wide -- a normal outcome to report. But
                # PIL.DecompressionBombError subclasses neither ValueError nor OSError, so
                # a narrow catch lets an oversized upload escape every handler in the
                # chain and leaves a stale preview.
                preview.content = ""
                preview.update()
                status_label.set_text(str(exc))
                return
            MOTIF_STATE["svg"] = svg
            preview.content = svg
            preview.update()
            status_label.set_text(f"{strokes} strokes, {points} points")

        def set_motif(key: str, value: Any) -> None:
            MOTIF_STATE[key] = value
            refresh()

        async def handle_upload(event: Any) -> None:
            try:
                name, data = await read_upload_event_payload(event)
            except Exception as exc:  # noqa: BLE001
                ui.notify(f"Picture upload failed: {exc}", color="negative")
                return
            if not data:
                ui.notify("Picture upload failed: file is empty", color="negative")
                return
            MOTIF_STATE["name"] = name
            MOTIF_STATE["bytes"] = data
            selected_label.set_text(f"Selected: {name}")
            if not MOTIF_STATE["motif_name"]:
                MOTIF_STATE["motif_name"] = Path(name).stem
                name_input.value = MOTIF_STATE["motif_name"]
            refresh()

        # Unlabelled, a QUploader renders as a black progress strip rather than a picker.
        # Capped like the generative SVG route: the bytes land in a module global that is
        # never freed, and a phone photo past ~20MB buys no detail the 100mm motif keeps.
        ui.upload(label="Drop a photo here, or click + to choose", on_upload=handle_upload).props(
            "accept=.png,.jpg,.jpeg,.bmp,.webp,.gif max-files=1 auto-upload max-file-size=20971520"
        ).classes("w-full")

        # The knobs as one (controls, render)-shaped building block, same as the sheet and
        # conversion cards. The uploader and the name/save strip stay outside: the uploader
        # feeds the knobs, and the name belongs to the SAVE action, not the trace.
        def motif_controls() -> None:
            with ui.row().classes("gap-2 w-full items-center"):
                for key, label in (
                    ("crop_left", "Crop L %"),
                    ("crop_top", "Crop T %"),
                    ("crop_width", "Crop W %"),
                    ("crop_height", "Crop H %"),
                ):
                    ui.number(
                        label,
                        value=MOTIF_STATE[key],
                        min=0,
                        max=100,
                        step=1,
                        on_change=lambda e, k=key: set_motif(k, float(e.value or 0.0)),
                    ).props("dense outlined").classes("w-28")

            with ui.row().classes("gap-2 w-full items-center"):
                ctx.fields["motif_mode"] = (
                    ui.select(
                        sorted(MODES),
                        value=MOTIF_STATE["mode"],
                        label="Mode",
                        on_change=lambda e: set_motif("mode", str(e.value)),
                    )
                    .props("dense outlined")
                    .classes("w-40")
                )
                ctx.fields["motif_cell_mm"] = (
                    ui.number(
                        "Cell mm",
                        value=MOTIF_STATE["cell_mm"],
                        min=0.1,
                        step=0.1,
                        on_change=lambda e: set_motif("cell_mm", float(e.value or 0.8)),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                    .tooltip("Sampling pitch. Smaller = more detail and more points.")
                )
                ctx.fields["motif_gamma"] = (
                    ui.number(
                        "Gamma",
                        value=MOTIF_STATE["gamma"],
                        min=0.1,
                        step=0.1,
                        on_change=lambda e: set_motif("gamma", float(e.value or 1.0)),
                    )
                    .props("dense outlined")
                    .classes("w-28")
                    .tooltip("Above 1 pushes midtones to white and drops texture.")
                )

            with ui.row().classes("gap-2 w-full items-center"):
                ctx.fields["motif_despeckle_mm"] = (
                    ui.number(
                        "Despeckle mm",
                        value=MOTIF_STATE["despeckle_mm"],
                        min=0,
                        step=0.5,
                        on_change=lambda e: set_motif("despeckle_mm", float(e.value or 0.0)),
                    )
                    .props("dense outlined")
                    .classes("w-32")
                    .tooltip("Drops strokes whose bounding box is smaller than this.")
                )
                ctx.fields["motif_simplify_mm"] = (
                    ui.number(
                        "Simplify mm",
                        value=MOTIF_STATE["simplify_mm"],
                        min=0,
                        step=0.1,
                        on_change=lambda e: set_motif("simplify_mm", float(e.value or 0.0)),
                    )
                    .props("dense outlined")
                    .classes("w-32")
                    .tooltip("Douglas-Peucker tolerance on a 100 mm motif.")
                )
                ctx.fields["motif_autocontrast"] = ui.switch(
                    "Autocontrast",
                    value=MOTIF_STATE["autocontrast"],
                    on_change=lambda e: set_motif("autocontrast", bool(e.value)),
                ).tooltip("Off for fabric photos: on, it stretches weave texture into ink.")
                ctx.fields["motif_invert"] = ui.switch(
                    "Invert",
                    value=MOTIF_STATE["invert"],
                    on_change=lambda e: set_motif("invert", bool(e.value)),
                ).tooltip("For light motifs on a dark garment.")

        motif_controls()

        with ui.row().classes("gap-2 w-full items-center"):
            name_input = (
                ui.input(
                    "Motif name",
                    value=MOTIF_STATE["motif_name"],
                    on_change=lambda e: MOTIF_STATE.update(motif_name=str(e.value or "")),
                )
                .props("dense outlined")
                .classes("w-56")
            )

            def save_motif() -> None:
                if not MOTIF_STATE["svg"]:
                    refresh()
                if not MOTIF_STATE["svg"]:
                    ui.notify("Nothing to save — check the preview first", color="warning")
                    return
                try:
                    target = bank.save_motif(str(MOTIF_STATE["motif_name"] or "motif"), str(MOTIF_STATE["svg"]))
                except (ValueError, OSError) as exc:
                    ui.notify(f"Save failed: {exc}", color="negative")
                    return
                # The sketch fetches the bank once in setup(), so without this nudge the
                # motif just saved stays invisible until the iframe is reloaded. Same
                # channel the stream toggle uses (workspaces/generative.py).
                ui.run_javascript(
                    "document.getElementById('generative-frame')?.contentWindow?.postMessage({type: 'bank'}, '*');"
                )
                ui.notify(f"Saved {target.name} to the pattern bank", color="positive")

            primary_action_button("SAVE TO BANK", lambda: save_motif())
            safe_action_button("REFRESH", lambda: refresh())

        refresh()
