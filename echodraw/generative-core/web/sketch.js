// ============================================================================
// EchoDraw Generative Pen Plotter Sketch
// Adapted from 01_Circles.js - grid-based circles with seeded randomness
// ============================================================================

// Canvas & plotter settings
const PLOTTER_WIDTH_MM = 200;
const PLOTTER_HEIGHT_MM = 200;
const SCALE_FACTOR = 3; // px/mm
const CANVAS_WIDTH_PX = PLOTTER_WIDTH_MM * SCALE_FACTOR; // 600
const CANVAS_HEIGHT_PX = PLOTTER_HEIGHT_MM * SCALE_FACTOR; // 600

// Pattern parameters
const GRID_COLS = 10;
const GRID_ROWS = 10;
const MIN_CIRCLE_RADIUS_MM = 0.5;
const MAX_CIRCLE_RADIUS_MM = 4;
const SCATTER_CIRCLES = 15; // Additional random circles

// Layer system parameters
const MAX_LAYERS = 5;
const MAX_TOTAL_SHAPES = 600;
const LAYER_SEED_STRIDE = 1013;

// State
let currentSeed = 12345;
let currentSvgString = '';
let shapes = []; // For building SVG (concatenation of all layers)
let streamTimer = null; // Interval handle while streaming
let layers = [
  { generator: 'circles', density: 0.5, scale: 0.5, mask: false }
];

