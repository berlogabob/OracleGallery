// Texture node editor. Vanilla JS, one canvas, no library -- p5 from CDN is already the only
// external script this project loads, and a texture must still be authorable offline.
//
// The `graph` object below IS the wire format: JSON.stringify(graph) is the POST body, the saved
// file, and what the Python evaluator parses. There is no serialisation layer to drift.

const NODE_WIDTH = 152;
const HEADER_H = 22;
const SOCKET_ROW_H = 18;
const SOCKET_R = 5;
const HIT_R = 9;

const COLOR = {
  page: '#fffdf8',
  body: '#fffaf0',
  edge: '#dac9ad',
  accent: '#8f4f2b',
  ink: '#1f1a17',
  muted: '#9b8e83',
  wire: '#b98c66',
  output: '#c0392b'
};

const graph = { version: 1, seed: 7, output: '', nodes: {}, ui: {} };
let KINDS = {};
let selected = null;
let drag = null;             // {mode:'node'|'wire'|'pan', ...}
let view = { x: 0, y: 0 };
let nextId = 1;

const canvas = document.getElementById('graph-canvas');
const context = canvas.getContext('2d');

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------
function nodeHeight(nodeId) {
  const kind = KINDS[graph.nodes[nodeId].kind];
  const rows = Math.max(kind ? kind.inputs.length : 0, 1);
  return HEADER_H + rows * SOCKET_ROW_H + 8;
}

function nodePos(nodeId) {
  const at = graph.ui[nodeId] || { x: 40, y: 40 };
  return { x: at.x + view.x, y: at.y + view.y };
}

function inputSocketPos(nodeId, index) {
  const at = nodePos(nodeId);
  return { x: at.x, y: at.y + HEADER_H + SOCKET_ROW_H / 2 + index * SOCKET_ROW_H };
}

function outputSocketPos(nodeId) {
  const at = nodePos(nodeId);
  return { x: at.x + NODE_WIDTH, y: at.y + HEADER_H + SOCKET_ROW_H / 2 };
}

