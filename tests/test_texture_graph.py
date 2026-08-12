"""Graph validation, blend semantics, masking, and coordinate threading."""

from __future__ import annotations

import numpy as np
import pytest

from neje_oracle.blocks.imaging import texture


def _field(graph, *, width_mm=40.0, height_mm=40.0, cell_mm=1.0, seed=None):
    return texture.evaluate_field(graph, width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm, seed=seed)


def _constant(value: float) -> dict:
    return {"kind": "constant", "params": {"value": value}}


def _mix_graph(blend: str, a: float, b: float, *, fac: str | None = None, extra: dict | None = None) -> dict:
    nodes = {
        "a": _constant(a),
        "b": _constant(b),
        "out": {
            "kind": "mix",
            "params": {"blend": blend, "factor": 1.0, "clamp": True},
            "inputs": {"a": "a", "b": "b"},
        },
    }
    if fac is not None:
        nodes["out"]["inputs"]["fac"] = fac
    nodes.update(extra or {})
    return {"seed": 1, "output": "out", "nodes": nodes}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_direct_cycle_is_rejected():
    graph = {
        "output": "a",
        "nodes": {
            "a": {"kind": "invert", "inputs": {"fac": "b"}},
            "b": {"kind": "invert", "inputs": {"fac": "a"}},
        },
    }
    with pytest.raises(ValueError, match="cycle") as error:
        texture.TextureGraph.from_dict(graph)
    assert "a" in str(error.value) and "b" in str(error.value)


def test_self_loop_is_rejected():
    graph = {"output": "a", "nodes": {"a": {"kind": "invert", "inputs": {"fac": "a"}}}}
    with pytest.raises(ValueError, match="cycle"):
        texture.TextureGraph.from_dict(graph)


def test_missing_output_lists_the_nodes_that_exist():
    graph = {"output": "nope", "nodes": {"a": _constant(0.5)}}
    with pytest.raises(ValueError, match="nope") as error:
        texture.TextureGraph.from_dict(graph)
    assert "a" in str(error.value)


def test_unknown_kind_lists_valid_kinds():
    with pytest.raises(ValueError, match="perlin") as error:
        texture.TextureGraph.from_dict({"output": "a", "nodes": {"a": {"kind": "plasma"}}})
    assert "plasma" in str(error.value)


def test_unknown_param_is_rejected():
    graph = {"output": "a", "nodes": {"a": {"kind": "perlin", "params": {"scale_mmm": 4.0}}}}
    with pytest.raises(ValueError, match="scale_mmm"):
        texture.TextureGraph.from_dict(graph)


def test_out_of_range_param_is_rejected():
    graph = {"output": "a", "nodes": {"a": {"kind": "perlin", "params": {"octaves": 40}}}}
    with pytest.raises(ValueError, match="octaves"):
        texture.TextureGraph.from_dict(graph)


def test_bad_enum_lists_the_choices():
    graph = {"output": "a", "nodes": {"a": {"kind": "worley", "params": {"metric": "f9"}}}}
    with pytest.raises(ValueError, match="f2-f1"):
        texture.TextureGraph.from_dict(graph)


def test_dangling_input_is_rejected():
    graph = {"output": "a", "nodes": {"a": {"kind": "invert", "inputs": {"fac": "ghost"}}}}
    with pytest.raises(ValueError, match="ghost"):
        texture.TextureGraph.from_dict(graph)


def test_unwired_required_socket_is_rejected():
    graph = {"output": "a", "nodes": {"a": {"kind": "mix", "inputs": {}}}}
    with pytest.raises(ValueError, match="needs"):
        texture.TextureGraph.from_dict(graph)


def test_unknown_socket_is_rejected():
    graph = {"output": "a", "nodes": {"a": {"kind": "invert", "inputs": {"nope": "b"}}, "b": _constant(0.5)}}
    with pytest.raises(ValueError, match="nope"):
        texture.TextureGraph.from_dict(graph)


