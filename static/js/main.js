// The management page: edit the screens on the display, with a live view of the panel.
// Changes save automatically (PUT /api/config) and the display picks them up right away.

import { api } from './api.js';
import { $, cls, h, icon, syncList } from './dom.js';
import { compose, decodeBase64, drawLeds } from './led.js';
import { DELETE_KEY, MOD, SHIFT, isMac, openMenu } from './menu.js';

const SWATCHES = ['#ffffff', '#ff3b30', '#ff9500', '#ffd60a', '#34c759', '#32d1ff', '#3d7bff', '#bf5af2'];

const state = {
  W: 64,
  H: 32,
  catalog: new Map(),   // component type -> its info from /api/state
  fonts: [],
  config: null,         // the layout: {screens: [...]}
  screenId: null,       // screen being edited
  selectedId: null,     // selected widget on it
  sprites: new Map(),   // widget id -> {w, h, hash, pixels, note, error}
  live: null,           // last /api/live
  online: true,
  outlines: true,
  clipboard: null,      // a copied widget: {widget, size, sprite}
  images: [],           // uploaded images and built-in icons, from /api/images
  prebuilt: [],         // ready-made screens for the + menu: [{name, description, widgets, thumbnail}]
  pitch: 12,            // CSS pixels per LED on the editor board
};

// ---------- Lookups ----------

const screens = () => state.config.screens;
const findScreen = id => screens().find(s => s.id === id);
const currentScreen = () => findScreen(state.screenId) || screens()[0];
const findWidget = id => currentScreen().widgets.find(w => w.id === id);
const selectedWidget = () => (state.selectedId ? findWidget(state.selectedId) || null : null);
const uid = prefix => prefix + Math.random().toString(36).slice(2, 10);
const clone = value => JSON.parse(JSON.stringify(value));
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
// For show_if / resize_when: each option must equal the value, be one of a list, or start with 'prefix*'
const matches = (condition, options) => !condition || Object.entries(condition).every(([key, want]) => {
  const value = options[key];
  if (Array.isArray(want)) return want.includes(value);
  if (typeof want === 'string' && want.endsWith('*')) return typeof value === 'string' && value.startsWith(want.slice(0, -1));
  return value === want;
});

function canResize(widget) {
  const component = state.catalog.get(widget.type);
  return Boolean(component.resize && matches(component.resize_when, widget.options));
}

// The dark outline draws a pixel outside the text on every side (see renderer.outlined)
const outlinePad = widget => (widget.options.outline === true ? 2 : 0);

// A widget's box in LEDs. The server measures it when drawing the sprite; boxes you can
// resize take their size straight from their options so the handle feels instant.
function widgetSize(widget) {
  const component = state.catalog.get(widget.type);
  const sprite = state.sprites.get(widget.id);
  let width = sprite && sprite.w ? sprite.w : component.thumbnail.w;
  let height = sprite && sprite.h ? sprite.h : component.thumbnail.h;
  if (canResize(widget)) {
    if (component.resize.w) width = widget.options[component.resize.w] + outlinePad(widget);
    if (component.resize.h) height = widget.options[component.resize.h] + outlinePad(widget);
  }
  return [width, height];
}

// Keeps a box on the display; it can only hang off an edge if it's bigger than the display
function clampPosition(x, y, width, height) {
  return [
    clamp(x, Math.min(0, state.W - width), Math.max(0, state.W - width)),
    clamp(y, Math.min(0, state.H - height), Math.max(0, state.H - height)),
  ];
}

// ---------- Undo, and saving ----------

const history = { undo: [], redo: [], key: null, at: 0 };

const snapshot = () => JSON.stringify({ config: state.config, screenId: state.screenId, selectedId: state.selectedId });

// Adds an undo step. Steps with the same key close together (typing, nudging) merge into one.
function record(before, key = null) {
  const now = performance.now();
  if (key && key === history.key && now - history.at < 1500) {
    history.at = now;
    return;
  }
  history.undo.push(before);
  if (history.undo.length > 200) history.undo.shift();
  history.redo.length = 0;
  history.key = key;
  history.at = now;
}

// Runs `mutate` on the layout; if it changed anything, records an undo step and saves.
function change(mutate, { key = null, sprites = false, inspector = true } = {}) {
  const before = snapshot();
  const beforeConfig = JSON.stringify(state.config);
  mutate();
  if (JSON.stringify(state.config) === beforeConfig) {
    render({ inspector });
    return;
  }
  record(before, key);
  changed({ sprites, inspector });
}

function changed({ sprites = false, inspector = true } = {}) {
  scheduleSave();
  if (sprites) refreshSpritesSoon();
  render({ inspector });
}

function travel(from, to) {
  if (!from.length) return;
  to.push(snapshot());
  const step = JSON.parse(from.pop());
  state.config = step.config;
  state.screenId = findScreen(step.screenId) ? step.screenId : screens()[0].id;
  state.selectedId = findWidget(step.selectedId) ? step.selectedId : null;
  history.key = null;
  anchors.clear(); // the step already has every widget where it was
  changed({ sprites: true });
}
const undo = () => travel(history.undo, history.redo);
const redo = () => travel(history.redo, history.undo);

const saving = { timer: null, inFlight: false, dirty: false, error: null };

function scheduleSave() {
  saving.dirty = true;
  saving.error = null;
  clearTimeout(saving.timer);
  saving.timer = setTimeout(save, 400);
  renderSaveStatus();
}

async function save() {
  clearTimeout(saving.timer);
  if (saving.inFlight) {
    saving.timer = setTimeout(save, 150);
    return;
  }
  if (!saving.dirty) return;
  saving.inFlight = true;
  saving.dirty = false;
  renderSaveStatus();
  try {
    await api.saveConfig(state.config);
  } catch (error) {
    saving.error = error.message;
    saving.dirty = true;
  } finally {
    saving.inFlight = false;
    renderSaveStatus();
  }
}

function renderSaveStatus() {
  const el = $('#save-status');
  if (saving.error) {
    el.className = 'save-status error';
    el.textContent = `Couldn't save: ${saving.error}`;
    el.title = 'Your changes are still here. They save with your next change.';
  } else if (saving.dirty || saving.inFlight) {
    el.className = 'save-status pending';
    el.textContent = 'Saving…';
    el.title = '';
  } else {
    el.className = 'save-status';
    el.textContent = 'Saved';
    el.title = 'Changes save automatically and show on the display right away';
  }
}

// ---------- Sprites (each widget drawn by the server) ----------

let spriteRequest = 0;
let spriteTimer = null;

function refreshSpritesSoon(delay = 60) {
  clearTimeout(spriteTimer);
  spriteTimer = setTimeout(refreshSprites, delay);
}

function storeSprite(id, sprite) {
  const previous = state.sprites.get(id);
  if (sprite.error) {
    state.sprites.set(id, { ...(previous || {}), error: sprite.error });
    return;
  }
  const pixels = sprite.rgba ? decodeBase64(sprite.rgba) : previous && previous.pixels;
  state.sprites.set(id, { w: sprite.w, h: sprite.h, hash: sprite.hash, note: sprite.note, pixels, error: null });
}

