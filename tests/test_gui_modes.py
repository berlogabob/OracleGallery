from __future__ import annotations

from neje_oracle.gui_modes import mode_policy, mode_to_control
from neje_oracle.models import SystemMode


def test_system_modes_map_to_safe_internal_control() -> None:
    test = mode_policy(SystemMode.TEST)
    dry = mode_policy(SystemMode.EXHIBITION_DRY)
    real = mode_policy(SystemMode.EXHIBITION_REAL)

    assert test.run_mode == "test"
    assert test.dry_run is True
    assert test.test_tools_enabled is True
    assert dry.run_mode == "exhibition"
    assert dry.dry_run is True
    assert dry.real_fluidnc_required is False
    assert real.run_mode == "exhibition"
    assert real.dry_run is False
    assert real.real_fluidnc_required is True


def test_mode_to_control_keeps_print_paused_by_default() -> None:
    control = mode_to_control(SystemMode.EXHIBITION_REAL)

    assert control.print_enabled is False
    assert control.operator_paused is True
    assert control.dry_run is False