// ============================================================================
// Simple seeded random number generator (Mulberry32)
// ============================================================================
function seededRandom(seed) {
  return function() {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ============================================================================
// SVG building: Pure function for consistent rendering
// ============================================================================
function buildSvg(shapes) {
  let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200mm" height="200mm">';

  for (let shape of shapes) {
    if (shape.type === 'circle') {
      const { cx, cy, r } = shape;
      svg += `<circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" r="${r.toFixed(2)}" fill="none" stroke="black" stroke-width="0.5"/>`;
    } else if (shape.type === 'polyline') {
      const { points } = shape;
      let pointsStr = points.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
      svg += `<polyline points="${pointsStr}" fill="none" stroke="black" stroke-width="0.5"/>`;
    }
  }

  svg += '</svg>';
  return svg;
}

// ============================================================================
// Helpers shared by generators
// ============================================================================
function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

function shapeCenter(shape) {
  if (shape.type === 'circle') {
    return { x: shape.cx, y: shape.cy };
  }
  if (shape.type === 'polyline' && shape.points && shape.points.length) {
    const mid = shape.points[Math.floor(shape.points.length / 2)];
    return { x: mid.x, y: mid.y };
  }
  return { x: 0, y: 0 };
}

function densityOf(params) {
  const d = params && typeof params.density === 'number' ? params.density : 0.5;
  return clamp(d, 0, 1);
}

function scaleOf(params) {
  const s = params && typeof params.scale === 'number' ? params.scale : 0.5;
  return clamp(s, 0, 1);
}

function triangle(rng, cx, cy, size) {
  const h = size * 0.45;
  return [{
    type: 'polyline',
    points: [
      { x: cx, y: cy - h },
      { x: cx + h, y: cy + h },
      { x: cx - h, y: cy + h },
      { x: cx, y: cy - h }
    ]
  }];
}

function spiral(rng, cx, cy, size) {
  const points = [];
  for (let i = 0; i < 28; i++) {
    const radius = size * 0.45 * i / 27;
    const angle = i / 27 * Math.PI * 4;
    points.push({
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius
    });
  }
  return [{ type: 'polyline', points: points }];
}

function zigzag(rng, cx, cy, size) {
  const points = [];
  for (let i = 0; i < 7; i++) {
    points.push({
      x: cx - size * 0.45 + size * 0.15 * i,
      y: cy + (i % 2 === 0 ? -1 : 1) * size * 0.3
    });
  }
  return [{ type: 'polyline', points: points }];
}

function ladder(rng, cx, cy, size) {
  const x = size * 0.28;
  const y = size * 0.42;
  const shapes = [
    { type: 'polyline', points: [{ x: cx - x, y: cy - y }, { x: cx - x, y: cy + y }] },
    { type: 'polyline', points: [{ x: cx + x, y: cy - y }, { x: cx + x, y: cy + y }] }
  ];
  for (let i = 0; i < 4; i++) {
    const rungY = cy - y + i * y * 2 / 3;
    shapes.push({ type: 'polyline', points: [{ x: cx - x, y: rungY }, { x: cx + x, y: rungY }] });
  }
  return shapes;
}

function hatchedTriangle(rng, cx, cy, size) {
  const shapes = triangle(rng, cx, cy, size);
  const h = size * 0.45;
  for (let i = 1; i <= 3; i++) {
    const y = cy - h + i * h / 2;
    const halfWidth = i * h / 4;
    shapes.push({
      type: 'polyline',
      points: [{ x: cx - halfWidth, y: y }, { x: cx + halfWidth, y: y }]
    });
  }
  return shapes;
}

function dots(rng, cx, cy, size) {
  const radius = size * 0.06;
  return [[-0.22, -0.22], [0.22, -0.22], [0, 0], [-0.22, 0.22], [0.22, 0.22]].map(function(offset) {
    return {
      type: 'circle',
      cx: cx + offset[0] * size,
      cy: cy + offset[1] * size,
      r: radius
    };
  });
}

function chevron(rng, cx, cy, size) {
  return [{
    type: 'polyline',
    points: [
      { x: cx - size * 0.4, y: cy - size * 0.25 },
      { x: cx, y: cy + size * 0.3 },
      { x: cx + size * 0.4, y: cy - size * 0.25 }
    ]
  }];
}

function eye(rng, cx, cy, size) {
  return [
    {
      type: 'polyline',
      points: [
        { x: cx - size * 0.45, y: cy },
        { x: cx - size * 0.22, y: cy - size * 0.22 },
        { x: cx, y: cy - size * 0.28 },
        { x: cx + size * 0.22, y: cy - size * 0.22 },
        { x: cx + size * 0.45, y: cy },
        { x: cx + size * 0.22, y: cy + size * 0.22 },
        { x: cx, y: cy + size * 0.28 },
        { x: cx - size * 0.22, y: cy + size * 0.22 },
        { x: cx - size * 0.45, y: cy }
      ]
    },
    { type: 'circle', cx: cx, cy: cy, r: size * 0.1 }
  ];
}

function cat(rng, cx, cy, size) {
  const shapes = [{
    type: 'polyline',
    points: [
      { x: cx - size * 0.32, y: cy - size * 0.2 },
      { x: cx - size * 0.25, y: cy - size * 0.3 },
      { x: cx + size * 0.25, y: cy - size * 0.3 },
      { x: cx + size * 0.32, y: cy - size * 0.2 },
      { x: cx + size * 0.32, y: cy + size * 0.22 },
      { x: cx + size * 0.24, y: cy + size * 0.3 },
      { x: cx - size * 0.24, y: cy + size * 0.3 },
      { x: cx - size * 0.32, y: cy + size * 0.22 },
      { x: cx - size * 0.32, y: cy - size * 0.2 }
    ]
  }];
  shapes.push({
    type: 'polyline',
    points: [
      { x: cx - size * 0.25, y: cy - size * 0.28 },
      { x: cx - size * 0.18, y: cy - size * 0.45 },
      { x: cx - size * 0.08, y: cy - size * 0.3 }
    ]
  });
  shapes.push({
    type: 'polyline',
    points: [
      { x: cx + size * 0.08, y: cy - size * 0.3 },
      { x: cx + size * 0.18, y: cy - size * 0.45 },
      { x: cx + size * 0.25, y: cy - size * 0.28 }
    ]
  });
  shapes.push({ type: 'circle', cx: cx - size * 0.12, cy: cy - size * 0.05, r: size * 0.035 });
  shapes.push({ type: 'circle', cx: cx + size * 0.12, cy: cy - size * 0.05, r: size * 0.035 });

  const tail = [];
  for (let i = 0; i <= 8; i++) {
    const angle = Math.PI * 0.65 - i * Math.PI * 0.16;
    tail.push({
      x: cx + size * 0.25 + Math.cos(angle) * size * 0.2,
      y: cy + size * 0.23 + Math.sin(angle) * size * 0.2
    });
  }
  shapes.push({ type: 'polyline', points: tail });
  return shapes;
}

const MOTIFS = {
  triangle,
  spiral,
  zigzag,
  ladder,
  hatchedTriangle,
  dots,
  chevron,
  eye,
  cat
};

function rotateShapes(shapes, cx, cy, radians) {
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  const rotatePoint = function(x, y) {
    const dx = x - cx;
    const dy = y - cy;
    return {
      x: cx + dx * cosine - dy * sine,
      y: cy + dx * sine + dy * cosine
    };
  };

  return shapes.map(function(shape) {
    if (shape.type === 'circle') {
      const center = rotatePoint(shape.cx, shape.cy);
      return { type: 'circle', cx: center.x, cy: center.y, r: shape.r };
    }
    return {
      type: 'polyline',
      points: shape.points.map(function(point) {
        return rotatePoint(point.x, point.y);
      })
    };
  });
}

const MARCHING_CASES = [
  [], [[3, 0]], [[0, 1]], [[3, 1]],
  [[1, 2]], [[3, 2], [0, 1]], [[0, 2]], [[3, 2]],
  [[2, 3]], [[0, 2]], [[0, 3], [1, 2]], [[1, 2]],
  [[1, 3]], [[0, 1]], [[3, 0]], []
];

function joinContourSegments(segments) {
  const links = new Map();
  const used = new Array(segments.length).fill(false);
  const keyOf = function(point) {
    return `${point.x.toFixed(5)},${point.y.toFixed(5)}`;
  };

  segments.forEach(function(segment, index) {
    for (let point of segment) {
      const key = keyOf(point);
      if (!links.has(key)) links.set(key, []);
      links.get(key).push(index);
    }
  });

  const runs = [];
  for (let i = 0; i < segments.length; i++) {
    if (used[i]) continue;
    used[i] = true;
    const run = [segments[i][0], segments[i][1]];

    for (let direction of [1, -1]) {
      while (true) {
        const end = direction === 1 ? run[run.length - 1] : run[0];
        const endKey = keyOf(end);
        const nextIndex = (links.get(endKey) || []).find(function(index) {
          return !used[index];
        });
        if (nextIndex === undefined) break;
        used[nextIndex] = true;
        const segment = segments[nextIndex];
        const next = keyOf(segment[0]) === endKey ? segment[1] : segment[0];
        if (direction === 1) run.push(next);
        else run.unshift(next);
      }
    }
    runs.push(run);
  }
  return runs;
}

// ============================================================================
// Generator registry: each generator is (rng, params) -> shapes[]
// ============================================================================
const GENERATORS = {
  // Original grid-of-circles pattern, extracted unchanged (density only
  // scales the scattered circle count; at density 0.5 this matches the
  // original fixed SCATTER_CIRCLES count).
  circles: function(rng, params) {
    const density = densityOf(params);
    const shapes = [];
    const cellWidth = PLOTTER_WIDTH_MM / GRID_COLS;
    const cellHeight = PLOTTER_HEIGHT_MM / GRID_ROWS;

    for (let i = 0; i < GRID_COLS; i++) {
      for (let j = 0; j < GRID_ROWS; j++) {
        const cx = (i + 0.5) * cellWidth;
        const cy = (j + 0.5) * cellHeight;
        const radius = MIN_CIRCLE_RADIUS_MM + rng() * (MAX_CIRCLE_RADIUS_MM - MIN_CIRCLE_RADIUS_MM);
        shapes.push({ type: 'circle', cx: cx, cy: cy, r: radius });
      }
    }

    const scatterCount = Math.round(density * SCATTER_CIRCLES * 2);
    for (let i = 0; i < scatterCount; i++) {
      let cx = rng() * PLOTTER_WIDTH_MM;
      let cy = rng() * PLOTTER_HEIGHT_MM;
      const radius = MIN_CIRCLE_RADIUS_MM + rng() * (MAX_CIRCLE_RADIUS_MM - MIN_CIRCLE_RADIUS_MM) * 0.6;
      cx = clamp(cx, radius, PLOTTER_WIDTH_MM - radius);
      cy = clamp(cy, radius, PLOTTER_HEIGHT_MM - radius);
      shapes.push({ type: 'circle', cx: cx, cy: cy, r: radius });
    }

    return shapes;
  },

  // 8-24 horizontal polylines displaced by seeded sine + noise.
  waves: function(rng, params) {
    const density = densityOf(params);
    const count = Math.round(8 + density * 16); // 8..24
    const pointsPerLine = 60;
    const shapes = [];

    for (let i = 0; i < count; i++) {
      const baseY = (i + 0.5) * (PLOTTER_HEIGHT_MM / count);
      const amp = 2 + rng() * 6;
      const freq = 1 + rng() * 3;
      const phase = rng() * Math.PI * 2;
      const points = [];

      for (let p = 0; p < pointsPerLine; p++) {
        const x = (p / (pointsPerLine - 1)) * PLOTTER_WIDTH_MM;
        const n = noise(x * 0.03, i * 0.5, phase) - 0.5; // centered ~[-0.5, 0.5]
        const y = baseY + Math.sin((x / PLOTTER_WIDTH_MM) * Math.PI * 2 * freq + phase) * amp + n * 4;
        points.push({ x: clamp(x, 0, 200), y: clamp(y, 0, 200) });
      }

      shapes.push({ type: 'polyline', points: points });
    }

    return shapes;
  },

  // One continuous polyline random-walking on a 5mm grid.
  gridwalk: function(rng, params) {
    const density = densityOf(params);
    const steps = Math.round(300 + density * 900); // 300..1200
    const gridSize = 5;
    const min = 5;
    const max = 195;
    const cellsPerAxis = Math.floor((max - min) / gridSize) + 1;

    let x = min + Math.floor(rng() * cellsPerAxis) * gridSize;
    let y = min + Math.floor(rng() * cellsPerAxis) * gridSize;
    const points = [{ x: x, y: y }];
    const dirs = [[gridSize, 0], [-gridSize, 0], [0, gridSize], [0, -gridSize]];

    for (let s = 0; s < steps; s++) {
      let nx = x;
      let ny = y;
      let tries = 0;
      do {
        const d = dirs[Math.floor(rng() * dirs.length)];
        nx = x + d[0];
        ny = y + d[1];
        tries++;
      } while ((nx < min || nx > max || ny < min || ny > max) && tries < 10);

      x = clamp(nx, min, max);
      y = clamp(ny, min, max);
      points.push({ x: x, y: y });
    }

    return [{ type: 'polyline', points: points }];
  },

  // Short polylines following a Perlin flow field.
  flowfield: function(rng, params) {
    const density = densityOf(params);
    const count = Math.round(20 + density * 60); // 20..80
    const stepLen = 2; // mm
    const steps = 30;
    const shapes = [];

    for (let i = 0; i < count; i++) {
      let x = clamp(rng() * PLOTTER_WIDTH_MM, 0, 200);
      let y = clamp(rng() * PLOTTER_HEIGHT_MM, 0, 200);
      const points = [{ x: x, y: y }];

      for (let s = 0; s < steps; s++) {
        const angle = noise(x * 0.01, y * 0.01) * (Math.PI * 2) * 2; // TWO_PI * 2
        x = clamp(x + Math.cos(angle) * stepLen, 0, 200);
        y = clamp(y + Math.sin(angle) * stepLen, 0, 200);
        points.push({ x: x, y: y });
      }

      shapes.push({ type: 'polyline', points: points });
    }

    return shapes;
  },

  mondrian: function(rng, params) {
    const density = densityOf(params);
    const scale = scaleOf(params);
    const depth = 1 + Math.round(density * 5);
    let cells = [{ x: 0, y: 0, width: PLOTTER_WIDTH_MM, height: PLOTTER_HEIGHT_MM }];

    for (let level = 0; level < depth; level++) {
      const next = [];
      for (let cell of cells) {
        const vertical = cell.width > cell.height || (cell.width === cell.height && rng() < 0.5);
        const split = 0.35 + rng() * 0.3;
        if (vertical) {
          const width = cell.width * split;
          next.push({ x: cell.x, y: cell.y, width: width, height: cell.height });
          next.push({ x: cell.x + width, y: cell.y, width: cell.width - width, height: cell.height });
        } else {
          const height = cell.height * split;
          next.push({ x: cell.x, y: cell.y, width: cell.width, height: height });
          next.push({ x: cell.x, y: cell.y + height, width: cell.width, height: cell.height - height });
        }
      }
      cells = next;
    }

    const shapes = [];
    for (let cell of cells) {
      const x2 = cell.x + cell.width;
      const y2 = cell.y + cell.height;
      shapes.push({
        type: 'polyline',
        points: [
          { x: cell.x, y: cell.y }, { x: x2, y: cell.y },
          { x: x2, y: y2 }, { x: cell.x, y: y2 }, { x: cell.x, y: cell.y }
        ]
      });
      if (rng() < 0.25) {
        const size = Math.min(cell.width, cell.height) * (0.45 + scale * 0.45);
        shapes.push(...MOTIFS.cat(rng, cell.x + cell.width / 2, cell.y + cell.height / 2, size));
      }
    }
    return shapes;
  },

  tribal: function(rng, params) {
    const density = densityOf(params);
    const scale = scaleOf(params);
    const cellSize = 12 + scale * 24;
    const cols = Math.max(1, Math.floor(PLOTTER_WIDTH_MM / cellSize));
    const rows = Math.max(1, Math.floor(PLOTTER_HEIGHT_MM / cellSize));
    const width = PLOTTER_WIDTH_MM / cols;
    const height = PLOTTER_HEIGHT_MM / rows;
    const motifNames = ['triangle', 'spiral', 'zigzag', 'ladder', 'hatchedTriangle', 'chevron', 'eye'];
    const shapes = [];

    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        if (rng() > density) continue;
        const cx = (col + 0.5) * width;
        const cy = (row + 0.5) * height;
        const name = motifNames[Math.floor(rng() * motifNames.length)];
        const stamp = MOTIFS[name](rng, cx, cy, Math.min(width, height) * 0.7);
        const rotated = rotateShapes(stamp, cx, cy, (rng() - 0.5) * Math.PI / 6);
        if (shapes.length + rotated.length <= MAX_TOTAL_SHAPES) shapes.push(...rotated);
      }
    }
    return shapes;
  },

  circuit: function(rng, params) {
    const density = densityOf(params);
    const scale = scaleOf(params);
    const traceCount = Math.round(density * 40);
    const turns = 4 + Math.round(density * 4);
    const step = 8 + scale * 16;
    const margin = 8;
    const shapes = [];

    for (let trace = 0; trace < traceCount; trace++) {
      let x = margin + rng() * (PLOTTER_WIDTH_MM - margin * 2);
      let y = margin + rng() * (PLOTTER_HEIGHT_MM - margin * 2);
      let horizontal = rng() < 0.5;
      const points = [{ x: x, y: y }];

      for (let turn = 0; turn < turns; turn++) {
        const distance = step * (0.6 + rng() * 1.4) * (rng() < 0.5 ? -1 : 1);
        if (horizontal) x = clamp(x + distance, margin, PLOTTER_WIDTH_MM - margin);
        else y = clamp(y + distance, margin, PLOTTER_HEIGHT_MM - margin);
        points.push({ x: x, y: y });
        horizontal = !horizontal;
      }
      shapes.push({ type: 'polyline', points: points });

      const padRadius = 0.35 + scale * 0.45;
      for (let point of points) {
        shapes.push({ type: 'circle', cx: point.x, cy: point.y, r: padRadius });
      }

      if (rng() < 0.45) {
        const segmentIndex = Math.floor(rng() * (points.length - 1));
        const a = points[segmentIndex];
        const b = points[segmentIndex + 1];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.hypot(dx, dy);
        if (distance > 2) {
          const ux = dx / distance;
          const uy = dy / distance;
          const px = -uy;
          const py = ux;
          const cx = (a.x + b.x) / 2;
          const cy = (a.y + b.y) / 2;
          const length = Math.min(distance * 0.8, 6 + scale * 8);
          const amplitude = 1.2 + scale * 1.8;
          const glyph = Math.floor(rng() * 3);

          if (glyph === 0) {
            const resistor = [];
            for (let i = 0; i <= 6; i++) {
              const along = -length / 2 + length * i / 6;
              const across = i === 0 || i === 6 ? 0 : (i % 2 === 0 ? -amplitude : amplitude);
              resistor.push({ x: cx + ux * along + px * across, y: cy + uy * along + py * across });
            }
            shapes.push({ type: 'polyline', points: resistor });
          } else if (glyph === 1) {
            for (let side of [-1, 1]) {
              const along = side * length * 0.14;
              shapes.push({
                type: 'polyline',
                points: [
                  { x: cx + ux * along - px * amplitude, y: cy + uy * along - py * amplitude },
                  { x: cx + ux * along + px * amplitude, y: cy + uy * along + py * amplitude }
                ]
              });
            }
          } else {
            const coil = [];
            const radius = length / 8;
            for (let arc = 0; arc < 4; arc++) {
              const center = -length / 2 + (arc + 0.5) * length / 4;
              for (let i = 0; i <= 6; i++) {
                const angle = Math.PI - i * Math.PI / 6;
                const along = center + Math.cos(angle) * radius;
                const across = Math.sin(angle) * Math.min(radius, amplitude);
                coil.push({ x: cx + ux * along + px * across, y: cy + uy * along + py * across });
              }
            }
            shapes.push({ type: 'polyline', points: coil });
          }
        }
      }
    }
    return shapes.slice(0, MAX_TOTAL_SHAPES);
  },

  motiftile: function(rng, params) {
    const density = densityOf(params);
    const scale = scaleOf(params);
    const names = Object.keys(MOTIFS);
    const motif = MOTIFS[names[Math.floor(rng() * names.length)]];
    const cellSize = 12 + scale * 28;
    const cols = Math.max(1, Math.floor(PLOTTER_WIDTH_MM / cellSize));
    const rows = Math.max(1, Math.floor(PLOTTER_HEIGHT_MM / cellSize));
    const width = PLOTTER_WIDTH_MM / cols;
    const height = PLOTTER_HEIGHT_MM / rows;
    const shapes = [];

    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        if (rng() > density) continue;
        const cx = (col + 0.5) * width;
        const cy = (row + 0.5) * height;
        const stamp = motif(rng, cx, cy, Math.min(width, height) * 0.8);
        const rotated = rotateShapes(stamp, cx, cy, Math.floor(rng() * 4) * Math.PI / 2);
        if (shapes.length + rotated.length <= MAX_TOTAL_SHAPES) shapes.push(...rotated);
      }
    }
    return shapes;
  },

  isolines: function(rng, params) {
    const density = densityOf(params);
    const scale = scaleOf(params);
    const levels = 3 + Math.round(density * 7);
    const cellSize = 4 + scale * 12;
    const cols = Math.ceil(PLOTTER_WIDTH_MM / cellSize);
    const rows = Math.ceil(PLOTTER_HEIGHT_MM / cellSize);
    const width = PLOTTER_WIDTH_MM / cols;
    const height = PLOTTER_HEIGHT_MM / rows;
    const offsetX = rng() * 100;
    const offsetY = rng() * 100;
    const samples = [];

    for (let row = 0; row <= rows; row++) {
      const values = [];
      for (let col = 0; col <= cols; col++) {
        values.push(noise(offsetX + col * 0.13, offsetY + row * 0.13, 0.5));
      }
      samples.push(values);
    }

    const shapes = [];
    for (let levelIndex = 1; levelIndex <= levels; levelIndex++) {
      const level = levelIndex / (levels + 1);
      const segments = [];
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          const values = [
            samples[row][col], samples[row][col + 1],
            samples[row + 1][col + 1], samples[row + 1][col]
          ];
          let state = 0;
          if (values[0] >= level) state |= 1;
          if (values[1] >= level) state |= 2;
          if (values[2] >= level) state |= 4;
          if (values[3] >= level) state |= 8;
          if (state === 0 || state === 15) continue;

          const corners = [
            { x: col * width, y: row * height },
            { x: (col + 1) * width, y: row * height },
            { x: (col + 1) * width, y: (row + 1) * height },
            { x: col * width, y: (row + 1) * height }
          ];
          const edgeCorners = [[0, 1], [1, 2], [3, 2], [0, 3]];
          const pointOnEdge = function(edge) {
            const indexes = edgeCorners[edge];
            const a = indexes[0];
            const b = indexes[1];
            const difference = values[b] - values[a];
            const amount = difference === 0 ? 0.5 : clamp((level - values[a]) / difference, 0, 1);
            return {
              x: clamp(corners[a].x + (corners[b].x - corners[a].x) * amount, 0, PLOTTER_WIDTH_MM),
              y: clamp(corners[a].y + (corners[b].y - corners[a].y) * amount, 0, PLOTTER_HEIGHT_MM)
            };
          };

          for (let pair of MARCHING_CASES[state]) {
            segments.push([pointOnEdge(pair[0]), pointOnEdge(pair[1])]);
          }
        }
      }

      for (let run of joinContourSegments(segments)) {
        if (shapes.length >= MAX_TOTAL_SHAPES) return shapes;
        shapes.push({ type: 'polyline', points: run });
      }
    }
    return shapes;
  },

  // Single-stroke SHX text, fetched from /api/text/paths and cached. The generator
  // stays synchronous (the layer system is sync); the fetch fills TEXT_CACHE and
  // triggers a regenerate when it lands.
  text: function(rng, params) {
    const cached = TEXT_CACHE.polylines;
    if (!cached || !cached.length) return [];
    const scale = 0.4 + scaleOf(params) * 1.2;
    const blockW = TEXT_CACHE.width_mm * scale;
    const blockH = TEXT_CACHE.height_mm * scale;
    const originX = (PLOTTER_WIDTH_MM - blockW) / 2;
    const originY = (PLOTTER_HEIGHT_MM - blockH) / 2;
    return cached.map(function(line) {
      return {
        type: 'polyline',
        points: line.map(function(p) {
          return {
            x: clamp(originX + p[0] * scale, 0, PLOTTER_WIDTH_MM),
            y: clamp(originY + p[1] * scale, 0, PLOTTER_HEIGHT_MM)
          };
        })
      };
    });
  },

  weave: function(rng, params) {
    const density = densityOf(params);
    const scale = scaleOf(params);
    const spacing = 10 + scale * 20;
    const cols = Math.round(PLOTTER_WIDTH_MM / spacing * density);
    const rows = Math.round(PLOTTER_HEIGHT_MM / spacing * density);
    const xs = [];
    const ys = [];
    const shapes = [];
    for (let col = 0; col < cols; col++) xs.push((col + 1) * PLOTTER_WIDTH_MM / (cols + 1));
    for (let row = 0; row < rows; row++) ys.push((row + 1) * PLOTTER_HEIGHT_MM / (rows + 1));
    // Strips are two rails wide, not a centre line: a single line has no visible
    // over/under, which is the only thing that makes a weave read as a weave.
    const half = Math.min(spacing * 0.35, 8);

    // Emit one rail of a strip, broken wherever the perpendicular strip passes over.
    function strip(fixed, crossings, horizontal) {
      const segments = [];
      let start = 0;
      for (let i = 0; i < crossings.length; i++) {
        const cut = crossings[i];
        if (cut - half > start) segments.push([start, cut - half]);
        start = cut + half;
      }
      const limit = horizontal ? PLOTTER_WIDTH_MM : PLOTTER_HEIGHT_MM;
      if (start < limit) segments.push([start, limit]);

      for (let s = 0; s < segments.length; s++) {
        const a = segments[s][0];
        const b = segments[s][1];
        for (const offset of [-half, half]) {
          const rail = horizontal
            ? [{ x: a, y: clamp(fixed + offset, 0, 200) }, { x: b, y: clamp(fixed + offset, 0, 200) }]
            : [{ x: clamp(fixed + offset, 0, 200), y: a }, { x: clamp(fixed + offset, 0, 200), y: b }];
          shapes.push({ type: 'polyline', points: rail });
        }
        // Cap the cut ends so the strip reads as woven tape rather than two loose rails.
        for (const end of [a, b]) {
          const cap = horizontal
            ? [{ x: end, y: clamp(fixed - half, 0, 200) }, { x: end, y: clamp(fixed + half, 0, 200) }]
            : [{ x: clamp(fixed - half, 0, 200), y: end }, { x: clamp(fixed + half, 0, 200), y: end }];
          shapes.push({ type: 'polyline', points: cap });
        }
      }
    }

    for (let row = 0; row < ys.length; row++) {
      const under = xs.filter(function(_, col) { return (row + col) % 2 !== 0; });
      strip(ys[row], under, true);
    }
    for (let col = 0; col < xs.length; col++) {
      const under = ys.filter(function(_, row) { return (row + col) % 2 === 0; });
      strip(xs[col], under, false);
    }
    return shapes.slice(0, MAX_TOTAL_SHAPES);
  }
};

