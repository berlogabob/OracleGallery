from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from .models import ComponentState, ComponentStatus


STATUS_COLORS = {
    ComponentStatus.RUNNING: "#2f7d46",
    ComponentStatus.STARTING: "#9a5b24",
    ComponentStatus.WARNING: "#b7791f",
    ComponentStatus.ERROR: "#a43c2f",
    ComponentStatus.OFFLINE: "#7a6f66",
    ComponentStatus.STOPPED: "#7a6f66",
}


def status_pill(label: str) -> Any:
    return ui.label(f"{label}: -").classes("status-pill")


def update_status_pill(label: Any, state: ComponentState | None, display_name: str) -> None:
    if state is None:
        label.set_text(f"{display_name}: -")
        label.style("border-color:#dac9ad;color:#7a6f66")
        return
    color = STATUS_COLORS.get(state.status, "#7a6f66")
    label.set_text(f"{display_name}: {state.status.value}")
    label.style(f"border-color:{color};color:{color}")


def primary_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    return ui.button(label, on_click=on_click).props("dense color=positive")


def danger_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    return ui.button(label, on_click=on_click).props("dense color=warning")


def safe_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    return ui.button(label, on_click=on_click).props("dense flat")


def warning_banner(text: str) -> Any:
    return ui.label(text).classes("warning-banner")


def number_control(
    fields: dict[str, Any],
    key: str,
    *,
    label: str,
    value: float,
    default: float,
    min_value: float,
    step: float = 1.0,
    width_class: str = "w-28",
    tooltip: str = "",
    on_change: Callable[[], Any],
) -> Any:
    control = ui.number(label, value=value, min=min_value, step=step).props("dense outlined").classes(width_class)
    control.on_value_change(on_change)
    control.on("dblclick", lambda _: _reset_control(control, default, on_change))
    if tooltip:
        control.tooltip(tooltip)
    fields[key] = control
    return control


def log_viewer(lines: list[str]) -> Any:
    return ui.textarea(value="\n".join(lines)).props("readonly outlined autogrow").classes("w-full text-xs log-viewer")


def _reset_control(control: Any, default: float, on_change: Callable[[], Any]) -> None:
    control.value = default
    control.update()
    on_change()