// Linear scan, back to front. At MAX_NODES=64 a spatial index would be more code than the loop it
// replaces, and this runs once per pointer event.
function hitTest(x, y) {
  const ids = Object.keys(graph.nodes).reverse();
  for (const nodeId of ids) {
    const kind = KINDS[graph.nodes[nodeId].kind];
    if (!kind) continue;
    const out = outputSocketPos(nodeId);
    if (Math.hypot(x - out.x, y - out.y) <= HIT_R) return { nodeId: nodeId, socket: null, kind: 'out' };
    for (let index = 0; index < kind.inputs.length; index++) {
      const at = inputSocketPos(nodeId, index);
      if (Math.hypot(x - at.x, y - at.y) <= HIT_R) {
        return { nodeId: nodeId, socket: kind.inputs[index], kind: 'in' };
      }
    }
    const at = nodePos(nodeId);
    if (x >= at.x && x <= at.x + NODE_WIDTH && y >= at.y && y <= at.y + nodeHeight(nodeId)) {
      return { nodeId: nodeId, socket: null, kind: 'body' };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Rendering -- immediate mode: clear and redraw everything on any state change.
// ---------------------------------------------------------------------------
function wirePath(from, to) {
  const bend = Math.max(30, Math.abs(to.x - from.x) * 0.5);
  context.beginPath();
  context.moveTo(from.x, from.y);
  context.bezierCurveTo(from.x + bend, from.y, to.x - bend, to.y, to.x, to.y);
  context.stroke();
}

function redraw() {
  context.fillStyle = COLOR.page;
  context.fillRect(0, 0, canvas.width, canvas.height);

  context.lineWidth = 1.8;
  context.strokeStyle = COLOR.wire;
  for (const nodeId of Object.keys(graph.nodes)) {
    const kind = KINDS[graph.nodes[nodeId].kind];
    if (!kind) continue;
    const inputs = graph.nodes[nodeId].inputs || {};
    for (const socket of Object.keys(inputs)) {
      const source = inputs[socket];
      if (!graph.nodes[source]) continue;
      const index = kind.inputs.indexOf(socket);
      if (index < 0) continue;
      wirePath(outputSocketPos(source), inputSocketPos(nodeId, index));
    }
  }

  if (drag && drag.mode === 'wire') {
    context.strokeStyle = COLOR.accent;
    context.setLineDash([5, 4]);
    const anchor = drag.from.kind === 'out'
      ? outputSocketPos(drag.from.nodeId)
      : inputSocketPos(drag.from.nodeId, KINDS[graph.nodes[drag.from.nodeId].kind].inputs.indexOf(drag.from.socket));
    wirePath(anchor, { x: drag.x, y: drag.y });
    context.setLineDash([]);
  }

  for (const nodeId of Object.keys(graph.nodes)) {
    drawNode(nodeId);
  }
}

function drawNode(nodeId) {
  const node = graph.nodes[nodeId];
  const kind = KINDS[node.kind];
  if (!kind) return;
  const at = nodePos(nodeId);
  const height = nodeHeight(nodeId);
  const isOutput = nodeId === graph.output;

  context.fillStyle = COLOR.body;
  context.strokeStyle = isOutput ? COLOR.output : (nodeId === selected ? COLOR.accent : COLOR.edge);
  context.lineWidth = (isOutput || nodeId === selected) ? 2 : 1;
  context.beginPath();
  context.roundRect(at.x, at.y, NODE_WIDTH, height, 8);
  context.fill();
  context.stroke();

  context.fillStyle = COLOR.accent;
  context.font = '600 11px -apple-system, sans-serif';
  context.textBaseline = 'middle';
  context.fillText(node.kind, at.x + 9, at.y + HEADER_H / 2 + 1);
  if (isOutput) {
    context.fillStyle = COLOR.output;
    context.fillText('OUT', at.x + NODE_WIDTH - 30, at.y + HEADER_H / 2 + 1);
  }
  context.strokeStyle = COLOR.edge;
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(at.x, at.y + HEADER_H);
  context.lineTo(at.x + NODE_WIDTH, at.y + HEADER_H);
  context.stroke();

  context.font = '10px -apple-system, sans-serif';
  for (let index = 0; index < kind.inputs.length; index++) {
    const socket = kind.inputs[index];
    const pos = inputSocketPos(nodeId, index);
    const wired = (node.inputs || {})[socket];
    const required = kind.required.indexOf(socket) >= 0;
    context.beginPath();
    context.arc(pos.x, pos.y, SOCKET_R, 0, Math.PI * 2);
    context.fillStyle = wired ? COLOR.accent : (required ? COLOR.output : COLOR.page);
    context.fill();
    context.strokeStyle = COLOR.edge;
    context.stroke();
    context.fillStyle = COLOR.ink;
    context.fillText(socket, pos.x + 10, pos.y);
  }

  const out = outputSocketPos(nodeId);
  context.beginPath();
  context.arc(out.x, out.y, SOCKET_R, 0, Math.PI * 2);
  context.fillStyle = COLOR.accent;
  context.fill();
  context.strokeStyle = COLOR.edge;
  context.stroke();
}

// ---------------------------------------------------------------------------
// Graph edits
// ---------------------------------------------------------------------------
function defaultParams(kindName) {
  const params = {};
  const kind = KINDS[kindName];
  for (const name of Object.keys(kind.params)) params[name] = kind.params[name].default;
  return params;
}

function freshId(kindName) {
  let id = kindName + nextId++;
  while (graph.nodes[id]) id = kindName + nextId++;
  return id;
}

function addNode(kindName, x, y) {
  const id = freshId(kindName);
  graph.nodes[id] = { kind: kindName, params: defaultParams(kindName), inputs: {} };
  graph.ui[id] = { x: x - view.x, y: y - view.y };
  if (!graph.output) graph.output = id;
  selected = id;
  changed();
  return id;
}

function deleteNode(nodeId) {
  if (!nodeId || nodeId === graph.output) {
    setStatus('The output node cannot be deleted. Set another node as output first.');
    return;
  }
  delete graph.nodes[nodeId];
  delete graph.ui[nodeId];
  for (const other of Object.keys(graph.nodes)) {
    const inputs = graph.nodes[other].inputs || {};
    for (const socket of Object.keys(inputs)) {
      if (inputs[socket] === nodeId) delete inputs[socket];
    }
  }
  if (selected === nodeId) selected = null;
  changed();
}

// Connecting source -> target makes target depend on source. That closes a loop only if source
// already depends on target, so walk source's ancestors. Checked here as well as on the server so
// the operator gets instant feedback instead of a 400 after the fact.
function wouldCycle(source, target) {
  const stack = [source];
  const seen = {};
  while (stack.length) {
    const current = stack.pop();
    if (current === target) return true;
    if (seen[current] || !graph.nodes[current]) continue;
    seen[current] = true;
    const inputs = graph.nodes[current].inputs || {};
    for (const socket of Object.keys(inputs)) stack.push(inputs[socket]);
  }
  return false;
}

function connect(source, targetNode, targetSocket) {
  if (source === targetNode || wouldCycle(source, targetNode)) {
    setStatus('That connection would make a loop.');
    return;
  }
  graph.nodes[targetNode].inputs = graph.nodes[targetNode].inputs || {};
  graph.nodes[targetNode].inputs[targetSocket] = source;
  changed();
}

// ---------------------------------------------------------------------------
// Pointer interaction
// ---------------------------------------------------------------------------
function pointerAt(event) {
  const rect = canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

canvas.addEventListener('contextmenu', function(event) { event.preventDefault(); });

canvas.addEventListener('pointerdown', function(event) {
  const at = pointerAt(event);
  canvas.setPointerCapture(event.pointerId);

  if (event.button === 2) {
    drag = { mode: 'pan', x: at.x, y: at.y, originX: view.x, originY: view.y };
    return;
  }

  const hit = hitTest(at.x, at.y);
  if (!hit) { selected = null; renderParams(); redraw(); return; }

  if (hit.kind === 'out') {
    drag = { mode: 'wire', from: hit, x: at.x, y: at.y };
  } else if (hit.kind === 'in') {
    const wired = (graph.nodes[hit.nodeId].inputs || {})[hit.socket];
    if (wired) {
      // Blender behaviour: grabbing a wired input picks the wire up rather than starting a second.
      delete graph.nodes[hit.nodeId].inputs[hit.socket];
      drag = { mode: 'wire', from: { nodeId: wired, socket: null, kind: 'out' }, x: at.x, y: at.y };
      schedulePreview();
    } else {
      drag = { mode: 'wire', from: hit, x: at.x, y: at.y };
    }
  } else {
    selected = hit.nodeId;
    const pos = nodePos(hit.nodeId);
    drag = { mode: 'node', nodeId: hit.nodeId, dx: at.x - pos.x, dy: at.y - pos.y };
    renderParams();
  }
  redraw();
});

canvas.addEventListener('pointermove', function(event) {
  if (!drag) return;
  const at = pointerAt(event);
  if (drag.mode === 'pan') {
    view.x = drag.originX + (at.x - drag.x);
    view.y = drag.originY + (at.y - drag.y);
  } else if (drag.mode === 'node') {
    graph.ui[drag.nodeId] = { x: at.x - drag.dx - view.x, y: at.y - drag.dy - view.y };
  } else {
    drag.x = at.x;
    drag.y = at.y;
  }
  redraw();
});

canvas.addEventListener('pointerup', function(event) {
  if (drag && drag.mode === 'wire') {
    const hit = hitTest(drag.x, drag.y);
    if (hit && drag.from.kind === 'out' && hit.kind === 'in') {
      connect(drag.from.nodeId, hit.nodeId, hit.socket);
    } else if (hit && drag.from.kind === 'in' && hit.kind === 'out') {
      connect(hit.nodeId, drag.from.nodeId, drag.from.socket);
    }
  }
  drag = null;
  redraw();
});

canvas.addEventListener('dblclick', function(event) {
  const at = pointerAt(event);
  const hit = hitTest(at.x, at.y);
  if (hit) { graph.output = hit.nodeId; changed(); }
});

document.addEventListener('keydown', function(event) {
  if (event.target.tagName === 'INPUT' || event.target.tagName === 'SELECT') return;
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault();
    deleteNode(selected);
  }
});

// ---------------------------------------------------------------------------
// Parameter panel -- generated from /api/texture/kinds, never hand-written
// ---------------------------------------------------------------------------
function renderParams() {
  const host = document.getElementById('params');
  const title = document.getElementById('params-title');
  const help = document.getElementById('node-help');
  host.innerHTML = '';
  if (!selected || !graph.nodes[selected]) {
    title.textContent = 'Parameters';
    help.textContent = 'Select a node. Double-click a node to make it the output.';
    return;
  }
  const node = graph.nodes[selected];
  const kind = KINDS[node.kind];
  title.textContent = node.kind + '  ·  ' + selected;
  help.textContent = kind.help || '';

  for (const name of Object.keys(kind.params)) {
    const spec = kind.params[name];
    const row = document.createElement('div');
    row.className = 'param-row';
    const label = document.createElement('label');
    label.textContent = name.replace(/_/g, ' ');
    if (spec.help) label.title = spec.help;
    row.appendChild(label);

    if (spec.kind === 'enum') {
      const select = document.createElement('select');
      for (const choice of spec.choices) {
        const option = document.createElement('option');
        option.value = choice;
        option.textContent = choice;
        if (choice === node.params[name]) option.selected = true;
        select.appendChild(option);
      }
      select.addEventListener('change', function() { node.params[name] = select.value; changed(); });
      row.appendChild(select);
    } else if (spec.kind === 'bool') {
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = !!node.params[name];
      box.addEventListener('change', function() { node.params[name] = box.checked; changed(); });
      row.appendChild(box);
    } else if (spec.kind === 'vec2') {
      for (let axis = 0; axis < 2; axis++) {
        const field = document.createElement('input');
        field.type = 'number';
        field.className = 'vec';
        field.step = 'any';
        field.value = node.params[name][axis];
        field.addEventListener('input', function() {
          const pair = node.params[name].slice();
          pair[axis] = parseFloat(field.value) || 0;
          node.params[name] = pair;
          changed();
        });
        row.appendChild(field);
      }
    } else if (spec.kind === 'stops') {
      row.appendChild(buildStopsEditor(node, name));
    } else {
      const field = document.createElement('input');
      field.type = 'number';
      field.step = spec.kind === 'int' ? '1' : 'any';
      if (spec.minimum !== null && spec.minimum !== undefined) field.min = spec.minimum;
      if (spec.maximum !== null && spec.maximum !== undefined) field.max = spec.maximum;
      field.value = node.params[name];
      field.addEventListener('input', function() {
        const value = parseFloat(field.value);
        if (!isNaN(value)) { node.params[name] = spec.kind === 'int' ? Math.round(value) : value; changed(); }
      });
      row.appendChild(field);
    }
    host.appendChild(row);
  }
}

function buildStopsEditor(node, name) {
  const wrap = document.createElement('div');

  function rebuild() {
    wrap.innerHTML = '';
    node.params[name].forEach(function(stop, index) {
      const row = document.createElement('div');
      row.className = 'stop-row';
      [0, 1].forEach(function(axis) {
        const field = document.createElement('input');
        field.type = 'number';
        field.step = '0.05';
        field.value = stop[axis];
        field.addEventListener('input', function() {
          const stops = node.params[name].map(function(pair) { return pair.slice(); });
          stops[index][axis] = parseFloat(field.value) || 0;
          node.params[name] = stops;
          changed();
        });
        row.appendChild(field);
      });
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '−';
      remove.disabled = node.params[name].length <= 1;
      remove.addEventListener('click', function() {
        node.params[name] = node.params[name].filter(function(_, i) { return i !== index; });
        rebuild();
        changed();
      });
      row.appendChild(remove);
      wrap.appendChild(row);
    });
    const add = document.createElement('button');
    add.type = 'button';
    add.textContent = '+ stop';
    add.addEventListener('click', function() {
      node.params[name] = node.params[name].concat([[1.0, 1.0]]);
      rebuild();
      changed();
    });
    wrap.appendChild(add);
  }

  rebuild();
  return wrap;
}

// ---------------------------------------------------------------------------
// Live preview -- debounced, with the in-flight request cancelled
// ---------------------------------------------------------------------------
let previewTimer = null;
let previewAbort = null;

function setStatus(text) {
  document.getElementById('status').textContent = text || '';
}

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer);
  // 150 ms plus an abort: dragging a slider otherwise issues one full evaluation per frame, and the
  // late ones arrive out of order and flicker the preview backwards.
  previewTimer = setTimeout(runPreview, 150);
}

function runPreview() {
  if (previewAbort) previewAbort.abort();
  previewAbort = new AbortController();
  fetch('/api/texture/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph: graph, width_mm: 200, height_mm: 200, cell_mm: 0.5 }),
    signal: previewAbort.signal
  }).then(function(response) {
    if (!response.ok) return response.json().then(function(payload) { throw new Error(payload.error); });
    return response.blob();
  }).then(function(blob) {
    const image = document.getElementById('preview-image');
    const url = URL.createObjectURL(blob);
    const previous = image.dataset.url;
    image.src = url;
    image.dataset.url = url;
    if (previous) URL.revokeObjectURL(previous);
    setStatus('');
  }).catch(function(error) {
    if (error.name !== 'AbortError') setStatus(error.message);
  });
}

