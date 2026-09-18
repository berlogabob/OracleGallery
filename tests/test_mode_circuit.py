"""Contract + circuit-specific coverage for the PCB-trace routing mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.circuit import circuit, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_circuit_contract() -> None:
    report = check_mode_contract(circuit, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 32.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_traces_never_share_a_grid_cell() -> None:
    """The occupancy set is the whole collision-avoidance strategy; prove it actually holds.

    Solid black at a coarse pitch is the adversarial case: every cell is eligible, so the
    router spends most of its budget fighting over a small, saturated grid -- exactly where a
    collision would show up if the occupancy check were wrong. A trace's OWN node path (what
    actually enters `occupied`) must never repeat a node another trace already claimed; the
    `junction` a trace may end by touching is deliberately excluded from that path (see
    `_walk`) and is checked separately below -- it must always be a node some other trace
    already owns, never a stray coordinate.
    """
    from neje_oracle.blocks.imaging.art.circuit import _route_board

    tone = _uniform_tone(1.0, size_mm=24.0, cell_mm=1.0)
    traces = _route_board(tone, pitch_mm=2.0, min_darkness=0.05, seed=3, max_traces=2_000)
    assert len(traces) > 0

    seen: set[tuple[int, int]] = set()
    for path, _junction in traces:
        for node in path:
            assert node not in seen, f"node {node} claimed by more than one trace"
            seen.add(node)
    for _path, junction in traces:
        if junction is not None:
            assert junction in seen, f"junction {junction} does not belong to any claimed trace"


def test_segments_are_axis_aligned_or_45_degrees() -> None:
    """Every drawn segment -- trace hops and pad edges alike -- must be one of the 8 grid directions."""
    tone = _uniform_tone(0.6, size_mm=24.0, cell_mm=1.0)
    polylines = circuit(tone, pitch_mm=2.0, seed=5)
    assert len(polylines) > 0
    allowed_degrees = {0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 360.0}
    for polyline in polylines:
        for start, end in zip(polyline, polyline[1:], strict=False):
            dx, dy = end[0] - start[0], end[1] - start[1]
            if math.hypot(dx, dy) < 1e-9:
                continue
            angle = math.degrees(math.atan2(dy, dx)) % 360.0
            assert any(math.isclose(angle, deg, abs_tol=1e-6) for deg in allowed_degrees), (
                f"segment {start}->{end} at {angle} degrees is not axis-aligned or 45 degrees"
            )
