"""Tests workspace for the Oracle GUI.

The Tests workspace provides diagnostic and operational controls:
- System health checks
- Test print functionality
- Manual machine controls (jog, home, pen up/down)
- Emergency stop button
- FluidNC diagnostic tools
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ..gui_components import danger_action_button, primary_action_button, section
from ..supervisor import SupervisorService


def build_tests_workspace(supervisor: SupervisorService) -> None:
    """Build the Tests workspace UI.
    
    Args:
        supervisor: The SupervisorService instance for system operations
    """
    with ui.column().classes("workspace-scroll"):
        # System Health Check
        with section("System Health"):
            primary_action_button(
                "Run System Check",
                lambda: None,  # Placeholder
                icon="verified",
            )
            ui.label("Last check: Never").classes("text-sm text-grey-7 mt-2")
        
        # Test Print
        with section("Test Print"):
            ui.label("Print a test pattern to verify motion").classes("text-sm text-grey-7")
            primary_action_button(
                "Start Test Print",
                lambda: None,  # Placeholder
                icon="local_print_shop",
            )
        
        # Manual Controls
        with section("Manual Controls"):
            # Jog controls
            ui.label("Jogging (X, Y movement)").classes("font-semibold text-sm")
            with ui.row().classes("gap-2 mt-2"):
                ui.button("← X").classes("w-12 h-12")
                ui.button("→ X").classes("w-12 h-12")
                ui.button("← Y").classes("w-12 h-12")
                ui.button("→ Y").classes("w-12 h-12")
            
            # Home buttons
            ui.label("Homing").classes("font-semibold text-sm mt-4")
            with ui.row().classes("gap-2 mt-2"):
                ui.button("Home XY").classes("flex-1")
                ui.button("Set Zero").classes("flex-1")
            
            # Pen controls
            ui.label("Pen (Z-axis)").classes("font-semibold text-sm mt-4")
            with ui.row().classes("gap-2 mt-2"):
                ui.button("Pen Up").classes("flex-1")
                ui.button("Pen Down").classes("flex-1")
        
        # Emergency Control
        with section("Emergency"):
            danger_action_button(
                "EMERGENCY STOP",
                lambda: None,  # Placeholder
                icon="warning",
            ).classes("w-full")