async function refreshSprites() {
  clearTimeout(spriteTimer);
  const widgets = screens().flatMap(s => s.widgets).map(({ id, type, options }) => ({ id, type, options }));
  const known = {};
  for (const w of widgets) {
    const sprite = state.sprites.get(w.id);
    if (sprite && sprite.hash && sprite.pixels) known[w.id] = sprite.hash;
  }
  const request = ++spriteRequest;
  const sent = new Map([...anchors].map(([id, anchor]) => [id, anchor.edit]));
  try {
    const { sprites } = await api.render(widgets, known);
    if (request !== spriteRequest) return; // a newer request is on its way
    let moved = false;
    for (const [id, sprite] of Object.entries(sprites)) {
      const before = state.sprites.get(id);
      storeSprite(id, sprite);
      const after = state.sprites.get(id);
      const anchor = anchors.get(id);
      const widget = findAnywhere(id);
      if (anchor && sent.has(id) && widget && !drag.active) {
        moved = keepAlignedSide(widget, anchor) || moved;
        // Edits since this request was sent are measured from here
        if (anchor.edit === sent.get(id)) anchors.delete(id);
        else [anchor.w, anchor.h] = widgetSize(widget);
      }
      if (before && before.w && after.w && (before.w !== after.w || before.h !== after.h)) moved = keepOnDisplay(id) || moved;
    }
    for (const id of anchors.keys()) if (!findAnywhere(id)) anchors.delete(id);
    // Part of the change that resized it, so it needs no undo step of its own
    if (moved) scheduleSave();
    const ids = new Set(widgets.map(w => w.id));
    for (const id of state.sprites.keys()) if (!ids.has(id)) state.sprites.delete(id);
    if (!drag.active) {
      renderBoard();
      renderScreenList();
      renderLayers();
      syncInspector();
    }
  } catch {
    // shown by the live view's connection status
  }
}

// When a setting makes a box bigger (a larger font, showing seconds), moves it back onto
// the display if it now hangs off an edge. Returns whether it moved.
function keepOnDisplay(id) {
  if (drag.active) return false;
  for (const screen of screens()) {
    const widget = screen.widgets.find(w => w.id === id);
    if (!widget) continue;
    const [width, height] = widgetSize(widget);
    const [x, y] = clampPosition(widget.x, widget.y, width, height);
    if (x === widget.x && y === widget.y) return false;
    widget.x = x;
    widget.y = y;
    return true;
  }
  return false;
}

// ---------- Keeping the aligned side in place ----------

// When an edit in the inspector changes a box's size (a bigger font, a longer label), the side
// the component is aligned to stays where it was: a right-aligned temperature grows to the left.
// The server measures the new size, so the size from before the edit is kept until it has.
const anchors = new Map(); // widget id -> {w, h, edit}
let edits = 0;

function findAnywhere(id) {
  for (const screen of screens()) {
    const widget = screen.widgets.find(w => w.id === id);
    if (widget) return widget;
  }
  return null;
}

// The widget's align and valign, if the inspector shows them (null if not)
function alignment(widget) {
  const component = state.catalog.get(widget.type);
  const shown = key => {
    const option = component.options.find(o => o.key === key);
    return option && matches(option.show_if, widget.options) ? widget.options[key] : null;
  };
  return { align: shown('align'), valign: shown('valign') };
}

// Call before an edit that may change the widget's size
function rememberSize(widget) {
  if (!anchors.has(widget.id)) {
    const [w, h] = widgetSize(widget);
    anchors.set(widget.id, { w, h });
  }
  anchors.get(widget.id).edit = ++edits;
}

// Moves a widget so its aligned side is where it was when it was `before` in size. Returns whether it moved.
function keepAlignedSide(widget, before) {
  const [w, h] = widgetSize(widget);
  const { align, valign } = alignment(widget);
  const offset = (side, far, near, grew) => (side === far ? grew : side === near ? Math.round(grew / 2) : 0);
  const dx = offset(align, 'right', 'center', before.w - w);
  const dy = offset(valign, 'bottom', 'middle', before.h - h);
  if (!dx && !dy) return false;
  widget.x += dx;
  widget.y += dy;
  return true;
}

// ---------- Actions ----------

function selectScreen(id) {
  if (state.screenId === id) return;
  state.screenId = id;
  state.selectedId = null;
  render();
}

function select(id) {
  if (state.selectedId === id) return;
  state.selectedId = id;
  render();
}

// Adds a widget with its default options (plus any in `options`). `size` is its box if known
// ahead of the server drawing it; x, y default to the middle of the display.
function addWidget(type, x, y, options = {}, size = null) {
  const component = state.catalog.get(type);
  const [w, h] = size || [component.thumbnail.w, component.thumbnail.h];
  if (x === undefined) [x, y] = [Math.round((state.W - w) / 2), Math.round((state.H - h) / 2)];
  [x, y] = clampPosition(x, y, w, h);
  const widget = { id: uid('w'), type, x, y, hidden: false, options: { ...clone(component.defaults), ...options } };
  if (!size) state.sprites.set(widget.id, { ...component.sprite });
  change(() => {
    // Backgrounds (scenes) go under everything already there
    if (component.background) currentScreen().widgets.unshift(widget);
    else currentScreen().widgets.push(widget);
    state.selectedId = widget.id;
  }, { sprites: true });
}

function duplicateWidget(id) {
  const widgets = currentScreen().widgets;
  const index = widgets.findIndex(w => w.id === id);
  if (index < 0) return;
  const copy = clone(widgets[index]);
  copy.id = uid('w');
  const [w, h] = widgetSize(widgets[index]);
  [copy.x, copy.y] = clampPosition(copy.x + 2, copy.y + 2, w, h);
  if (state.sprites.has(id)) state.sprites.set(copy.id, { ...state.sprites.get(id) });
  change(() => {
    widgets.splice(index + 1, 0, copy);
    state.selectedId = copy.id;
  }, { sprites: true });
}

function deleteWidget(id) {
  change(() => {
    const widgets = currentScreen().widgets;
    const index = widgets.findIndex(w => w.id === id);
    if (index >= 0) widgets.splice(index, 1);
    if (state.selectedId === id) state.selectedId = null;
  });
}

// Moves a widget up (towards the top, drawn last) or down the stack; ±Infinity for the very top or bottom
function restack(id, delta) {
  change(() => {
    const widgets = currentScreen().widgets;
    const from = widgets.findIndex(w => w.id === id);
    const to = clamp(from + delta, 0, widgets.length - 1);
    if (from < 0 || to === from) return;
    widgets.splice(to, 0, widgets.splice(from, 1)[0]);
  });
}

// Moves a widget's box to an edge or the middle of the display: left, center, right, top, middle or bottom
function placeWidget(id, side) {
  updateWidget(id, w => {
    const [width, height] = widgetSize(w);
    if (side === 'left') w.x = 0;
    else if (side === 'center') w.x = Math.round((state.W - width) / 2);
    else if (side === 'right') w.x = state.W - width;
    else if (side === 'top') w.y = 0;
    else if (side === 'middle') w.y = Math.round((state.H - height) / 2);
    else if (side === 'bottom') w.y = state.H - height;
  }, { inspector: false });
}

function copyWidget(id) {
  const widget = findWidget(id);
  if (!widget) return;
  const sprite = state.sprites.get(id);
  state.clipboard = { widget: clone(widget), size: widgetSize(widget), sprite: sprite ? { ...sprite } : null };
}

function cutWidget(id) {
  copyWidget(id);
  deleteWidget(id);
}

// Pastes the copied widget onto the screen being edited: centered on `at` (in LEDs) if given,
// otherwise where it was, nudged along if a copy is already there.
function pasteWidget(at) {
  const clip = state.clipboard;
  if (!clip) return;
  const [w, h] = clip.size;
  const copy = clone(clip.widget);
  copy.id = uid('w');
  let { x, y } = copy;
  if (at) {
    [x, y] = [Math.round(at.x - w / 2), Math.round(at.y - h / 2)];
  } else {
    const taken = (px, py) => currentScreen().widgets.some(o => o.type === copy.type && o.x === px && o.y === py);
    for (let i = 0; i < 20 && taken(x, y); i++) [x, y] = clampPosition(x + 2, y + 2, w, h);
  }
  [copy.x, copy.y] = clampPosition(x, y, w, h);
  if (clip.sprite) state.sprites.set(copy.id, { ...clip.sprite });
  change(() => {
    currentScreen().widgets.push(copy);
    state.selectedId = copy.id;
  }, { sprites: true });
}

