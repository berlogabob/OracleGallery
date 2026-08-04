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
  { generator: 'circles', density: 0.5, mask: false }
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
      const cx = rng() * PLOTTER_WIDTH_MM;
      const cy = rng() * PLOTTER_HEIGHT_MM;
      const radius = MIN_CIRCLE_RADIUS_MM + rng() * (MAX_CIRCLE_RADIUS_MM - MIN_CIRCLE_RADIUS_MM) * 0.6;
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
    let layerShapes = genFn(rng, { density: layer.density });

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
      layers.push({ generator: 'circles', density: 0.5, mask: false });
      renderLayersUI();
      regenerateAll();
      redraw();
    }
  });

  document.getElementById('stream-checkbox').addEventListener('change', (e) => {
    if (e.target.checked) {
      startStreaming();
    } else {
      stopStreaming();
    }
  });

  document.getElementById('stream-interval').addEventListener('change', () => {
    if (document.getElementById('stream-checkbox').checked) {
      startStreaming(); // restart with new interval
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
function startStreaming() {
  stopStreaming(); // clear any existing interval first

  const intervalInput = document.getElementById('stream-interval');
  const seconds = Math.max(5, parseInt(intervalInput.value, 10) || 15);
  intervalInput.value = seconds;

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

// ============================================================================
// Debug: expose current SVG
// ============================================================================
window.currentSvg = function() {
  return currentSvgString;
};
