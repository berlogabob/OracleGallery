"""Ratchets that let the GUI redesign be done in parallel without diverging.

The operator GUI grew feature-first and its styling never had an owner: 226 loose
`.classes()` literals, 28 hand-styled cards, 77 raw hex colours, and a palette that is
*near* the Oracle design system but never equal. No test asserted any of it, so nothing
stopped the drift.

These are **burn-down baselines, not absolutes**. Each migrated workspace lowers a number;
nothing may raise one. That is what makes it safe to hand a workspace each to several
agents at once -- they answer to one shared contract instead of inventing their own.

When you migrate a file, lower the number here in the same commit. A ratchet that is
edited upward is a bug being papered over.
"""

from __future__ import annotations

import re
from pathlib import Path

GUI_ROOT = Path(__file__).resolve().parents[1] / "src" / "neje_oracle" / "blocks" / "gui"

# ui.py owns presentation; tokens.py owns the palette. Everything else is view code that
# should be composing components, not styling.
STYLE_OWNERS = {"ui.py", "tokens.py"}

# Measured on 2026-08-11 at commit 5995e3b, before any migration. These are this
# module's own counts (regex matches, ui.py and tokens.py excluded) -- deliberately
# exact, not the looser grep line-counts, so a single regression trips them.
# -2 classes, -1 hex, -1 card: the generative workspace's hand-styled iframe became
# ui.embedded_page, which the new texture workspace composes too rather than restyling.
#
# +7 classes, +1 card (2026-08-13, SETUP segmentation): the section containers that let a
# segmented switch show one calibration section at a time, and the Advanced expansion
# honestly becoming a card -- an expansion inside a segmented switch is an accordion inside
# tabs, which hides state. New surface with a purpose, not un-migrated styling; the CREATE
# rewrite takes these counts down again.
#
# -6 classes, -1 hex, -1 card: the image workspace's Conversion card became one
# ui.render_card call, and the generative workspace lost the capture readout with the buffer.
# ui.py is a STYLE_OWNER, so what a workspace hands it leaves these counts entirely rather
# than moving behind them -- which is the whole reason the helper lives there.
#
# -10 buttons: the machine rail routes jog, homing, pen and work zero through the three
# action helpers, so the four bare-text controls the audit raised (F-007, F-023) now carry
# the same chrome as the buttons beside them. +8 classes and +2 cards is new surface --
# the rail, and the status bar's state chip / position readout / e-stop gap -- not
# un-migrated surface. The rail also removed a duplicated motion panel from two
# workspaces, and the status bar removed the permanent warning banner.
MAX_RAW_CLASSES = 203
MAX_RAW_HEX = 42
MAX_RAW_CARDS = 17
MAX_RAW_BUTTONS = 9

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _view_files() -> list[Path]:
    return sorted(p for p in GUI_ROOT.rglob("*.py") if p.name not in STYLE_OWNERS)


def _count(pattern: str | re.Pattern[str]) -> dict[str, int]:
    regex = re.compile(pattern) if isinstance(pattern, str) else pattern
    counts: dict[str, int] = {}
    for path in _view_files():
        hits = len(regex.findall(path.read_text(encoding="utf-8")))
        if hits:
            counts[str(path.relative_to(GUI_ROOT))] = hits
    return counts


def _report(counts: dict[str, int]) -> str:
    return ", ".join(f"{name}={n}" for name, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def test_raw_classes_only_shrink() -> None:
    """Every `.classes("...")` outside ui.py is a component that was never extracted."""
    counts = _count(r"\.classes\(")
    total = sum(counts.values())
    assert total <= MAX_RAW_CLASSES, (
        f"raw .classes() rose to {total} (ratchet {MAX_RAW_CLASSES}). Use a ui.py component. {_report(counts)}"
    )


def test_raw_hex_colors_only_shrink() -> None:
    """Colors belong in tokens.py. 22 distinct values are in use where the system has 10."""
    counts = _count(HEX)
    total = sum(counts.values())
    assert total <= MAX_RAW_HEX, (
        f"raw hex colors rose to {total} (ratchet {MAX_RAW_HEX}). Use a token. {_report(counts)}"
    )


def test_raw_cards_only_shrink() -> None:
    """All 28 cards are styled by hand; 23 repeat card + bold title + helper text."""
    counts = _count(r"ui\.card\(")
    total = sum(counts.values())
    assert total <= MAX_RAW_CARDS, (
        f"raw ui.card() rose to {total} (ratchet {MAX_RAW_CARDS}). Use the card component. {_report(counts)}"
    )


def test_raw_buttons_only_shrink() -> None:
    """42% of buttons bypass the button helpers, across 6 distinct styles."""
    counts = _count(r"ui\.button\(")
    total = sum(counts.values())
    assert total <= MAX_RAW_BUTTONS, (
        f"raw ui.button() rose to {total} (ratchet {MAX_RAW_BUTTONS}). Use a button helper. {_report(counts)}"
    )


def test_ratchets_are_not_slack() -> None:
    """A ratchet set above the real count silently permits regression.

    Catches the failure mode where someone 'fixes' a red test by raising the number:
    each ratchet must equal the actual count, so a single regression trips it.
    """
    for name, pattern, ratchet in (
        ("classes", r"\.classes\(", MAX_RAW_CLASSES),
        ("hex", HEX, MAX_RAW_HEX),
        ("cards", r"ui\.card\(", MAX_RAW_CARDS),
        ("buttons", r"ui\.button\(", MAX_RAW_BUTTONS),
    ):
        actual = sum(_count(pattern).values())
        assert ratchet == actual, (
            f"{name} ratchet is {ratchet} but {actual} exist -- set it to {actual}; "
            "slack lets the next regression through unnoticed"
        )


def test_tokens_match_the_flutter_reference() -> None:
    """The operator GUI and the gallery must describe one design system.

    public_gallery/lib/theme/oracle_theme.dart is the faithful implementation of
    assets/Design system/. The operator app used to carry a fourth palette that was near
    but never equal -- rust #8f4f2b vs #8B4513 across 27 uses. Parsing the Dart rather
    than copying the values means a change on either side fails here instead of silently
    splitting the brand again.
    """
    from neje_oracle.blocks.gui import tokens

    dart = (Path(__file__).resolve().parents[1] / "public_gallery/lib/theme/oracle_theme.dart").read_text(
        encoding="utf-8"
    )
    reference = {
        name: "#" + value.upper()
        for name, value in re.findall(r"static const (\w+) = Color\(0xFF([0-9a-fA-F]{6})\)", dart)
    }
    assert reference, "could not parse oracle_theme.dart; has the reference moved?"

    for dart_name, token_name in (
        ("cream", "CREAM"),
        ("paper", "PAPER"),
        ("ink", "INK"),
        ("inkMid", "INK_MID"),
        ("inkMuted", "INK_MUTED"),
        ("rust", "RUST"),
        ("gold", "GOLD"),
        ("goldDim", "GOLD_DIM"),
        ("rule", "RULE"),
        ("voidColor", "VOID"),
    ):
        expected = reference.get(dart_name)
        if expected is None:
            continue
        assert getattr(tokens, token_name) == expected, (
            f"tokens.{token_name} is {getattr(tokens, token_name)} but oracle_theme.dart says {expected}"
        )


def test_style_owners_exist() -> None:
    """The ratchets are meaningless if the files that are allowed to style do not exist."""
    assert (GUI_ROOT / "ui.py").exists()