function changed() {
  redraw();
  renderParams();
  schedulePreview();
}

// ---------------------------------------------------------------------------
// Save / load
// ---------------------------------------------------------------------------
function refreshGraphList(selectName) {
  return fetch('/api/texture/graphs').then(function(response) { return response.json(); }).then(function(payload) {
    const select = document.getElementById('load-select');
    select.innerHTML = '<option value="">load…</option>';
    (payload.graphs || []).forEach(function(name) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      if (name === selectName) option.selected = true;
      select.appendChild(option);
    });
  });
}

function adoptGraph(data) {
  graph.version = 1;
  graph.seed = data.seed || 0;
  graph.output = data.output;
  graph.nodes = data.nodes;
  graph.ui = data.ui || {};
  // A loaded graph brings its own ids; keep the counter clear of them.
  nextId = Object.keys(graph.nodes).length + 1;
  selected = graph.output;
  document.getElementById('seed-input').value = graph.seed;
  changed();
}

// ---------------------------------------------------------------------------
// Render and print -- reuses /api/generative/svg, so the whole capture -> direct-SVG -> G-code
// path already in the plotter serves textures with no new plumbing.
// ---------------------------------------------------------------------------
let renderedSvg = '';

function renderForPlot() {
  const payload = {
    graph: graph,
    mode: document.getElementById('mode-select').value,
    width_mm: parseFloat(document.getElementById('plot-width').value) || 150,
    height_mm: parseFloat(document.getElementById('plot-height').value) || 150,
    cell_mm: parseFloat(document.getElementById('plot-cell').value) || 0.8,
    seed: graph.seed
  };
  document.getElementById('cost').textContent = 'Rendering…';
  fetch('/api/texture/svg', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function(response) { return response.json(); }).then(function(result) {
    if (!result.ok) {
      renderedSvg = '';
      document.getElementById('send-btn').disabled = true;
      document.getElementById('cost').textContent = result.error;
      return;
    }
    renderedSvg = result.svg;
    document.getElementById('send-btn').disabled = false;
    document.getElementById('render-preview').innerHTML = result.svg;
    document.getElementById('cost').textContent =
      result.strokes + ' strokes, ' + result.segments + ' segments, ' +
      (result.draw_mm / 1000).toFixed(1) + ' m drawn + ' +
      (result.travel_mm / 1000).toFixed(1) + ' m travel';
  }).catch(function(error) {
    document.getElementById('cost').textContent = String(error);
  });
}

