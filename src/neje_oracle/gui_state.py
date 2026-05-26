"""Immutable GUI state management.

This module defines the GUI state model - a single source of truth
for all GUI-related state. State is immutable: every change creates
a new state object rather than mutating the current one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class GUIState:
    """Immutable GUI state container.
    
    All state is frozen (immutable). To change state, create a new instance
    using the with_* methods or dataclasses.replace().
    """
    
    # Workspace management
    active_workspace: str = "connection"
    preview_mode: str = "preview"  # "preview" or "printing"
    
    # SVG upload state
    selected_svg_name: str = ""
    selected_svg_bytes: bytes = b""
    
    # GUI settings loaded from persistent storage
    gui_settings: dict[str, Any] = field(default_factory=dict)
    
    # Symbol scales loaded from persistent storage
    symbol_scales: dict[str, Any] = field(default_factory=dict)
    
    # Available symbols list
    available_symbols: list[str] = field(default_factory=list)
    
    # Current field values (form inputs)
    field_values: dict[str, Any] = field(default_factory=dict)
    
    # Current component statuses
    component_statuses: dict[str, Any] = field(default_factory=dict)
    
    # Last system check result
    last_system_check: dict[str, Any] = field(default_factory=dict)
    
    # Active error messages
    error_messages: list[str] = field(default_factory=list)
    
    # Logger output lines
    recent_logs: list[str] = field(default_factory=list)
    
    def with_workspace(self, workspace: str) -> GUIState:
        """Return new state with different active workspace.
        
        Args:
            workspace: New workspace name ('connection', 'calibration', etc)
            
        Returns:
            New GUIState with updated workspace
        """
        return GUIState(
            active_workspace=workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=self.error_messages,
            recent_logs=self.recent_logs,
        )
    
    def with_preview_mode(self, mode: str) -> GUIState:
        """Return new state with different preview mode.
        
        Args:
            mode: New preview mode ('preview' or 'printing')
            
        Returns:
            New GUIState with updated preview mode
        """
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=self.error_messages,
            recent_logs=self.recent_logs,
        )
    
    def with_selected_svg(self, name: str, data: bytes) -> GUIState:
        """Return new state with selected SVG.
        
        Args:
            name: SVG filename
            data: SVG file bytes
            
        Returns:
            New GUIState with updated SVG selection
        """
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=name,
            selected_svg_bytes=data,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=self.error_messages,
            recent_logs=self.recent_logs,
        )
    
    def with_field_values(self, values: dict[str, Any]) -> GUIState:
        """Return new state with updated field values.
        
        Args:
            values: Dictionary of field name -> value
            
        Returns:
            New GUIState with updated fields
        """
        new_values = {**self.field_values, **values}
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=new_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=self.error_messages,
            recent_logs=self.recent_logs,
        )
    
    def with_component_statuses(self, statuses: dict[str, Any]) -> GUIState:
        """Return new state with updated component statuses.
        
        Args:
            statuses: Dictionary of component -> status
            
        Returns:
            New GUIState with updated statuses
        """
        new_statuses = {**self.component_statuses, **statuses}
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=new_statuses,
            last_system_check=self.last_system_check,
            error_messages=self.error_messages,
            recent_logs=self.recent_logs,
        )
    
    def with_error(self, message: str) -> GUIState:
        """Return new state with added error message.
        
        Args:
            message: Error message to add
            
        Returns:
            New GUIState with error added
        """
        new_errors = [*self.error_messages, message]
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=new_errors,
            recent_logs=self.recent_logs,
        )
    
    def clear_errors(self) -> GUIState:
        """Return new state with all errors cleared.
        
        Returns:
            New GUIState with empty error list
        """
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=[],
            recent_logs=self.recent_logs,
        )
    
    def with_logs(self, logs: list[str]) -> GUIState:
        """Return new state with updated logs.
        
        Args:
            logs: New log lines list
            
        Returns:
            New GUIState with updated logs
        """
        return GUIState(
            active_workspace=self.active_workspace,
            preview_mode=self.preview_mode,
            selected_svg_name=self.selected_svg_name,
            selected_svg_bytes=self.selected_svg_bytes,
            gui_settings=self.gui_settings,
            symbol_scales=self.symbol_scales,
            available_symbols=self.available_symbols,
            field_values=self.field_values,
            component_statuses=self.component_statuses,
            last_system_check=self.last_system_check,
            error_messages=self.error_messages,
            recent_logs=logs,
        )


# Default empty state
DEFAULT_GUI_STATE = GUIState()
