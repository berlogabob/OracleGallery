"""The node editor's graph model, run headlessly in node.

Only the model is covered -- wiring, cycle refusal, deletion, socket geometry. The canvas drawing
itself is not verified here and needs eyes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "echodraw" / "generative-core" / "web"
HARNESS = WEB / "_nodes_harness.mjs"


@pytest.fixture(scope="module")
def editor_results() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    completed = subprocess.run([node, str(HARNESS)], check=True, capture_output=True, text=True, cwd=str(WEB))
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_sockets_wire_to_the_named_input(editor_results):
    assert editor_results["wired"]["a"] != editor_results["wired"]["b"]


@pytest.mark.parametrize(
    "check",
    [
        "cycleRefused",  # the ancestor walk spots the loop
        "cycleNotWritten",  # and connect() refuses to write it
        "selfRefused",  # a node cannot feed itself
        "legalAllowed",  # a legal connection is not caught by the same check
    ],
)
def test_cycles_are_refused_client_side(editor_results, check):
    """Checked in the browser as well as the server so the operator gets instant feedback while
    dragging, rather than a 400 after the fact."""
    assert editor_results[check] is True


@pytest.mark.parametrize("check", ["deletedGone", "uiCleaned", "wireCleaned"])
def test_deleting_a_node_removes_every_reference(editor_results, check):
    """A wire left pointing at a deleted node is a dangling input, which the server rejects on the
    next save -- with an error about a node the operator can no longer see."""
    assert editor_results[check] is True


def test_output_node_cannot_be_deleted(editor_results):
    assert editor_results["outputProtected"] is True


@pytest.mark.parametrize("check", ["socketsSpaced", "socketsInside", "outputOnRight"])
def test_socket_geometry_is_clickable(editor_results, check):
    """Sockets drawn on top of each other or outside the node box are unhittable, and the editor
    then looks broken in a way no error message explains."""
    assert editor_results[check] is True


def test_hit_test_finds_the_socket_it_draws(editor_results):
    assert editor_results["hitFindsOutput"] is True


def test_editor_loads_no_external_scripts():
    """A strict-offline ratchet, in the spirit of test_gui_design_system: the sketch already depends
    on a CDN for p5, and the texture editor must not add a second thing that fails without internet.
    """
    html = (WEB / "nodes.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html
