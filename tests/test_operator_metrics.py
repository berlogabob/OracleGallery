"""Burn-down metrics for the operator redesign, so "progress" is a number.

Phases 0 and 1 fixed defects that were individually testable: a preview that disagreed with
the plotter, a layout that clipped itself, controls that saved nothing. What is left is
structural -- seven screens named after Python modules, and seven different ways to put ink on
paper -- and structure is the kind of thing that gets *discussed* rather than measured, then
quietly stays as it was. Three refactors already went by without moving it.

So each number here is counted from the source, and asserted with `==` rather than `<=`, the
same trick `test_gui_design_system.py` uses: a metric that can only be satisfied exactly cannot
be quietly loosened to make a red test green. When a step lands, lower the constant in the same
commit and say why. A constant edited *upward* is a regression being written down as a fact.

Targets, and the plan they come from:
  M1 screens 7 -> 3          DONE -- PRINT / CREATE / SETUP
  M2 python print paths 7 -> 1   one button that says what it does
  M3 web send buttons 2 -> 0     the browser stops being a print client
  M4 cost blocks 3 -> 1          DONE -- one estimator call site behind one helper
  M5 estimator in a view 1 -> 0  DONE -- it moved to blocks/imaging/modes.py
  M6 module-global UI state 6 -> <=2
  M7 duplicate action labels -> 0 per screen   every label names one action, once
  M8 fixed-height iframes 2 -> 0     iframes become canvas-hosted flex
  M9 dead tab strings -> 0           text stops naming tabs that no longer exist
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest
from nicegui import ui

from neje_oracle.blocks.gui import screens
from neje_oracle.blocks.gui.context import GuiContext
from neje_oracle.shared.gui_settings import GuiSettings

REPO = Path(__file__).resolve().parents[1]
GUI = REPO / "src" / "neje_oracle" / "blocks" / "gui"
WORKSPACES = GUI / "workspaces"
WEB = REPO / "echodraw" / "generative-core" / "web"

# --- the trackables -------------------------------------------------------------
SCREENS = 3  # reached target: PRINT / CREATE / SETUP
PRINT_ENTRY_POINTS = 4  # -3: the capture buffer, image conversion and texture all print through render_card
WEB_SEND_BUTTONS = 0  # reached target: the browser is no longer a print client
COST_BLOCKS = 1  # reached target: one estimator call site, behind ui.render_card
ESTIMATOR_IN_VIEW = 0
MODULE_STATE_DICTS = 5  # -1: LATEST deleted; the browser no longer pushes SVG at us
DUPLICATE_ACTION_LABELS_PER_SCREEN = {"print": 1, "create": 8, "setup": 2}
FIXED_HEIGHT_IFRAMES = 2  # generative sketch + texture nodes, each an embedded_page(height_px=...)
DEAD_TAB_STRINGS = 0  # reached target: no operator-facing text names a deleted tab  # "Connection tab" in context.py; the other five markers are already gone

_TAB = re.compile(r"ui\.tab\(")
_PRINT_CALL = re.compile(r"print_svg_payload|print_generative_svg|print_uploaded_svg|print_svg\(")
_SEND_BUTTON = re.compile(r'id="send-btn"')
_COST_CALL = re.compile(r"plot_minutes_for\(|plot_minutes\(")
_ESTIMATOR_DEF = re.compile(r"def plot_minutes")
_STATE_DICT = re.compile(r"(?m)^(STATE|SHEET_STATE|MOTIF_STATE|LATEST|STREAM)\b")
_EMBEDDED_PAGE = re.compile(r"embedded_page\(")

# Operator-facing sentences that name tabs deleted in M1. Exact markers rather than a regex
# over string literals, because "exclude comments and docstrings" is not a regex-shaped job.
_DEAD_TAB_MARKERS = (
    "TESTS tab",
    "Connection tab",
    "on the TESTS",
    "Exhibition controls",
    "Test workspace notes",
    "into CALIBRATION",
)

_SCREEN_BUILDERS: tuple[tuple[str, Callable[[GuiContext], None]], ...] = (
    ("print", screens.build_print),
    ("create", screens.build_create),
    ("setup", screens.build_setup),
)


def _count(pattern: re.Pattern[str], paths: list[Path]) -> int:
    return sum(len(pattern.findall(path.read_text(encoding="utf-8"))) for path in paths)


def _workspace_files() -> list[Path]:
    return sorted(WORKSPACES.glob("*.py"))


def _gui_package_files() -> list[Path]:
    return sorted(GUI.rglob("*.py"))


def _dead_tab_string_count() -> int:
    return sum(
        path.read_text(encoding="utf-8").count(marker) for path in _gui_package_files() for marker in _DEAD_TAB_MARKERS
    )


def _duplicate_label_count(monkeypatch: pytest.MonkeyPatch, build: Callable[[GuiContext], None]) -> int:
    """Headless-build one screen and count distinct visible labels rendered more than once.

    Same harness as test_gui_workspaces.py: NiceGUI elements attach to the implicit default
    page context, so build(ctx) runs for real under a plain ui.column(). Each element's text
    and its Quasar "label" prop are read as a per-element set, because on a ui.button they
    are the same string and would otherwise count every button as its own duplicate.
    """
    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda *a, **k: GuiSettings())
    ctx = GuiContext()
    with ui.column() as root:
        build(ctx)
    labels: list[str] = []
    for element in root.descendants():
        texts = {str(text) for text in (getattr(element, "text", None), element._props.get("label")) if text}
        labels.extend(text for text in texts if len(text) > 1)
    return sum(1 for occurrences in Counter(labels).values() if occurrences > 1)


def _measured_duplicate_labels(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    # A fresh GuiContext and a fresh ui.column per screen, so no screen inherits another's tree.
    return {name: _duplicate_label_count(monkeypatch, build) for name, build in _SCREEN_BUILDERS}


def test_screen_count() -> None:
    """Seven tabs is this machine's P&ID, which ISA-101 says a display must not be."""
    assert _count(_TAB, [GUI / "service.py"]) == SCREENS, (
        "screens changed; set SCREENS to the measured value. Target is 3: PRINT / CREATE / SETUP."
    )


