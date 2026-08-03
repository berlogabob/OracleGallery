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

// State
let currentSeed = 12345;
let currentSvgString = '';
let shapes = []; // For building SVG

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
// Pattern generation
// ============================================================================
function generatePattern(seed) {
  shapes = [];
  const rng = seededRandom(seed);

  // Grid circles
  const cellWidth = PLOTTER_WIDTH_MM / GRID_COLS;
  const cellHeight = PLOTTER_HEIGHT_MM / GRID_ROWS;

  for (let i = 0; i < GRID_COLS; i++) {
    for (let j = 0; j < GRID_ROWS; j++) {
      const cx = (i + 0.5) * cellWidth;
      const cy = (j + 0.5) * cellHeight;
      const radius = MIN_CIRCLE_RADIUS_MM + rng() * (MAX_CIRCLE_RADIUS_MM - MIN_CIRCLE_RADIUS_MM);

      shapes.push({
        type: 'circle',
        cx: cx,
        cy: cy,
        r: radius
      });
    }
  }

  // Scattered circles for visual interest (not exceeding ~300 total elements)
  for (let i = 0; i < SCATTER_CIRCLES; i++) {
    const cx = rng() * PLOTTER_WIDTH_MM;
    const cy = rng() * PLOTTER_HEIGHT_MM;
    const radius = MIN_CIRCLE_RADIUS_MM + rng() * (MAX_CIRCLE_RADIUS_MM - MIN_CIRCLE_RADIUS_MM) * 0.6;

    shapes.push({
      type: 'circle',
      cx: cx,
      cy: cy,
      r: radius
    });
  }

  // Build SVG
  currentSvgString = buildSvg(shapes);
}

// ============================================================================
// p5.js setup and draw
// ============================================================================
function setup() {
  const container = document.getElementById('canvas-container');
  const cnv = createCanvas(CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX);
  cnv.parent(container);

  // Initial pattern
  generatePattern(currentSeed);

  noLoop(); // Only redraw when we call redraw()

  // Wire up buttons
  document.getElementById('regenerate-btn').addEventListener('click', () => {
    currentSeed = Math.floor(Math.random() * 1000000);
    generatePattern(currentSeed);
    redraw();
    document.getElementById('status').textContent = `Generated (seed: ${currentSeed})`;
  });

  document.getElementById('send-btn').addEventListener('click', sendToPlotter);
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
// Debug: expose current SVG
// ============================================================================
window.currentSvg = function() {
  return currentSvgString;
};