function toggleHidden(id) {
  updateWidget(id, w => (w.hidden = !w.hidden));
}

function updateWidget(id, mutate, options) {
  change(() => {
    const widget = findWidget(id);
    if (widget) mutate(widget);
  }, options);
}

// Adds a blank screen, or a copy of a prebuilt one
function addScreen(prebuilt = null) {
  const screen = { id: uid('s'), name: `Screen ${screens().length + 1}`, duration: 15, enabled: true, widgets: [] };
  if (prebuilt) {
    const names = new Set(screens().map(s => s.name));
    let name = prebuilt.name;
    for (let n = 2; names.has(name); n++) name = `${prebuilt.name} ${n}`;
    screen.name = name;
    screen.widgets = prebuilt.widgets.map(widget => ({ ...clone(widget), id: uid('w') }));
  }
  change(() => {
    screens().push(screen);
    state.screenId = screen.id;
    state.selectedId = null;
  }, { sprites: Boolean(prebuilt) });
}

// ---------- New screen picker ----------
//
// The + next to Screens opens it: start from a blank screen, or pick a prebuilt one. The
// prebuilt previews are live, redrawn by the server several times a second while it's open,
// so they follow the time and the weather just as they will on the display.

const picker = { canvases: new Map(), timer: null, busy: false };

function drawPickerFrame(canvas, frame) {
  drawLeds(canvas, decodeBase64(frame.rgb), frame.w, frame.h, 5, { background: '#060708' });
}

function openNewScreen() {
  const dialog = $('#new-screen');
  const choose = prebuilt => {
    dialog.close();
    addScreen(prebuilt);
  };
  picker.canvases.clear();
  const card = prebuilt => {
    const canvas = h('canvas', { 'aria-hidden': 'true' });
    drawPickerFrame(canvas, prebuilt.thumbnail);
    picker.canvases.set(prebuilt.id, canvas);
    return h('button', { type: 'button', class: 'picker-card', onclick: () => choose(prebuilt) },
      h('span', { class: 'picker-art' }, canvas),
      h('span', { class: 'picker-name' }, prebuilt.name),
      h('span', { class: 'picker-desc' }, prebuilt.description));
  };
  dialog.replaceChildren(h('div', { class: 'picker-body' },
    h('div', { class: 'picker-head' },
      h('h2', { id: 'new-screen-title' }, 'New screen'),
      h('button', { type: 'button', class: 'icon-btn', title: 'Close (Esc)', onclick: () => dialog.close() }, icon('x'))),
    h('button', { type: 'button', class: 'picker-blank', onclick: () => choose(null) },
      h('span', { class: 'picker-blank-art' }, icon('plus')),
      h('span', { class: 'picker-text' },
        h('span', { class: 'picker-name' }, 'Blank screen'),
        h('span', { class: 'picker-desc' }, 'Start empty and add components yourself'))),
    state.prebuilt.length ? h('div', { class: 'picker-heading' },
      h('span', null, 'Prebuilt'),
      h('span', { class: 'picker-live' }, h('span', { class: 'live-dot' }), 'Live: the time and weather right now')) : null,
    h('div', { class: 'picker-grid' }, ...state.prebuilt.map(card))));
  dialog.showModal();
  pollPicker();
}

async function pollPicker() {
  clearTimeout(picker.timer);
  const dialog = $('#new-screen');
  if (!dialog.open) return;
  if (!document.hidden && !picker.busy) {
    picker.busy = true;
    try {
      const { screens } = await api.prebuilt();
      if (dialog.open) {
        for (const screen of screens) {
          const canvas = picker.canvases.get(screen.id);
          if (canvas) drawPickerFrame(canvas, screen.frame);
        }
      }
    } catch {
      // keep the last frames; the live view shows if the app is offline
    } finally {
      picker.busy = false;
    }
  }
  if (dialog.open) picker.timer = setTimeout(pollPicker, 150);
}

function setUpPicker() {
  const dialog = $('#new-screen');
  // A click on the dimmed backdrop lands on the dialog itself (its content fills it)
  dialog.addEventListener('click', e => {
    if (e.target === dialog) dialog.close();
  });
  // Keys belong to the picker while it's open, so they can't undo or delete behind it
  dialog.addEventListener('keydown', e => e.stopPropagation());
  dialog.addEventListener('close', () => clearTimeout(picker.timer));
}

function duplicateScreen(id) {
  const index = screens().findIndex(s => s.id === id);
  const copy = clone(screens()[index]);
  copy.id = uid('s');
  copy.name = `${copy.name} copy`.slice(0, 40);
  for (const widget of copy.widgets) {
    const old = widget.id;
    widget.id = uid('w');
    if (state.sprites.has(old)) state.sprites.set(widget.id, { ...state.sprites.get(old) });
  }
  change(() => {
    screens().splice(index + 1, 0, copy);
    state.screenId = copy.id;
    state.selectedId = null;
  }, { sprites: true });
}

function deleteScreen(id) {
  if (screens().length < 2) return;
  const screen = findScreen(id);
  if (screen.widgets.length && !confirm(`Delete “${screen.name}” and the ${screen.widgets.length} component(s) on it? You can undo this.`)) return;
  change(() => {
    const index = screens().findIndex(s => s.id === id);
    screens().splice(index, 1);
    state.screenId = screens()[Math.max(0, index - 1)].id;
    state.selectedId = null;
  });
}

function moveScreen(id, delta) {
  change(() => {
    const list = screens();
    const from = list.findIndex(s => s.id === id);
    const to = from + delta;
    if (to < 0 || to >= list.length) return;
    list.splice(to, 0, list.splice(from, 1)[0]);
  });
}

function updateScreen(id, mutate, options) {
  change(() => {
    const screen = findScreen(id);
    if (screen) mutate(screen);
  }, options);
}

// Waits for pending changes to reach the server (e.g. a screen you just added)
async function saved() {
  for (let i = 0; i < 20 && (saving.inFlight || saving.dirty) && !saving.error; i++) {
    if (saving.inFlight) await new Promise(resolve => setTimeout(resolve, 100));
    else await save();
  }
}

async function showNow(id) {
  try {
    await saved();
    await api.show(id);
    pollLive();
  } catch (error) {
    toast(`Couldn't show it: ${error.message}`);
  }
}

let toastTimer = null;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 4000);
}

// ---------- Rendering ----------

function render({ inspector = true } = {}) {
  if (!findScreen(state.screenId)) state.screenId = screens()[0].id;
  if (state.selectedId && !findWidget(state.selectedId)) state.selectedId = null;
  renderScreenList();
  renderStage();
  renderBoard();
  renderLayers();
  if (inspector) renderInspector();
  else syncInspector();
}

function renderScreenList() {
  const liveId = state.live && state.live.screen && state.live.screen.id;
  syncList($('#screen-list'), screens(), s => s.id, id => {
    const toggle = h('input', {
      type: 'checkbox',
      onchange: () => updateScreen(id, s => (s.enabled = toggle.checked)),
    });
    return h('li', {
      class: 'screen-item',
      onclick: e => { if (!e.target.closest('.switch')) selectScreen(id); },
      oncontextmenu: e => {
        e.preventDefault();
        selectScreen(id);
        screenMenu(id, e.clientX, e.clientY);
      },
    },
      h('canvas', { class: 'screen-thumb' }),
      h('div', { class: 'screen-info' },
        h('div', { class: 'screen-name' }),
        h('div', { class: 'screen-meta' }, h('span'), h('span', { class: 'live-pill' }, 'Live'))),
      h('label', { class: 'switch', title: 'Take turns on the display' }, toggle, h('span')));
  }, (el, screen) => {
    el.className = cls('screen-item', screen.id === state.screenId && 'active', !screen.enabled && 'off',
      screen.id === liveId && 'live');
    el.querySelector('.screen-name').textContent = screen.name;
    el.querySelector('.screen-meta span').textContent = screen.enabled ? `${screen.duration}s` : 'Not in rotation';
    el.querySelector('input').checked = screen.enabled;
    drawLeds(el.querySelector('canvas'), compose(screen.widgets, state.sprites, state.W, state.H),
      state.W, state.H, 1.25, { off: null });
  });

  const enabled = screens().filter(s => s.enabled);
  $('#rotation-hint').textContent = !enabled.length
    ? 'No screen is in the rotation, so the display is blank.'
    : enabled.length === 1
      ? `“${enabled[0].name}” stays on the display. Add more screens to take turns.`
      : `${enabled.length} screens take turns, each for its time.`;
  $('#rotation-hint').classList.toggle('warning', !enabled.length);
}

