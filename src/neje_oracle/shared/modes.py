from __future__ import annotations

from dataclasses import dataclass

from .models import PlotterControlState, PlotterRuntimeConfig, SystemMode

MODE_LABELS = {
    SystemMode.TEST: "TEST",
    SystemMode.EXHIBITION: "EXHIBITION",
}


@dataclass(frozen=True)
class ModePolicy:
    mode: SystemMode
    label: str
    run_mode: str
    dry_run: bool
    test_tools_enabled: bool
    real_output_required: bool
    firebase_required: bool


def mode_policy(mode: SystemMode | str) -> ModePolicy:
    resolved = SystemMode(mode)
    if resolved == SystemMode.TEST:
        return ModePolicy(
            mode=resolved,
            label=MODE_LABELS[resolved],
            run_mode="test",
            dry_run=False,
            test_tools_enabled=True,
            real_output_required=True,
            firebase_required=False,
        )
    return ModePolicy(
        mode=resolved,
        label=MODE_LABELS[resolved],
        run_mode="exhibition",
        dry_run=False,
        test_tools_enabled=False,
        real_output_required=True,
        firebase_required=True,
    )


def mode_to_control(mode: SystemMode | str, *, print_enabled: bool = False) -> PlotterControlState:
    policy = mode_policy(mode)
    return PlotterControlState(
        print_enabled=print_enabled,
        operator_paused=not print_enabled,
        run_mode=policy.run_mode,
        dry_run=policy.dry_run,
    )


def apply_mode_to_config(config: PlotterRuntimeConfig, mode: SystemMode | str) -> PlotterRuntimeConfig:
    policy = mode_policy(mode)
    config.run_mode = policy.run_mode
    config.dry_run = policy.dry_run
    return config
