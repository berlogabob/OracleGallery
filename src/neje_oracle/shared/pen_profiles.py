"""Named settings bundles for drawing instruments.

A fineliner, a gel pen and a ballpoint want different feeds, pen pressure and ink
start-up time. Only the instrument-dependent fields live in a profile -- sheet size,
layout, sampling and origin belong to the machine and the job, and switching pens must
not disturb them.

Shipped values are starting points, not measurements. The calibration sheet
(blocks/gcode/pen_cal.py) is what turns them into real numbers; see RUNBOOK.md.

Mirrors shared/symbols.py, the existing "named JSON map edited from the GUI" pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import _repo_root

if TYPE_CHECKING:
    from .gui_settings import GuiSettings

# Written on the first SAVE AS PROFILE, not shipped: STARTER_PROFILES below is the set the
# app ships with, and this file is the operator's own measurements layered over it. It used
# to be tracked with the same four pens spelled out a second time, kept honest only by a
# drift test.
PROFILE_PATH = _repo_root() / "assets" / "pen_profiles.json"

# The instrument-dependent subset of GuiSettings. Adding a field here makes it part of
# every profile; it must also exist on GuiSettings.
PEN_PROFILE_FIELDS = (
    "pen_width_mm",
    "draw_rate",
    "travel_rate",
    "z_down_mm",
    "z_up_mm",
    "z_fix_mm",
    "z_feed_mm_min",
    "pen_down_dwell_ms",
)

# Fields whose value is a Z target: clamped to the servo's travel on load, because the
# file is hand-editable and a past-travel target either trips the board's soft limit into
# Alarm or stalls the servo against its stop. z_fix_mm is one of them -- the pen-fix
# position sits about a millimetre off the mechanical end, with no room to spare.
_Z_TARGET_FIELDS = ("z_down_mm", "z_fix_mm")
_Z_TRAVEL_FLOOR_MM = -25.0

# The shipped set, used until the operator saves their own, so the GUI always has
# something to select. Deliberately conservative: slower and shallower than the machine can manage,
# because an over-pressed nib is damaged and an over-fast one just skips.
#
# z_down_mm floor is -25.0: the servo's configured travel. "More pressure" via a deeper
# command (the old -25.5/-26.0 values) is unreachable -- the board's soft limit rejects
# the move into Alarm, or the servo stalls against its mechanical stop, and stall
# current is the prime suspect for the ESP32 brownout panics. Real pressure tuning
# belongs in the servo pulse-range calibration, not past-travel Z targets.
STARTER_PROFILES: dict[str, dict[str, float]] = {
    "fineliner": {
        "pen_width_mm": 0.3,
        "draw_rate": 1800.0,
        "travel_rate": 5000.0,
        "z_down_mm": -25.0,
        "z_up_mm": 0.0,
        "z_fix_mm": -25.0,
        "z_feed_mm_min": 1000.0,
        "pen_down_dwell_ms": 0.0,
    },
    # Gel ink needs a moment to reach the ball, or the first millimetres of every stroke
    # come out dry. Slower draw for the same reason.
    "gel": {
        "pen_width_mm": 0.5,
        "draw_rate": 1400.0,
        "travel_rate": 5000.0,
        "z_down_mm": -25.0,
        "z_up_mm": 0.0,
        "z_fix_mm": -25.0,
        "z_feed_mm_min": 800.0,
        "pen_down_dwell_ms": 120.0,
    },
    # Ballpoints need real pressure to write at all, and tolerate speed well.
    "ballpoint": {
        "pen_width_mm": 0.4,
        "draw_rate": 2400.0,
        "travel_rate": 5000.0,
        "z_down_mm": -25.0,
        "z_up_mm": 0.0,
        "z_fix_mm": -25.0,
        "z_feed_mm_min": 1200.0,
        "pen_down_dwell_ms": 60.0,
    },
    # Textile ball-tip marker: the line width is pressure-sensitive, so the Z ladder is
    # the decisive calibration block — these numbers start from ballpoint and only the
    # paper can pick the real depth. Ink flows freely, so no dwell.
    "textile": {
        "pen_width_mm": 0.8,
        "draw_rate": 2400.0,
        "travel_rate": 5000.0,
        "z_down_mm": -25.0,
        "z_up_mm": 0.0,
        "z_fix_mm": -25.0,
        "z_feed_mm_min": 1200.0,
        "pen_down_dwell_ms": 0.0,
    },
}


def load_pen_profiles(path: Path | None = None) -> dict[str, dict[str, float]]:
    """Profiles from disk, falling back to the starters when the file is absent."""
    profile_path = path or PROFILE_PATH
    if not profile_path.exists():
        return {name: dict(values) for name, values in STARTER_PROFILES.items()}
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    profiles: dict[str, dict[str, float]] = {}
    for name, values in payload.items():
        if not isinstance(values, dict):
            continue
        # Unknown keys are dropped rather than raising: the file is hand-editable, and a
        # stale key from a renamed field must not make every profile unloadable.
        loaded = {field: float(values[field]) for field in PEN_PROFILE_FIELDS if field in values}
        # The file is hand-editable, so a past-travel depth (see STARTER_PROFILES note)
        # can come back: clamp every Z target to the servo's travel here, once, for every
        # consumer.
        for z_field in _Z_TARGET_FIELDS:
            if z_field in loaded:
                loaded[z_field] = min(0.0, max(_Z_TRAVEL_FLOOR_MM, loaded[z_field]))
        profiles[str(name)] = loaded
    return profiles


def save_pen_profiles(profiles: dict[str, dict[str, float]], path: Path | None = None) -> None:
    profile_path = path or PROFILE_PATH
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        name: {field: float(values[field]) for field in PEN_PROFILE_FIELDS if field in values}
        for name, values in profiles.items()
    }
    profile_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture_pen_profile(settings: GuiSettings) -> dict[str, float]:
    """Current instrument settings as a profile payload.

    This is what closes the tune-adjust loop: read the best rung off the calibration
    sheet, type the numbers in, then save them back under a name.
    """
    return {field: float(getattr(settings, field)) for field in PEN_PROFILE_FIELDS}


def apply_pen_profile(
    settings: GuiSettings,
    name: str,
    profiles: dict[str, dict[str, float]] | None = None,
) -> None:
    """Overwrite only the instrument fields on `settings`, in place."""
    available = profiles if profiles is not None else load_pen_profiles()
    if name not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise ValueError(f"unknown pen profile {name!r}; known profiles: {known}")
    for field, value in available[name].items():
        if field in PEN_PROFILE_FIELDS:
            setattr(settings, field, float(value))
    settings.pen_profile = name


def profile_matches(settings: GuiSettings, name: str, profiles: dict[str, dict[str, float]] | None = None) -> bool:
    """Whether the live settings still equal the named profile.

    Guards a data-loss path: apply_pen_profile overwrites every instrument field, so the
    CALIBRATION picker checks this before switching and refuses while the current profile
    has unsaved tuning. Typing numbers off the calibration sheet before pressing SAVE AS
    PROFILE is exactly the loop RUNBOOK section 9 prescribes.
    """
    available = profiles if profiles is not None else load_pen_profiles()
    values: dict[str, Any] = available.get(name, {})
    if not values:
        return False
    return all(
        abs(float(getattr(settings, field)) - float(value)) < 1e-9
        for field, value in values.items()
        if field in PEN_PROFILE_FIELDS
    )


def delete_pen_profile(name: str, profiles: dict[str, dict[str, float]] | None = None) -> dict[str, dict[str, float]]:
    """Remove a profile and write the file. Returns what remains.

    Refuses the last one: an empty picker would leave the operator with no way back to a
    known-good pen, and the values a profile holds cost a printed sheet to find.
    """
    available = profiles if profiles is not None else load_pen_profiles()
    if name not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise ValueError(f"unknown pen profile {name!r}; known profiles: {known}")
    if len(available) <= 1:
        raise ValueError(f"{name!r} is the only pen profile; keep at least one")
    remaining = {key: values for key, values in available.items() if key != name}
    save_pen_profiles(remaining)
    return remaining


def rename_pen_profile(
    old: str, new: str, profiles: dict[str, dict[str, float]] | None = None
) -> dict[str, dict[str, float]]:
    """Move a profile's values to a new name in one write.

    Refuses to land on an existing name: that would overwrite another pen's measurements
    with this one's, silently, and the only copy of those numbers is on paper.
    """
    available = profiles if profiles is not None else load_pen_profiles()
    new = new.strip()
    if old not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise ValueError(f"unknown pen profile {old!r}; known profiles: {known}")
    if not new:
        raise ValueError("name the profile before renaming")
    if new in available and new != old:
        raise ValueError(f"pen profile {new!r} already exists; pick another name")
    renamed = {(new if key == old else key): values for key, values in available.items()}
    save_pen_profiles(renamed)
    return renamed