function renderStage() {
  const screen = currentScreen();
  const live = state.live && state.live.screen && state.live.screen.id === screen.id;
  $('#screen-title').textContent = screen.name;
  $('#screen-sub').textContent = live ? 'On the display now' : screen.enabled ? `${screen.duration}s in the rotation` : 'Not in the rotation';
  $('#screen-sub').classList.toggle('live', Boolean(live));
  $('#undo').disabled = !history.undo.length;
  $('#redo').disabled = !history.redo.length;
  $('#toggle-outlines').setAttribute('aria-pressed', String(state.outlines));

  const widget = selectedWidget();
  const foot = $('#stage-foot');
  if (widget) {
    const [w, h] = widgetSize(widget);
    foot.textContent = `${state.catalog.get(widget.type).label} · x ${widget.x}, y ${widget.y} · ${w} × ${h}   —   right-click for more · arrows nudge (${SHIFT} by 5) · ${DELETE_KEY} delete`;
  } else {
    foot.textContent = `${state.W} × ${state.H} LEDs   —   click a component to select it, drag to move it, right-click for more`;
  }
}

// LED size on the board: as big as fits. Wide windows give the board the space between the
// sidebars; narrower ones scroll, so there the board's own height can't be the limit.
function computePitch() {
  const wrap = $('#board-wrap');
  const style = getComputedStyle(wrap);
  const board = 28; // .board padding
  const width = wrap.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - board;
  const height = window.matchMedia('(max-width: 1180px)').matches
    ? window.innerHeight * 0.55
    : wrap.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom) - board;
  state.pitch = clamp(Math.floor(Math.min(width / state.W, height / state.H) * 2) / 2, 3, 22);
}

function renderBoard() {
  const screen = currentScreen();
  const P = state.pitch;
  drawLeds($('#board-canvas'), compose(screen.widgets, state.sprites, state.W, state.H), state.W, state.H, P);

  const overlay = $('#overlay');
  overlay.style.width = `${state.W * P}px`;
  overlay.style.height = `${state.H * P}px`;
  overlay.classList.toggle('outlines', state.outlines);
  syncList(overlay, screen.widgets, w => w.id,
    () => h('div', { class: 'box' }, h('span', { class: 'box-label' }), h('span', { class: 'box-handle' })),
    (el, widget, i) => {
      const [w, hgt] = widgetSize(widget);
      const component = state.catalog.get(widget.type);
      const selected = widget.id === state.selectedId;
      el.style.left = `${widget.x * P}px`;
      el.style.top = `${widget.y * P}px`;
      el.style.width = `${w * P}px`;
      el.style.height = `${hgt * P}px`;
      // The selected one comes to the front so you can drag it even if something covers it
      el.style.zIndex = selected ? 1000 : i + 1;
      el.className = cls('box', selected && 'selected', widget.hidden && 'is-hidden',
        canResize(widget) && (component.resize.h ? 'resize-both' : 'resize-width'),
        widget.y * P < 24 && 'label-below');
      el.querySelector('.box-label').textContent = component.label;
    });
}

function summary(widget) {
  const o = widget.options;
  const component = state.catalog.get(widget.type);
  const choice = key => {
    const option = component.options.find(opt => opt.key === key);
    const found = option && option.choices.find(c => c.value === o[key]);
    return found ? found.label : '';
  };
  switch (widget.type) {
    case 'text': return o.text ? `“${o.text}”` : 'empty';
    case 'clock':
    case 'time': return `${o.hours}-hour · ${o.font}`;
    case 'date': return choice('format');
    case 'weather': return choice('show');
    case 'box': return `${o.width} × ${o.height}${o.fill ? '' : ' outline'}`;
    case 'image': {
      const image = state.images.find(i => i.id === o.image);
      return image ? image.name : 'missing image';
    }
    case 'countdown': return o.label ? `${o.label} · ${o.date}` : o.date;
    case 'scene': return choice('theme');
    default: return '';
  }
}

function renderLayers() {
  const widgets = currentScreen().widgets.slice().reverse(); // top of the stack first
  $('#layers-empty').hidden = widgets.length > 0;
  syncList($('#layers'), widgets, w => w.id, id => {
    const eye = h('button', {
      class: 'icon-btn small',
      type: 'button',
      onclick: e => {
        e.stopPropagation();
        toggleHidden(id);
      },
    });
    return h('li', {
      class: 'layer',
      onclick: () => select(id),
      oncontextmenu: e => {
        e.preventDefault();
        select(id);
        widgetMenu(id, e.clientX, e.clientY);
      },
    },
      eye,
      h('span', { class: 'layer-name' }),
      h('span', { class: 'layer-summary' }));
  }, (el, widget) => {
    el.className = cls('layer', widget.id === state.selectedId && 'selected', widget.hidden && 'is-hidden');
    const eye = el.querySelector('button');
    eye.replaceChildren(icon(widget.hidden ? 'eyeOff' : 'eye'));
    eye.title = widget.hidden ? 'Hidden. Click to show it' : 'Hide it (stays in the layout)';
    el.querySelector('.layer-name').textContent = state.catalog.get(widget.type).label;
    el.querySelector('.layer-summary').textContent = summary(widget);
  });
}

// ---------- Inspector (the settings panel) ----------

// Inputs showing layout values, refreshed by syncInspector() unless you're typing in them
let bound = [];

function bind(el, read, prop = 'value') {
  bound.push({ el, read, prop });
  el[prop] = read();
  return el;
}

function syncInspector() {
  for (const { el, read, prop } of bound) {
    if (document.activeElement === el) continue;
    const value = read();
    if (value !== undefined && el[prop] !== value) el[prop] = value;
  }
  const note = $('#inspector-note');
  const widget = selectedWidget();
  if (note && widget) {
    const sprite = state.sprites.get(widget.id);
    const text = sprite && (sprite.error ? `Couldn't draw it: ${sprite.error}` : sprite.note);
    note.textContent = text || '';
    note.hidden = !text;
    note.classList.toggle('error', Boolean(sprite && sprite.error));
  }
  renderStage();
}

function field(label, control, extra) {
  return h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control, extra);
}

function numberInput({ min, max, read, write }) {
  const input = h('input', {
    type: 'number',
    step: 1,
    min: min ?? '',
    max: max ?? '',
    oninput: () => {
      const value = parseInt(input.value, 10);
      if (!Number.isNaN(value)) write(clamp(value, min ?? -Infinity, max ?? Infinity));
    },
    onblur: () => (input.value = read()),
  });
  return bind(input, read);
}

function switchInput(read, write) {
  const input = h('input', { type: 'checkbox', onchange: () => write(input.checked) });
  bind(input, read, 'checked');
  return h('span', { class: 'switch' }, input, h('span'));
}

function selectInput(choices, read, write) {
  const select = h('select', { onchange: () => write(select.value) },
    ...choices.map(c => h('option', { value: c.value }, c.label)));
  return bind(select, read);
}