// ============================================================================
// Layer system: build all layers, concat, cap total shape count
// ============================================================================
function regenerateAll() {
  let allShapes = [];

  for (let i = 0; i < layers.length; i++) {
    const layer = layers[i];
    const seed = currentSeed + i * LAYER_SEED_STRIDE;
    const rng = seededRandom(seed);
    if (typeof noiseSeed === 'function') {
      noiseSeed(seed);
    }

    const genFn = GENERATORS[layer.generator] || GENERATORS.circles;
    let layerShapes = genFn(rng, { density: layer.density, scale: layer.scale });

    if (layer.mask) {
      layerShapes = layerShapes.filter(function(shape) {
        const c = shapeCenter(shape);
        return noise(c.x / 50, c.y / 50, i * 7.7) >= 0.5;
      });
    }

    allShapes = allShapes.concat(layerShapes);
  }

  let subsampled = false;
  if (allShapes.length > MAX_TOTAL_SHAPES) {
    const stride = allShapes.length / MAX_TOTAL_SHAPES;
    const sampled = [];
    for (let i = 0; i < MAX_TOTAL_SHAPES; i++) {
      sampled.push(allShapes[Math.floor(i * stride)]);
    }
    allShapes = sampled;
    subsampled = true;
  }

  shapes = allShapes;
  currentSvgString = buildSvg(shapes);

  const statusEl = document.getElementById('status');
  if (statusEl) {
    let text = `${shapes.length} shapes, ${layers.length} layers`;
    if (subsampled) {
      text += ' (subsampled)';
    }
    statusEl.textContent = text;
  }
}