def test_python_print_entry_points() -> None:
    """Seven ways to start a plot, none of which say how they differ from the others."""
    assert _count(_PRINT_CALL, _workspace_files()) == PRINT_ENTRY_POINTS, (
        "print entry points changed; set PRINT_ENTRY_POINTS to the measured value. Target is 1."
    )


def test_web_send_to_plotter_buttons() -> None:
    """Both lie: they POST to a capture buffer and print nothing.

    Worse, they POST to the *same* buffer, so the sketch's stream timer can pick up a texture
    the operator rendered but never meant to send.
    """
    assert _count(_SEND_BUTTON, sorted(WEB.glob("*.html"))) == WEB_SEND_BUTTONS, (
        "web send buttons changed; set WEB_SEND_BUTTONS to the measured value. Target is 0."
    )


def test_duplicated_cost_blocks() -> None:
    """Each copy formats the operator's time estimate slightly differently."""
    assert _count(_COST_CALL, _workspace_files()) == COST_BLOCKS, (
        "cost call sites changed; set COST_BLOCKS to the measured value. Target is 1, behind ui.render_card."
    )


def test_estimator_is_not_defined_in_a_view_module() -> None:
    """Held at zero: it lived in the image workspace and texture had to reach across for it."""
    assert _count(_ESTIMATOR_DEF, _workspace_files()) == ESTIMATOR_IN_VIEW, (
        "the plot estimator is back in a view module; it belongs in blocks/imaging/modes.py"
    )


def test_module_global_ui_state() -> None:
    """Module globals outlive the page but not the process, and are shared across sessions.

    Two browser tabs fight over one dict, and nothing survives a restart.
    """
    assert _count(_STATE_DICT, _workspace_files()) == MODULE_STATE_DICTS, (
        "module-global UI state changed; set MODULE_STATE_DICTS to the measured value. Target is <=2."
    )


def test_duplicate_action_labels_per_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same words on two controls make the operator guess which one they meant.

    Merging seven tabs into three stacked screens stacked their vocabularies too: each old
    workspace brought its own PRINT/refresh/preview buttons, and nothing renamed them when
    they became neighbours. Target is 0 per screen -- every label names one action, once.
    """
    measured = _measured_duplicate_labels(monkeypatch)
    assert measured == DUPLICATE_ACTION_LABELS_PER_SCREEN, (
        f"duplicate labels changed; set DUPLICATE_ACTION_LABELS_PER_SCREEN to {measured}. Target is 0 per screen."
    )


def test_fixed_height_iframes() -> None:
    """A fixed-height iframe scrolls inside the page's scroll, and clips at the wrong size.

    Each embedded_page() call site pins a height in pixels (min-capped at 62vh), so the sketch
    and the node editor get a letterboxed window instead of the room the screen actually has.
    Target is 0 -- the embedded pages become canvas-hosted flex children.
    """
    assert _count(_EMBEDDED_PAGE, _workspace_files()) == FIXED_HEIGHT_IFRAMES, (
        "embedded_page call sites changed; set FIXED_HEIGHT_IFRAMES to the measured value. Target is 0."
    )


def test_dead_tab_strings() -> None:
    """Text that navigates the operator to a tab that no longer exists.

    The seven tabs are gone, but sentences like "on the TESTS tab" survived the merge and now
    give directions to nowhere. Target is 0 -- no string names a deleted destination.
    """
    assert _dead_tab_string_count() == DEAD_TAB_STRINGS, (
        "dead-tab strings changed; set DEAD_TAB_STRINGS to the measured value. Target is 0."
    )


def test_metrics_are_not_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    """A constant set above the real count silently permits regression.

    Same failure mode the design-system ratchets guard: someone 'fixes' a red test by raising
    the number, and the thing it was measuring is never measured again.
    """
    for name, constant, actual in (
        ("SCREENS", SCREENS, _count(_TAB, [GUI / "service.py"])),
        ("PRINT_ENTRY_POINTS", PRINT_ENTRY_POINTS, _count(_PRINT_CALL, _workspace_files())),
        ("WEB_SEND_BUTTONS", WEB_SEND_BUTTONS, _count(_SEND_BUTTON, sorted(WEB.glob("*.html")))),
        ("COST_BLOCKS", COST_BLOCKS, _count(_COST_CALL, _workspace_files())),
        ("ESTIMATOR_IN_VIEW", ESTIMATOR_IN_VIEW, _count(_ESTIMATOR_DEF, _workspace_files())),
        ("MODULE_STATE_DICTS", MODULE_STATE_DICTS, _count(_STATE_DICT, _workspace_files())),
        ("FIXED_HEIGHT_IFRAMES", FIXED_HEIGHT_IFRAMES, _count(_EMBEDDED_PAGE, _workspace_files())),
        ("DEAD_TAB_STRINGS", DEAD_TAB_STRINGS, _dead_tab_string_count()),
    ):
        assert constant == actual, f"{name} is {constant} but {actual} exist -- set it to {actual}"

    measured = _measured_duplicate_labels(monkeypatch)
    assert measured == DUPLICATE_ACTION_LABELS_PER_SCREEN, (
        f"DUPLICATE_ACTION_LABELS_PER_SCREEN is {DUPLICATE_ACTION_LABELS_PER_SCREEN} "
        f"but {measured} exist -- set it to {measured}"
    )
