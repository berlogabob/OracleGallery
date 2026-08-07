from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode

EXPECTED_GENERATORS = {
    "circles",
    "waves",
    "gridwalk",
    "flowfield",
    "mondrian",
    "tribal",
    "circuit",
    "motiftile",
    "isolines",
    "weave",
}
# Server-backed: renders nothing without /api/text/paths, covered by test_shx_text.py.
SERVER_BACKED_GENERATORS = {"text"}
HARNESS = Path(__file__).resolve().parents[1] / "echodraw" / "generative-core" / "web" / "_harness.mjs"


@pytest.fixture(scope="module")
def generated_patterns(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, int]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    output = tmp_path_factory.mktemp("pattern-generators")
    subprocess.run([node, str(HARNESS), str(output)], check=True)
    manifest = json.loads((output / "manifest.json").read_text())
    return output, manifest


def _gcode(path: Path) -> str:
    return generate_absolute_svg_gcode(
        path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )


def test_all_generators_registered(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    _, manifest = generated_patterns
    assert set(manifest) == EXPECTED_GENERATORS | SERVER_BACKED_GENERATORS
    assert manifest["text"] == 0, "text must be empty without the /api/text route"


def test_every_generator_produces_valid_gcode(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    output, _ = generated_patterns
    for name in EXPECTED_GENERATORS:
        gcode = _gcode(output / f"{name}.svg")
        assert "G21" in gcode
        assert "G90" in gcode
        assert "M3 S15" in gcode
        assert "M5" in gcode
        assert any(line.startswith("G1 ") for line in gcode.splitlines())


def test_no_coordinates_out_of_bounds(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    output, _ = generated_patterns
    coordinate = re.compile(r"^G[01] X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?)")
    for name in EXPECTED_GENERATORS:
        points = [
            (float(match.group(1)), float(match.group(2)))
            for line in _gcode(output / f"{name}.svg").splitlines()
            if (match := coordinate.match(line))
        ]
        assert points, f"No coordinates found for {name}"
        for x, y in points:
            assert -0.01 <= x <= 200.01, f"{name}: X coordinate {x} outside [0, 200] mm"
            assert -0.01 <= y <= 200.01, f"{name}: Y coordinate {y} outside [0, 200] mm"


def test_shape_count_capped(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    _, manifest = generated_patterns
    assert all(count <= 600 for count in manifest.values())


def test_deterministic(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    output, _ = generated_patterns
    for name in EXPECTED_GENERATORS:
        assert (output / f"{name}.svg").read_bytes() == (output / "repeat" / f"{name}.svg").read_bytes()