def test_half_wired_orphan_nodes_are_allowed():
    """The editor holds these while an operator is still building; refusing to save would make it
    unusable. Only nodes reachable from the output are wire-checked."""
    graph = {
        "output": "out",
        "nodes": {"out": _constant(0.5), "orphan": {"kind": "mix", "inputs": {}}},
    }
    assert _field(graph).mean() == pytest.approx(0.5)


def test_too_many_nodes_is_rejected():
    nodes = {f"n{index}": _constant(0.5) for index in range(texture.MAX_NODES + 1)}
    graph = {"output": "n0", "nodes": nodes}
    with pytest.raises(ValueError, match=str(texture.MAX_NODES)):
        texture.TextureGraph.from_dict(graph)


def test_evaluation_cap_catches_a_mapping_fan_out():
    """Each mapping re-evaluates its whole subtree in a new coordinate frame, so a level feeding two
    differently-mapped branches doubles the work per level -- 28 nodes here, but 2**9 evaluations.
    That is why the cap counts evaluations rather than nodes."""
    nodes: dict = {"src": {"kind": "perlin", "params": {"scale_mm": 5.0}}}
    previous = "src"
    for index in range(9):
        left, right = f"l{index}", f"r{index}"
        nodes[left] = {"kind": "mapping", "params": {"translate_mm": [3.0, 0.0]}, "inputs": {"fac": previous}}
        nodes[right] = {"kind": "mapping", "params": {"translate_mm": [0.0, 7.0]}, "inputs": {"fac": previous}}
        previous = f"m{index}"
        nodes[previous] = {"kind": "mix", "params": {"blend": "add"}, "inputs": {"a": left, "b": right}}
    assert len(nodes) <= texture.MAX_NODES
    with pytest.raises(ValueError, match="evaluations"):
        _field({"output": previous, "nodes": nodes})


def test_oversized_grid_is_rejected_with_advice():
    with pytest.raises(ValueError, match="cell_mm"):
        _field(texture.default_graph(), width_mm=200.0, height_mm=200.0, cell_mm=0.01)


def test_round_trip_preserves_ui_layout():
    original = texture.default_graph()
    graph = texture.TextureGraph.from_dict(original)
    assert texture.TextureGraph.from_dict(graph.to_dict()).to_dict() == graph.to_dict()
    assert graph.to_dict()["ui"] == original["ui"]


# ---------------------------------------------------------------------------
# Blend modes
# ---------------------------------------------------------------------------
_BLEND_CASES = [
    ("mix", 0.25, 0.75, 0.75),
    ("multiply", 0.5, 0.5, 0.25),
    ("add", 0.3, 0.4, 0.7),
    ("add", 0.8, 0.9, 1.0),  # clamped
    ("subtract", 0.8, 0.3, 0.5),
    ("subtract", 0.2, 0.9, 0.0),  # clamped
    ("screen", 0.5, 0.5, 0.75),
    ("overlay", 0.25, 0.75, 0.375),
    ("overlay", 0.75, 0.5, 0.75),
    ("difference", 0.6, 0.6, 0.0),
    ("difference", 0.9, 0.2, 0.7),
    ("minimum", 0.3, 0.7, 0.3),
    ("maximum", 0.3, 0.7, 0.7),
    ("dodge", 0.25, 0.5, 0.5),
    ("dodge", 0.5, 1.0, 1.0),  # divisor floored, then clamped -- not inf
    ("burn", 0.5, 1.0, 0.5),
    ("burn", 0.5, 0.0, 0.0),  # divisor floored, then clamped -- not -inf
]


@pytest.mark.parametrize(("blend", "a", "b", "expected"), _BLEND_CASES)
def test_blend_modes(blend, a, b, expected):
    assert _field(_mix_graph(blend, a, b)).mean() == pytest.approx(expected, abs=1e-4)


