"""The noise primitives and the properties a plotter depends on."""

from __future__ import annotations

import numpy as np
import pytest

from neje_oracle.blocks.imaging import texture


def _graph(kind: str, **params) -> dict:
    return {"seed": 5, "output": "n", "nodes": {"n": {"kind": kind, "params": params}}}


def _field(graph, *, width_mm=60.0, height_mm=60.0, cell_mm=1.0, seed=None):
    return texture.evaluate_field(graph, width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm, seed=seed)


def test_same_graph_is_deterministic():
    graph = texture.default_graph()
    assert np.array_equal(_field(graph), _field(graph))


def test_seed_changes_the_field():
    graph = _graph("perlin", scale_mm=12.0)
    one = _field(graph, seed=1)
    two = _field(graph, seed=2)
    assert np.abs(one - two).mean() > 0.05
    assert one.std() > 0.01 and two.std() > 0.01


@pytest.mark.parametrize("kind", sorted(texture.NODE_KINDS))
def test_every_kind_evaluates_in_range(kind):
    """Registry-driven, so a kind added later is covered without editing this test."""
    spec = texture.NODE_KINDS[kind]
    nodes: dict[str, dict] = {"n": {"kind": kind, "params": {}, "inputs": {}}}
    for index, socket in enumerate(spec.inputs):
        source = f"src{index}"
        nodes[source] = {"kind": "perlin", "params": {"scale_mm": 10.0 + index, "seed": index}}
        nodes["n"]["inputs"][socket] = source
    field = _field({"seed": 3, "output": "n", "nodes": nodes})
    assert np.isfinite(field).all()
    assert field.min() >= 0.0 and field.max() <= 1.0
    assert field.dtype == np.float32


def test_field_is_scale_invariant_in_mm():
    """Halving cell_mm must sharpen the sampling without moving a feature. This is the property the
    whole plotter contract rests on: cell_mm is a quality dial, not a texture dial."""
    graph = _graph("perlin", scale_mm=20.0, octaves=3)
    coarse = _field(graph, cell_mm=1.0)
    fine = _field(graph, cell_mm=0.5)
    rows, cols = coarse.shape
    pooled = fine[: rows * 2, : cols * 2].reshape(rows, 2, cols, 2).mean(axis=(1, 3))
    assert np.allclose(coarse, pooled, atol=0.03)


def test_field_is_tile_independent():
    """A 60 mm sheet equals the left 60 mm of a 120 mm sheet, exactly. Proves lattice hashing rather
    than a per-call RNG -- with an RNG these would be unrelated pictures."""
    graph = _graph("worley", scale_mm=9.0, metric="f1")
    small = _field(graph, width_mm=60.0, height_mm=60.0, cell_mm=1.0)
    large = _field(graph, width_mm=120.0, height_mm=60.0, cell_mm=1.0)
    assert np.array_equal(small, large[:, :60])


def test_hash_handles_negative_lattice_cells():
    """The NEP 50 guard. A bare Python constant in the hash would promote to int64, the
    two's-complement wrap would vanish, and negative cells would hash into a narrow band."""
    negative = np.arange(-2000, -1000, dtype=np.int32)
    zeros = np.zeros_like(negative)
    values = texture._hash2(negative, zeros, 17)
    assert values.dtype == np.uint32
    assert np.array_equal(values, texture._hash2(negative, zeros, 17))
    # Uniform across the 32-bit range, not clustered: every octile should be populated.
    octiles = np.histogram(values.astype(np.float64) / 2**32, bins=8, range=(0.0, 1.0))[0]
    assert octiles.min() > 0


def test_gradient_table_is_unit_length():
    """Unit length is what bounds 2-D Perlin at sqrt(2)/2 and makes the normalisation exact."""
    lengths = np.hypot(texture._GRADIENTS[:, 0], texture._GRADIENTS[:, 1])
    assert np.allclose(lengths, 1.0, atol=1e-6)


def test_more_octaves_adds_fine_detail():
    coarse = _field(_graph("perlin", scale_mm=25.0, octaves=1))
    detailed = _field(_graph("perlin", scale_mm=25.0, octaves=5))
    assert np.abs(np.diff(detailed, axis=1)).mean() > np.abs(np.diff(coarse, axis=1)).mean()


def test_worley_f1_never_exceeds_f2():
    """The classic bug in this function is updating f1 before reading it for f2, which collapses
    f2 onto f1 and makes the f2-f1 crack metric uniformly zero."""
    x, y = np.meshgrid(np.linspace(0.0, 12.0, 120, dtype=np.float32), np.linspace(0.0, 12.0, 120, dtype=np.float32))
    f1, f2, _ = texture._worley(x, y, 42, jitter=1.0)
    assert (f1 <= f2 + 1e-6).all()
    assert (f2 - f1).max() > 0.2


def test_worley_cracks_have_a_near_zero_set():
    field = _field(_graph("worley", scale_mm=8.0, metric="f2-f1"))
    assert (field < 0.05).mean() > 0.02


def test_worley_cell_metric_is_flat_per_cell():
    """A mosaic, not a gradient: the number of distinct values should track the lattice cells."""
    field = _field(_graph("worley", scale_mm=10.0, metric="cell"), width_mm=100.0, height_mm=100.0, cell_mm=1.0)
    distinct = len(np.unique(field))
    assert 80 <= distinct <= 145  # a 10x10 lattice plus the partly-covered border ring


def test_ridged_differs_from_smooth():
    smooth = _field(_graph("perlin", scale_mm=20.0, ridged=False))
    ridged = _field(_graph("perlin", scale_mm=20.0, ridged=True))
    assert np.abs(smooth - ridged).mean() > 0.05


def test_default_graph_has_real_contrast():
    """fbm's practical spread is about 0.5 +/- 0.12 -- flat mid-grey, which plots as uniform
    hatching and reads as broken. Every shipped preset must end in a ramp that fixes that."""
    field = _field(texture.default_graph(), width_mm=120.0, height_mm=120.0, cell_mm=0.8)
    low, high = np.percentile(field, [5, 95])
    assert high - low > 0.4
