from __future__ import annotations

from neje_oracle.blocks.gui.modes import mode_policy, mode_to_control
from neje_oracle.shared.models import SystemMode


def test_system_modes_map_to_safe_internal_control() -> None:
    test = mode_policy(SystemMode.TEST)
    exhibition = mode_policy(SystemMode.EXHIBITION)

    assert test.run_mode == "test"
    assert test.dry_run is False
    assert test.real_output_required is True
    assert test.firebase_required is False
    assert exhibition.run_mode == "exhibition"
    assert exhibition.dry_run is False
    assert exhibition.real_output_required is True
    assert exhibition.firebase_required is True


def test_legacy_exhibition_modes_normalize_to_exhibition() -> None:
    dry = mode_policy("exhibition_dry")
    real = mode_policy("exhibition_real")

    assert dry.mode == SystemMode.EXHIBITION
    assert real.mode == SystemMode.EXHIBITION
    assert dry.dry_run is False
    assert real.dry_run is False


def test_mode_to_control_keeps_print_paused_by_default() -> None:
    control = mode_to_control(SystemMode.EXHIBITION)

    assert control.print_enabled is False
    assert control.operator_paused is True
    assert control.dry_run is False