def test_every_blend_mode_is_covered_by_a_case():
    """A blend added later must arrive with an assertion, not silently untested."""
    assert {blend for blend, *_ in _BLEND_CASES} == set(texture.BLEND_MODES)


# ---------------------------------------------------------------------------
# Masking -- the fac socket
# ---------------------------------------------------------------------------
def test_fac_zero_returns_a_untouched():
    graph = _mix_graph("multiply", 0.8, 0.1, fac="zero", extra={"zero": _constant(0.0)})
    assert np.array_equal(_field(graph), np.full((40, 40), 0.8, dtype=np.float32))


def test_fac_one_returns_the_blend():
    graph = _mix_graph("multiply", 0.8, 0.5, fac="one", extra={"one": _constant(1.0)})
    assert _field(graph).mean() == pytest.approx(0.4, abs=1e-4)


def test_fac_node_masks_per_cell():
    """A gradient on fac is a mask: the result lerps from `a` to the blend across the sheet."""
    graph = _mix_graph(
        "multiply",
        0.8,
        0.0,
        fac="ramp",
        extra={"ramp": {"kind": "gradient", "params": {"kind": "linear", "angle_deg": 0.0}}},
    )
    field = _field(graph)
    mask = _field({"seed": 1, "output": "ramp", "nodes": {"ramp": graph["nodes"]["ramp"]}})
    assert np.allclose(field, 0.8 + mask * (0.0 - 0.8), atol=1e-5)
    assert field[:, 0].mean() > field[:, -1].mean()  # untouched on the left, fully masked on the right


# ---------------------------------------------------------------------------
# Ramp
# ---------------------------------------------------------------------------
def test_ramp_clamps_outside_its_stops():
    graph = {
        "output": "out",
        "nodes": {
            "src": _constant(0.05),
            "out": {"kind": "ramp", "params": {"stops": [[0.2, 0.3], [0.8, 0.9]]}, "inputs": {"fac": "src"}},
        },
    }
    assert _field(graph).mean() == pytest.approx(0.3, abs=1e-4)


def test_ramp_unsorted_stops_are_normalised():
    """np.interp on unsorted xp returns garbage without complaining, and the editor lets an operator
    drag one stop past another."""
    graph = {
        "output": "out",
        "nodes": {
            "src": _constant(0.5),
            "out": {"kind": "ramp", "params": {"stops": [[0.8, 1.0], [0.2, 0.0]]}, "inputs": {"fac": "src"}},
        },
    }
    assert _field(graph).mean() == pytest.approx(0.5, abs=1e-4)


@pytest.mark.parametrize(("interpolation", "expected"), [("linear", 0.25), ("constant", 0.0), ("ease", 0.15625)])
def test_ramp_interpolations(interpolation, expected):
    graph = {
        "output": "out",
        "nodes": {
            "src": _constant(0.25),
            "out": {
                "kind": "ramp",
                "params": {"stops": [[0.0, 0.0], [1.0, 1.0]], "interpolation": interpolation},
                "inputs": {"fac": "src"},
            },
        },
    }
    assert _field(graph).mean() == pytest.approx(expected, abs=1e-4)


# ---------------------------------------------------------------------------
# Coordinate threading
# ---------------------------------------------------------------------------
def test_identity_mapping_changes_nothing():
    source = {"kind": "perlin", "params": {"scale_mm": 12.0}}
    plain = _field({"seed": 4, "output": "src", "nodes": {"src": source}})
    mapped = _field(
        {
            "seed": 4,
            "output": "out",
            "nodes": {"src": source, "out": {"kind": "mapping", "params": {}, "inputs": {"fac": "src"}}},
        }
    )
    assert np.allclose(plain, mapped, atol=1e-6)


