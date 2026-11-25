// Right-click menus.
//
// openMenu(x, y, items) shows a menu at (x, y). Each item is one of:
//   {label, icon, shortcut, action, disabled, danger}   a command
//   {label, checked, action}                            a command with a checkmark
//   {heading: 'Text'}                                   a small heading
//   '-'                                                 a divider
// It closes on a click elsewhere, Escape, scrolling or resizing, or after a command runs.
// (Not on window blur: the desktop app's browser pane can fire one just as the menu opens.)

import { cls, h, icon } from './dom.js';

const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
export const isMac = /mac|iphone|ipad/i.test(platform);
export const MOD = isMac ? '⌘' : 'Ctrl+';
export const SHIFT = isMac ? '⇧' : 'Shift+';
export const DELETE_KEY = isMac ? '⌫' : 'Del';

let open = null;

export const menuIsOpen = () => open !== null;

export function closeMenu() {
  if (!open) return;
  open.cleanup();
  open.el.remove();
  open = null;
}

function itemElement(item) {
  if (item === '-') return h('div', { class: 'menu-sep', role: 'separator' });
  if (item.heading) return h('div', { class: 'menu-heading' }, item.heading);
  const checkable = item.checked !== undefined;
  return h('button', {
    type: 'button',
    role: checkable ? 'menuitemcheckbox' : 'menuitem',
    'aria-checked': checkable ? String(item.checked) : null,
    class: cls('menu-item', item.danger && 'danger'),
    disabled: item.disabled,
    onclick: () => {
      closeMenu();
      item.action();
    },
  },
    icon(checkable ? (item.checked ? 'check' : 'blank') : item.icon || 'blank'),
    h('span', { class: 'menu-label' }, item.label),
    item.shortcut ? h('kbd', { class: 'menu-key' }, item.shortcut) : null);
}

export function openMenu(x, y, items) {
  closeMenu();
  const el = h('div', { class: 'menu', role: 'menu', tabIndex: -1 }, ...items.map(itemElement));
  document.body.append(el);

  // Keep it on screen: flip left of / above the pointer if it would run off the edge
  const { width, height } = el.getBoundingClientRect();
  const left = x + width > window.innerWidth - 8 ? Math.max(8, x - width) : x;
  const top = y + height > window.innerHeight - 8 ? Math.max(8, y - height) : y;
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  el.focus({ preventScroll: true });

  el.addEventListener('keydown', e => {
    // While the menu is open, keys belong to it (so ⌫ can't delete something behind it)
    e.stopPropagation();
    const buttons = [...el.querySelectorAll('.menu-item:not(:disabled)')];
    const index = buttons.indexOf(document.activeElement);
    const focus = i => buttons.length && buttons[(i + buttons.length) % buttons.length].focus();
    if (e.key === 'ArrowDown') focus(index + 1);
    else if (e.key === 'ArrowUp') focus(index < 0 ? -1 : index - 1);
    else if (e.key === 'Home') focus(0);
    else if (e.key === 'End') focus(-1);
    else if (e.key === 'Escape' || e.key === 'Tab') closeMenu();
    else return; // Enter and Space press the focused item as usual
    e.preventDefault();
  });

  const onPointerDown = e => {
    if (!el.contains(e.target)) closeMenu();
  };
  const onScroll = e => {
    if (!el.contains(e.target)) closeMenu();
  };
  document.addEventListener('pointerdown', onPointerDown, true);
  document.addEventListener('scroll', onScroll, true);
  window.addEventListener('resize', closeMenu);
  open = {
    el,
    cleanup() {
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', closeMenu);
    },
  };
}
