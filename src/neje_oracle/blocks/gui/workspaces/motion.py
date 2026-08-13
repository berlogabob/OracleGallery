"""The persistent machine rail: what the operator can always reach.

Jog, homing, pen and work zero do not belong to a workspace. Bringing the machine up is
one continuous job -- connect, home, set zero, mark, run -- and it used to be spread across
four tabs. These controls live in a rail visible from every screen (LightBurn's docked
laser window, Mainsail's locked status panel, FluidNC's own ESP3D-WebUI all do the same;
ISA-101 states the rule: displays organised by task, "not on P&IDs").

One home per action. SET WORK ZERO lives at the end of the jog flow -- it is literally the
last step of jogging to the paper origin -- and START PRINT lives on the next-action button.
The rail used to render SET WORK ZERO twice (its own card plus the next-action button
whenever zero was unset), which meant the single most consequential rail control appeared
as a pair of identical buttons two cards apart.
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import (
    danger_action_button,
    helper_text,
    primary_action_button,
    safe_action_button,
    section_title,
)


def render_machine_rail(ctx: GuiContext) -> None:
    """Machine control that never changes with navigation."""
    with ui.column().classes("machine-rail"):
        _next_action(ctx)
        _jog_and_zero(ctx)


def _next_action(ctx: GuiContext) -> None:
    """The readiness state machine as a control.

    The button renders only when the next action's home is *this button* -- starting a
    print. When the next step is setting work zero, the hint points at the SET WORK ZERO
    control below instead of growing an identical twin of it; two buttons for one
    irreversible machine action is how the wrong one gets pressed.
    """

    async def run() -> None:
        if ctx.next_action_key == "start_print":
            await ctx.start_print()

    with ui.card().classes("oracle-card compact-card w-full"):
        section_title("Next action")
        ctx.next_action_button = primary_action_button("—", run).classes("w-full")
        ctx.next_action_hint = helper_text("—")
        ctx.blockers_label = ui.label("blockers: —").classes("oracle-helper")


def _jog_and_zero(ctx: GuiContext) -> None:
    with ui.card().classes("oracle-card compact-card w-full"):
        section_title("Manual motion")
        helper_text("Blocked while G-code streams.")
        with ui.row().classes("gap-2 items-end"):
            ctx.fields["jog_step"] = (
                ui.select(
                    {1.0: "1", 5.0: "5", 10.0: "10", 25.0: "25", 50.0: "50", 100.0: "100"},
                    value=1.0,
                    label="Step mm",
                )
                .props("dense outlined")
                .classes("w-24")
            )
            ctx.fields["jog_feed"] = (
                ui.number("Feed", value=1000, min=1, step=100).props("dense outlined").classes("w-24")
            )
        # A real cross. The middle cell used to hold Y-, which put the two Y buttons on the
        # same row as X- and X+ and left the pad reading as four scattered buttons.
        with ui.grid(columns=3).classes("jog-pad"):
            ui.label("")
            safe_action_button("Y+", ctx.jog_y_positive)
            ui.label("")
            safe_action_button("X-", ctx.jog_x_negative)
            ui.label("")
            safe_action_button("X+", ctx.jog_x_positive)
            ui.label("")
            safe_action_button("Y-", ctx.jog_y_negative)
            ui.label("")
        with ui.row().classes("gap-1 flex-wrap"):
            # These four were bare text with no button chrome at all, sitting under filled
            # buttons that ran the same class of machine command (audit F-007, F-023).
            safe_action_button("PEN UP", ctx.pen_up)
            safe_action_button("PEN DOWN", ctx.pen_down)
            safe_action_button("HOME X", lambda: ctx.home_axis("X"))
            safe_action_button("HOME Y", lambda: ctx.home_axis("Y"))
        # Homing is routine setup, not a caution action; it used to carry the same gold as
        # STOP SYSTEM, so one colour meant both "do this next" and "halt" (audit F-022/F-026).
        safe_action_button("HOME ALL", ctx.home_xy).classes("w-full")
        # Zeroing concludes the jog flow: fix paper, jog to the upper-left origin, lower Z
        # to pen contact, then confirm. It moves the machine's idea of where the sheet is,
        # hence the danger treatment.
        danger_action_button("SET WORK ZERO", ctx.set_work_zero).classes("w-full").tooltip(
            "Fix paper, jog to the upper-left origin, lower Z and set pen contact, then confirm."
        )
        ctx.ready_labels["message"] = ui.label("-").classes("oracle-helper path-label")