function optionField(widget, option) {
  const id = widget.id;
  const read = () => {
    const w = findWidget(id);
    return w ? w.options[option.key] : undefined;
  };
  // Changes that can show or hide other fields rebuild the panel
  const write = (value, rebuild = false) => updateWidget(id, w => {
    rememberSize(w);
    w.options[option.key] = value;
    // If this sets the box's size (e.g. turning on scrolling), keep the box on the display
    if (canResize(w)) {
      const [width, height] = widgetSize(w);
      [w.x, w.y] = clampPosition(w.x, w.y, width, height);
    }
  }, { key: `option:${id}:${option.key}`, sprites: true, inspector: rebuild });

  switch (option.type) {
    case 'text':
      return field(option.label, bind(h('input', {
        type: 'text',
        maxLength: option.maxlength,
        oninput: e => write(e.target.value),
      }), read));
    case 'number':
      return field(option.label, h('span', { class: 'with-unit' },
        numberInput({ min: option.min, max: option.max, read, write }),
        option.unit ? h('span', { class: 'unit' }, option.unit) : null));
    case 'bool':
      return h('label', { class: 'field inline' },
        h('span', { class: 'field-label' }, option.label),
        switchInput(read, value => write(value, true)));
    case 'color': {
      const picker = bind(h('input', { type: 'color', oninput: e => write(e.target.value) }), read);
      const swatches = h('span', { class: 'swatches' }, ...SWATCHES.map(color => h('button', {
        type: 'button',
        class: cls('swatch', read() === color && 'current'),
        style: { background: color },
        title: color,
        onclick: () => write(color, true),
      })));
      return field(option.label, h('span', { class: 'color-row' }, picker, swatches));
    }
    case 'font': {
      // A font setting whose default is 'auto' picks a size that suits what the component shows
      const fonts = state.fonts.map(f => ({ value: f, label: f }));
      if (option.default === 'auto') fonts.unshift({ value: 'auto', label: 'Automatic' });
      return field(option.label, selectInput(fonts, read, write));
    }
    case 'select':
      return field(option.label, selectInput(option.choices, read, value => write(value, true)));
    case 'date':
    case 'time':
      // The browser leaves the value empty until it's a whole date or time
      return field(option.label, bind(h('input', {
        type: option.type,
        required: true,
        oninput: e => { if (e.target.value) write(e.target.value); },
      }), read));
    case 'image':
      return imageField(widget, option, read);
    default:
      return null;
  }
}

const SIDE_NAMES = { left: 'Left', center: 'Center', right: 'Right', top: 'Top', middle: 'Middle', bottom: 'Bottom' };

// "Top right", "Bottom", "Left", "Center"...
function alignmentName(align, valign) {
  if (!valign || valign === 'middle') return SIDE_NAMES[align || valign];
  if (!align || align === 'center') return SIDE_NAMES[valign];
  return `${SIDE_NAMES[valign]} ${align}`;
}

// The align and valign options as one grid: where what's showing sits in its box. Either can be
// missing (scrolling text only lines up top to bottom), which leaves a row or column of three.
function alignField(widget, horizontal, vertical) {
  const id = widget.id;
  const read = key => {
    const w = findWidget(id);
    return w ? w.options[key] : undefined;
  };
  const columns = horizontal ? horizontal.choices.map(c => c.value) : [null];
  const rows = vertical ? vertical.choices.map(c => c.value) : [null];
  const cells = rows.flatMap(valign => columns.map(align => {
    const name = alignmentName(align, valign);
    const current = () => (!align || read('align') === align) && (!valign || read('valign') === valign);
    const cell = h('button', {
      type: 'button',
      class: 'align-cell',
      title: name,
      'aria-label': name,
      dataset: { align: align || 'center', valign: valign || 'middle' },
      onclick: () => updateWidget(id, w => {
        rememberSize(w);
        if (align) w.options.align = align;
        if (valign) w.options.valign = valign;
      }, { key: `align:${id}`, sprites: true, inspector: false }),
    }, h('i'));
    return bind(cell, () => cls('align-cell', current() && 'current'), 'className');
  }));
  const grid = h('div', { class: 'align-grid', style: { gridTemplateColumns: `repeat(${columns.length}, 22px)` } }, ...cells);
  const label = bind(h('span', { class: 'align-name' }),
    () => alignmentName(horizontal && read('align'), vertical && read('valign')), 'textContent');
  return h('div', { class: 'field' },
    h('span', { class: 'field-label' }, 'Align'),
    h('div', { class: 'align-row' }, grid,
      h('span', { class: 'align-text' }, label,
        h('span', { class: 'align-hint' }, 'in its box, by the LEDs it lights. It’s also the side that stays put when the box changes size.'))));
}

// ---------- Images ----------

const imageUrl = image => `/api/images/file/${image.id}`;
const imageBox = (image, width) => [width, Math.max(1, Math.round((width * image.height) / image.width))];

async function loadImages() {
  try {
    state.images = (await api.images()).images;
  } catch (error) {
    toast(`Couldn't load the images: ${error.message}`);
  }
}

// Uploads an image file; returns its info, or null (after saying why) if it didn't work
async function uploadImage(file) {
  toast(`Uploading ${file.name}…`);
  try {
    const { image } = await api.uploadImage(file);
    await loadImages();
    toast(`Uploaded ${file.name}`);
    return image;
  } catch (error) {
    toast(`Couldn't upload ${file.name}: ${error.message}`);
    return null;
  }
}

// Shows `image` in a widget, sized to fit the display
function pickImage(widgetId, image) {
  updateWidget(widgetId, w => {
    w.options.image = image.id;
    w.options.width = image.fit_width;
    const [width, height] = imageBox(image, image.fit_width);
    [w.x, w.y] = clampPosition(w.x, w.y, width, height);
  }, { sprites: true });
}

async function deleteImage(image) {
  const users = screens().flatMap(s => s.widgets).filter(w => w.type === 'image' && w.options.image === image.id).length;
  const warning = users === 0 ? '' : users === 1 ? ' A component shows it and will go blank.' : ` ${users} components show it and will go blank.`;
  if (!confirm(`Delete “${image.name}”?${warning} This can't be undone.`)) return;
  try {
    await api.deleteImage(image.id);
  } catch (error) {
    toast(`Couldn't delete it: ${error.message}`);
  }
  await loadImages();
  refreshSpritesSoon();
  render();
}

function imageField(widget, option, read) {
  const id = widget.id;
  const fileInput = h('input', {
    type: 'file',
    accept: 'image/png,image/jpeg,image/gif,image/webp',
    hidden: true,
    onchange: async () => {
      const file = fileInput.files[0];
      fileInput.value = '';
      const image = file && (await uploadImage(file));
      if (image) pickImage(id, image);
    },
  });
  const choice = image => h('div', { class: cls('image-choice', read() === image.id && 'current') },
    h('button', {
      type: 'button',
      class: 'image-pick',
      title: `${image.name} · ${image.width}×${image.height}${image.frames > 1 ? ` · animated, ${image.frames} frames` : ''}`,
      onclick: () => pickImage(id, image),
    }, h('img', { src: imageUrl(image), alt: image.name })),
    image.builtin ? null : h('button', {
      type: 'button',
      class: 'image-delete',
      title: `Delete “${image.name}”`,
      onclick: () => deleteImage(image),
    }, icon('x')));
  const group = (label, list) => list.length
    ? h('div', { class: 'image-group' }, h('span', { class: 'image-group-label' }, label), h('div', { class: 'image-grid' }, ...list.map(choice)))
    : null;
  return h('div', { class: 'field' },
    h('span', { class: 'field-label' }, option.label),
    h('div', { class: 'image-picker' },
      h('button', { type: 'button', class: 'btn upload-btn', onclick: () => fileInput.click() }, icon('upload'), 'Upload an image'),
      h('p', { class: 'hint small' }, 'PNG, JPG, GIF or WebP. You can also drop a file onto the display.'),
      group('Your images', state.images.filter(i => !i.builtin)),
      group('Icons', state.images.filter(i => i.builtin))),
    fileInput);
}

