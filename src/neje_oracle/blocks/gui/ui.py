"""Shared components for the operator GUI.

Every helper here emits a **semantic class name** (`oracle-card`, `oracle-helper`) that
PAGE_STYLE styles once from tokens.py. Workspaces compose components; they do not style.
That is what the ratchets in tests/test_gui_design_system.py enforce -- before this file
grew, 226 `.classes()` literals and 77 hex values were spread across the view code, with
23 near-identical copies of the same card block.

Components exist here because a count justified them, not because they seemed tidy:
card 28, section title 30, dense-outlined controls 34, action rows 25.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from ..imaging.modes import Polylines, polylines_to_svg, travel_length_mm, travel_preview_svg
from .support import plot_minutes_for

# --- actions --------------------------------------------------------------------
# Three intents, three styles. The prior audit raised DS-BTN-1 (5 differently styled
# primary actions) and DS-COL-1 (gold meaning both STOP and HOME ALL).


def primary_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    """The one action that advances the task on this card."""
    return ui.button(label, on_click=on_click).props("dense unelevated").classes("oracle-btn oracle-btn-primary")


def safe_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    """Reversible: generate, refresh, preview."""
    return ui.button(label, on_click=on_click).props("dense flat").classes("oracle-btn oracle-btn-safe")


def danger_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    """Stops something, loses something, or moves the machine unexpectedly."""
    return ui.button(label, on_click=on_click).props("dense unelevated").classes("oracle-btn oracle-btn-danger")


# --- structure ------------------------------------------------------------------


@contextmanager
def card(title: str | None = None, helper: str | None = None) -> Any:
    """The workspace building block: a panel with an optional title and helper line.

    Replaces 23 hand-written copies of card + bold label + helper_text.
    """
    with ui.card().classes("oracle-card") as element:
        if title:
            section_title(title)
        if helper:
            helper_text(helper)
        yield element


def section_title(text: str) -> Any:
    return ui.label(text).classes("oracle-card-title")


def helper_text(text: str) -> Any:
    """Explanatory line under a title. Was 31 helper calls plus 13 hand-inlined copies."""
    return ui.label(text).classes("oracle-helper")


@contextmanager
def toolbar(full_width: bool = False) -> Any:
    """A row of actions or controls. Covers the `items-center gap-2` row, 25 of them."""
    classes = "oracle-toolbar" + (" oracle-toolbar-wide" if full_width else "")
    with ui.row().classes(classes) as element:
        yield element


@contextmanager
def workspace() -> Any:
    """The scrolling column every workspace opens with -- 7 copy-pasted wrappers."""
    with ui.column().classes("oracle-workspace") as element:
        yield element


def mini_metric(label: str, *, extra_classes: str = "", style: str = "") -> Any:
    """div.mini-metric > label.label(label) > label.value("-"); returns the value handle."""
    classes = f"mini-metric {extra_classes}".strip()
    with ui.element("div").classes(classes) as element:
        if style:
            element.style(style)
        ui.label(label).classes("label")
        return ui.label("-").classes("value")


def embedded_page(src: str, *, element_id: str = "") -> Any:
    """An iframe onto one of the pages under the /generative static mount.

    Always fills its pane: the fixed-height form (900px, then min(px, 62vh)) put an editor
    with its own scrollbar inside a scrolling page -- the measured shape of the old CREATE
    screen. An editor is a canvas; the pane it sits in decides its size.
    """
    props = f'src="{src}"' + (f' id="{element_id}"' if element_id else "")
    return ui.element("iframe").props(props).classes("oracle-embed oracle-embed-fill")


def metric_line(text: str = "-") -> Any:
    """A one-line cost/extent readout under a preview. Returns the handle to set_text on."""
    return ui.label(text).classes("oracle-metric-line")


def preview_pane() -> Any:
    """The SVG preview box every render path drops its output into."""
    return ui.html().classes("preview-frame")


def warning_banner(text: str) -> Any:
    return ui.label(text).classes("warning-banner")


def log_viewer(lines: list[str]) -> Any:
    return ui.textarea(value="\n".join(lines)).props("readonly outlined autogrow").classes("w-full text-xs log-viewer")


# --- inputs ---------------------------------------------------------------------
# `dense outlined` appeared 34 times by hand. One place now decides how a field looks.

_FIELD_PROPS = "dense outlined"


def select(options: Any, *, value: Any = None, label: str = "", on_change: Callable[..., Any] | None = None) -> Any:
    control = ui.select(options, value=value, label=label).props(_FIELD_PROPS).classes("oracle-field")
    if on_change is not None:
        control.on_value_change(on_change)
    return control


def text_input(label: str, *, value: str = "", on_change: Callable[..., Any] | None = None) -> Any:
    control = ui.input(label, value=value).props(_FIELD_PROPS).classes("oracle-field")
    if on_change is not None:
        control.on_value_change(on_change)
    return control


def switch(label: str, *, value: bool = False, on_change: Callable[..., Any] | None = None) -> Any:
    control = ui.switch(label, value=value)
    if on_change is not None:
        control.on_value_change(on_change)
    return control


def number_control(
    fields: dict[str, Any],
    key: str,
    *,
    label: str,
    value: float,
    default: float,
    min_value: float,
    step: float = 1.0,
    width_class: str = "oracle-field",
    tooltip: str = "",
    on_change: Callable[[], Any],
) -> Any:
    control = ui.number(label, value=value, min=min_value, step=step).props(_FIELD_PROPS).classes(width_class)
    control.on_value_change(on_change)
    control.on("dblclick", lambda _: _reset_control(control, default, on_change))
    if tooltip:
        control.tooltip(tooltip)
    fields[key] = control
    return control


# --- lifecycle ------------------------------------------------------------------


def client_timer(interval: float, callback: Callable[[], Any], *, once: bool = False) -> Any:
    """A ui.timer that stops when its client disconnects.

    A bare per-client ui.timer keeps firing after its slot is torn down: one browser
    session left 24 "The parent slot of Timer(...) has been deleted" errors in the log.
    Binding to the client's disconnect makes that structurally impossible instead of
    relying on every caller remembering.
    """
    timer = ui.timer(interval, callback, once=once)
    # No client context (headless tests, auto-index page) means the timer is bound to the
    # app rather than a client, so there is no slot for it to outlive.
    with contextlib.suppress(Exception):
        # Swallow the argument nicegui hands disconnect handlers: Timer.cancel() takes
        # none, so passing it directly raised on every disconnect and the timer was never
        # actually cancelled. This helper had no callers until now, so nothing caught it.
        ui.context.client.on_disconnect(lambda *_: timer.cancel())
    return timer


# --- render + print --------------------------------------------------------------
# Three workspaces each carried their own copy of: render -> polylines_to_svg -> travel
# preview -> travel_length_mm -> plot_minutes -> format a cost string. Same fifty lines, three
# slightly different cost sentences, and one of them reached into a sibling workspace to
# borrow the estimator. It lives here because ui.py is a design-system STYLE_OWNER: every
# .classes() and ui.card() absorbed from a workspace is deleted from the ratchet counts rather
# than moved around behind them.


@dataclass(frozen=True)
class Render:
    """What a source hands the print pipeline. The only currency it accepts."""

    polylines: Polylines
    width_mm: float
    height_mm: float
    name: str


class RenderCard:
    """Handle onto a rendered card: the printable SVG, a refresh, and the print itself."""

    def __init__(self) -> None:
        self.svg = ""
        # The preview element is exposed so a test can prove the screen-only travel overlay
        # never leaks into `svg`. That leak would put pen-up hairlines on the paper.
        self.preview: Any = None
        # And the travel switch, so a workspace can persist the operator's choice. Without
        # this the helper could restore the setting but never observe a change to it.
        self.travel: Any = None
        self._refresh: Callable[[], None] = lambda: None
        self._print: Callable[[], Any] = lambda: None

    def refresh(self) -> None:
        self._refresh()

    async def print(self) -> Any:
        return await self._print()


def cost_line(polylines: Polylines, *, draw_mm: float, travel_mm: float, minutes: tuple[float, float]) -> str:
    """The operator's time estimate, worded once.

    The pen-lift term is only mentioned when it is big enough to matter -- on a servo pen it
    routinely dominates, and a 488-stroke halftone that reads as "1.7 min" is how a plot gets
    started that will still be running an hour later.
    """
    xy_minutes, pen_minutes = minutes
    segments = sum(max(0, len(polyline) - 1) for polyline in polylines)
    pen_note = f" + {pen_minutes:.0f} min pen lifts" if pen_minutes >= 0.5 else ""
    return (
        f"{len(polylines)} strokes, {segments} segments, "
        f"{draw_mm / 1000:.1f} m drawn + {travel_mm / 1000:.1f} m travel, "
        f"~{xy_minutes + pen_minutes:.0f} min at current feeds "
        f"({xy_minutes:.0f} min moving{pen_note})"
    )


def render_card(
    ctx: Any,
    *,
    title: str,
    render: Callable[[], Render],
    helper: str = "",
    controls: Callable[[], None] | None = None,
    button_label: str = "PRINT",
    travel_default: bool = True,
    cost_suffix: Callable[[Render], str] | None = None,
    on_render: Callable[[str], None] | None = None,
    preview_slot: Any = None,
    actions: bool = True,
) -> RenderCard:
    """A source, its knobs, an honest preview, a time estimate, and one print button.

    `render` raises ValueError to say something the operator should read -- a cap breached, no
    image chosen -- and it lands in the cost line rather than as a traceback. Every existing
    copy already treated a cap breach as a normal outcome; this keeps that.

    `on_render` receives the printable bytes (and "" on failure) so a caller can mirror them
    into state it already exposes, rather than every caller being rewritten to hold a handle.

    With travel lines off the preview *is* the bytes that will be sent, which is the property
    that makes it a proof rather than an illustration. travel_preview_svg draws pen-up moves
    as real <line> elements, and svg_gcode would gladly draw every one of them.

    `preview_slot` moves the preview out of the card and into that container -- the CREATE
    screen's canvas column -- so a source's knobs and its picture can live in different grid
    tracks while staying one refresh.
    """
    handle = RenderCard()

    if preview_slot is not None:
        with preview_slot:
            preview = preview_pane().classes("preview-fill")

    with card(title, helper or None):
        if controls is not None:
            controls()
        travel = switch("Travel lines", value=travel_default)
        cost = metric_line()
        if preview_slot is None:
            preview = preview_pane()

        def refresh() -> None:
            try:
                result = render()
            except (ValueError, OSError) as exc:
                handle.svg = ""
                if on_render is not None:
                    on_render("")
                preview.content = ""
                preview.update()
                cost.set_text(str(exc))
                return
            handle.svg = polylines_to_svg(
                result.polylines,
                width_mm=result.width_mm,
                height_mm=result.height_mm,
                pen_width_mm=ctx.settings.pen_width_mm,
            )
            # Lets a workspace keep mirroring the printable bytes into its own state, which
            # is what existing callers and their tests already read.
            if on_render is not None:
                on_render(handle.svg)
            preview.content = (
                travel_preview_svg(result.polylines, width_mm=result.width_mm, height_mm=result.height_mm)
                if travel.value
                else handle.svg
            )
            preview.update()
            draw_mm, travel_mm = travel_length_mm(result.polylines)
            minutes = plot_minutes_for(
                ctx.settings,
                strokes=len(result.polylines),
                draw_mm=draw_mm,
                travel_mm=travel_mm,
                use_z_servo=ctx.supervisor.plotter_settings.use_z_servo,
            )
            text = cost_line(result.polylines, draw_mm=draw_mm, travel_mm=travel_mm, minutes=minutes)
            cost.set_text(text + (cost_suffix(result) if cost_suffix else ""))

        async def do_print() -> Any:
            if not handle.svg:
                refresh()
            if not handle.svg:
                ui.notify("Nothing to print yet.", color="warning")
                return False
            return await ctx.print_svg_payload(handle.svg.encode("utf-8"), f"{render().name}.svg")

        travel.on_value_change(lambda _: refresh())
        # actions=False is the CREATE screen: one shared print strip dispatches on the
        # active source through the handle, so the card carries no buttons of its own.
        if actions:
            with toolbar():
                safe_action_button("REFRESH PREVIEW", refresh)
                primary_action_button(button_label, do_print)

    handle.preview = preview
    handle.travel = travel
    handle._refresh = refresh
    handle._print = do_print
    return handle


def notify_if_connected(message: str, **kwargs: Any) -> None:
    """ui.notify that gives up quietly once its client has gone.

    An async handler started from a page-load timer routinely outlives the browser tab --
    a probe that takes seconds, a tab closed mid-check. Notifying a torn-down slot raises,
    and the traceback reads exactly like a real fault in the log an unattended run is
    judged by. The message has nobody to reach at that point; the log entry is pure noise.
    """
    with contextlib.suppress(Exception):
        ui.notify(message, **kwargs)


def _reset_control(control: Any, default: float, on_change: Callable[[], Any]) -> None:
    control.value = default
    control.update()
    on_change()
