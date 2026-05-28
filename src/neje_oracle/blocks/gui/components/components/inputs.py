"""Input components for NiceGUI.

This module provides reusable input controls with validation,
styling, and common behaviors.
"""

from typing import Any, Callable, Optional

from nicegui import ui


def number_control(
    label: str,
    initial_value: float,
    min_value: float = 0,
    max_value: float = 100,
    step: float = 1,
    on_change: Optional[Callable[[float], None]] = None,
    unit: Optional[str] = None,
    help_text: Optional[str] = None,
) -> tuple[ui.number, ui.slider]:
    """Create a labeled number input with integrated slider.

    Args:
        label: Label for the control
        initial_value: Starting value
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        step: Step size for increments
        on_change: Optional callback on value change
        unit: Optional unit suffix (e.g., "mm", "%")
        help_text: Optional help text below control

    Returns:
        Tuple of (number_input, slider) for further customization
    """
    with ui.column().classes("w-full"):
        # Label row
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(label).classes("font-semibold")
            if unit:
                ui.label(unit).classes("text-grey-7 text-sm")

        # Number input
        number_input = ui.number(
            label="",
            value=initial_value,
            min=min_value,
            max=max_value,
            step=step,
        ).classes("w-full")

        # Slider
        slider = ui.slider(
            min=min_value,
            max=max_value,
            value=initial_value,
            step=step,
        ).classes("w-full")

        # Sync number and slider
        def sync_from_number() -> None:
            slider.value = number_input.value
            if on_change:
                on_change(number_input.value)

        def sync_from_slider() -> None:
            number_input.value = slider.value
            if on_change:
                on_change(slider.value)

        number_input.on_change(sync_from_number)
        slider.on_change(sync_from_slider)

        # Help text
        if help_text:
            ui.label(help_text).classes("text-grey-7 text-xs mt-1")

    return number_input, slider


def text_control(
    label: str,
    initial_value: str = "",
    placeholder: Optional[str] = None,
    on_change: Optional[Callable[[str], None]] = None,
    readonly: bool = False,
    multiline: bool = False,
    help_text: Optional[str] = None,
) -> ui.input:
    """Create a labeled text input field.

    Args:
        label: Label for the control
        initial_value: Starting text value
        placeholder: Placeholder text
        on_change: Optional callback on value change
        readonly: If True, field is read-only
        multiline: If True, creates textarea
        help_text: Optional help text below control

    Returns:
        Configured ui.input instance
    """
    with ui.column().classes("w-full"):
        ui.label(label).classes("font-semibold")

        text_input = ui.input(
            label="",
            value=initial_value,
            placeholder=placeholder,
        ).classes("w-full")

        if multiline:
            text_input.props("type=textarea rows=4")

        if readonly:
            text_input.enabled = False

        if on_change:
            text_input.on_change(on_change)

        if help_text:
            ui.label(help_text).classes("text-grey-7 text-xs mt-1")

    return text_input


def checkbox_control(
    label: str,
    initial_value: bool = False,
    on_change: Optional[Callable[[bool], None]] = None,
    help_text: Optional[str] = None,
) -> ui.checkbox:
    """Create a labeled checkbox.

    Args:
        label: Label for the control
        initial_value: Initial checked state
        on_change: Optional callback on change
        help_text: Optional help text below control

    Returns:
        Configured ui.checkbox instance
    """
    with ui.column().classes("w-full"):
        checkbox = ui.checkbox(label, value=initial_value)

        if on_change:
            checkbox.on_change(on_change)

        if help_text:
            ui.label(help_text).classes("text-grey-7 text-xs mt-1")

    return checkbox


def select_control(
    label: str,
    options: list[str],
    initial_value: Optional[str] = None,
    on_change: Optional[Callable[[str], None]] = None,
    help_text: Optional[str] = None,
) -> ui.select:
    """Create a labeled select/dropdown.

    Args:
        label: Label for the control
        options: List of selectable options
        initial_value: Initial selection
        on_change: Optional callback on selection change
        help_text: Optional help text below control

    Returns:
        Configured ui.select instance
    """
    with ui.column().classes("w-full"):
        ui.label(label).classes("font-semibold")

        select = ui.select(
            label="",
            options=options,
            value=initial_value or (options[0] if options else None),
        ).classes("w-full")

        if on_change:
            select.on_change(on_change)

        if help_text:
            ui.label(help_text).classes("text-grey-7 text-xs mt-1")

    return select
