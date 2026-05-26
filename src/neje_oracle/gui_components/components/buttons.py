"""Reusable button components for NiceGUI.

This module provides consistent, styled button components used across
all GUI workspaces. All buttons follow the Oracle design system.
"""

from typing import Callable, Optional

from nicegui import ui


def safe_action_button(
    text: str,
    on_click: Callable[..., None],
    *,
    icon: Optional[str] = None,
    size: str = "md",
    enabled: bool = True,
    tooltip: Optional[str] = None,
) -> ui.button:
    """Create a safe/positive action button (green).
    
    Args:
        text: Button label
        on_click: Click handler
        icon: Optional NiceGUI icon name (e.g., 'play', 'stop')
        size: Button size ('sm', 'md', 'lg')
        enabled: Whether button is clickable
        tooltip: Optional hover tooltip text
        
    Returns:
        Configured ui.button instance
    """
    button = ui.button(text)
    button.classes("safe-action")
    button.props(f"color=positive size={size}")
    
    if icon:
        button.props(f"icon={icon}")
    
    if tooltip:
        button.tooltip(tooltip)
    
    button.enabled = enabled
    button.on_click(on_click)
    
    return button


def danger_action_button(
    text: str,
    on_click: Callable[..., None],
    *,
    icon: Optional[str] = None,
    size: str = "md",
    enabled: bool = True,
    tooltip: Optional[str] = None,
) -> ui.button:
    """Create a danger/destructive action button (red).
    
    Args:
        text: Button label
        on_click: Click handler
        icon: Optional NiceGUI icon name
        size: Button size ('sm', 'md', 'lg')
        enabled: Whether button is clickable
        tooltip: Optional hover tooltip text
        
    Returns:
        Configured ui.button instance
    """
    button = ui.button(text)
    button.classes("danger-action")
    button.props(f"color=negative size={size}")
    
    if icon:
        button.props(f"icon={icon}")
    
    if tooltip:
        button.tooltip(tooltip)
    
    button.enabled = enabled
    button.on_click(on_click)
    
    return button


def primary_action_button(
    text: str,
    on_click: Callable[..., None],
    *,
    icon: Optional[str] = None,
    size: str = "md",
    enabled: bool = True,
    tooltip: Optional[str] = None,
) -> ui.button:
    """Create a primary action button (accent color).
    
    Args:
        text: Button label
        on_click: Click handler
        icon: Optional NiceGUI icon name
        size: Button size ('sm', 'md', 'lg')
        enabled: Whether button is clickable
        tooltip: Optional hover tooltip text
        
    Returns:
        Configured ui.button instance
    """
    button = ui.button(text)
    button.classes("primary-action")
    button.props(f"color=primary size={size}")
    
    if icon:
        button.props(f"icon={icon}")
    
    if tooltip:
        button.tooltip(tooltip)
    
    button.enabled = enabled
    button.on_click(on_click)
    
    return button


def warning_action_button(
    text: str,
    on_click: Callable[..., None],
    *,
    icon: Optional[str] = None,
    size: str = "md",
    enabled: bool = True,
    tooltip: Optional[str] = None,
) -> ui.button:
    """Create a warning/caution action button (orange).
    
    Args:
        text: Button label
        on_click: Click handler
        icon: Optional NiceGUI icon name
        size: Button size ('sm', 'md', 'lg')
        enabled: Whether button is clickable
        tooltip: Optional hover tooltip text
        
    Returns:
        Configured ui.button instance
    """
    button = ui.button(text)
    button.classes("warning-action")
    button.props(f"color=warning size={size}")
    
    if icon:
        button.props(f"icon={icon}")
    
    if tooltip:
        button.tooltip(tooltip)
    
    button.enabled = enabled
    button.on_click(on_click)
    
    return button
