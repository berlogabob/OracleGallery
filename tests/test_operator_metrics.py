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
  M1 screens 7 -> 3          PRINT / CREATE / SETUP
  M2 python print paths 7 -> 1   one button that says what it does
  M3 web send buttons 2 -> 0     the browser stops being a print client
  M4 cost blocks 3 -> 1          one estimator call site behind one helper
  M5 estimator in a view 1 -> 0  DONE -- it moved to blocks/imaging/modes.py
  M6 module-global UI state 6 -> <=2
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUI = REPO / "src" / "neje_oracle" / "blocks" / "gui"
WORKSPACES = GUI / "workspaces"
WEB = REPO / "echodraw" / "generative-core" / "web"

# --- the trackables -------------------------------------------------------------
SCREENS = 7
PRINT_ENTRY_POINTS = 5  # -2: print_generative_svg deleted, and image conversion now prints via render_card
WEB_SEND_BUTTONS = 0  # reached target: the browser is no longer a print client
COST_BLOCKS = 2  # -1: image conversion costs through the shared helper now
ESTIMATOR_IN_VIEW = 0
MODULE_STATE_DICTS = 5  # -1: LATEST deleted; the browser no longer pushes SVG at us

_TAB = re.compile(r"ui\.tab\(")
_PRINT_CALL = re.compile(r"print_svg_payload|print_generative_svg|print_uploaded_svg|print_svg\(")
_SEND_BUTTON = re.compile(r'id="send-btn"')
_COST_CALL = re.compile(r"plot_minutes_for\(|plot_minutes\(")
_ESTIMATOR_DEF = re.compile(r"def plot_minutes")
_STATE_DICT = re.compile(r"(?m)^(STATE|SHEET_STATE|MOTIF_STATE|LATEST|STREAM)\b")


def _count(pattern: re.Pattern[str], paths: list[Path]) -> int:
    return sum(len(pattern.findall(path.read_text(encoding="utf-8"))) for path in paths)


def _workspace_files() -> list[Path]:
    return sorted(WORKSPACES.glob("*.py"))


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


def test_metrics_are_not_slack() -> None:
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
    ):
        assert constant == actual, f"{name} is {constant} but {actual} exist -- set it to {actual}"