const hasFiles = e => Boolean(e.dataTransfer) && Array.from(e.dataTransfer.types || []).includes('Files');

// Dropping an image file on the display uploads it and adds it where it was dropped
function setUpFileDrop() {
  const wrap = $('#board-wrap');
  // A file dropped anywhere else would make the browser leave the page to open it
  window.addEventListener('dragover', e => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener('drop', e => { if (hasFiles(e)) e.preventDefault(); });
  wrap.addEventListener('dragover', e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    wrap.classList.add('file-over');
  });
  wrap.addEventListener('dragleave', e => {
    if (!wrap.contains(e.relatedTarget)) wrap.classList.remove('file-over');
  });
  wrap.addEventListener('drop', async e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    wrap.classList.remove('file-over');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const rect = $('#overlay').getBoundingClientRect();
    const at = { x: (e.clientX - rect.left) / state.pitch, y: (e.clientY - rect.top) / state.pitch };
    const image = await uploadImage(file);
    if (!image) return;
    const [w, hgt] = imageBox(image, image.fit_width);
    addWidget('image', Math.round(at.x - w / 2), Math.round(at.y - hgt / 2), { image: image.id, width: image.fit_width }, [w, hgt]);
  });
}

function actionButton(label, iconName, onclick, { danger = false, disabled = false, title = '' } = {}) {
  return h('button', { type: 'button', class: cls('btn', danger && 'danger'), onclick, disabled, title },
    icon(iconName), label);
}

function widgetInspector(widget) {
  const id = widget.id;
  const component = state.catalog.get(widget.type);
  const widgets = currentScreen().widgets;
  const index = widgets.indexOf(widget);
  const position = axis => numberInput({
    read: () => {
      const w = findWidget(id);
      return w ? w[axis] : undefined;
    },
    write: value => updateWidget(id, w => {
      const [width, height] = widgetSize(w);
      const [x, y] = clampPosition(axis === 'x' ? value : w.x, axis === 'y' ? value : w.y, width, height);
      w.x = x;
      w.y = y;
    }, { key: `position:${id}`, inspector: false }),
  });

  const place = (side, iconName, title) =>
    h('button', { type: 'button', class: 'icon-btn', title, 'aria-label': title, onclick: () => placeWidget(id, side) }, icon(iconName));
  const shown = component.options.filter(o => matches(o.show_if, widget.options));
  const horizontal = shown.find(o => o.type === 'align');
  const vertical = shown.find(o => o.type === 'valign');
  const fieldFor = o => {
    if (o.type === 'align' || (o.type === 'valign' && !horizontal)) return alignField(widget, horizontal, vertical);
    return o.type === 'valign' ? null : optionField(widget, o);
  };

  return [
    h('div', { class: 'panel-head' },
      h('h2', {}, component.label),
      h('button', { class: 'icon-btn', type: 'button', title: 'Done (Esc)', onclick: () => select(null) }, icon('x'))),
    h('p', { class: 'hint' }, component.description),
    h('div', { class: 'field-row' },
      field('X', position('x')),
      field('Y', position('y'))),
    !component.background && h('div', { class: 'field' },
      h('span', { class: 'field-label' }, 'Move to the display’s'),
      h('div', { class: 'place-row' },
        h('span', { class: 'place-group' },
          place('left', 'toLeft', 'Left edge'), place('center', 'centerX', 'Center'), place('right', 'toRight', 'Right edge')),
        h('span', { class: 'place-group' },
          place('top', 'toTop', 'Top edge'), place('middle', 'centerY', 'Middle'), place('bottom', 'toBottom', 'Bottom edge')))),
    ...shown.map(fieldFor),
    h('p', { class: 'note', id: 'inspector-note', hidden: true }),
    h('div', { class: 'actions' },
      actionButton('Forward', 'forward', () => restack(id, 1), { disabled: index === widgets.length - 1, title: 'Bring forward ( ] )' }),
      actionButton('Back', 'backward', () => restack(id, -1), { disabled: index === 0, title: 'Send backward ( [ )' }),
      actionButton('Duplicate', 'copy', () => duplicateWidget(id), { title: '⌘D' }),
      actionButton(widget.hidden ? 'Show' : 'Hide', widget.hidden ? 'eye' : 'eyeOff', () => updateWidget(id, w => (w.hidden = !w.hidden))),
      actionButton('Delete', 'trash', () => deleteWidget(id), { danger: true, title: 'Delete (⌫)' })),
  ];
}

function screenInspector(screen) {
  const id = screen.id;
  const read = key => () => {
    const s = findScreen(id);
    return s ? s[key] : undefined;
  };
  const index = screens().indexOf(screen);
  return [
    h('div', { class: 'panel-head' }, h('h2', {}, 'Screen')),
    field('Name', bind(h('input', {
      type: 'text',
      maxLength: 40,
      oninput: e => updateScreen(id, s => (s.name = e.target.value), { key: `name:${id}`, inspector: false }),
      onblur: e => { if (!e.target.value.trim()) updateScreen(id, s => (s.name = `Screen ${index + 1}`)); },
    }), read('name'))),
    field('Show for', h('span', { class: 'with-unit' },
      numberInput({
        min: 1,
        max: 86400,
        read: read('duration'),
        write: value => updateScreen(id, s => (s.duration = value), { key: `duration:${id}`, inspector: false }),
      }),
      h('span', { class: 'unit' }, 'seconds'))),
    h('label', { class: 'field inline' },
      h('span', { class: 'field-label' }, 'Take turns on the display'),
      switchInput(read('enabled'), value => updateScreen(id, s => (s.enabled = value)))),
    h('p', { class: 'hint' }, 'Screens that take turns are shown in order, each for its time. Select a component on the display to change it.'),
    h('div', { class: 'actions' },
      actionButton('Show now', 'show', () => showNow(id), { title: 'Put this screen on the display now, for its time' }),
      actionButton('Duplicate', 'copy', () => duplicateScreen(id)),
      actionButton('Up', 'up', () => moveScreen(id, -1), { disabled: index === 0, title: 'Move up the list' }),
      actionButton('Down', 'down', () => moveScreen(id, 1), { disabled: index === screens().length - 1, title: 'Move down the list' }),
      actionButton('Delete', 'trash', () => deleteScreen(id), { danger: true, disabled: screens().length < 2, title: screens().length < 2 ? 'The display needs at least one screen' : '' })),
  ];
}

function renderInspector() {
  bound = [];
  const widget = selectedWidget();
  $('#inspector').replaceChildren(...(widget ? widgetInspector(widget) : screenInspector(currentScreen())).filter(Boolean));
  syncInspector();
}

// ---------- Dragging on the board ----------

const drag = { active: false };

function onBoardPointerDown(e) {
  if (e.button !== 0 || (isMac && e.ctrlKey)) return; // Ctrl+click on a Mac opens the menu
  const box = e.target.closest('.box');
  if (!box) {
    select(null);
    return;
  }
  e.preventDefault();
  const id = box.dataset.key;
  select(id);
  const widget = findWidget(id);
  const [w, hgt] = widgetSize(widget);
  Object.assign(drag, {
    active: true,
    id,
    resizing: Boolean(e.target.closest('.box-handle')) && canResize(widget),
    before: snapshot(),
    beforeConfig: JSON.stringify(state.config),
    startX: e.clientX,
    startY: e.clientY,
    x: widget.x,
    y: widget.y,
    w,
    h: hgt,
  });
  $('#overlay').setPointerCapture(e.pointerId);
  document.body.classList.add(drag.resizing ? 'resizing' : 'moving');
}

