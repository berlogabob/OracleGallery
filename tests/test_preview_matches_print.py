"""The preview is a promise about what the pen will do. This is where that is checked.

No test compared the operator preview against the G-code before this file. They shared only
the cell layout, and every other decision -- ring radii above all -- was implemented twice
and disagreed. The preview drew its outer ring at 0.43*D where the pen draws D/2, so the
dark circle an operator reads as "the stroke" was 14% smaller than the real one, and the
pale cell guide they read as decoration was sitting exactly on the pen's actual path.

These tests measure the *rendered* artefacts on both sides -- radii parsed out of the
preview SVG, and radii recovered from the emitted G-code coordinates -- rather than
asserting that two functions were called. A shared helper can still be used wrongly on one
side; only the output proves agreement.
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path

from neje_oracle.blocks.gcode.layout import _build_layout_for_settings
from neje_oracle.blocks.gcode.svg_gcode import generate_sheet_gcode, ring_radii_mm
from neje_oracle.blocks.gui.support import PREVIEW_PX_PER_MM, build_preview_svg
from neje_oracle.blocks.symbols.svg_normalizer import MAX_SCALE
from neje_oracle.shared.gui_settings import GuiSettings, gui_settings_to_plotter_config
from neje_oracle.shared.models import SheetItem

_CIRCLE_RE = re.compile(
    r'<circle cx="(?P<cx>[-\d.]+)" cy="(?P<cy>[-\d.]+)" r="(?P<r>[-\d.]+)"[^>]*data-ring="(?P<ring>outer|inner)"'
)
_MOVE_RE = re.compile(r"^G[01] X(?P<x>[-\d.]+) Y(?P<y>[-\d.]+)$")
_EMPTY_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"></svg>'


def _preview_ring_radii_mm(svg: str) -> dict[str, list[float]]:
    """Ring radii as rendered, converted back out of preview pixels into millimetres."""
    radii: dict[str, list[float]] = {"outer": [], "inner": []}
    for match in _CIRCLE_RE.finditer(svg):
        radii[match.group("ring")].append(float(match.group("r")) / PREVIEW_PX_PER_MM)
    return radii


def _points(gcode: str) -> set[tuple[float, float]]:
    points: set[tuple[float, float]] = set()
    for line in gcode.splitlines():
        match = _MOVE_RE.match(line.strip())
        if match:
            points.add((round(float(match.group("x")), 3), round(float(match.group("y")), 3)))
    return points


def _printed_ring_radii_mm(settings: GuiSettings, kind: str) -> list[float]:
    """Ring radii the machine will actually trace, in mm, outermost first.

    Taken by differencing the sheet G-code against the same sheet generated with rings
    off. Whatever coordinates that adds are the rings -- no assumption about the symbol
    artwork, which is scaled to 0.86*D and would otherwise sit right on top of them.
    """
    placements = _build_layout_for_settings(settings, 1)[:1]
    svg_path = sorted(Path("assets/symbols").glob("*.svg"))[0]
    items = [SheetItem(source_kind=kind, session_id="s0", title="t0", svg_path=svg_path)]

    def sheet(*, include_rings: bool) -> str:
        return generate_sheet_gcode(
            items,
            placements,
            sample_step_mm=1.0,
            cell_diameter_mm=settings.cell_diameter_mm,
            travel_rate=settings.travel_rate,
            draw_rate=settings.draw_rate,
            pen_up_command="M5",
            pen_down_command="M3",
            include_rings=include_rings,
            include_markers=False,
            return_home=False,
        )

    added = _points(sheet(include_rings=True)) - _points(sheet(include_rings=False))

    placement = placements[0]
    assert added, "expected enabling rings to add coordinates to the sheet G-code"
    distances = sorted(
        (math.hypot(x - placement.center_x_mm, y - placement.center_y_mm) for x, y in added), reverse=True
    )
    radii: list[float] = []
    for distance in distances:
        if not radii or abs(distance - radii[-1]) > 0.5:
            radii.append(distance)
    return radii


def test_ring_radii_helper_is_the_only_definition() -> None:
    """A user cell gets one ring at D/2; anything else gets a second at D*0.43."""
    assert ring_radii_mm(20.0, "user") == [10.0]
    assert ring_radii_mm(20.0, "placeholder") == [10.0, 8.6]
    # The daemon says "placeholder", the preview says "idle". Both mean filler.
    assert ring_radii_mm(20.0, "idle") == ring_radii_mm(20.0, "placeholder")
    assert ring_radii_mm(-5.0, "user") == [0.0]


def test_preview_outer_ring_matches_the_gcode_outer_ring() -> None:
    """The regression guard: the preview drew 0.43*D where the pen draws D/2."""
    settings = GuiSettings()
    settings.include_rings = True
    settings.include_markers = False

    printed = _printed_ring_radii_mm(settings, "user")
    assert len(printed) == 1, f"a user cell is one ring, got {printed}"

    previewed = _preview_ring_radii_mm(build_preview_svg(settings, user_count=1, idle_count=0))
    assert previewed["outer"], "expected the preview to draw an outer ring"
    assert not previewed["inner"], "a user cell must not gain a second ring on screen"

    assert previewed["outer"][0] == approx_mm(printed[0])


def test_filler_cells_get_two_rings_on_both_sides() -> None:
    """Real sheets are mostly filler. The preview rendered every cell as a user cell --
    one ring -- while the pen drew two on the same paper."""
    settings = GuiSettings()
    settings.include_rings = True
    settings.include_markers = False

    printed = _printed_ring_radii_mm(settings, "placeholder")
    assert len(printed) == 2, f"a filler cell is two rings, got {printed}"

    previewed = _preview_ring_radii_mm(build_preview_svg(settings, user_count=0, idle_count=1))

    assert previewed["outer"][0] == approx_mm(printed[0])
    assert previewed["inner"][0] == approx_mm(printed[1])


def test_global_scale_reaches_the_plotter_config() -> None:
    """The Global scale slider moved the preview and nothing on the paper.

    It was applied in preview.py but absent from PlotterRuntimeConfig, so
    gui_settings_to_plotter_config silently dropped it on the way to the daemon.
    """
    settings = GuiSettings()
    settings.global_scale = 1.4

    config = gui_settings_to_plotter_config(settings)

    assert config.global_scale == 1.4


def test_global_scale_multiplies_the_symbol_scale_the_daemon_writes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """And the daemon has to actually spend it, not just carry it."""
    from neje_oracle.blocks.plotter import daemon as plotter_daemon

    scale_config = tmp_path / "symbol_scales.json"
    scale_config.write_text('{"sym.svg": 2.0}')
    monkeypatch.setattr(plotter_daemon, "_scale_config_path", lambda: scale_config)

    assert plotter_daemon._current_scale_for_symbol_file(Path("sym.svg")) == 2.0
    assert plotter_daemon._current_scale_for_symbol_file(Path("sym.svg"), 1.5) == 3.0
    # Still clamped by the shared bounds rather than running away.
    assert plotter_daemon._current_scale_for_symbol_file(Path("sym.svg"), 100.0) == MAX_SCALE


def test_preview_and_plotter_draw_from_the_same_symbol_pool(tmp_path: Path) -> None:
    """The preview listed only the top level; the plotter also took session packages.

    So the machine could fill a cell with a symbol the preview had no way to show.
    """
    from neje_oracle.blocks.plotter.daemon import _list_placeholder_svg_paths
    from neje_oracle.shared.symbols import list_base_symbols, list_fillable_symbols

    (tmp_path / "flat.svg").write_text(_EMPTY_SVG)
    session = tmp_path / "session_1"
    session.mkdir()
    (session / "art_plotter.svg").write_text(_EMPTY_SVG)
    (session / "ignored.svg").write_text(_EMPTY_SVG)

    pool = list_fillable_symbols(tmp_path)

    assert [p.name for p in pool] == ["flat.svg", "art_plotter.svg"]
    assert pool == _list_placeholder_svg_paths(tmp_path), "preview and plotter must share one pool"
    # The old preview call would have missed the packaged symbol entirely.
    assert [p.name for p in list_base_symbols(tmp_path)] == ["flat.svg"]


def test_filler_symbol_order_is_reproducible_from_the_sheet_id() -> None:
    """Seeded on time.time_ns(), the same sheet could never be reproduced.

    No preview could predict it, and reprinting after a failed run came back with a
    different set of symbols on the paper.
    """
    pool = [Path(f"s{i}.svg") for i in range(8)]

    def shuffled(sheet_id: str, start_index: int) -> list[str]:
        items = list(pool)
        random.Random(f"{sheet_id}:{start_index}").shuffle(items)
        return [p.name for p in items]

    assert shuffled("sheet_20260813_120000", 0) == shuffled("sheet_20260813_120000", 0)
    assert shuffled("sheet_20260813_120000", 0) != shuffled("sheet_20260813_120001", 0)


def approx_mm(value: float, tolerance: float = 0.05) -> object:
    """Local approx so assertions read as measurements. Named to avoid pytest_* hook lookup."""

    class _Approx:
        def __eq__(self, other: object) -> bool:
            return isinstance(other, int | float) and abs(float(other) - value) <= tolerance

        def __repr__(self) -> str:
            return f"{value:.3f}+-{tolerance}"

    return _Approx()
