from __future__ import annotations

from dataclasses import dataclass

from .models import PlotterControlState, PlotterRuntimeConfig, SystemMode

# The two modes differ in exactly one thing, so the labels say that thing instead of
# implying a safety difference that does not exist (both draw real ink).
MODE_LABELS = {
    SystemMode.TEST: "Firebase not required (local-only)",
    SystemMode.EXHIBITION: "Firebase required",
}


@dataclass(frozen=True)
class ModePolicy:
    mode: SystemMode
    label: str
    run_mode: str
    dry_run: bool
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
            real_output_required=True,
            firebase_required=False,
        )
    return ModePolicy(
        mode=resolved,
        label=MODE_LABELS[resolved],
        run_mode="exhibition",
        dry_run=False,
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
