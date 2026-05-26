"""Layout components and containers for NiceGUI.

This module provides reusable layout patterns used throughout the GUI,
including cards, sections, and grid layouts.
"""

from contextlib import contextmanager
from typing import Any, Generator, Optional

from nicegui import ui


@contextmanager
def oracle_card(
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    classes: str = "",
) -> Generator[ui.card, None, None]:
    """Context manager for creating an Oracle-styled card.
    
    Args:
        title: Optional card title
        subtitle: Optional card subtitle
        classes: Additional CSS classes to apply
        
    Yields:
        The card element for adding content
        
    Example:
        with oracle_card("Settings") as card:
            ui.label("Content here")
    """
    card = ui.card()
    card.classes("oracle-card " + classes)
    
    if title:
        with card:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(title).classes("oracle-title text-lg font-semibold")
                if subtitle:
                    ui.label(subtitle).classes("text-grey-7 text-sm")
    
    yield card


@contextmanager
def section(
    title: str,
    collapsible: bool = False,
    collapsed: bool = False,
    classes: str = "",
) -> Generator[ui.expansion, None, None]:
    """Create a collapsible or static section with title.
    
    Args:
        title: Section title
        collapsible: If True, section can collapse
        collapsed: Initial collapsed state
        classes: Additional CSS classes
        
    Yields:
        Container for section content
    """
    if collapsible:
        with ui.expansion(title, icon="unfold_more").classes(classes) as expansion:
            expansion.set_value(not collapsed)
            yield expansion
    else:
        with ui.column().classes("w-full " + classes):
            ui.label(title).classes("oracle-title text-md font-semibold mb-2")
            yield ui.column().classes("w-full")


@contextmanager
def form_row(label: Optional[str] = None) -> Generator[ui.row, None, None]:
    """Create a form row with optional label.
    
    Args:
        label: Optional left-side label
        
    Yields:
        Row container for form elements
    """
    with ui.row().classes("w-full items-center gap-4") as row:
        if label:
            ui.label(label).classes("font-semibold min-w-32")
        
        yield row


@contextmanager
def control_group(
    label: str,
    description: Optional[str] = None,
) -> Generator[ui.column, None, None]:
    """Create a labeled group of related controls.
    
    Args:
        label: Group label/heading
        description: Optional description text
        
    Yields:
        Container for grouped controls
    """
    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("w-full items-baseline gap-2"):
            ui.label(label).classes("font-semibold")
            if description:
                ui.label(description).classes("text-grey-7 text-sm")
        
        yield ui.column().classes("w-full ml-4")


def live_strip(items: list[tuple[str, str]]) -> None:
    """Create a live status strip (6-column grid layout).
    
    Displays key metrics in a compact grid with labels and values.
    
    Args:
        items: List of (label, value) tuples to display
    """
    with ui.row().classes("live-strip"):
        for label, value in items:
            with ui.card().classes("mini-metric"):
                ui.label(label).classes("text-xs text-grey-7")
                ui.label(value).classes("text-sm font-semibold")


def badge_row(
    items: list[tuple[str, str, Optional[str]]],
) -> None:
    """Create a row of status badges.
    
    Args:
        items: List of (label, color, icon) tuples
    """
    with ui.row().classes("w-full items-center gap-2"):
        for label, color, icon in items:
            badge = ui.badge(label)
            badge.props(f"color={color}")
            if icon:
                badge.props(f"icon={icon}")


@contextmanager
def two_column_layout() -> Generator[tuple[ui.column, ui.column], None, None]:
    """Create a two-column layout.
    
    Yields:
        Tuple of (left_column, right_column)
    """
    with ui.row().classes("w-full gap-4"):
        left = ui.column().classes("flex-1")
        right = ui.column().classes("flex-1")
        
        yield left, right


@contextmanager
def three_column_layout() -> Generator[tuple[ui.column, ui.column, ui.column], None, None]:
    """Create a three-column layout.
    
    Yields:
        Tuple of (left_column, center_column, right_column)
    """
    with ui.row().classes("w-full gap-4"):
        left = ui.column().classes("flex-1")
        center = ui.column().classes("flex-1")
        right = ui.column().classes("flex-1")
        
        yield left, center, right


def spacer(height: str = "md") -> None:
    """Add vertical spacing.
    
    Args:
        height: Spacing size ('xs', 'sm', 'md', 'lg', 'xl')
    """
    size_map = {
        "xs": "h-2",
        "sm": "h-4",
        "md": "h-6",
        "lg": "h-8",
        "xl": "h-12",
    }
    
    ui.element().classes(size_map.get(height, size_map["md"]))


def divider() -> None:
    """Add a horizontal divider line."""
    ui.separator().classes("my-4")
