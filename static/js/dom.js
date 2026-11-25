// Small DOM helpers, so the page needs no framework or build step.

// h('button', {class: 'btn', onclick: fn}, 'Label', childElement)
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'style') Object.assign(el.style, value);
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key in el && key !== 'list') el[key] = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  el.append(...children.flat().filter(c => c !== null && c !== undefined && c !== false));
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);

export const cls = (...names) => names.filter(Boolean).join(' ');

// Updates a container's children to match `items` in order, keeping the elements of items
// that were already there (so a click in progress, focus, or a canvas survives).
export function syncList(container, items, keyOf, create, update) {
  const existing = new Map();
  for (const el of container.children) existing.set(el.dataset.key, el);
  items.forEach((item, i) => {
    const key = keyOf(item);
    let el = existing.get(key);
    if (el) existing.delete(key);
    else {
      el = create(key, item);
      el.dataset.key = key;
    }
    update(el, item, i);
    if (container.children[i] !== el) container.insertBefore(el, container.children[i] || null);
  });
  for (const el of existing.values()) el.remove();
}

const svg = inner =>
  `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" ` +
  `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;

const ICONS = {
  plus: svg('<path d="M12 5v14M5 12h14"/>'),
  x: svg('<path d="M18 6 6 18M6 6l12 12"/>'),
  trash: svg('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>'),
  copy: svg('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'),
  eye: svg('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  eyeOff: svg('<path d="m3 3 18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.9 8.3 2 12 2 12s3.5 7 10 7c1.9 0 3.6-.6 5-1.4M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'),
  up: svg('<path d="M12 19V5M5 12l7-7 7 7"/>'),
  down: svg('<path d="M12 5v14M19 12l-7 7-7-7"/>'),
  undo: svg('<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>'),
  redo: svg('<path d="m15 14 5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>'),
  show: svg('<rect x="2" y="4" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="m10 8.5 4.5 2.5-4.5 2.5z" fill="currentColor"/>'),
  power: svg('<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>'),
  forward: svg('<path d="M7 11l5-5 5 5"/><path d="M7 17l5-5 5 5"/>'),
  backward: svg('<path d="m7 7 5 5 5-5"/><path d="m7 13 5 5 5-5"/>'),
  front: svg('<path d="M5 3h14"/><path d="m18 13-6-6-6 6"/><path d="M12 7v14"/>'),
  back: svg('<path d="M19 21H5"/><path d="m6 11 6 6 6-6"/><path d="M12 17V3"/>'),
  cut: svg('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>'),
  paste: svg('<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'),
  duplicate: svg('<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/><path d="M14.5 11.5v6M11.5 14.5h6"/>'),
  centerX: svg('<path d="M12 2v20"/><rect x="5" y="8" width="14" height="8" rx="1.5"/>'),
  centerY: svg('<path d="M2 12h20"/><rect x="8" y="5" width="8" height="14" rx="1.5"/>'),
  toLeft: svg('<path d="M4 3v18"/><rect x="8" y="8" width="12" height="8" rx="1.5"/>'),
  toRight: svg('<path d="M20 3v18"/><rect x="4" y="8" width="12" height="8" rx="1.5"/>'),
  toTop: svg('<path d="M3 4h18"/><rect x="8" y="8" width="8" height="12" rx="1.5"/>'),
  toBottom: svg('<path d="M3 20h18"/><rect x="8" y="4" width="8" height="12" rx="1.5"/>'),
  check: svg('<path d="M20 6 9 17l-5-5"/>'),
  upload: svg('<path d="M12 15V3"/><path d="m7 8 5-5 5 5"/><path d="M5 15v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"/>'),
  blank: svg(''),
};

export function icon(name) {
  const span = document.createElement('span');
  span.className = 'icon';
  span.innerHTML = ICONS[name];
  return span;
}
