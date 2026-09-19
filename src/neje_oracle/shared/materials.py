"""Named thickness offsets for the drawing surface.

The pen-down depth is tuned against a bare spoilboard. Put a silicone mat, thicker card
or a plastic sheet on the bed and the surface it draws on rises by that material's
thickness, so the pen must stop that much higher or it will drive into the mat instead of
the paper. A material profile holds nothing but the one number the operator would
otherwise have to re-measure and re-type into the Z positions every time they switch
surfaces.

Shipped values are starting points, not measurements -- an operator's own caliper reading
on the actual stock overwrites them. Mirrors shared/pen_profiles.py, the same
"named JSON map edited from the GUI" pattern:

- paper (0.1 mm): a single sheet of ~80-100 gsm printer paper laid over the spoilboard.
- card (0.3 mm): a sheet of ~250-300 gsm cardstock, the common greeting-card weight.
- plastic sheet (0.5 mm): a thin acetate or PET overlay used for stencils or transparencies.
- thick card (1.0 mm): mounting board or doubled-up heavy cardstock.
- silicone mat (2.0 mm): a craft silicone mat used to protect the spoilboard, thick enough
  that skipping the offset would visibly lift the pen off the surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import _repo_root

# Written on the first SAVE AS MATERIAL, not shipped: STARTER_MATERIALS below is the set
# the app ships with, and this file is the operator's own measurements layered over it.
# Keeping it out of version control means there is one definition of "card", not a tracked
# JSON copy of the code kept honest only by a drift test.
MATERIAL_PATH = _repo_root() / "assets" / "materials.json"

# One field today. A second one (a friction note, a recommended dwell) costs a line here
# and in STARTER_MATERIALS, not a rewrite of load/save/apply.
MATERIAL_FIELDS = ("thickness_mm",)

# The file is hand-editable, and a thickness past the servo's whole travel would ask the
# pen to park above its own top of travel. 20 mm is comfortably past any material this
# plotter draws on; 0 mm is the bare-spoilboard case, i.e. no material at all.
_THICKNESS_FLOOR_MM = 0.0
_THICKNESS_CEIL_MM = 20.0

# The shipped set, used until the operator saves their own, so the picker always has
# something to select. See the module docstring for where each number comes from.
STARTER_MATERIALS: dict[str, dict[str, float]] = {
    "paper": {"thickness_mm": 0.1},
    "card": {"thickness_mm": 0.3},
    "plastic sheet": {"thickness_mm": 0.5},
    "thick card": {"thickness_mm": 1.0},
    "silicone mat": {"thickness_mm": 2.0},
}


def load_materials(path: Path | None = None) -> dict[str, dict[str, float]]:
    """Materials from disk, falling back to the starters when the file is absent."""
    material_path = path or MATERIAL_PATH
    if not material_path.exists():
        return {name: dict(values) for name, values in STARTER_MATERIALS.items()}
    payload = json.loads(material_path.read_text(encoding="utf-8"))
    materials: dict[str, dict[str, float]] = {}
    for name, values in payload.items():
        if not isinstance(values, dict):
            continue
        # Unknown keys are dropped rather than raising: the file is hand-editable, and a
        # stale key from a renamed field must not make every material unloadable.
        loaded = {field: float(values[field]) for field in MATERIAL_FIELDS if field in values}
        # The file is hand-editable, so an out-of-range thickness (see _THICKNESS_CEIL_MM
        # note) can come back: clamp it here, once, for every consumer.
        if "thickness_mm" in loaded:
            loaded["thickness_mm"] = min(_THICKNESS_CEIL_MM, max(_THICKNESS_FLOOR_MM, loaded["thickness_mm"]))
        materials[str(name)] = loaded
    return materials


def save_materials(materials: dict[str, dict[str, float]], path: Path | None = None) -> None:
    material_path = path or MATERIAL_PATH
    material_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        name: {field: float(values[field]) for field in MATERIAL_FIELDS if field in values}
        for name, values in materials.items()
    }
    material_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture_material(thickness_mm: float) -> dict[str, float]:
    """A measured thickness as a material payload, ready to save under a name.

    This is what closes the measure-and-save loop: the operator puts a caliper on the
    stock, types the reading in, then saves it under a name.
    """
    return {"thickness_mm": float(thickness_mm)}


def apply_material(name: str, materials: dict[str, dict[str, float]] | None = None) -> float:
    """The named material's thickness, in mm."""
    available = materials if materials is not None else load_materials()
    if name not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise ValueError(f"unknown material {name!r}; known materials: {known}")
    return float(available[name]["thickness_mm"])


def delete_material(name: str, materials: dict[str, dict[str, float]] | None = None) -> dict[str, dict[str, float]]:
    """Remove a material and write the file. Returns what remains.

    Refuses the last one: an empty picker would leave the operator with no way back to a
    known offset, and the number a material holds cost a caliper measurement to find.
    """
    available = materials if materials is not None else load_materials()
    if name not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise ValueError(f"unknown material {name!r}; known materials: {known}")
    if len(available) <= 1:
        raise ValueError(f"{name!r} is the only material; keep at least one")
    remaining = {key: values for key, values in available.items() if key != name}
    save_materials(remaining)
    return remaining


def rename_material(
    old: str, new: str, materials: dict[str, dict[str, float]] | None = None
) -> dict[str, dict[str, float]]:
    """Move a material's value to a new name in one write.

    Refuses to land on an existing name: that would overwrite another material's
    measurement with this one's, silently, and the only other copy is on paper.
    """
    available = materials if materials is not None else load_materials()
    new = new.strip()
    if old not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise ValueError(f"unknown material {old!r}; known materials: {known}")
    if not new:
        raise ValueError("name the material before renaming")
    if new in available and new != old:
        raise ValueError(f"material {new!r} already exists; pick another name")
    renamed = {(new if key == old else key): values for key, values in available.items()}
    save_materials(renamed)
    return renamed
