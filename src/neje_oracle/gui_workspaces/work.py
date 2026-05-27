"""Work workspace for the Oracle GUI.

The Work workspace is the core production interface:
- SVG file upload and selection
- G-code preview (two modes: layout preview and printing preview)
- Dry run generation for testing
- Start Print button with system checks
- Live status strip showing real-time progress
- Log viewer for operation history
- Queue status display
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
)
from ..supervisor import SupervisorService


def build_work_workspace(supervisor: SupervisorService) -> None:
    """Build the Work workspace UI (core production workflow).
    
    Args:
        supervisor: The SupervisorService instance for system operations
    """
    with ui.column().classes("workspace-scroll"):
        # SVG Upload Section
        with section("Upload Artwork"):
            with ui.row().classes("w-full gap-4"):
                ui.upload(
                    label="Select SVG file",
                    on_upload=lambda _: None,  # Placeholder
                ).classes("flex-1")
                safe_action_button(
                    "Clear",
                    lambda: None,  # Placeholder
                )
            
            ui.label("No SVG selected").classes("text-sm text-grey-7")
        
        # Preview Section
        with section("Preview"):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("Mode:").classes("font-semibold")
                ui.radio(["Layout", "Printing"], value="Layout")
            
            preview_container = ui.html().classes("preview-frame")
            preview_container.set_content("<p>Preview will appear here</p>")
        
        # G-code Controls
        with section("Generation"):
            with ui.row().classes("w-full gap-2"):
                safe_action_button(
                    "Generate Dry Run",
                    lambda: None,  # Placeholder
                    icon="description",
                )
                ui.label("G-code details...").classes("text-sm text-grey-7")
        
        # Status Display
        with section("Status"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Progress:").classes("font-semibold")
                ui.linear_progress(value=0).classes("flex-1 ml-4")
            
            ui.label("Ready to print").classes("text-sm text-grey-7")
        
        # Action Button
        primary_action_button(
            "START PRINT",
            lambda: None,  # Placeholder
            icon="play_arrow",
            size="lg",
        ).classes("w-full mt-4")
        
        # Logs
        with section("Operation Log"):
            log_container = ui.textarea(readonly=True).classes("w-full h-24")
            log_container.value = "Waiting for operations...\n"