function onBoardPointerMove(e) {
  if (!drag.active) return;
  const widget = findWidget(drag.id);
  if (!widget) return;
  const dx = Math.round((e.clientX - drag.startX) / state.pitch);
  const dy = Math.round((e.clientY - drag.startY) / state.pitch);
  if (drag.resizing) {
    const component = state.catalog.get(widget.type);
    const resize = (key, start, delta, room) => {
      const option = component.options.find(o => o.key === key);
      widget.options[key] = clamp(start + delta, option.min ?? 1, Math.min(option.max ?? 512, Math.max(option.min ?? 1, room)));
    };
    const pad = outlinePad(widget);
    if (component.resize.w) resize(component.resize.w, drag.w - pad, dx, state.W - widget.x - pad);
    if (component.resize.h) resize(component.resize.h, drag.h - pad, dy, state.H - widget.y - pad);
    refreshSpritesSoon(80);
  } else {
    const [x, y] = clampPosition(drag.x + dx, drag.y + dy, drag.w, drag.h);
    if (x === widget.x && y === widget.y) return;
    widget.x = x;
    widget.y = y;
  }
  renderBoard();
  syncInspector();
}

function onBoardPointerUp() {
  if (!drag.active) return;
  drag.active = false;
  document.body.classList.remove('moving', 'resizing');
  if (JSON.stringify(state.config) !== drag.beforeConfig) {
    record(drag.before);
    changed({ sprites: drag.resizing, inspector: false });
  }
}

// ---------- Dragging from the palette ----------

function startPaletteDrag(e, component) {
  if (e.button !== 0 || (isMac && e.ctrlKey)) return;
  e.preventDefault();
  const startX = e.clientX;
  const startY = e.clientY;
  const { w, h: hgt } = component.thumbnail;
  let ghost = null;
  let target = null;

  const move = ev => {
    if (!ghost) {
      if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < 4) return;
      ghost = h('canvas', { class: 'drag-ghost' });
      drawLeds(ghost, component.sprite.pixels, w, hgt, state.pitch, { channels: 4, background: null, off: null });
      document.body.append(ghost);
      document.body.classList.add('moving');
    }
    const P = state.pitch;
    const rect = $('#board-canvas').getBoundingClientRect();
    const inside = ev.clientX >= rect.left && ev.clientX <= rect.right && ev.clientY >= rect.top && ev.clientY <= rect.bottom;
    if (inside) {
      // Snap to the LED grid where it would land
      const [x, y] = clampPosition(
        Math.round((ev.clientX - rect.left) / P - w / 2),
        Math.round((ev.clientY - rect.top) / P - hgt / 2), w, hgt);
      target = { x, y };
      ghost.style.left = `${rect.left + x * P}px`;
      ghost.style.top = `${rect.top + y * P}px`;
    } else {
      target = null;
      ghost.style.left = `${ev.clientX - (w * P) / 2}px`;
      ghost.style.top = `${ev.clientY - (hgt * P) / 2}px`;
    }
    ghost.classList.toggle('over', inside);
  };
  const end = (ev, cancelled) => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('pointercancel', cancel);
    document.body.classList.remove('moving');
    if (!ghost) {
      if (!cancelled) addWidget(component.type); // a click
      return;
    }
    ghost.remove();
    if (target && !cancelled) addWidget(component.type, target.x, target.y);
  };
  const up = ev => end(ev, false);
  const cancel = ev => end(ev, true);
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
  window.addEventListener('pointercancel', cancel);
}

function renderPalette() {
  $('#palette').replaceChildren(...[...state.catalog.values()].map(component => {
    const { w, h: hgt } = component.thumbnail;
    const pitch = clamp(Math.floor(Math.min(96 / w, 40 / hgt) * 2) / 2, 1, 4);
    const thumb = h('canvas', { class: 'palette-thumb' });
    drawLeds(thumb, component.sprite.pixels, w, hgt, pitch, { channels: 4, background: null, off: null });
    return h('li', {
      class: 'palette-item',
      title: `${component.description}. Drag onto the display, or click to add it in the middle.`,
      onpointerdown: e => startPaletteDrag(e, component),
    },
      h('span', { class: 'palette-art' }, thumb),
      h('span', { class: 'palette-text' },
        h('span', { class: 'palette-name' }, component.label),
        h('span', { class: 'palette-desc' }, component.description)));
  }));
}

// ---------- Live view and brightness ----------

let liveTimer = null;

// Polls four times a second while the page is visible. Calling it polls right away.
async function pollLive() {
  clearTimeout(liveTimer);
  if (!document.hidden) {
    try {
      state.live = await api.live();
      state.online = true;
    } catch {
      state.online = false;
    }
    renderLive();
  }
  clearTimeout(liveTimer);
  liveTimer = setTimeout(pollLive, 250);
}

let brightnessTimer = null;
let brightnessHeld = false;
let lastBrightness = 100;

function renderLive() {
  const live = state.live;
  $('#live').classList.toggle('offline', !state.online);
  $('#live-status').textContent = state.online ? 'On the display' : "Can't reach the display";
  if (live) {
    drawLeds($('#live-canvas'), decodeBase64(live.rgb), live.width, live.height, 3, { off: '#121418' });
    $('#live-screen').textContent = live.screen ? live.screen.name : 'Nothing (no screen in rotation)';
    const others = screens().filter(s => s.enabled).length > 1 || (live.screen && !findScreen(live.screen.id)?.enabled);
    $('#live-time').textContent = live.screen && others ? `next in ${Math.ceil(live.remaining)}s` : '';
    $('#live').classList.toggle('dark', live.brightness === 0);
    if (!brightnessHeld) setBrightnessUI(live.brightness);
  }
  // Live badges on the screen list and stage
  const liveId = live && live.screen && live.screen.id;
  for (const el of $('#screen-list').children) el.classList.toggle('live', el.dataset.key === liveId);
  renderStage();
}

function setBrightnessUI(value) {
  $('#brightness').value = value;
  $('#brightness-value').textContent = value === 0 ? 'Off' : `${value}%`;
  $('#brightness').style.setProperty('--fill', `${value}%`);
  $('#power').classList.toggle('off', value === 0);
  if (value > 0) lastBrightness = value;
}

function setBrightness(value) {
  setBrightnessUI(value);
  clearTimeout(brightnessTimer);
  brightnessTimer = setTimeout(async () => {
    try {
      await api.brightness(value);
    } catch (error) {
      toast(`Couldn't change the brightness: ${error.message}`);
    }
    brightnessHeld = false;
  }, 80);
}

// ---------- Keyboard ----------

function onKeyDown(e) {
  const target = e.target;
  const typing = target.closest && target.closest('input, select, textarea') && target.type !== 'checkbox';
  const mod = e.metaKey || e.ctrlKey;
  const key = e.key.toLowerCase();
  if (mod && (key === 'z' || key === 'y')) {
    if (typing) return; // let the field undo its own typing
    e.preventDefault();
    if (key === 'y' || e.shiftKey) redo();
    else undo();
    return;
  }
  if (typing) return;
  const widget = selectedWidget();
  if (e.key === 'Escape') {
    select(null);
    return;
  }
  if (mod && key === 'v' && state.clipboard) {
    e.preventDefault();
    pasteWidget();
    return;
  }
  if (!widget) return;
  const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (arrows[e.key]) {
    e.preventDefault();
    const step = e.shiftKey ? 5 : 1;
    const [dx, dy] = arrows[e.key];
    updateWidget(widget.id, w => {
      const [width, height] = widgetSize(w);
      [w.x, w.y] = clampPosition(w.x + dx * step, w.y + dy * step, width, height);
    }, { key: `position:${widget.id}`, inspector: false });
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault();
    deleteWidget(widget.id);
  } else if (mod && key === 'd') {
    e.preventDefault();
    duplicateWidget(widget.id);
  } else if (mod && key === 'c') {
    e.preventDefault();
    copyWidget(widget.id);
    toast(`Copied the ${state.catalog.get(widget.type).label.toLowerCase()}. Paste it on any screen with ${MOD}V.`);
  } else if (mod && key === 'x') {
    e.preventDefault();
    cutWidget(widget.id);
  } else if (mod || e.altKey) {
    // leave other shortcuts to the browser
  } else if (e.code === 'BracketRight' || e.key === ']' || e.key === '}') {
    restack(widget.id, e.shiftKey ? Infinity : 1);
  } else if (e.code === 'BracketLeft' || e.key === '[' || e.key === '{') {
    restack(widget.id, e.shiftKey ? -Infinity : -1);
  } else if (key === 'h') {
    toggleHidden(widget.id);
  }
}

