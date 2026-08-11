// Builds the pattern-bank evidence sheet by running the REAL sketch.js bank generator.
//
// Re-implementing the grid/round-robin/rotation logic here (or in Python) would test the
// replica rather than the code that actually plots, so this loads sketch.js the same way
// _harness.mjs does. The stub table below is duplicated from that file on purpose: the
// harness is load-bearing for tests/test_pattern_generators.py and a shared module is not
// worth the coupling for ~30 lines. Merge them if a third consumer appears.
//
// usage: node _bank_sheet.mjs <bank.json> <out.svg>
//   bank.json: {canvas:{width_mm,height_mm}, motifs:{name:[[[x,y],...],...]}}

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BANDS = 4;
const BAND_GAP_MM = 4;
const TICK_MM = 5;
const SEED = 4242;
const MIXES = [0, 0.5, 1.0];

let activeNoiseSeed = 0;

function noiseSeed(seed) {
  activeNoiseSeed = Number(seed) | 0;
}

function noise(...values) {
  let hash = activeNoiseSeed ^ 0x9e3779b9;
  for (const value of values) {
    hash = Math.imul(hash ^ Math.round(value * 1000), 0x45d9f3b);
    hash ^= hash >>> 16;
  }
  return (hash >>> 0) / 4294967295;
}

function loadSketch() {
  const sketchPath = join(dirname(fileURLToPath(import.meta.url)), 'sketch.js');
  const source = readFileSync(sketchPath, 'utf8') +
    '\n;globalThis.__GEN = GENERATORS; globalThis.__BUILD = buildSvg; globalThis.__SEEDED = seededRandom;' +
    ' globalThis.__SETBANK = setBank; globalThis.__SETCANVAS = setCanvasMm;';
  const noOp = () => {};
  const names = [
    'noise', 'noiseSeed', 'document', 'window', 'createCanvas', 'background',
    'stroke', 'noFill', 'strokeWeight', 'circle', 'beginShape', 'vertex',
    'endShape', 'fetch', 'setInterval', 'clearInterval', 'noLoop', 'redraw'
  ];
  const values = [
    noise, noiseSeed,
    { getElementById: () => null },
    { addEventListener: noOp },
    () => ({ parent: noOp }),
    noOp, noOp, noOp, noOp, noOp, noOp, noOp, noOp,
    async () => ({ json: async () => ({}) }),
    noOp, noOp, noOp, noOp
  ];
  new Function(...names, source)(...values);
}

function translate(shapes, dx, dy) {
  return shapes.map(function(shape) {
    if (shape.type === 'circle') {
      return { type: 'circle', cx: shape.cx + dx, cy: shape.cy + dy, r: shape.r };
    }
    return {
      type: 'polyline',
      points: shape.points.map(function(p) { return { x: p.x + dx, y: p.y + dy }; })
    };
  });
}

// Band 4: each motif once, straight from the bank rather than through the generator --
// its question is about the motifs themselves, not about placement.
function motifRow(motifs, bandWidth, bandHeight) {
  const names = Object.keys(motifs).sort();
  if (!names.length) return [];
  const slot = bandWidth / names.length;
  const size = Math.min(slot * 0.75, bandHeight * 0.75);
  const shapes = [];
  names.forEach(function(name, index) {
    const cx = (index + 0.5) * slot;
    const cy = bandHeight / 2;
    for (const points of motifs[name]) {
      shapes.push({
        type: 'polyline',
        points: points.map(function(p) { return { x: cx + p[0] * size, y: cy + p[1] * size }; })
      });
    }
  });
  return shapes;
}

// Bands are numbered by tick strokes in the left margin: text would mean pulling the SHX
// renderer (Python) into a Node script for a label.
function ticks(count, y) {
  const shapes = [];
  for (let i = 0; i < count; i++) {
    const ty = y + 3 + i * 3;
    shapes.push({ type: 'polyline', points: [{ x: 0, y: ty }, { x: TICK_MM, y: ty }] });
  }
  return shapes;
}

const [bankPath, outPath] = process.argv.slice(2);
if (!bankPath || !outPath) throw new Error('usage: node _bank_sheet.mjs <bank.json> <out.svg>');

const payload = JSON.parse(readFileSync(bankPath, 'utf8'));
const sheetWidth = payload.canvas.width_mm;
const sheetHeight = payload.canvas.height_mm;
const bandHeight = (sheetHeight - BAND_GAP_MM * (BANDS - 1)) / BANDS;

loadSketch();
globalThis.__SETBANK(payload.motifs);

let all = [];
MIXES.forEach(function(mix, index) {
  // Generate at band size so cells come out at their natural mm, not scaled down: what
  // plots has to be what the operator sees in the sketch.
  globalThis.__SETCANVAS(sheetWidth, bandHeight);
  noiseSeed(SEED);
  const shapes = globalThis.__GEN.bank(globalThis.__SEEDED(SEED), { density: 1.0, scale: 0.5, mix });
  const offsetY = index * (bandHeight + BAND_GAP_MM);
  all = all.concat(translate(shapes, 0, offsetY), ticks(index + 1, offsetY));
});

const lastOffset = MIXES.length * (bandHeight + BAND_GAP_MM);
all = all.concat(
  translate(motifRow(payload.motifs, sheetWidth, bandHeight), 0, lastOffset),
  ticks(BANDS, lastOffset)
);

// Restore the full sheet so buildSvg emits the right viewBox.
globalThis.__SETCANVAS(sheetWidth, sheetHeight);
writeFileSync(outPath, globalThis.__BUILD(all));

const points = all.reduce(function(sum, s) { return sum + (s.points ? s.points.length : 1); }, 0);
console.log(JSON.stringify({ shapes: all.length, points: points, motifs: Object.keys(payload.motifs).length }));
