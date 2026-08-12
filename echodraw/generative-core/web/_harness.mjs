import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
    ' globalThis.__SETBANK = setBank;' +
    ' globalThis.__FIELD = { setFieldData, sampleField, applyField, scaleShape };';
  const noOp = () => {};
  const names = [
    'noise', 'noiseSeed', 'document', 'window', 'createCanvas', 'background',
    'stroke', 'noFill', 'strokeWeight', 'circle', 'beginShape', 'vertex',
    'endShape', 'fetch', 'setInterval', 'clearInterval', 'noLoop', 'redraw'
  ];
  const values = [
    noise,
    noiseSeed,
    { getElementById: () => null },
    { addEventListener: noOp },
    () => ({ parent: noOp }),
    noOp,
    noOp,
    noOp,
    noOp,
    noOp,
    noOp,
    noOp,
    noOp,
    noOp,
    async () => ({ json: async () => ({}) }),
    noOp,
    noOp,
    noOp,
    noOp
  ];
  new Function(...names, source)(...values);
  // The real bank is fetched in setup(), which p5 calls and this harness does
  // not. Inject a fixed stub so `bank` is testable offline like every other
  // generator, instead of being excused as server-backed.
  globalThis.__SETBANK(STUB_BANK);
  return {
    generators: globalThis.__GEN,
    buildSvg: globalThis.__BUILD,
    seededRandom: globalThis.__SEEDED,
    setBank: globalThis.__SETBANK
  };
}

// Two unit-box motifs, matching what /api/patterns/bank serves.
const STUB_BANK = {
  stubA: [[[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]]],
  stubB: [[[-0.5, 0], [0, -0.5], [0.5, 0], [0, 0.5], [-0.5, 0]]]
};

function generatePass(directory, sketch) {
  mkdirSync(directory, { recursive: true });
  const manifest = {};
  for (const [name, generator] of Object.entries(sketch.generators)) {
    noiseSeed(12345);
    const shapes = generator(sketch.seededRandom(12345), { density: 1.0, scale: 0.5 });
    if (!Array.isArray(shapes)) {
      throw new Error(`${name} did not return an array`);
    }
    if (shapes.length === 0) {
      // `text` is server-backed: offline it is legitimately empty, and it is
      // covered by tests/test_shx_text.py instead.
      if (name !== 'text') throw new Error(`${name} did not produce shapes`);
      manifest[name] = 0;
      continue;
    }
    manifest[name] = shapes.length;
    writeFileSync(join(directory, `${name}.svg`), sketch.buildSvg(shapes));
  }
  return manifest;
}

try {
  const outputDirectory = process.argv[2];
  if (!outputDirectory) throw new Error('usage: node _harness.mjs <output-directory>');
  const sketch = loadSketch();
  const manifest = generatePass(outputDirectory, sketch);
  generatePass(join(outputDirectory, 'repeat'), sketch);

  // The predictability claim: at mix 0 the bank generator must not let any rng
  // value reach its output, so two different seeds give the same field.
  mkdirSync(outputDirectory, { recursive: true });
  for (const seed of [12345, 999]) {
    noiseSeed(seed);
    const shapes = sketch.generators.bank(sketch.seededRandom(seed), { density: 1.0, scale: 0.5, mix: 0 });
    writeFileSync(join(outputDirectory, `mix0-seed${seed}.svg`), sketch.buildSvg(shapes));
  }

  // Budget coverage. A photo-traced motif is ~60 polylines against 1-9 for a
  // hand-authored one, so a full grid overruns MAX_TOTAL_SHAPES several times over.
  // The generator has to drop whole cells spread across the sheet; truncating the
  // flat shape list instead blanks the bottom edge, which is what it used to do.
  // Run last: it replaces the stub bank.
  const heavy = Array.from({ length: 61 }, (_, i) => [[-0.5, -0.5 + i / 120], [0.5, -0.5 + i / 120]]);
  sketch.setBank({ ...STUB_BANK, heavy: heavy });
  const coverage = {};
  for (const scale of [0.5, 0.25, 0]) {
    noiseSeed(1);
    const shapes = sketch.generators.bank(sketch.seededRandom(1), { density: 1.0, scale: scale, mix: 0 });
    const ys = shapes.flatMap(function(s) { return s.points ? s.points.map(function(p) { return p.y; }) : [s.cy]; });
    coverage[String(scale)] = { shapes: shapes.length, yMax: Math.max(...ys) };
  }
  writeFileSync(join(outputDirectory, 'coverage.json'), JSON.stringify(coverage, null, 2) + '\n');

  // Texture fields. A synthetic 8x8 field over the 200 mm canvas: left half 0, right half 255.
  // The real field arrives as a PNG the browser decodes, which node cannot do, so it is injected
  // through setFieldData -- the DOM-free half of the cache, which exists for exactly this.
  const field = globalThis.__FIELD;
  const grey = new Uint8Array(64);
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) grey[row * 8 + col] = col < 4 ? 0 : 255;
  }
  field.setFieldData('half', grey, 8, 8, 200, 200);

  noiseSeed(7);
  const source = sketch.generators.circles(sketch.seededRandom(7), { density: 1.0, scale: 0.5 });
  const centres = (list) => list.map((s) => (s.type === 'circle' ? s.cx : s.points[Math.floor(s.points.length / 2)].x));

  const masked = field.applyField(source, { name: 'half', target: 'mask', threshold: 0.5 }, sketch.seededRandom(7));
  const maskedX = centres(masked);
  // An unknown field must be a no-op, not a wipe: that cold-cache rule is what lets regenerateAll
  // stay synchronous while the PNG is still in flight.
  const cold = field.applyField(source, { name: 'absent', target: 'mask', threshold: 0.5 }, sketch.seededRandom(7));
  const dense = field.applyField(source, { name: 'half', target: 'density', strength: 1.0 }, sketch.seededRandom(7));
  const sized = field.applyField(source, { name: 'half', target: 'size', strength: 1.0 }, sketch.seededRandom(7));
  const invMasked = field.applyField(
    source, { name: 'half', target: 'mask', threshold: 0.5, invert: true }, sketch.seededRandom(7)
  );

  writeFileSync(join(outputDirectory, 'field.json'), JSON.stringify({
    total: source.length,
    kept: masked.length,
    keptMinX: maskedX.length ? Math.min(...maskedX) : null,
    keptMaxX: maskedX.length ? Math.max(...maskedX) : null,
    coldKept: cold.length,
    densityKept: dense.length,
    sizedCount: sized.length,
    invertedKept: invMasked.length,
    sampleLeft: field.sampleField('half', 20, 100),
    sampleRight: field.sampleField('half', 180, 100),
    sampleAbsent: field.sampleField('absent', 20, 100)
  }, null, 2) + '\n');

  writeFileSync(join(outputDirectory, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
} catch (error) {
  console.error(`pattern harness failed: ${error.stack || error}`);
  process.exitCode = 1;
}
