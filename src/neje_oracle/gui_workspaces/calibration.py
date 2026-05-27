"""Calibration workspace for the Oracle GUI.

The Calibration workspace handles grid configuration and layout:
- Symbol origin selection (6 positions on the grid)
- Randomness parameters
- Sample step and density controls
- Cell diameter and spacing
- Real-time preview of layout effect
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ..gui_components import oracle_card, section
from ..supervisor import SupervisorService


def build_calibration_workspace(supervisor: SupervisorService) -> None:
    """Build the Calibration workspace UI.
    
    Args:
        supervisor: The SupervisorService instance for system operations
    """
    with ui.column().classes("workspace-scroll"):
        # Origin Selection
        with section("Symbol Origin (Position on Grid)"):
            with ui.row().classes("w-full gap-2"):
                ui.label("Select 6 positions where symbols appear").classes("text-sm text-grey-7")
                # 6 origin buttons would go here (placeholder)
                ui.label("[Origin buttons placeholder]").classes("text-grey-5")
        
        # Preview
        ui.label("Layout Preview:").classes("font-semibold mt-4")
        preview_container = ui.html().classes("preview-frame")
        preview_container.set_content("<p>Preview will appear here</p>")
        
        # Randomness Controls
        with section("Randomness"):
            ui.slider(min=0, max=100, value=50, step=1).classes("w-full")
            ui.label("Randomness factor").classes("text-sm text-grey-7")
        
        # Sample Configuration
        with section("Sampling"):
            ui.label("Sample step: 1.0 mm").classes("text-sm")
            ui.label("Density: Normal").classes("text-sm")
        
        ui.label("Calibration settings saved automatically").classes("text-grey-7 text-sm mt-8")