function sendToPlotter() {
  if (!renderedSvg) return;
  fetch('/api/generative/svg', { method: 'POST', headers: { 'Content-Type': 'image/svg+xml' }, body: renderedSvg })
    .then(function(response) { return response.json(); })
    .then(function(result) { setStatus(result.ok ? 'Captured ' + result.name : result.error); })
    .catch(function(error) { setStatus(String(error)); });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
fetch('/api/texture/kinds').then(function(response) { return response.json(); }).then(function(payload) {
  KINDS = payload.kinds;

  const addSelect = document.getElementById('add-kind');
  Object.keys(KINDS).forEach(function(name) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    addSelect.appendChild(option);
  });

  const modeSelect = document.getElementById('mode-select');
  (payload.modes || []).forEach(function(name) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    if (name === 'hatch') option.selected = true;
    modeSelect.appendChild(option);
  });

  return refreshGraphList();
}).then(function() {
  // Start from the shipped default rather than an empty canvas: a blank node editor is the least
  // useful thing to hand someone who has not used one before.
  return fetch('/api/texture/graphs?name=clouds').then(function(response) {
    return response.ok ? response.json() : null;
  });
}).then(function(payload) {
  if (payload && payload.ok) {
    adoptGraph(payload.graph);
  } else {
    addNode('perlin', 80, 120);
    const ramp = addNode('ramp', 320, 120);
    connect(Object.keys(graph.nodes)[0], ramp, 'fac');
    graph.output = ramp;
    changed();
  }
}).catch(function(error) {
  setStatus('Could not reach the texture API: ' + error);
});

