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
    "bank",
    "ribbon",
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


def test_bank_field_covers_the_sheet_with_a_heavy_motif(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    """A photo-traced motif must not blank the bottom of the sheet.

    A traced motif is ~60 polylines where a hand-authored one is 1-9, so a full grid
    overruns MAX_TOTAL_SHAPES. Truncating the flat shape list cuts in raster order and
    leaves the bottom edge empty -- measured at 225/282mm before the fix, and 49/282 at
    the finest grid. Dropping whole cells by stride keeps coverage instead.
    """
    output, _ = generated_patterns
    coverage = json.loads((output / "coverage.json").read_text())
    assert coverage, "harness did not emit coverage data"
    for scale, result in coverage.items():
        assert result["shapes"] <= 600, f"scale {scale}: over the shape budget"
        # Canvas is the harness default 200mm; the last row of cells must be drawn.
        assert result["yMax"] > 170, f"scale {scale}: field stops at {result['yMax']}mm of 200"


def test_bank_at_mix_zero_ignores_the_seed(
    generated_patterns: tuple[Path, dict[str, int]],
) -> None:
    """The whole point of the bank: mix 0 is predictable, not merely repeatable.

    Every other generator is only asserted to repeat for a fixed seed. This one
    must produce the same field for *different* seeds, which is what fails if a
    stray rng() call ever reaches the mix-0 branch.
    """
    output, _ = generated_patterns
    assert (output / "mix0-seed12345.svg").read_bytes() == (output / "mix0-seed999.svg").read_bytes()


@pytest.fixture(scope="module")
def field_results(generated_patterns: tuple[Path, dict[str, int]]) -> dict:
    output, _ = generated_patterns
    return json.loads((output / "field.json").read_text())


def test_field_mask_culls_where_the_texture_is_dark(field_results: dict) -> None:
    """The harness field is left half 0, right half 255 over a 200 mm canvas. At threshold 0.5 the
    survivors must all sit in the right half -- which is what fails if the sampler transposes rows
    and columns, or reads the field in pixels instead of mm.
    """
    assert 0 < field_results["kept"] < field_results["total"]
    assert field_results["keptMinX"] >= 100
    assert field_results["keptMaxX"] <= 200


def test_field_sampler_reads_mm_coordinates(field_results: dict) -> None:
    assert field_results["sampleLeft"] == 0
    assert field_results["sampleRight"] == 1


def test_unknown_field_is_a_no_op(field_results: dict) -> None:
    """The cold-cache contract, and the reason regenerateAll() can stay synchronous: while the PNG
    is still in flight the field must mean "no effect", not "cull everything". Getting this wrong
    blanks the canvas on every seed change and looks like the generators broke.
    """
    assert field_results["sampleAbsent"] == 1
    assert field_results["coldKept"] == field_results["total"]


def test_field_targets_do_different_things(field_results: dict) -> None:
    """density culls probabilistically, size scales without culling, invert takes the complement."""
    assert field_results["densityKept"] < field_results["total"]
    assert field_results["sizedCount"] == field_results["total"]
    assert field_results["invertedKept"] + field_results["kept"] == field_results["total"]