def test_zero_strength_warp_changes_nothing():
    source = {"kind": "perlin", "params": {"scale_mm": 12.0}}
    plain = _field({"seed": 4, "output": "src", "nodes": {"src": source}})
    warped = _field(
        {
            "seed": 4,
            "output": "out",
            "nodes": {
                "src": source,
                "push": _constant(0.5),  # 0.5 maps to a zero offset
                "out": {"kind": "warp", "params": {"strength_mm": 0.0}, "inputs": {"fac": "src", "vector_x": "push"}},
            },
        }
    )
    assert np.allclose(plain, warped, atol=1e-6)


def test_one_node_reached_through_two_frames_is_evaluated_twice():
    """The memo is keyed by (node, frame). Keyed by node id alone -- or by id(frame), which CPython
    recycles -- the mapped branch would return the unmapped array and this difference would be zero:
    a plausible but wrong picture, never a crash.
    """
    graph = {
        "seed": 9,
        "output": "out",
        "nodes": {
            "src": {"kind": "perlin", "params": {"scale_mm": 8.0}},
            "moved": {"kind": "mapping", "params": {"translate_mm": [17.0, 11.0]}, "inputs": {"fac": "src"}},
            "out": {
                "kind": "mix",
                "params": {"blend": "difference", "factor": 1.0},
                "inputs": {"a": "src", "b": "moved"},
            },
        },
    }
    assert _field(graph).mean() > 0.05


def test_mapping_translation_matches_a_shifted_window():
    """Translating by +20 mm must equal sampling the untranslated field 20 mm to the left, exactly.
    Anything approximate here means the child field is being resampled rather than the coordinates
    threaded."""
    source = {"kind": "perlin", "params": {"scale_mm": 15.0, "octaves": 2}}
    mapped = _field(
        {
            "seed": 6,
            "output": "out",
            "nodes": {
                "src": source,
                "out": {"kind": "mapping", "params": {"translate_mm": [20.0, 0.0]}, "inputs": {"fac": "src"}},
            },
        },
        width_mm=40.0,
        height_mm=40.0,
    )
    # The mapping subtracts the translation before sampling, so column i reads the plain field at
    # x = i - 20 mm. Evaluating a 60 mm-wide sheet whose origin sits 20 mm earlier is the same rows.
    plain_wide = _field({"seed": 6, "output": "src", "nodes": {"src": source}}, width_mm=60.0, height_mm=40.0)
    assert np.allclose(mapped[:, 20:], plain_wide[:, :20], atol=1e-6)


def test_warp_displaces_the_field():
    source = {"kind": "perlin", "params": {"scale_mm": 10.0}}
    plain = _field({"seed": 2, "output": "src", "nodes": {"src": source}})
    warped = _field(
        {
            "seed": 2,
            "output": "out",
            "nodes": {
                "src": source,
                "push": {"kind": "perlin", "params": {"scale_mm": 30.0, "seed": 99}},
                "out": {"kind": "warp", "params": {"strength_mm": 8.0}, "inputs": {"fac": "src", "vector_x": "push"}},
            },
        }
    )
    assert np.abs(plain - warped).mean() > 0.02


def test_default_graph_evaluates():
    graph = texture.TextureGraph.from_dict(texture.default_graph())
    tone = texture.evaluate(graph, width_mm=50.0, height_mm=50.0, cell_mm=1.0)
    assert tone.darkness.shape == (50, 50)
    assert tone.darkness.dtype == np.float64
    assert tone.width_mm == 50.0 and tone.cell_mm == 1.0


def test_kinds_schema_covers_the_registry():
    schema = texture.kinds_schema()
    assert set(schema) == set(texture.NODE_KINDS)
    assert schema["mix"]["required"] == ["a", "b"]
    assert "multiply" in schema["mix"]["params"]["blend"]["choices"]


def test_png_round_trip():
    field = _field(texture.default_graph())
    assert np.allclose(texture.png_to_field(texture.field_to_png(field)), field, atol=1.0 / 255.0)


def test_png_rejects_junk():
    with pytest.raises(ValueError, match="texture PNG"):
        texture.png_to_field(b"not a png")