document.getElementById('add-node-btn').addEventListener('click', function() {
  addNode(document.getElementById('add-kind').value, canvas.width / 2, canvas.height / 2);
});
document.getElementById('delete-node-btn').addEventListener('click', function() { deleteNode(selected); });
document.getElementById('set-output-btn').addEventListener('click', function() {
  if (selected) { graph.output = selected; changed(); }
});
document.getElementById('seed-input').addEventListener('input', function(event) {
  graph.seed = parseInt(event.target.value, 10) || 0;
  schedulePreview();
});
document.getElementById('reseed-btn').addEventListener('click', function() {
  graph.seed = Math.floor(Math.random() * 100000);
  document.getElementById('seed-input').value = graph.seed;
  schedulePreview();
});
document.getElementById('load-select').addEventListener('change', function(event) {
  const name = event.target.value;
  if (!name) return;
  fetch('/api/texture/graphs?name=' + encodeURIComponent(name))
    .then(function(response) { return response.json(); })
    .then(function(payload) {
      if (payload.ok) {
        adoptGraph(payload.graph);
        document.getElementById('save-name').value = name;
      } else {
        setStatus(payload.error);
      }
    });
});
document.getElementById('save-btn').addEventListener('click', function() {
  const name = document.getElementById('save-name').value.trim();
  if (!name) { setStatus('Type a name first.'); return; }
  fetch('/api/texture/graphs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name, graph: graph })
  }).then(function(response) { return response.json(); }).then(function(result) {
    if (!result.ok) { setStatus(result.error); return; }
    setStatus('Saved as ' + result.name);
    document.getElementById('save-name').value = result.name;
    refreshGraphList(result.name);
    // The sketch's field picker is now stale; it listens for this.
    if (window.parent) window.parent.postMessage({ type: 'textures' }, '*');
  });
});
document.getElementById('render-btn').addEventListener('click', renderForPlot);
document.getElementById('send-btn').addEventListener('click', sendToPlotter);

redraw();