// ---------- Right-click menus ----------

function widgetMenu(id, x, y) {
  const widgets = currentScreen().widgets;
  const index = widgets.findIndex(w => w.id === id);
  if (index < 0) return;
  const widget = widgets[index];
  const top = index === widgets.length - 1;
  const bottom = index === 0;
  openMenu(x, y, [
    { label: 'Cut', icon: 'cut', shortcut: `${MOD}X`, action: () => cutWidget(id) },
    { label: 'Copy', icon: 'copy', shortcut: `${MOD}C`, action: () => copyWidget(id) },
    { label: 'Paste', icon: 'paste', shortcut: `${MOD}V`, disabled: !state.clipboard, action: () => pasteWidget() },
    { label: 'Duplicate', icon: 'duplicate', shortcut: `${MOD}D`, action: () => duplicateWidget(id) },
    '-',
    { label: 'Bring to front', icon: 'front', shortcut: `${SHIFT}]`, disabled: top, action: () => restack(id, Infinity) },
    { label: 'Bring forward', icon: 'forward', shortcut: ']', disabled: top, action: () => restack(id, 1) },
    { label: 'Send backward', icon: 'backward', shortcut: '[', disabled: bottom, action: () => restack(id, -1) },
    { label: 'Send to back', icon: 'back', shortcut: `${SHIFT}[`, disabled: bottom, action: () => restack(id, -Infinity) },
    '-',
    { label: 'Center horizontally', icon: 'centerX', action: () => placeWidget(id, 'center') },
    { label: 'Center vertically', icon: 'centerY', action: () => placeWidget(id, 'middle') },
    { label: widget.hidden ? 'Show' : 'Hide', icon: widget.hidden ? 'eye' : 'eyeOff', shortcut: 'H', action: () => toggleHidden(id) },
    '-',
    { label: 'Delete', icon: 'trash', shortcut: DELETE_KEY, danger: true, action: () => deleteWidget(id) },
  ]);
}

// For an empty spot on the board; `at` is that spot in LEDs
function boardMenu(x, y, at) {
  openMenu(x, y, [
    { label: 'Paste here', icon: 'paste', shortcut: `${MOD}V`, disabled: !state.clipboard, action: () => pasteWidget(at) },
    '-',
    { heading: 'Add here' },
    ...[...state.catalog.values()].map(component => ({
      label: component.label,
      icon: 'plus',
      action: () => {
        const { w, h } = component.thumbnail;
        addWidget(component.type, Math.round(at.x - w / 2), Math.round(at.y - h / 2));
      },
    })),
  ]);
}

function screenMenu(id, x, y) {
  const screen = findScreen(id);
  const index = screens().indexOf(screen);
  openMenu(x, y, [
    { label: 'Show on display now', icon: 'show', action: () => showNow(id) },
    { label: 'Take turns on the display', checked: screen.enabled, action: () => updateScreen(id, s => (s.enabled = !s.enabled)) },
    '-',
    { label: 'Duplicate', icon: 'duplicate', action: () => duplicateScreen(id) },
    { label: 'Move up', icon: 'up', disabled: index === 0, action: () => moveScreen(id, -1) },
    { label: 'Move down', icon: 'down', disabled: index === screens().length - 1, action: () => moveScreen(id, 1) },
    '-',
    { label: 'Delete screen', icon: 'trash', danger: true, disabled: screens().length < 2, action: () => deleteScreen(id) },
  ]);
}

function onBoardContextMenu(e) {
  e.preventDefault();
  if (drag.active) return;
  const box = e.target.closest('.box');
  if (box) {
    select(box.dataset.key);
    widgetMenu(box.dataset.key, e.clientX, e.clientY);
    return;
  }
  select(null);
  const rect = $('#overlay').getBoundingClientRect();
  boardMenu(e.clientX, e.clientY, { x: (e.clientX - rect.left) / state.pitch, y: (e.clientY - rect.top) / state.pitch });
}

// ---------- Start ----------

function setUpChrome() {
  $('#add-screen').append(icon('plus'));
  $('#undo').append(icon('undo'));
  $('#redo').append(icon('redo'));
  $('#show-now').append(icon('show'), 'Show on display');
  $('#power').append(icon('power'));

  $('#add-screen').addEventListener('click', openNewScreen);
  setUpPicker();
  $('#undo').addEventListener('click', undo);
  $('#redo').addEventListener('click', redo);
  $('#show-now').addEventListener('click', () => showNow(currentScreen().id));
  $('#toggle-outlines').addEventListener('click', () => {
    state.outlines = !state.outlines;
    try {
      localStorage.setItem('outlines', state.outlines ? '1' : '0');
    } catch {
      // private browsing: just don't remember it
    }
    render({ inspector: false });
  });
  $('#live').addEventListener('click', () => {
    const id = state.live && state.live.screen && state.live.screen.id;
    if (id && findScreen(id)) selectScreen(id);
  });

  $('#brightness').addEventListener('input', e => {
    brightnessHeld = true;
    setBrightness(Number(e.target.value));
  });
  $('#power').addEventListener('click', () => {
    brightnessHeld = true;
    setBrightness(Number($('#brightness').value) === 0 ? lastBrightness || 100 : 0);
  });

  const overlay = $('#overlay');
  overlay.addEventListener('pointerdown', onBoardPointerDown);
  overlay.addEventListener('pointermove', onBoardPointerMove);
  overlay.addEventListener('pointerup', onBoardPointerUp);
  overlay.addEventListener('pointercancel', onBoardPointerUp);
  overlay.addEventListener('contextmenu', onBoardContextMenu);
  $('#board-wrap').addEventListener('pointerdown', e => {
    if (e.target === e.currentTarget) select(null);
  });
  document.addEventListener('keydown', onKeyDown);

  new ResizeObserver(() => {
    const before = state.pitch;
    computePitch();
    if (state.pitch !== before) renderBoard();
  }).observe($('#board-wrap'));

  // Send anything unsaved if the page is closed within the save delay
  window.addEventListener('pagehide', () => {
    if (saving.dirty) {
      fetch('/api/config', {
        method: 'PUT',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state.config),
      });
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      pollLive();
      refreshSprites();
    }
  });
}

async function start() {
  const data = await api.state();
  state.W = data.display.width;
  state.H = data.display.height;
  state.fonts = data.fonts;
  state.images = data.images;
  state.prebuilt = data.prebuilt || [];
  state.config = data.config;
  state.screenId = data.config.screens[0].id;
  for (const component of data.components) {
    const t = component.thumbnail;
    component.sprite = { w: t.w, h: t.h, hash: t.hash, note: t.note, pixels: decodeBase64(t.rgba), error: null };
    state.catalog.set(component.type, component);
  }
  try {
    state.outlines = localStorage.getItem('outlines') !== '0';
  } catch {
    state.outlines = true;
  }

  setUpChrome();
  setUpFileDrop();
  setBrightnessUI(data.brightness);
  computePitch();
  renderPalette();
  render();
  renderSaveStatus();
  await refreshSprites();
  pollLive();
  // Clocks tick and the weather changes: redraw the sprites every second
  setInterval(() => {
    if (!document.hidden && !drag.active) refreshSprites();
  }, 1000);
}

start().catch(error => {
  const el = $('#fatal');
  el.hidden = false;
  el.textContent = `Couldn't load the dashboard: ${error.message}. Is the app running? Reload to try again.`;
  console.error(error);
});
