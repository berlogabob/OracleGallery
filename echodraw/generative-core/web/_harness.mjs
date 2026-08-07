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
    '\n;globalThis.__GEN = GENERATORS; globalThis.__BUILD = buildSvg; globalThis.__SEEDED = seededRandom;';
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
  return {
    generators: globalThis.__GEN,
    buildSvg: globalThis.__BUILD,
    seededRandom: globalThis.__SEEDED
  };
}

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
  writeFileSync(join(outputDirectory, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
} catch (error) {
  console.error(`pattern harness failed: ${error.stack || error}`);
  process.exitCode = 1;
}
