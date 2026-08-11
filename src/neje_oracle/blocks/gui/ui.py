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
from typing import Any

from nicegui import ui

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
        ui.context.client.on_disconnect(timer.cancel)
    return timer


def _reset_control(control: Any, default: float, on_change: Callable[[], Any]) -> None:
    control.value = default
    control.update()
    on_change()
