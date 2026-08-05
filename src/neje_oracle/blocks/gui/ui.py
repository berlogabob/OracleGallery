from __future__ import annotations

from typing import Any, Callable

from nicegui import ui


def primary_action_button(label, on_click) -> Any:
    return ui.button(label, on_click=on_click).props("dense color=positive")


def danger_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    return ui.button(label, on_click=on_click).props("dense color=warning")


def safe_action_button(label: str, on_click: Callable[..., Any]) -> Any:
    return ui.button(label, on_click=on_click).props("dense flat")


def warning_banner(text: str) -> Any:
    return ui.label(text).classes("warning-banner")


def mini_metric(label: str, *, extra_classes: str = "", style: str = "") -> Any:
    """div.mini-metric > label.label(label) > label.value("-"); returns the value handle."""
    classes = f"mini-metric {extra_classes}".strip()
    with ui.element("div").classes(classes) as element:
        if style:
            element.style(style)
        ui.label(label).classes("label")
        return ui.label("-").classes("value")


def helper_text(text: str) -> None:
    ui.label(text).classes("text-xs text-[#8f4f2b]")


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
