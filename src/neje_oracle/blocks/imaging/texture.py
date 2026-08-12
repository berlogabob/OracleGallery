"""Procedural texture node graphs: a DAG of noise and mix nodes that evaluates to a ToneGrid.

`load_tone` (modes.py) is the only producer of ToneGrid today, and it needs a picture. This
module is the second producer, and that is the whole design: everything downstream of ToneGrid --
the 11 renderers in MODES, serpentine ordering, the segment cap, polylines_to_svg, the direct-SVG
print path -- consumes a ToneGrid and cannot tell where it came from. A texture graph that
evaluates to one gets all of it for free.

Masking is not a separate concept here, exactly as in Blender: a `mix` node's `fac` socket takes
another node, and that node is the mask.

No new dependency. Perlin and Worley are hand-rolled over numpy for the same reason the distance
transform in modes.py:701 is -- an exact scipy import buys nothing we do not immediately round away.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from .modes import (
    MAX_SEGMENTS_DEFAULT,
    PEN_WIDTH_MM_DEFAULT,
    Polylines,
    ToneGrid,
    polylines_to_svg,
    tone_to_polylines,
)

# A graph is authored by hand in a node editor, so these are generous-but-finite guards against a
# malformed or hostile POST body rather than limits an operator should ever feel.
MAX_NODES = 64
# The cap is on evaluations, not nodes: `mapping` and `warp` re-evaluate their whole subtree in a
# new coordinate frame, so a chain of them multiplies work in a way a node count cannot see.
MAX_EVALUATIONS = 256
# 4M cells is 200x200 mm at 0.1 mm. Past that a six-octave fbm's transient allocations dominate
# the machine rather than the plot.
# ponytail: whole-field evaluation, tile it if a sheet ever needs to exceed this.
MAX_CELLS = 4_000_000

# float32 throughout: at 4M cells the float64 gradient lookups alone are hundreds of MB, and a
# texture that feeds a 0.3 mm pen does not need 15 significant digits.
Field = np.ndarray

_U32 = np.uint32
_TWO_PI = np.float32(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Lattice hashing
# ---------------------------------------------------------------------------
def _hash2(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Two integer lattice coordinates -> a well-avalanched uint32.

    All randomness in this module comes from hashing integer lattice cells rather than from an
    RNG with state. That is what makes a texture tile-independent: the left 100 mm of a 200 mm
    sheet is byte-identical to a 100 mm sheet, so changing the sheet size does not reshuffle the
    picture.

    astype(uint32) on a negative int32 wraps two's-complement, which is exactly what is wanted --
    cell (-1, -1) must hash as stably as (1, 1). Every constant is wrapped in np.uint32 ON PURPOSE:
    under NEP 50 a bare Python int promotes the expression to int64, the wrap-around silently
    disappears, and the result is still a plausible-looking hash with a visibly worse distribution.
    Three multiply-xorshift rounds (an xxhash-class finalizer); two left faint diagonal striping in
    the worley cell metric, which is the most revealing of the consumers.
    """
    h = (ix.astype(np.uint32) * _U32(0x27D4EB2D)) ^ (iy.astype(np.uint32) * _U32(0x165667B1)) ^ _U32(seed & 0xFFFFFFFF)
    h ^= h >> _U32(15)
    h *= _U32(0x2C1B3C6D)
    h ^= h >> _U32(13)
    h *= _U32(0x297A2D39)
    h ^= h >> _U32(16)
    return h


def _mix_seed(graph_seed: int, node_seed: int) -> int:
    """Fold the graph's seed into a node's own, so re-seeding a whole graph moves every node."""
    return int((int(graph_seed) * 0x9E3779B1 + int(node_seed) * 0x85EBCA6B) & 0xFFFFFFFF)


# ---------------------------------------------------------------------------
# Perlin / fbm
# ---------------------------------------------------------------------------
# 8 unit gradients: 4 axis-aligned + 4 diagonal. Unit length is what bounds 2-D Perlin at
# +/- sqrt(2)/2, which makes the normalisation below exact rather than a fudge factor.
_R = 0.7071067811865476
_GRADIENTS = np.array(
    [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (_R, _R), (-_R, _R), (_R, -_R), (-_R, -_R)],
    dtype=np.float32,
)
_PERLIN_NORM = np.float32(math.sqrt(2.0))


def _fade(t: np.ndarray) -> np.ndarray:
    """Perlin's improved quintic. The original cubic leaves second-derivative seams on the lattice."""
    return t * t * t * (t * (t * np.float32(6.0) - np.float32(15.0)) + np.float32(10.0))