// ============================================================================
// Layer UI: renders per-layer controls into #layers-container
// ============================================================================
// ============================================================================
// Text layer: /api/text/paths is the only async source in the sketch, so its
// result is cached and the layer generator reads the cache synchronously.
// ============================================================================
const TEXT_CACHE = { polylines: [], width_mm: 0, height_mm: 0 };
const TEXT_INPUT = { text: 'NEJE\nORACLE', font: '' };

function fetchTextPaths() {
  const query = 'text=' + encodeURIComponent(TEXT_INPUT.text) +
    '&font=' + encodeURIComponent(TEXT_INPUT.font) + '&h=10';
  fetch('/api/text/paths?' + query)
    .then(function(response) { return response.json(); })
    .then(function(payload) {
      if (!payload.ok) throw new Error(payload.error || 'text render failed');
      TEXT_CACHE.polylines = payload.polylines;
      TEXT_CACHE.width_mm = payload.width_mm;
      TEXT_CACHE.height_mm = payload.height_mm;
      regenerateAll();
      redraw();
    })
    .catch(function(error) {
      const statusEl = document.getElementById('status');
      if (statusEl) statusEl.textContent = 'text: ' + error.message;
    });
}

function initTextControls() {
  const fontSelect = document.getElementById('text-font');
  const textField = document.getElementById('text-input');
  if (!fontSelect || !textField) return;

  textField.value = TEXT_INPUT.text;
  textField.addEventListener('change', function(e) {
    TEXT_INPUT.text = e.target.value;
    fetchTextPaths();
  });
  fontSelect.addEventListener('change', function(e) {
    TEXT_INPUT.font = e.target.value;
    fetchTextPaths();
  });

  fetch('/api/text/fonts')
    .then(function(response) { return response.json(); })
    .then(function(payload) {
      (payload.fonts || []).forEach(function(name) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        fontSelect.appendChild(opt);
      });
      TEXT_INPUT.font = payload.fonts && payload.fonts.length ? payload.fonts[0] : '';
      fetchTextPaths();
    })
    .catch(function() { /* fonts unavailable; the text layer just stays empty */ });
}

