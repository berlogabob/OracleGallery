"""Acceptance tests for the budgeted one-line joiner (shared/pathops.py).

Contract: join_with_budget(polylines, max_lifts, speck_mm=0.0, simplify_mm=0.0)
- polylines: list[list[tuple[float, float]]] in mm; one polyline == one pen-down stroke.
- max_lifts: allowed pen lifts between strokes -> output has at most max_lifts + 1 strokes.
- Merging is greedy shortest-jump-first over stroke endpoints (either end, reversal allowed),
  so the longest jumps are the ones left as pen lifts.
- speck_mm: strokes whose bbox diagonal is below this are dropped before joining.
- simplify_mm: Douglas-Peucker tolerance applied to the joined output.
- Input must never be mutated.
"""

import copy
import random
import time

from neje_oracle.shared.pathops import join_with_budget


def _points(polylines):
    return {point for polyline in polylines for point in polyline}


def _strokes(n, rng, span=200.0):
    out = []
    for _ in range(n):
        x, y = rng.uniform(0, span), rng.uniform(0, span)
        out.append([(x, y), (x + rng.uniform(1, 5), y + rng.uniform(1, 5))])
    return out


def test_empty_input():
    assert join_with_budget([], 0) == []


def test_budget_zero_is_single_stroke():
    strokes = _strokes(5, random.Random(1))
    original = copy.deepcopy(strokes)
    joined = join_with_budget(strokes, 0)
    assert len(joined) == 1
    assert _points(original) <= _points(joined)
    assert strokes == original  # input not mutated


def test_budget_is_respected():
    strokes = _strokes(10, random.Random(2))
    joined = join_with_budget(strokes, 3)
    assert len(joined) <= 4
    assert _points(strokes) <= _points(joined)


def test_ample_budget_is_identity():
    strokes = _strokes(6, random.Random(3))
    assert join_with_budget(strokes, len(strokes) - 1) == strokes
    assert join_with_budget(strokes, 1024) == strokes


def test_shortest_jump_merges_first():
    near_a = [(0.0, 0.0), (1.0, 0.0)]
    near_b = [(1.1, 0.0), (2.0, 0.0)]
    far = [(100.0, 0.0), (101.0, 0.0)]
    joined = join_with_budget([near_a, near_b, far], 1)
    assert len(joined) == 2
    merged = max(joined, key=len)
    assert _points([near_a, near_b]) <= set(merged)
    assert [tuple(p) for p in min(joined, key=len)] == far


def test_speck_drop():
    speck = [(50.0, 50.0), (50.05, 50.05)]
    real = [(0.0, 0.0), (10.0, 0.0)]
    joined = join_with_budget([real, speck], 1024, speck_mm=0.5)
    assert joined == [real]


def test_simplify_collinear():
    wiggly = [[(0.0, 0.0), (1.0, 0.001), (2.0, 0.0), (3.0, 0.001), (4.0, 0.0)]]
    joined = join_with_budget(wiggly, 1024, simplify_mm=0.1)
    assert len(joined) == 1
    assert len(joined[0]) == 2
    assert joined[0][0] == (0.0, 0.0) and joined[0][-1] == (4.0, 0.0)


def test_thousand_strokes_under_two_seconds():
    strokes = _strokes(1000, random.Random(4))
    start = time.monotonic()
    joined = join_with_budget(strokes, 10)
    assert time.monotonic() - start < 2.0
    assert len(joined) <= 11


def test_flat_anisotropic_cloud_joins_fast():
    # A wide, flat hatch (200 x 2 mm) must not degrade the endpoint grid to a
    # single row of overcrowded cells.
    rng = random.Random(9)
    strokes = []
    for _ in range(2000):
        x, y = rng.uniform(0, 200.0), rng.uniform(0, 2.0)
        strokes.append([(x, y), (x + rng.uniform(0.5, 2.0), y)])
    start = time.monotonic()
    joined = join_with_budget(strokes, 10)
    assert time.monotonic() - start < 2.0
    assert len(joined) <= 11
