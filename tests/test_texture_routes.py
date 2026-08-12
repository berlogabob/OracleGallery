"""The /api/texture surface, exercised by calling the handlers directly.

No server is started: a Starlette Request is a scope dict plus a receive callable, which is cheap
enough to build here and keeps these tests as fast as the rest of the suite.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pytest
from PIL import Image
from starlette.requests import Request

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode
from neje_oracle.blocks.gui.workspaces import texture as texture_routes
from neje_oracle.blocks.imaging import texture, texture_bank
from neje_oracle.blocks.imaging.modes import MODES


def _request(method: str, body: bytes = b"", query: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": "/api/texture/test",
        "query_string": urlencode(query or {}).encode(),
        "headers": [],
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _post(handler, payload: dict | bytes, query: dict | None = None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return asyncio.run(handler(_request("POST", body, query)))


def _json(response) -> dict:
    return json.loads(response.body)


@pytest.fixture
def bank(tmp_path, monkeypatch):
    """Redirect the bank at tmp_path. conftest deliberately does not sandbox assets/."""
    monkeypatch.setattr(texture_bank, "BANK_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------
def test_preview_returns_a_png():
    response = _post(
        texture_routes._handle_preview,
        {"graph": texture.default_graph(), "width_mm": 100, "height_mm": 100, "cell_mm": 1.0},
    )
    assert response.status_code == 200
    assert response.media_type == "image/png"
    assert response.body[:4] == b"\x89PNG"
    with Image.open(io.BytesIO(response.body)) as image:
        assert image.size == (100, 100)
    assert response.headers["X-Texture-Cols"] == "100"
    assert response.headers["X-Texture-Rows"] == "100"


def test_preview_png_round_trips_to_the_field():
    """Pins the quantisation contract the sketch depends on: it reads this PNG's red channel back
    as a field, so anything lossier than 1/255 would silently shift every mask threshold."""
    graph = texture.default_graph()
    response = _post(texture_routes._handle_preview, {"graph": graph, "width_mm": 60, "height_mm": 60, "cell_mm": 1.0})
    expected = texture.evaluate_field(graph, width_mm=60, height_mm=60, cell_mm=1.0)
    assert np.allclose(texture.png_to_field(response.body), expected, atol=1.0 / 255.0)


def test_preview_clamps_a_punishing_cell_size():
    """The browser must not be able to ask for a 4M-cell evaluation on every slider drag."""
    response = _post(
        texture_routes._handle_preview,
        {"graph": texture.default_graph(), "width_mm": 2000, "height_mm": 2000, "cell_mm": 0.01},
    )
    assert response.status_code == 200
    assert int(response.headers["X-Texture-Cols"]) <= texture_routes.MAX_PREVIEW_CELLS


def test_preview_rejects_a_cyclic_graph():
    graph = {"output": "a", "nodes": {"a": {"kind": "invert", "inputs": {"fac": "a"}}}}
    response = _post(texture_routes._handle_preview, {"graph": graph})
    assert response.status_code == 400
    assert "cycle" in _json(response)["error"]


def test_preview_rejects_an_oversized_body():
    response = _post(texture_routes._handle_preview, b"x" * (texture_routes.MAX_BODY_BYTES + 1))
    assert response.status_code == 400
    assert "too large" in _json(response)["error"]


def test_preview_rejects_junk_with_400_not_500():
    response = _post(texture_routes._handle_preview, b"{ not json")
    assert response.status_code == 400
    assert not _json(response)["ok"]


def test_preview_rejects_an_empty_body():
    assert _post(texture_routes._handle_preview, b"").status_code == 400


def test_preview_rejects_a_non_numeric_extent():
    response = _post(texture_routes._handle_preview, {"graph": texture.default_graph(), "width_mm": "wide"})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# svg
# ---------------------------------------------------------------------------
def test_svg_route_returns_geometry_and_a_cost_line():
    response = _post(
        texture_routes._handle_svg,
        {
            "graph": texture.default_graph(),
            "mode": "hatch",
            "width_mm": 100,
            "height_mm": 100,
            "cell_mm": 1.0,
            "params": {"line_spacing_mm": 1.6},
        },
    )
    payload = _json(response)
    assert payload["ok"]
    assert payload["svg"].startswith("<svg")
    assert 'viewBox="0 0 100 100"' in payload["svg"]
    assert payload["strokes"] > 10
    assert payload["segments"] > payload["strokes"]
    assert payload["draw_mm"] > 0 and payload["travel_mm"] > 0


def test_svg_route_output_is_printable(tmp_path: Path):
    """The end-to-end claim: a texture graph becomes G-code the machine will run."""
    response = _post(
        texture_routes._handle_svg,
        {"graph": texture.default_graph(), "mode": "contour", "width_mm": 80, "height_mm": 80, "cell_mm": 1.0},
    )
    svg_path = tmp_path / "texture.svg"
    svg_path.write_text(_json(response)["svg"])
    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=1.0,
        travel_rate=5000.0,
        draw_rate=1800.0,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )
    assert "G21" in gcode and "G90" in gcode
    assert "M3 S15" in gcode and "M5" in gcode
    assert any(line.startswith("G1 ") for line in gcode.splitlines())


def test_svg_route_surfaces_the_segment_cap_as_advice():
    """A texture is dark everywhere, unlike a photograph, so this cap is reachable by accident. It
    must arrive as operator advice with a 400, not a 500."""
    response = _post(
        texture_routes._handle_svg,
        {
            "graph": texture.default_graph(),
            "mode": "dither",
            "width_mm": 200,
            "height_mm": 200,
            "cell_mm": 0.4,
            "max_segments": 500,
        },
    )
    assert response.status_code == 400
    assert "cell_mm" in _json(response)["error"]


def test_svg_route_rejects_an_unknown_mode():
    response = _post(texture_routes._handle_svg, {"graph": texture.default_graph(), "mode": "sparkle"})
    assert response.status_code == 400
    assert "unknown mode" in _json(response)["error"]


def test_svg_route_rejects_a_param_the_mode_does_not_have():
    response = _post(
        texture_routes._handle_svg,
        {"graph": texture.default_graph(), "mode": "hatch", "params": {"nonsense_mm": 1.0}},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# graphs
# ---------------------------------------------------------------------------
def test_graphs_post_then_get_round_trip(bank):
    saved = _json(_post(texture_routes._handle_graphs_post, {"name": "mist", "graph": texture.default_graph()}))
    assert saved == {"ok": True, "name": "mist"}

    listed = _json(texture_routes._handle_graphs_get(_request("GET")))
    assert listed["graphs"] == ["mist"]

    fetched = _json(texture_routes._handle_graphs_get(_request("GET", query={"name": "mist"})))
    assert fetched["graph"] == texture.TextureGraph.from_dict(texture.default_graph()).to_dict()


def test_graphs_post_reports_the_deduplicated_stem(bank):
    _post(texture_routes._handle_graphs_post, {"name": "mist", "graph": texture.default_graph()})
    second = _json(_post(texture_routes._handle_graphs_post, {"name": "mist", "graph": texture.default_graph()}))
    assert second["name"] == "mist-2"


def test_graphs_post_requires_a_name(bank):
    response = _post(texture_routes._handle_graphs_post, {"graph": texture.default_graph()})
    assert response.status_code == 400
    assert "name" in _json(response)["error"]


def test_graphs_post_rejects_an_invalid_graph(bank):
    response = _post(texture_routes._handle_graphs_post, {"name": "broken", "graph": {"output": "a", "nodes": {}}})
    assert response.status_code == 400
    assert list(bank.glob("*")) == []


def test_graphs_get_unknown_name_is_404(bank):
    assert texture_routes._handle_graphs_get(_request("GET", query={"name": "ghost"})).status_code == 404


# ---------------------------------------------------------------------------
# kinds and field
# ---------------------------------------------------------------------------
def test_kinds_route_lists_the_whole_registry():
    payload = _json(texture_routes._handle_kinds(_request("GET")))
    assert set(payload["kinds"]) == set(texture.NODE_KINDS)
    assert set(payload["blends"]) == set(texture.BLEND_MODES)
    assert set(payload["modes"]) == set(MODES)
    assert payload["limits"]["max_nodes"] == texture.MAX_NODES


def test_field_route_serves_a_saved_graph_as_png(bank):
    texture_bank.save_graph("mist", texture.default_graph(), bank_dir=bank)
    response = texture_routes._handle_field(
        _request("GET", query={"name": "mist", "width_mm": 80, "height_mm": 80, "cell_mm": 1.0, "seed": 3})
    )
    assert response.status_code == 200
    assert response.body[:4] == b"\x89PNG"
    with Image.open(io.BytesIO(response.body)) as image:
        assert image.size == (80, 80)


def test_field_route_unknown_name_is_400(bank):
    assert texture_routes._handle_field(_request("GET", query={"name": "ghost"})).status_code == 400