function renderLayersUI() {
  const container = document.getElementById('layers-container');
  if (!container) return;
  container.innerHTML = '';

  layers.forEach(function(layer, i) {
    const row = document.createElement('div');
    row.className = 'layer-row';

    const select = document.createElement('select');
    Object.keys(GENERATORS).forEach(function(name) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      if (name === layer.generator) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener('change', function(e) {
      layers[i].generator = e.target.value;
      regenerateAll();
      redraw();
    });

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = '0';
    slider.max = '100';
    slider.value = String(Math.round(layer.density * 100));
    slider.className = 'density-slider';
    slider.title = 'density';
    slider.addEventListener('input', function(e) {
      layers[i].density = parseInt(e.target.value, 10) / 100;
      regenerateAll();
      redraw();
    });

    const scaleLabel = document.createElement('label');
    scaleLabel.appendChild(document.createTextNode('scale '));
    const scaleSlider = document.createElement('input');
    scaleSlider.type = 'range';
    scaleSlider.min = '0';
    scaleSlider.max = '100';
    scaleSlider.value = String(Math.round(scaleOf(layer) * 100));
    scaleSlider.className = 'density-slider';
    scaleSlider.title = 'scale';
    scaleSlider.addEventListener('input', function(e) {
      layers[i].scale = parseInt(e.target.value, 10) / 100;
      regenerateAll();
      redraw();
    });
    scaleLabel.appendChild(scaleSlider);

    const maskLabel = document.createElement('label');
    maskLabel.className = 'mask-label';
    const maskCheckbox = document.createElement('input');
    maskCheckbox.type = 'checkbox';
    maskCheckbox.checked = !!layer.mask;
    maskCheckbox.addEventListener('change', function(e) {
      layers[i].mask = e.target.checked;
      regenerateAll();
      redraw();
    });
    maskLabel.appendChild(maskCheckbox);
    maskLabel.appendChild(document.createTextNode('mask'));

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.textContent = '×';
    removeBtn.className = 'layer-remove-btn';
    removeBtn.disabled = layers.length <= 1;
    removeBtn.addEventListener('click', function() {
      if (layers.length > 1) {
        layers.splice(i, 1);
        renderLayersUI();
        regenerateAll();
        redraw();
      }
    });

    row.appendChild(select);
    row.appendChild(slider);
    row.appendChild(scaleLabel);
    row.appendChild(maskLabel);
    row.appendChild(removeBtn);
    container.appendChild(row);
  });

  const addBtn = document.getElementById('add-layer-btn');
  if (addBtn) {
    addBtn.disabled = layers.length >= MAX_LAYERS;
  }
}

// ============================================================================
// p5.js setup and draw
// ============================================================================
function setup() {
  const container = document.getElementById('canvas-container');
  const cnv = createCanvas(CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX);
  cnv.parent(container);

  // Initial pattern
  renderLayersUI();
  initTextControls();
  regenerateAll();

  noLoop(); // Only redraw when we call redraw()

  // Wire up buttons
  document.getElementById('regenerate-btn').addEventListener('click', () => {
    currentSeed = Math.floor(Math.random() * 1000000);
    regenerateAll();
    redraw();
  });

  document.getElementById('send-btn').addEventListener('click', sendToPlotter);

  document.getElementById('add-layer-btn').addEventListener('click', () => {
    if (layers.length < MAX_LAYERS) {
      layers.push({ generator: 'circles', density: 0.5, scale: 0.5, mask: false });
      renderLayersUI();
      regenerateAll();
      redraw();
    }
  });

}

function draw() {
  background(255);
  stroke(0);
  strokeWeight(1);
  noFill();

  // Draw each shape on canvas
  for (let shape of shapes) {
    if (shape.type === 'circle') {
      const cx_px = shape.cx * SCALE_FACTOR;
      const cy_px = shape.cy * SCALE_FACTOR;
      const r_px = shape.r * SCALE_FACTOR;
      circle(cx_px, cy_px, r_px * 2); // p5.circle expects diameter
    } else if (shape.type === 'polyline') {
      beginShape();
      for (let pt of shape.points) {
        vertex(pt.x * SCALE_FACTOR, pt.y * SCALE_FACTOR);
      }
      endShape();
    }
  }
}

// ============================================================================
// Send to plotter
// ============================================================================
function sendToPlotter() {
  const statusEl = document.getElementById('status');
  statusEl.textContent = 'Sending...';

  fetch('/api/generative/svg', {
    method: 'POST',
    headers: { 'Content-Type': 'image/svg+xml' },
    body: currentSvgString
  })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        statusEl.textContent = `Sent: ${d.name}`;
      } else {
        statusEl.textContent = `Error: ${d.error}`;
      }
    })
    .catch(e => {
      statusEl.textContent = 'Send failed: ' + e.message;
    });
}

// ============================================================================
// Stream mode: regenerate + send on a repeating interval
// ============================================================================
function startStreaming(seconds) {
  stopStreaming(); // clear any existing interval first

  seconds = Math.max(5, Number(seconds) || 15);

  streamTimer = setInterval(() => {
    currentSeed = Math.floor(Math.random() * 1000000);
    regenerateAll();
    redraw();
    sendToPlotter();
  }, seconds * 1000);
}

function stopStreaming() {
  if (streamTimer !== null) {
    clearInterval(streamTimer);
    streamTimer = null;
  }
}

window.addEventListener('message', (event) => {
  const message = event.data;
  if (!message || message.type !== 'stream' || typeof message.enabled !== 'boolean') return;
  if (message.enabled) {
    startStreaming(message.seconds);
  } else {
    stopStreaming();
  }
});

// ============================================================================
// Debug: expose current SVG
// ============================================================================
window.currentSvg = function() {
  return currentSvgString;
};
