"""NiceGUI components library.

Provides reusable, styled UI components for the Oracle GUI.
"""

from .components.buttons import (
    danger_action_button,
    primary_action_button,
    safe_action_button,
    warning_action_button,
)
from .components.inputs import (
    checkbox_control,
    number_control,
    select_control,
    text_control,
)
from .components.layout import (
    badge_row,
    control_group,
    divider,
    form_row,
    live_strip,
    oracle_card,
    section,
    spacer,
    three_column_layout,
    two_column_layout,
)
from .components.status import (
    progress_status,
    status_pill,
    status_row,
    update_status_pill,
)

__all__ = [
    # Buttons
    "safe_action_button",
    "danger_action_button",
    "primary_action_button",
    "warning_action_button",
    # Inputs
    "number_control",
    "text_control",
    "checkbox_control",
    "select_control",
    # Status
    "status_pill",
    "update_status_pill",
    "status_row",
    "progress_status",
    # Layout
    "oracle_card",
    "section",
    "form_row",
    "control_group",
    "live_strip",
    "badge_row",
    "two_column_layout",
    "three_column_layout",
    "spacer",
    "divider",
]
