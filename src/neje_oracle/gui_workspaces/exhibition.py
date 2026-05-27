"""Exhibition workspace for the Oracle GUI.

The Exhibition workspace provides a minimal, focused interface for
live exhibitions and demonstrations:
- Large, clear status display
- Minimal control surfaces (start/stop only)
- Full-screen capable
- High visibility, low distraction
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ..gui_components import (
    danger_action_button,
    primary_action_button,
    section,
    status_pill,
)
from ..supervisor import SupervisorService


def build_exhibition_workspace(supervisor: SupervisorService) -> None:
    """Build the Exhibition workspace UI (minimal, focused display).
    
    Args:
        supervisor: The SupervisorService instance for system operations
    """
    with ui.column().classes("workspace-scroll items-center justify-center"):
        # Large Status Display
        with ui.card().classes("w-full"):
            ui.label("ORACLE OPERATOR").classes("text-4xl font-bold text-center")
            
            # Main status
            with ui.row().classes("w-full items-center justify-center gap-4 mt-8"):
                ui.label("Status:").classes("text-2xl font-semibold")
                status_pill(
                    status_enum=None,  # Will be updated
                    label="READY",
                    size="lg",
                )
            
            # Progress display
            with ui.row().classes("w-full mt-6"):
                ui.linear_progress(value=0).classes("flex-1")
            
            with ui.row().classes("w-full justify-between items-center mt-2"):
                ui.label("Progress:").classes("font-semibold")
                ui.label("0 / 100 symbols").classes("text-right")
        
        # Minimal Controls
        with ui.row().classes("w-full gap-4 mt-8"):
            primary_action_button(
                "START PRINTING",
                lambda: None,  # Placeholder
                icon="play_arrow",
                size="lg",
            ).classes("flex-1")
            
            danger_action_button(
                "STOP",
                lambda: None,  # Placeholder
                icon="stop",
                size="lg",
            ).classes("flex-1")
        
        # Live metrics (minimal)
        with ui.row().classes("w-full gap-2 mt-6"):
            with ui.card().classes("flex-1"):
                ui.label("Speed").classes("text-sm text-grey-7")
                ui.label("100%").classes("text-lg font-semibold")
            
            with ui.card().classes("flex-1"):
                ui.label("Symbols").classes("text-sm text-grey-7")
                ui.label("0/100").classes("text-lg font-semibold")
            
            with ui.card().classes("flex-1"):
                ui.label("Time").classes("text-sm text-grey-7")
                ui.label("--:--").classes("text-lg font-semibold")
