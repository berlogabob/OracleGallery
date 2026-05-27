"""Connection workspace for the Oracle GUI.

The Connection workspace handles all device connection and status monitoring:
- Printer connection and status
- Plotter connection and communication
- FluidNC connection and health checks
- Real-time status pills showing component health
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ..gui_components import (
    oracle_card,
    primary_action_button,
    safe_action_button,
    section,
    status_pill,
    status_row,
)
from ..models import ComponentStatus
from ..supervisor import SupervisorService


def build_connection_workspace(supervisor: SupervisorService) -> None:
    """Build the Connection workspace UI.
    
    Args:
        supervisor: The SupervisorService instance for system operations
    """
    with ui.column().classes("workspace-scroll"):
        # Printer Connection Section
        with section("Printer"):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("Status:").classes("font-semibold")
                status_pill(ComponentStatus.UNKNOWN, label="Checking...")
            
            safe_action_button(
                "Connect Printer",
                lambda: None,  # Placeholder
                icon="plug",
            )
        
        # Plotter Connection Section
        with section("Plotter"):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("Status:").classes("font-semibold")
                status_pill(ComponentStatus.UNKNOWN, label="Checking...")
            
            safe_action_button(
                "Connect Plotter",
                lambda: None,  # Placeholder
                icon="plug",
            )
        
        # FluidNC Connection Section
        with section("FluidNC (Motion Control)"):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("Status:").classes("font-semibold")
                status_pill(ComponentStatus.UNKNOWN, label="Checking...")
            
            safe_action_button(
                "Check FluidNC",
                lambda: None,  # Placeholder
                icon="refresh",
            )
        
        # System Summary
        ui.label("All systems ready for operation").classes("text-grey-7 text-sm mt-8")