def _perlin2(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    """Gradient noise. x and y are in LATTICE units (mm / scale_mm). Returns float32 in [-1, 1]."""
    x0 = np.floor(x)
    y0 = np.floor(y)
    ix = x0.astype(np.int32)
    iy = y0.astype(np.int32)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    u = _fade(fx)
    v = _fade(fy)
    one = np.float32(1.0)

    def corner(cx: np.ndarray, cy: np.ndarray, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
        gradient = _GRADIENTS[_hash2(cx, cy, seed) & _U32(7)]
        return gradient[..., 0] * dx + gradient[..., 1] * dy

    n00 = corner(ix, iy, fx, fy)
    n10 = corner(ix + 1, iy, fx - one, fy)
    n01 = corner(ix, iy + 1, fx, fy - one)
    n11 = corner(ix + 1, iy + 1, fx - one, fy - one)
    nx0 = n00 + u * (n10 - n00)
    nx1 = n01 + u * (n11 - n01)
    return (nx0 + v * (nx1 - nx0)) * _PERLIN_NORM


def _fbm(
    x: np.ndarray,
    y: np.ndarray,
    seed: int,
    *,
    octaves: int,
    lacunarity: float,
    gain: float,
    ridged: bool,
) -> np.ndarray:
    """Fractal sum of Perlin octaves, in [-1, 1].

    Accumulated in place. Collecting the octaves into a list and summing costs octaves x the peak
    memory for an identical result -- at 0.1 mm over 200 mm that is the difference between roughly
    30 MB and 200 MB resident.
    """
    total = np.zeros(x.shape, dtype=np.float32)
    amplitude = np.float32(1.0)
    normaliser = np.float32(0.0)
    frequency = np.float32(1.0)
    for octave in range(int(octaves)):
        layer = _perlin2(x * frequency, y * frequency, seed + octave * 0x9E3779B1)
        if ridged:
            # Fold the field at zero and square the ridge: what turns smooth clouds into dunes.
            layer = np.float32(1.0) - np.abs(layer)
            layer = layer * layer * np.float32(2.0) - np.float32(1.0)
        total += amplitude * layer
        normaliser += amplitude
        amplitude *= np.float32(gain)
        frequency *= np.float32(lacunarity)
    return total / max(normaliser, np.float32(1e-6))


# ---------------------------------------------------------------------------
# Worley / Voronoi
# ---------------------------------------------------------------------------
def _worley(x: np.ndarray, y: np.ndarray, seed: int, *, jitter: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """F1, F2 and cell id over a 3x3 lattice neighbourhood. x and y are in lattice units.

    3x3 is exact for F1 whenever jitter <= 1, because a jittered feature point never leaves its own
    cell -- which is why jitter is clamped to 1.0 rather than merely documented. F2 can in principle
    come from the 5x5 ring; the case is rare, the error is bounded by one cell width, and 25
    neighbours is 2.8x the work for an artefact invisible at pen resolution.
    ponytail: widen to 5x5 if the f2-f1 "cracks" preset ever shows lattice seams.
    """
    ix = np.floor(x).astype(np.int32)
    iy = np.floor(y).astype(np.int32)
    xf = x.astype(np.float32)
    yf = y.astype(np.float32)
    # 9.0 is unreachable in lattice units over a 3x3 neighbourhood (max ~2.9), so it acts as
    # +inf without needing to special-case the first comparison.
    f1 = np.full(x.shape, np.float32(9.0))
    f2 = np.full(x.shape, np.float32(9.0))
    cell = np.zeros(x.shape, dtype=np.uint32)
    amount = np.float32(min(1.0, max(0.0, float(jitter))))
    half = np.float32(0.5)
    scale16 = np.float32(65535.0)

    for offset_y in (-1, 0, 1):
        for offset_x in (-1, 0, 1):
            cx = ix + offset_x
            cy = iy + offset_y
            h = _hash2(cx, cy, seed)
            # One hash, two offsets: after three avalanche rounds the high and low 16 bits are
            # independently uniform, so a second hash call buys nothing.
            jx = ((h >> _U32(16)) & _U32(0xFFFF)).astype(np.float32) / scale16
            jy = (h & _U32(0xFFFF)).astype(np.float32) / scale16
            px = cx.astype(np.float32) + half + amount * (jx - half)
            py = cy.astype(np.float32) + half + amount * (jy - half)
            distance = np.hypot(xf - px, yf - py)
            closer = distance < f1
            # Reads the OLD f1 on purpose: when this point beats the incumbent, the incumbent
            # becomes F2. Updating f1 first is the classic bug here and silently yields f2 == f1.
            f2 = np.where(closer, f1, np.minimum(f2, distance))
            cell = np.where(closer, h, cell)
            f1 = np.minimum(f1, distance)
    return f1, f2, cell


# ---------------------------------------------------------------------------
# Blend modes
# ---------------------------------------------------------------------------
def _blend_overlay(a: Field, b: Field) -> Field:
    return np.where(
        a < np.float32(0.5), np.float32(2.0) * a * b, np.float32(1.0) - np.float32(2.0) * (1.0 - a) * (1.0 - b)
    )


BLEND_MODES: dict[str, Callable[[Field, Field], Field]] = {
    "mix": lambda a, b: b,
    "multiply": lambda a, b: a * b,
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "screen": lambda a, b: np.float32(1.0) - (np.float32(1.0) - a) * (np.float32(1.0) - b),
    "overlay": _blend_overlay,
    "difference": lambda a, b: np.abs(a - b),
    "minimum": np.minimum,
    "maximum": np.maximum,
    # 1e-6 floors the divisor: dodge at b == 1 and burn at b == 0 are both a division by zero, and
    # the resulting inf/nan would propagate through every downstream node instead of clipping.
    "dodge": lambda a, b: a / np.clip(np.float32(1.0) - b, np.float32(1e-6), None),
    "burn": lambda a, b: np.float32(1.0) - (np.float32(1.0) - a) / np.clip(b, np.float32(1e-6), None),
}


# ---------------------------------------------------------------------------
# Parameter and node specifications
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParamSpec:
    kind: str  # float | int | bool | enum | vec2 | stops
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    help: str = ""


def _coerce(name: str, spec: ParamSpec, value: Any) -> Any:
    """Coerce and range-check one param. Raises rather than clamping: a slider cannot produce an
    out-of-range value, so one that arrives is a bug in a hand-edited graph and should say so."""
    if spec.kind in ("float", "int"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"param {name!r} must be a number, got {value!r}") from None
        if not math.isfinite(number):
            raise ValueError(f"param {name!r} must be finite, got {value!r}")
        if spec.minimum is not None and number < spec.minimum:
            raise ValueError(f"param {name!r} must be >= {spec.minimum}, got {number}")
        if spec.maximum is not None and number > spec.maximum:
            raise ValueError(f"param {name!r} must be <= {spec.maximum}, got {number}")
        return int(round(number)) if spec.kind == "int" else number
    if spec.kind == "bool":
        if not isinstance(value, bool | int) or isinstance(value, float):
            raise ValueError(f"param {name!r} must be true or false, got {value!r}")
        return bool(value)
    if spec.kind == "enum":
        text = str(value)
        if text not in spec.choices:
            raise ValueError(f"param {name!r} must be one of {', '.join(spec.choices)}; got {text!r}")
        return text
    if spec.kind == "vec2":
        if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 2:
            raise ValueError(f"param {name!r} must be a pair of numbers, got {value!r}")
        try:
            pair = (float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            raise ValueError(f"param {name!r} must be a pair of numbers, got {value!r}") from None
        if not all(math.isfinite(component) for component in pair):
            raise ValueError(f"param {name!r} must be finite, got {value!r}")
        return pair
    if spec.kind == "stops":
        if not isinstance(value, Sequence) or isinstance(value, str) or not value:
            raise ValueError(f"param {name!r} must be a non-empty list of [position, value] pairs")
        stops = []
        for entry in value:
            if not isinstance(entry, Sequence) or isinstance(entry, str) or len(entry) != 2:
                raise ValueError(f"param {name!r} entries must be [position, value] pairs, got {entry!r}")
            try:
                position, level = float(entry[0]), float(entry[1])
            except (TypeError, ValueError):
                raise ValueError(f"param {name!r} entries must be numbers, got {entry!r}") from None
            if not (math.isfinite(position) and math.isfinite(level)):
                raise ValueError(f"param {name!r} entries must be finite, got {entry!r}")
            stops.append((position, level))
        # Sorted here rather than trusted: the editor lets an operator drag one stop past another,
        # and np.interp on unsorted xp returns garbage without complaining.
        return tuple(sorted(stops))
    raise ValueError(f"unknown param kind {spec.kind!r}")


@dataclass(frozen=True)
class NodeKind:
    name: str
    inputs: tuple[str, ...]
    required: tuple[str, ...]
    params: Mapping[str, ParamSpec]
    evaluate: Callable[..., Field]
    help: str


@dataclass(frozen=True)
class NodeSpec:
    kind: str
    params: Mapping[str, Any]
    inputs: Mapping[str, str]  # socket name -> node id


# ---------------------------------------------------------------------------
# Coordinate frames
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Frame:
    """The mm coordinates a subtree is sampled at.

    `mapping` and `warp` do not transform a field, they transform the coordinates their subtree is
    sampled at. Resampling a child field afterwards would be lossy and grid-aligned; threading
    coordinates is exact and stays resolution-independent.
    """

    x: np.ndarray
    y: np.ndarray
    index: int


class _Context:
    def __init__(self, graph: TextureGraph, *, seed: int, width_mm: float, height_mm: float) -> None:
        self.graph = graph
        self.seed = seed
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.memo: dict[tuple[str, int], Field] = {}
        self.evaluations = 0
        self._frames = 0

    def new_frame(self, x: np.ndarray, y: np.ndarray) -> _Frame:
        self._frames += 1
        return _Frame(x, y, self._frames)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------
Resolve = Callable[..., "Field | None"]


def _node_perlin(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    scale = np.float32(params["scale_mm"])
    value = _fbm(
        frame.x / scale,
        frame.y / scale,
        _mix_seed(ctx.seed, params["seed"]),
        octaves=params["octaves"],
        lacunarity=params["lacunarity"],
        gain=params["gain"],
        ridged=params["ridged"],
    )
    return np.float32(0.5) * (value + np.float32(1.0))


def _node_worley(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    scale = np.float32(params["scale_mm"])
    f1, f2, cell = _worley(
        frame.x / scale,
        frame.y / scale,
        _mix_seed(ctx.seed, params["seed"]),
        jitter=params["jitter"],
    )
    metric = params["metric"]
    if metric == "f1":
        # 1.5 lattice units is the furthest a point can sit from its nearest feature at jitter 1.
        return f1 / np.float32(1.5)
    if metric == "f2":
        return f2 / np.float32(2.2)
    if metric == "f2-f1":
        return f2 - f1
    return cell.astype(np.float32) / np.float32(4294967295.0)


def _node_gradient(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    centre_x = np.float32(params["center"][0] * ctx.width_mm)
    centre_y = np.float32(params["center"][1] * ctx.height_mm)
    if params["kind"] == "linear":
        angle = math.radians(params["angle_deg"])
        dx, dy = np.float32(math.cos(angle)), np.float32(math.sin(angle))
        projected = frame.x * dx + frame.y * dy
        # Normalise by the sheet's own extent along the gradient direction, so a linear ramp always
        # spans 0..1 across the paper whatever angle it is at.
        span = abs(ctx.width_mm * float(dx)) + abs(ctx.height_mm * float(dy))
        low = min(0.0, ctx.width_mm * float(dx)) + min(0.0, ctx.height_mm * float(dy))
        return (projected - np.float32(low)) / np.float32(max(span, 1e-6))
    radius = np.float32(max(params["radius_mm"], 1e-6))
    distance = np.hypot(frame.x - centre_x, frame.y - centre_y) / radius
    if params["kind"] == "radial":
        return np.float32(1.0) - distance
    # spherical: the same falloff eased at both ends, so a vignette has no visible hard edge.
    eased = np.clip(np.float32(1.0) - distance, np.float32(0.0), np.float32(1.0))
    return eased * eased * (np.float32(3.0) - np.float32(2.0) * eased)


def _node_checker(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    size = np.float32(params["size_mm"])
    angle = math.radians(params["angle_deg"])
    cos_a, sin_a = np.float32(math.cos(angle)), np.float32(math.sin(angle))
    u = (frame.x * cos_a + frame.y * sin_a) / size
    v = (-frame.x * sin_a + frame.y * cos_a) / size
    return ((np.floor(u).astype(np.int32) + np.floor(v).astype(np.int32)) & 1).astype(np.float32)


def _node_wave(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    scale = np.float32(params["scale_mm"])
    if params["kind"] == "bands":
        angle = math.radians(params["angle_deg"])
        phase = (frame.x * np.float32(math.cos(angle)) + frame.y * np.float32(math.sin(angle))) / scale
    else:
        centre_x = np.float32(0.5 * ctx.width_mm)
        centre_y = np.float32(0.5 * ctx.height_mm)
        phase = np.hypot(frame.x - centre_x, frame.y - centre_y) / scale
    distortion = float(params["distortion"])
    if distortion:
        # Distortion perturbs the phase, not the output: that is what bends the bands into a
        # marble/wood grain instead of merely fading them.
        phase = phase + np.float32(distortion) * _fbm(
            frame.x / scale,
            frame.y / scale,
            _mix_seed(ctx.seed, params["seed"]),
            octaves=params["detail"],
            lacunarity=2.0,
            gain=0.5,
            ridged=False,
        )
    return np.float32(0.5) * (np.sin(phase * _TWO_PI) + np.float32(1.0))


def _node_constant(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    return np.full(frame.x.shape, np.float32(params["value"]), dtype=np.float32)


def _node_mix(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    a = resolve("a")
    b = resolve("b")
    blended = BLEND_MODES[params["blend"]](a, b)
    factor = np.float32(params["factor"])
    fac = resolve("fac")
    weight = factor if fac is None else fac * factor
    # Blender's Mix semantics, and the whole masking story: fac == 0 is `a` untouched, fac == 1 is
    # the blend, and a NODE on fac is a mask.
    result = a + weight * (blended - a)
    return np.clip(result, np.float32(0.0), np.float32(1.0)) if params["clamp"] else result


def _node_ramp(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    fac = resolve("fac")
    stops = params["stops"]
    positions = np.array([position for position, _ in stops], dtype=np.float32)
    levels = np.array([level for _, level in stops], dtype=np.float32)
    interpolation = params["interpolation"]
    if interpolation == "constant":
        # searchsorted gives the index of the stop at or below fac; clip handles below-first.
        index = np.clip(np.searchsorted(positions, fac, side="right") - 1, 0, len(stops) - 1)
        return levels[index]
    if interpolation == "linear":
        return np.interp(fac, positions, levels).astype(np.float32)
    # ease: smoothstep the local t between the bracketing stops, so a ramp used as a mask has no
    # visible crease where the two stops meet.
    upper = np.clip(np.searchsorted(positions, fac, side="right"), 1, len(stops) - 1)
    lower = upper - 1
    span = np.maximum(positions[upper] - positions[lower], np.float32(1e-6))
    t = np.clip((fac - positions[lower]) / span, np.float32(0.0), np.float32(1.0))
    t = t * t * (np.float32(3.0) - np.float32(2.0) * t)
    return levels[lower] + t * (levels[upper] - levels[lower])


def _node_math(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    a = resolve("a")
    b = resolve("b")
    if b is None:
        b = np.full(a.shape, np.float32(params["value"]), dtype=np.float32)
    operation = params["op"]
    if operation == "add":
        result = a + b
    elif operation == "multiply":
        result = a * b
    elif operation == "power":
        # a is already clipped to [0, 1] upstream, so the negative-base branch cannot arise.
        result = np.power(np.maximum(a, np.float32(0.0)), b)
    elif operation == "absolute":
        result = np.abs(a)
    elif operation == "clamp":
        result = np.clip(a, np.float32(0.0), np.float32(1.0))
    elif operation == "greater":
        result = (a > b).astype(np.float32)
    elif operation == "less":
        result = (a < b).astype(np.float32)
    else:
        result = np.sqrt(np.maximum(a, np.float32(0.0)))
    return np.clip(result, np.float32(0.0), np.float32(1.0)) if params["clamp"] else result


def _node_invert(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    return np.float32(1.0) - resolve("fac")


def _node_mapping(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    angle = math.radians(params["rotate_deg"])
    cos_a, sin_a = np.float32(math.cos(angle)), np.float32(math.sin(angle))
    scale_x = np.float32(max(abs(params["scale"][0]), 1e-6))
    scale_y = np.float32(max(abs(params["scale"][1]), 1e-6))
    centre_x = np.float32(0.5 * ctx.width_mm)
    centre_y = np.float32(0.5 * ctx.height_mm)
    # Inverse transform: moving the texture by +translate means sampling at -translate. Rotation is
    # about the sheet centre so that spinning a texture does not also slide it off the paper.
    px = frame.x - centre_x - np.float32(params["translate_mm"][0])
    py = frame.y - centre_y - np.float32(params["translate_mm"][1])
    rx = (px * cos_a + py * sin_a) / scale_x
    ry = (-px * sin_a + py * cos_a) / scale_y
    return resolve("fac", ctx.new_frame(rx + centre_x, ry + centre_y))


def _node_warp(frame: _Frame, params: Mapping[str, Any], resolve: Resolve, ctx: _Context) -> Field:
    # The displacement sources are read in the INCOMING frame; only `fac` moves.
    vector_x = resolve("vector_x")
    vector_y = resolve("vector_y")
    if vector_y is None:
        vector_y = vector_x
    strength = np.float32(params["strength_mm"])
    two = np.float32(2.0)
    one = np.float32(1.0)
    offset_x = strength * (two * vector_x - one)
    offset_y = strength * (two * vector_y - one)
    return resolve("fac", ctx.new_frame(frame.x + offset_x, frame.y + offset_y))


_SEED_PARAM = ParamSpec("int", 0, minimum=0, maximum=0xFFFFFFFF, help="Per-node seed, folded with the graph seed.")

NODE_KINDS: dict[str, NodeKind] = {
    "perlin": NodeKind(
        name="perlin",
        inputs=(),
        required=(),
        params={
            "scale_mm": ParamSpec("float", 30.0, minimum=0.01, maximum=10_000.0, help="Feature size in mm."),
            "octaves": ParamSpec("int", 4, minimum=1, maximum=8, help="Detail levels. Each doubles the work."),
            "lacunarity": ParamSpec("float", 2.0, minimum=1.0, maximum=8.0, help="Frequency step per octave."),
            "gain": ParamSpec("float", 0.5, minimum=0.0, maximum=1.0, help="Amplitude step per octave."),
            "ridged": ParamSpec("bool", False, help="Fold at zero for dune and ridge shapes."),
            "seed": _SEED_PARAM,
        },
        evaluate=_node_perlin,
        help="Fractal Perlin noise. Clouds, smoke, organic tone.",
    ),
    "worley": NodeKind(
        name="worley",
        inputs=(),
        required=(),
        params={
            "scale_mm": ParamSpec("float", 15.0, minimum=0.01, maximum=10_000.0, help="Cell size in mm."),
            "metric": ParamSpec(
                "enum", "f1", choices=("f1", "f2", "f2-f1", "cell"), help="f2-f1 gives cracks; cell gives a mosaic."
            ),
            "jitter": ParamSpec("float", 1.0, minimum=0.0, maximum=1.0, help="How far cell points wander."),
            "seed": _SEED_PARAM,
        },
        evaluate=_node_worley,
        help="Voronoi/cellular noise. Scales, stones, cracks.",
    ),
    "gradient": NodeKind(
        name="gradient",
        inputs=(),
        required=(),
        params={
            "kind": ParamSpec("enum", "linear", choices=("linear", "radial", "spherical")),
            "angle_deg": ParamSpec("float", 0.0, minimum=-360.0, maximum=360.0, help="Linear direction."),
            "center": ParamSpec("vec2", (0.5, 0.5), help="Radial centre, as a fraction of the sheet."),
            "radius_mm": ParamSpec("float", 80.0, minimum=0.01, maximum=10_000.0),
        },
        evaluate=_node_gradient,
        help="Linear or radial ramp across the sheet. The usual vignette mask.",
    ),
    "checker": NodeKind(
        name="checker",
        inputs=(),
        required=(),
        params={
            "size_mm": ParamSpec("float", 10.0, minimum=0.01, maximum=10_000.0),
            "angle_deg": ParamSpec("float", 0.0, minimum=-360.0, maximum=360.0),
        },
        evaluate=_node_checker,
        help="Hard checkerboard. Useful as a mask and for calibration.",
    ),
    "wave": NodeKind(
        name="wave",
        inputs=(),
        required=(),
        params={
            "kind": ParamSpec("enum", "bands", choices=("bands", "rings")),
            "scale_mm": ParamSpec("float", 20.0, minimum=0.01, maximum=10_000.0),
            "angle_deg": ParamSpec("float", 0.0, minimum=-360.0, maximum=360.0),
            "distortion": ParamSpec("float", 0.0, minimum=0.0, maximum=20.0, help="Noise added to the phase."),
            "detail": ParamSpec("int", 2, minimum=1, maximum=8, help="Octaves in the distortion."),
            "seed": _SEED_PARAM,
        },
        evaluate=_node_wave,
        help="Sine bands or rings, optionally bent by noise. Wood, marble, weave.",
    ),
    "constant": NodeKind(
        name="constant",
        inputs=(),
        required=(),
        params={"value": ParamSpec("float", 0.5, minimum=0.0, maximum=1.0)},
        evaluate=_node_constant,
        help="A flat value. Handy on a mix factor while wiring.",
    ),
    "mix": NodeKind(
        name="mix",
        inputs=("a", "b", "fac"),
        required=("a", "b"),
        params={
            "blend": ParamSpec("enum", "mix", choices=tuple(BLEND_MODES)),
            "factor": ParamSpec("float", 1.0, minimum=0.0, maximum=1.0),
            "clamp": ParamSpec("bool", True),
        },
        evaluate=_node_mix,
        help="Combine two textures. Wire a texture into fac to use it as a mask.",
    ),
    "ramp": NodeKind(
        name="ramp",
        inputs=("fac",),
        required=("fac",),
        params={
            "stops": ParamSpec("stops", ((0.0, 0.0), (1.0, 1.0)), help="[position, value] pairs."),
            "interpolation": ParamSpec("enum", "linear", choices=("linear", "constant", "ease")),
        },
        evaluate=_node_ramp,
        help="Remap levels. This is what turns flat mid-grey noise into contrast.",
    ),
    "math": NodeKind(
        name="math",
        inputs=("a", "b"),
        required=("a",),
        params={
            "op": ParamSpec(
                "enum", "multiply", choices=("add", "multiply", "power", "absolute", "clamp", "greater", "less", "sqrt")
            ),
            "value": ParamSpec("float", 0.5, minimum=-100.0, maximum=100.0, help="Used when b is unwired."),
            "clamp": ParamSpec("bool", True),
        },
        evaluate=_node_math,
        help="Per-cell arithmetic. greater/less threshold a field into a hard mask.",
    ),
    "invert": NodeKind(
        name="invert",
        inputs=("fac",),
        required=("fac",),
        params={},
        evaluate=_node_invert,
        help="1 - value.",
    ),
    "mapping": NodeKind(
        name="mapping",
        inputs=("fac",),
        required=("fac",),
        params={
            "translate_mm": ParamSpec("vec2", (0.0, 0.0)),
            "rotate_deg": ParamSpec("float", 0.0, minimum=-360.0, maximum=360.0),
            "scale": ParamSpec("vec2", (1.0, 1.0)),
        },
        evaluate=_node_mapping,
        help="Move, rotate or stretch everything beneath it.",
    ),
    "warp": NodeKind(
        name="warp",
        inputs=("fac", "vector_x", "vector_y"),
        required=("fac", "vector_x"),
        params={"strength_mm": ParamSpec("float", 5.0, minimum=0.0, maximum=500.0)},
        evaluate=_node_warp,
        help="Displace the sample position by another texture. Melts and swirls.",
    ),
}


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------
def _jsonable(value: Any) -> Any:
    """Tuples become lists, recursively. json.dumps does this on the way out anyway; doing it here
    keeps to_dict() == json round trip of to_dict(), which the bank and the routes both rely on."""
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class TextureGraph:
    nodes: Mapping[str, NodeSpec]
    output: str
    seed: int
    ui: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TextureGraph:
        """Parse and fully validate. Every check here runs before a single array is allocated, so a
        malformed graph costs microseconds and produces a message an operator can act on."""
        if not isinstance(data, Mapping):
            raise ValueError("texture graph must be an object")
        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, Mapping) or not raw_nodes:
            raise ValueError("texture graph must have a non-empty 'nodes' object")
        if len(raw_nodes) > MAX_NODES:
            raise ValueError(f"texture graph has {len(raw_nodes)} nodes, exceeding MAX_NODES={MAX_NODES}")

        nodes: dict[str, NodeSpec] = {}
        for node_id, raw in raw_nodes.items():
            if not isinstance(raw, Mapping):
                raise ValueError(f"node {node_id!r} must be an object")
            kind_name = str(raw.get("kind", ""))
            kind = NODE_KINDS.get(kind_name)
            if kind is None:
                raise ValueError(
                    f"node {node_id!r} has unknown kind {kind_name!r}; valid kinds: {', '.join(sorted(NODE_KINDS))}"
                )
            raw_params = raw.get("params") or {}
            if not isinstance(raw_params, Mapping):
                raise ValueError(f"node {node_id!r} 'params' must be an object")
            unknown = set(raw_params) - set(kind.params)
            if unknown:
                valid = ", ".join(sorted(kind.params)) or "(none)"
                raise ValueError(
                    f"node {node_id!r} ({kind_name}) has unknown params {', '.join(sorted(unknown))}; valid: {valid}"
                )
            params = {
                name: _coerce(f"{node_id}.{name}", spec, raw_params.get(name, spec.default))
                for name, spec in kind.params.items()
            }
            raw_inputs = raw.get("inputs") or {}
            if not isinstance(raw_inputs, Mapping):
                raise ValueError(f"node {node_id!r} 'inputs' must be an object")
            inputs = {str(socket): str(target) for socket, target in raw_inputs.items()}
            nodes[str(node_id)] = NodeSpec(kind_name, params, inputs)

        output = str(data.get("output", ""))
        if output not in nodes:
            raise ValueError(f"output node {output!r} is not in the graph; nodes are: {', '.join(sorted(nodes))}")

        # Only nodes reachable from the output are wire-checked. The editor legitimately holds
        # half-wired orphans while an operator is building, and refusing to save those would make it
        # unusable.
        for node_id in _reachable(nodes, output):
            spec = nodes[node_id]
            kind = NODE_KINDS[spec.kind]
            for socket, target in spec.inputs.items():
                if socket not in kind.inputs:
                    valid = ", ".join(kind.inputs) or "(none)"
                    raise ValueError(f"node {node_id!r} ({spec.kind}) has no input {socket!r}; valid: {valid}")
                if target not in nodes:
                    raise ValueError(f"node {node_id!r} input {socket!r} points at missing node {target!r}")
            missing = [socket for socket in kind.required if socket not in spec.inputs]
            if missing:
                raise ValueError(f"node {node_id!r} ({spec.kind}) needs {', '.join(missing)} wired")

        _topological_order(nodes, output)  # raises on a cycle

        raw_seed = data.get("seed", 0)
        try:
            seed = int(raw_seed) & 0xFFFFFFFF
        except (TypeError, ValueError):
            raise ValueError(f"seed must be an integer, got {raw_seed!r}") from None
        ui = data.get("ui") or {}
        if not isinstance(ui, Mapping):
            raise ValueError("'ui' must be an object")
        return cls(nodes, output, seed, dict(ui))

    def to_dict(self) -> dict[str, Any]:
        """The wire format. This IS what the editor POSTs and what the bank stores, so it must be
        JSON-shaped: _coerce returns tuples for vec2 and stops, and leaving them as tuples makes an
        in-memory graph unequal to the same graph after a save/load round trip."""
        return {
            "version": 1,
            "seed": self.seed,
            "output": self.output,
            "nodes": {
                node_id: {
                    "kind": spec.kind,
                    "params": {name: _jsonable(value) for name, value in spec.params.items()},
                    "inputs": dict(spec.inputs),
                }
                for node_id, spec in self.nodes.items()
            },
            "ui": dict(self.ui),
        }


def _reachable(nodes: Mapping[str, NodeSpec], output: str) -> set[str]:
    seen: set[str] = set()
    stack = [output]
    while stack:
        node_id = stack.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        stack.extend(nodes[node_id].inputs.values())
    return seen


def _topological_order(nodes: Mapping[str, NodeSpec], output: str) -> list[str]:
    """Three-colour iterative DFS from the output. Iterative because a hand-authored graph can be
    64 deep and a cycle would otherwise surface as a RecursionError rather than a useful message."""
    white, grey, black = 0, 1, 2
    colour = dict.fromkeys(nodes, white)
    order: list[str] = []
    path: list[str] = []
    stack: list[tuple[str, bool]] = [(output, False)]
    while stack:
        node_id, finished = stack.pop()
        if finished:
            colour[node_id] = black
            order.append(node_id)
            path.pop()
            continue
        if colour.get(node_id, white) == black:
            continue
        if colour.get(node_id, white) == grey:
            loop = path[path.index(node_id) :] + [node_id]
            raise ValueError("texture graph has a cycle: " + " -> ".join(loop))
        colour[node_id] = grey
        path.append(node_id)
        stack.append((node_id, True))
        for target in nodes[node_id].inputs.values():
            if target in nodes:
                stack.append((target, False))
    return order


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def _eval(node_id: str, frame: _Frame, ctx: _Context) -> Field:
    # Keyed by (node, frame) and NOT by id(frame): CPython recycles object ids after GC, and the
    # collision would silently return another frame's array -- a plausible but wrong picture, never
    # a crash. A node reached through two mappings is meant to be evaluated twice.
    key = (node_id, frame.index)
    cached = ctx.memo.get(key)
    if cached is not None:
        return cached

    ctx.evaluations += 1
    if ctx.evaluations > MAX_EVALUATIONS:
        raise ValueError(
            f"texture graph needed more than {MAX_EVALUATIONS} node evaluations; "
            "mapping and warp nodes re-evaluate everything beneath them"
        )

    spec = ctx.graph.nodes[node_id]
    kind = NODE_KINDS[spec.kind]

    def resolve(socket: str, target_frame: _Frame | None = None) -> Field | None:
        target = spec.inputs.get(socket)
        if target is None:
            return None
        return _eval(target, target_frame or frame, ctx)

    field = kind.evaluate(frame, spec.params, resolve, ctx)
    # Every node lands in [0, 1] so blend modes and masks compose without each one re-checking.
    field = np.clip(field, np.float32(0.0), np.float32(1.0)).astype(np.float32, copy=False)
    ctx.memo[key] = field
    return field


def evaluate_field(
    graph: TextureGraph | Mapping[str, Any],
    *,
    width_mm: float,
    height_mm: float,
    cell_mm: float,
    seed: int | None = None,
) -> Field:
    """Evaluate a graph to a float32 field in [0, 1], shape (rows, cols)."""
    if not isinstance(graph, TextureGraph):
        graph = TextureGraph.from_dict(graph)
    if width_mm <= 0 or height_mm <= 0 or cell_mm <= 0:
        raise ValueError("width_mm, height_mm, and cell_mm must be positive")

    cols = max(1, round(width_mm / cell_mm))
    rows = max(1, round(height_mm / cell_mm))
    if rows * cols > MAX_CELLS:
        raise ValueError(
            f"texture grid is {cols}x{rows} = {rows * cols} cells, exceeding MAX_CELLS={MAX_CELLS}; "
            "increase cell_mm, or reduce width_mm/height_mm"
        )

    # Cell centres, in mm. Source nodes divide by scale_mm to reach lattice units, which is what
    # makes the texture resolution-independent: halving cell_mm doubles the sampling density without
    # moving a single feature. That matters on a plotter, where cell_mm is a quality dial.
    xs = (np.arange(cols, dtype=np.float32) + np.float32(0.5)) * np.float32(cell_mm)
    ys = (np.arange(rows, dtype=np.float32) + np.float32(0.5)) * np.float32(cell_mm)
    x, y = np.meshgrid(xs, ys)

    ctx = _Context(
        graph,
        seed=graph.seed if seed is None else int(seed) & 0xFFFFFFFF,
        width_mm=float(width_mm),
        height_mm=float(height_mm),
    )
    return _eval(graph.output, ctx.new_frame(x, y), ctx)


def evaluate(
    graph: TextureGraph | Mapping[str, Any],
    *,
    width_mm: float,
    height_mm: float,
    cell_mm: float,
    seed: int | None = None,
) -> ToneGrid:
    """Evaluate a graph to a ToneGrid, ready for any renderer in modes.MODES."""
    field = evaluate_field(graph, width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm, seed=seed)
    # float64 because load_tone produces float64 and no mode declares its dtype; the internal work
    # stays float32 for memory.
    return ToneGrid(field.astype(np.float64), float(cell_mm), float(width_mm), float(height_mm))


# ---------------------------------------------------------------------------
# Rendering -- mirrors image_to_polylines / image_to_svg one for one
# ---------------------------------------------------------------------------
def texture_to_polylines(
    graph: TextureGraph | Mapping[str, Any],
    *,
    mode: str,
    width_mm: float,
    height_mm: float,
    cell_mm: float = 1.0,
    seed: int | None = None,
    max_segments: int = MAX_SEGMENTS_DEFAULT,
    min_stroke_mm: float = 0.0,
    **params: Any,
) -> Polylines:
    tone = evaluate(graph, width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm, seed=seed)
    return tone_to_polylines(tone, mode=mode, max_segments=max_segments, min_stroke_mm=min_stroke_mm, **params)


def texture_to_svg(
    graph: TextureGraph | Mapping[str, Any],
    *,
    mode: str,
    width_mm: float,
    height_mm: float,
    pen_width_mm: float = PEN_WIDTH_MM_DEFAULT,
    **kwargs: Any,
) -> str:
    polylines = texture_to_polylines(graph, mode=mode, width_mm=width_mm, height_mm=height_mm, **kwargs)
    return polylines_to_svg(polylines, width_mm=width_mm, height_mm=height_mm, pen_width_mm=pen_width_mm)


# ---------------------------------------------------------------------------
# PNG transport
# ---------------------------------------------------------------------------
def field_to_png(field: Field) -> bytes:
    """Grayscale PNG. The browser decodes it natively and it is ~1 byte per cell against ~9 for
    "0.123456," in a JSON float array -- at 512x512 that is 260 KB against 2.4 MB."""
    grey = np.clip(np.asarray(field) * 255.0, 0.0, 255.0).round().astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(grey, mode="L").save(buffer, format="PNG")
    return buffer.getvalue()


def png_to_field(data: bytes) -> Field:
    """Inverse of field_to_png, to 1/255. That quantisation is the ceiling for the sketch's use of
    a field as a mask or density driver -- fine there, not fine as a tone source."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            grey = np.asarray(source.convert("L"), dtype=np.float32)
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError("unable to read texture PNG data") from error
    return grey / np.float32(255.0)


# ---------------------------------------------------------------------------
# Schema and presets
# ---------------------------------------------------------------------------
def kinds_schema() -> dict[str, Any]:
    """The registry as JSON. One source of truth, so the editor's param panel is generated rather
    than hand-written -- which is exactly what _mode_params in the image workspace never had."""
    return {
        name: {
            "inputs": list(kind.inputs),
            "required": list(kind.required),
            "help": kind.help,
            "params": {
                param: {
                    "kind": spec.kind,
                    "default": list(spec.default) if spec.kind in ("vec2", "stops") else spec.default,
                    "minimum": spec.minimum,
                    "maximum": spec.maximum,
                    "choices": list(spec.choices),
                    "help": spec.help,
                }
                for param, spec in kind.params.items()
            },
        }
        for name, kind in NODE_KINDS.items()
    }


def default_graph() -> dict[str, Any]:
    """fbm clouds multiplied by Voronoi cracks, but only in the middle of the sheet.

    The ramped radial gradient on `fac` is the mask: at the edges fac is 0, so the mix returns the
    clouds untouched. Note the trailing ramp on the noise -- fbm's practical distribution is about
    0.5 +/- 0.12, i.e. flat mid-grey, which renders as uniform hatching everywhere and reads as
    broken. Auto-normalising would fix the look and destroy the tile-independence, so every shipped
    preset ends in a ramp instead.
    """
    return {
        "version": 1,
        "seed": 7,
        "output": "out",
        "nodes": {
            "clouds": {"kind": "perlin", "params": {"scale_mm": 34.0, "octaves": 5, "gain": 0.5, "seed": 3}},
            "contrast": {
                "kind": "ramp",
                "params": {"stops": [[0.35, 0.0], [0.65, 1.0]], "interpolation": "ease"},
                "inputs": {"fac": "clouds"},
            },
            "cracks": {"kind": "worley", "params": {"scale_mm": 16.0, "metric": "f2-f1", "seed": 11}},
            "vignette": {"kind": "gradient", "params": {"kind": "radial", "center": [0.5, 0.5], "radius_mm": 78.0}},
            "mask": {
                "kind": "ramp",
                "params": {"stops": [[0.30, 0.0], [0.70, 1.0]], "interpolation": "ease"},
                "inputs": {"fac": "vignette"},
            },
            "out": {
                "kind": "mix",
                "params": {"blend": "multiply", "factor": 1.0, "clamp": True},
                "inputs": {"a": "contrast", "b": "cracks", "fac": "mask"},
            },
        },
        "ui": {
            "clouds": {"x": 40, "y": 40},
            "contrast": {"x": 250, "y": 40},
            "cracks": {"x": 40, "y": 170},
            "vignette": {"x": 40, "y": 300},
            "mask": {"x": 250, "y": 300},
            "out": {"x": 470, "y": 170},
        },
    }
