// Headless harness for nodes.js, mirroring _harness.mjs.
//
// nodes.js is a standalone page, so unlike sketch.js it may touch the DOM at module scope. That
// means the stubs below have to be real enough to get through boot: a canvas with a 2D context, an
// element per id the boot path reads, and a fetch that resolves the two endpoints it calls.
//
// What this actually tests is the graph model -- wouldCycle, connect, deleteNode. The canvas
// drawing is not verified here; it needs eyes.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

// Two node kinds are enough to exercise wiring: one source, one with two required inputs.
const STUB_KINDS = {
  perlin: { inputs: [], required: [], help: 'noise', params: { scale_mm: { kind: 'float', default: 30 } } },
  mix: {
    inputs: ['a', 'b', 'fac'],
    required: ['a', 'b'],
    help: 'combine',
    params: { blend: { kind: 'enum', default: 'mix', choices: ['mix', 'multiply'] } }
  },
  invert: { inputs: ['fac'], required: ['fac'], help: 'flip', params: {} }
};

function noOp() {}

function stubContext() {
  return new Proxy({}, {
    get(_target, key) {
      if (key === 'canvas') return { width: 760, height: 620 };
      return noOp;
    },
    set() { return true; }
  });
}

function stubElement(id) {
  const listeners = {};
  return {
    id,
    value: '',
    textContent: '',
    innerHTML: '',
    dataset: {},
    style: {},
    classList: { add: noOp, remove: noOp },
    disabled: false,
    width: 760,
    height: 620,
    getContext: stubContext,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 760, height: 620 }),
    setPointerCapture: noOp,
    appendChild: noOp,
    addEventListener: (name, handler) => { listeners[name] = handler; },
    fire: (name, event) => listeners[name] && listeners[name](event)
  };
}

function loadEditor() {
  const source = readFileSync(join(HERE, 'nodes.js'), 'utf8') +
    '\n;globalThis.__EDITOR = { graph, addNode, deleteNode, connect, wouldCycle, nodeHeight,' +
    ' inputSocketPos, outputSocketPos, hitTest, setKinds: (k) => { KINDS = k; } };';

  const elements = {};
  const document = {
    getElementById: (id) => (elements[id] = elements[id] || stubElement(id)),
    createElement: (tag) => stubElement(tag),
    addEventListener: noOp
  };

  // Boot calls /api/texture/kinds, then /api/texture/graphs, then ?name=clouds. Returning ok:false
  // for the last one drives the "no saved graph" fallback, which is the branch worth exercising:
  // it must leave a valid two-node graph behind rather than an empty canvas.
  const fetchStub = async (url) => ({
    ok: true,
    json: async () => {
      if (String(url).indexOf('/kinds') >= 0) return { ok: true, kinds: STUB_KINDS, modes: ['hatch'], blends: [] };
      if (String(url).indexOf('name=') >= 0) return { ok: false, error: 'absent' };
      return { ok: true, graphs: [] };
    },
    blob: async () => ({})
  });

  const names = ['document', 'window', 'fetch', 'setTimeout', 'clearTimeout', 'AbortController', 'URL'];
  const values = [
    document,
    { parent: null, postMessage: noOp },
    fetchStub,
    noOp,
    noOp,
    function () { return { abort: noOp, signal: null }; },
    { createObjectURL: () => 'blob:stub', revokeObjectURL: noOp }
  ];
  new Function(...names, source)(...values);
  return globalThis.__EDITOR;
}

const editor = loadEditor();
editor.setKinds(STUB_KINDS);

const results = {};

// A fresh graph, wired by hand.
editor.graph.nodes = {};
editor.graph.ui = {};
editor.graph.output = '';
const a = editor.addNode('perlin', 40, 40);
const b = editor.addNode('perlin', 40, 200);
const m = editor.addNode('mix', 300, 100);
editor.connect(a, m, 'a');
editor.connect(b, m, 'b');
results.wired = { a: editor.graph.nodes[m].inputs.a, b: editor.graph.nodes[m].inputs.b };

// A cycle must be refused: m already depends on a, so a <- m closes the loop.
const inv = editor.addNode('invert', 300, 300);
editor.connect(m, inv, 'fac');
results.cycleRefused = editor.wouldCycle(inv, m) === true;
const beforeCycle = JSON.stringify(editor.graph.nodes[m].inputs);
editor.connect(inv, m, 'fac');
results.cycleNotWritten = JSON.stringify(editor.graph.nodes[m].inputs) === beforeCycle;
results.selfRefused = editor.wouldCycle(a, a) === true;
results.legalAllowed = editor.wouldCycle(a, inv) === false;

// Deleting a node must also drop every wire pointing at it, or the graph references a ghost.
editor.graph.output = inv;
editor.deleteNode(b);
results.deletedGone = editor.graph.nodes[b] === undefined;
results.uiCleaned = editor.graph.ui[b] === undefined;
results.wireCleaned = editor.graph.nodes[m].inputs.b === undefined;

// The output node is protected.
editor.deleteNode(inv);
results.outputProtected = editor.graph.nodes[inv] !== undefined;

// Socket geometry: inputs must be spaced apart and inside the node box.
const height = editor.nodeHeight(m);
const first = editor.inputSocketPos(m, 0);
const second = editor.inputSocketPos(m, 1);
const out = editor.outputSocketPos(m);
results.socketsSpaced = second.y - first.y > 8;
results.socketsInside = second.y < editor.graph.ui[m].y + height;
results.outputOnRight = out.x > first.x;

// Hit testing must find the output socket it just drew.
const hit = editor.hitTest(out.x, out.y);
results.hitFindsOutput = !!hit && hit.nodeId === m && hit.kind === 'out';

// stdout only. _harness.mjs writes SVGs because the pattern tests feed them to the G-code
// generator; there is nothing here worth leaving in the working tree.
console.log(JSON.stringify(results));
