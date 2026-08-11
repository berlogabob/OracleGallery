"""Pattern bank: SVG files on disk become tileable motifs for the sketch.

A motif is normalized into a unit box centred on the origin -- every coordinate
within [-0.5, 0.5], aspect preserved, longest side exactly 1.0. That is the same
contract as the sketch's built-in JS motif functions (cx, cy, size), so a bank
motif drops straight into its MOTIFS registry.

Curation is which files are in the folder. Adding a motif is adding an SVG.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...shared.config import _repo_root
from ..gcode.svg_gcode import svg_to_polylines_mm

BANK_DIR = _repo_root() / "assets" / "patterns"

# Fine enough that a motif tiled at ~10 mm keeps its curves; the sketch scales
# these unit-box points up, so sampling error scales with it.
SAMPLE_STEP_MM = 0.25

Polylines = list[list[tuple[float, float]]]


def list_motifs(bank_dir: Path | None = None) -> list[str]:
    """Names of the SVGs in the bank, sorted. Round-robin order follows this."""
    directory = bank_dir or BANK_DIR
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.[sS][vV][gG]"))


def motif_polylines(name: str, bank_dir: Path | None = None) -> Polylines:
    """Load one motif, normalized to a unit box centred on the origin."""
    directory = bank_dir or BANK_DIR
    matches = [path for path in directory.glob("*.[sS][vV][gG]") if path.stem == name]
    if not matches:
        known = ", ".join(list_motifs(directory)[:5])
        raise ValueError(f"unknown motif {name!r}; bank contains: {known or '(empty)'}")
    return to_unit_box(svg_to_polylines_mm(matches[0], SAMPLE_STEP_MM))


def load_bank(bank_dir: Path | None = None) -> dict[str, Polylines]:
    """Every motif in the bank. Unreadable files are skipped, not fatal.

    A broken SVG dropped in the folder must not take the whole sketch down --
    the operator adds these by hand, mid-session.
    """
    directory = bank_dir or BANK_DIR
    motifs: dict[str, Polylines] = {}
    for name in list_motifs(directory):
        try:
            motifs[name] = motif_polylines(name, directory)
        except Exception:  # noqa: BLE001
            # Deliberately broad: this is a "user drops an arbitrary file into a
            # folder" boundary, and the parse stack (svgpathtools -> minidom ->
            # expat) raises ExpatError, ValueError, OSError and worse depending
            # on how the file is malformed. Enumerating them is a losing game.
            continue
    return motifs


def save_motif(name: str, svg_text: str, *, bank_dir: Path | None = None) -> Path:
    """Write an SVG into the bank under a safe name, and prove it loads back.

    load_bank() deliberately swallows unreadable files, so an unvalidated save would
    fail silently: the file sits in the folder and the motif simply never appears.
    """
    directory = bank_dir or BANK_DIR
    directory.mkdir(parents=True, exist_ok=True)

    # Same character class as _safe_upload_stem in blocks/gcode/direct_svg.py. Inlined
    # rather than imported: it is one regex, and the fallback name differs.
    #
    # Deliberately NOT Path(name).stem: this is a typed-in label, not a path, and .stem
    # would silently throw away everything before a slash -- "shirt 2026/08/05 tribal"
    # arrives as "05 tribal". Sanitizing the whole string keeps the name and still
    # cannot escape the directory, since the result has no separators left.
    raw = name.strip()
    if raw.lower().endswith(".svg"):
        raw = raw[:-4]
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("._-") or "motif"

    # Suffix rather than timestamp: the stem is user-facing, and list_motifs() order is
    # what the sketch's bank generator walks round-robin.
    target = directory / f"{safe}.svg"
    counter = 2
    while target.exists():
        target = directory / f"{safe}-{counter}.svg"
        counter += 1

    target.write_text(svg_text, encoding="utf-8")
    try:
        motif_polylines(target.stem, directory)
    except Exception as error:
        target.unlink(missing_ok=True)
        raise ValueError(f"motif {target.stem!r} does not load back as drawable geometry: {error}") from error
    return target


def to_unit_box(polylines: Polylines) -> Polylines:
    points = [point for polyline in polylines for point in polyline]
    if not points:
        raise ValueError("motif has no drawable geometry")

    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y

    # Uniform scale keeps the aspect ratio; a zero-extent axis (a single
    # straight line) would divide by zero, so fall back to the other one.
    longest = max(width, height)
    if longest <= 0.0:
        raise ValueError("motif collapses to a single point")
    scale = 1.0 / longest

    centre_x = (min_x + max_x) / 2.0
    centre_y = (min_y + max_y) / 2.0
    return [[((x - centre_x) * scale, (y - centre_y) * scale) for x, y in polyline] for polyline in polylines]
