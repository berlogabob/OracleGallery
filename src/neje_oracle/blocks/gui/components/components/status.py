"""Status display components for NiceGUI.

This module provides visual status indicators used throughout the GUI,
including status pills, badges, and status transitions.
"""

from typing import Any, Optional

from nicegui import ui

from .....shared.models import ComponentStatus


# Color mapping for component statuses
STATUS_COLORS: dict[ComponentStatus, str] = {
    ComponentStatus.STOPPED: "grey",
    ComponentStatus.STARTING: "blue",
    ComponentStatus.RUNNING: "info",
    ComponentStatus.OFFLINE: "grey",
    ComponentStatus.WARNING: "warning",
    ComponentStatus.ERROR: "negative",
}

# Display labels for statuses
STATUS_LABELS: dict[ComponentStatus, str] = {
    ComponentStatus.STOPPED: "Stopped",
    ComponentStatus.STARTING: "Starting...",
    ComponentStatus.RUNNING: "Running",
    ComponentStatus.OFFLINE: "Offline",
    ComponentStatus.WARNING: "Warning",
    ComponentStatus.ERROR: "Error",
}


def status_pill(
    status: ComponentStatus,
    label: Optional[str] = None,
    size: str = "md",
) -> ui.badge:
    """Create a status indicator pill (badge).

    Args:
        status: ComponentStatus enum value
        label: Optional custom label (uses default if not provided)
        size: Badge size - affects font and padding

    Returns:
        Configured ui.badge instance
    """
    display_label = label or STATUS_LABELS.get(status, str(status))
    color = STATUS_COLORS.get(status, "grey")

    badge = ui.badge(display_label)
    badge.props(f"color={color}")

    # Apply size styling
    if size == "sm":
        badge.classes("text-xs")
    elif size == "lg":
        badge.classes("text-lg")
    # default "md" has no extra styling

    return badge


def update_status_pill(
    badge: ui.badge,
    new_status: ComponentStatus,
    label: Optional[str] = None,
) -> None:
    """Update an existing status pill with new status.

    Args:
        badge: The badge element to update
        new_status: New ComponentStatus
        label: Optional custom label
    """
    display_label = label or STATUS_LABELS.get(new_status, str(new_status))
    color = STATUS_COLORS.get(new_status, "grey")

    badge.text = display_label
    badge.props(f"color={color}", remove="color")
    badge.update()


def status_row(
    label: str,
    status: ComponentStatus,
    detail: Optional[str] = None,
) -> None:
    """Create a status display row (label + pill + optional detail).

    Args:
        label: Left-side label (e.g., "Printer")
        status: ComponentStatus to display
        detail: Optional right-side detail text (e.g., "192.168.1.100")
    """
    with ui.row().classes("w-full items-center"):
        ui.label(label).classes("font-semibold text-grey-8")
        status_pill(status, size="md")

        if detail:
            ui.label(detail).classes("text-grey-7 text-sm ml-auto")


def progress_status(
    current: int,
    total: int,
    status: ComponentStatus,
) -> None:
    """Create a progress-style status display.

    Args:
        current: Current progress value
        total: Total/maximum value
        status: ComponentStatus to show
    """
    percentage = int((current / total * 100)) if total > 0 else 0

    with ui.row().classes("w-full items-center"):
        ui.linear_progress(value=percentage / 100).classes("flex-grow")
        ui.label(f"{current}/{total}").classes("text-grey-7 ml-2")
        status_pill(status, size="sm")
