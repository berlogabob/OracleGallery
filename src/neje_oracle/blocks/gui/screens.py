"""The three screens, named after what the operator is doing.

The tabs used to be CONNECTION, CALIBRATION, TESTS, WORK, EXHIBITION, GENERATIVE, IMAGE --
the module list, which is to say this machine's P&ID. ISA-101 puts it plainly: displays are
organised by task analysis, "not on P&IDs". None of those seven names is a thing an operator
does; "work" in particular predicted nothing at all.

Three remain, and each is a phase of the job:

    PRINT   the run. What you watch while the machine draws, and where you start it.
    CREATE  authoring what gets drawn -- sketch, texture, image, text.
    SETUP   getting the machine right. Used before a run, rarely during one.

Connecting, homing and zeroing are on none of them: they live in the machine rail, reachable
from every screen, because bringing the machine up is one continuous job and used to be a
scavenger hunt across four tabs.

This module composes the existing workspace builders rather than reimplementing them, so the
move can be reviewed for equivalence: every ctx.fields and ctx.*_labels key each workspace
registered before, it still registers. The workspaces contribute plain columns now and the
screen owns the one scrolling container, so stacking three of them does not create three
independent scroll areas.
"""

from __future__ import annotations

from nicegui import ui

from ...shared.origin_markers import ALL_ORIGINS, ORIGIN_LABELS, ORIGIN_MARKER_POSITIONS, ORIGIN_PREVIEW_COLORS
from . import tokens
from .context import GuiContext
from .ui import danger_action_button, helper_text, mini_metric, primary_action_button, safe_action_button, section_title
from .workspaces import calibration, connection, generative, image, tests, work


def _legend_dialog() -> ui.dialog:
    """The ring/marker legend, summoned rather than permanent.

    Two rows of legend chips used to sit above the preview on every screen, spending ~45px
    on decoding knowledge an operator internalises in a day. A ? next to the sheet keeps it
    one click away without charging every glance for it.
    """
    with ui.dialog() as dialog, ui.card().classes("oracle-card"):
        section_title("Reading the sheet")
        with ui.row().classes("items-center gap-3 flex-wrap"):
            with ui.element("div").classes("legend-chip"):
                ui.element("span").classes("legend-ring")
                ui.label("outer ring: real/user cell").classes("text-[10px]")
            with ui.element("div").classes("legend-chip"):
                ui.element("span").classes("legend-ring legend-double-ring")
                ui.label("double ring: filler/local cell").classes("text-[10px]")
            with ui.element("div").classes("legend-chip"):
                ui.element("span").classes("legend-dot").style(
                    "background:var(--ink-muted); border-color:var(--ink-muted); opacity:0.45;"
                )
                ui.label("gray: next in line").classes("text-[10px]")
        with ui.row().classes("items-center gap-3 flex-wrap"):
            for origin in ALL_ORIGINS:
                position = ORIGIN_MARKER_POSITIONS.get(origin, "right").replace("-", " ")
                color = ORIGIN_PREVIEW_COLORS.get(origin, tokens.INK_MUTED)
                with ui.element("div").classes("legend-chip"):
                    ui.element("span").classes("legend-dot").style(f"background:{color}; border-color:{color};")
                    ui.label(f"{ORIGIN_LABELS[origin]} dot: {position}").classes("text-[10px]")
    return dialog


def build_print(ctx: GuiContext) -> None:
    """The run. Canvas = the sheet, full size; a narrow band holds the run controls.

    This absorbs what used to be the Exhibition card, the System run card, the System check
    card and the Queue card -- four cards whose combined job is "start the run and tell me
    how it is going". The sheet preview moves here from the old always-visible right column:
    the sheet is what you watch while the machine draws, and PRINT is where you watch it.
    """
    with ui.grid(columns="minmax(0, 1fr) 280px").classes("w-full h-full gap-2 min-h-0"):
        # -- canvas: the sheet ----------------------------------------------------------
        with ui.column().classes("print-canvas min-h-0 h-full gap-1"):
            legend = _legend_dialog()
            with ui.row().classes("w-full items-center gap-2"):
                ctx.preview_progress_label = helper_text("-")
                ui.element("div").classes("status-spacer")
                safe_action_button("?", legend.open)
            ctx.preview = ui.html().classes("preview-frame w-full")
            # The live readouts sit under the sheet they describe, one line each.
            with ui.row().classes("w-full items-center gap-3"):
                ctx.plotter_labels["sheet"] = ui.label("no sheet yet").classes("path-label text-xs font-bold")
                ctx.plotter_labels["cells"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            ctx.progress = ui.linear_progress(value=0).classes("w-full")
            ctx.plotter_labels["message"] = ui.label("-").classes("path-label text-xs")

        # -- run band: start/stop the run, and the queue detail the bar does not show ----
        with ui.column().classes("run-band min-h-0 h-full gap-2"):
            section_title("System run")
            helper_text("Start services and reset the run baseline; stop safely between sheets.")
            primary_action_button("START SYSTEM", ctx.start_system).classes("w-full")
            safe_action_button("NEW RUN", ctx.reset_baseline).classes("w-full")
            danger_action_button("STOP SYSTEM", ctx.stop_system).classes("w-full")
            ui.separator()
            ctx.system_check_label = ui.label("System check runs automatically when print starts.").classes(
                "text-xs text-[#8f4f2b]"
            )
            ui.separator()
            section_title("Queue")
            with ui.grid(columns=3).classes("w-full gap-1"):
                for key, label in (("pending", "Pending"), ("active", "Active"), ("failed", "Fail/Skip")):
                    ctx.queue_labels[key] = mini_metric(label)
            # The bar owns online/offline; the key stays registered for the writer.
            hidden_state = ui.label("")
            hidden_state.set_visibility(False)
            ctx.queue_labels["state"] = hidden_state
            ctx.queue_labels["message"] = ui.label("-").classes("path-label text-[10px]")


def build_create(ctx: GuiContext) -> None:
    """Authoring a source. Every one of these ends at the same print pipeline."""
    with ui.column().classes("workspace-scroll gap-2"):
        generative.build(ctx)
        image.build(ctx)


def build_setup(ctx: GuiContext) -> None:
    """Getting the machine right, with the rarely-touched parts folded away.

    Diagnostics and commissioning are collapsed rather than deleted: they are needed on site
    and occasionally urgent, but they are not what an operator opens this screen for.
    """
    with ui.column().classes("workspace-scroll gap-2"):
        connection.build(ctx)
        calibration.build(ctx)
        tests.build(ctx)
        with ui.expansion("Diagnostics", icon="build").classes("w-full oracle-card compact-card"):
            work.build_diagnostics(ctx)
