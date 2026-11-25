"""What's on the display: a list of screens, each with components placed on it.

It's kept in one JSON file (data/display.json, or $LED_LAYOUT_FILE), written by the
management page. Until the first save the display shows default_config(): the
Skógafoss prebuilt screen, plus the layout the dashboard had before the management page
existed (clock, date and weather), out of the rotation.

    {
      "version": 1,
      "screens": [
        {"id": "main", "name": "Main", "duration": 15, "enabled": true,
         "widgets": [
           {"id": "clock", "type": "clock", "x": 8, "y": 1, "hidden": false,
            "options": {"color": "#ffffff", "font": "8x13B", ...}}
         ]}
      ]
    }

Enabled screens take turns on the display, each for its duration in seconds.
Widgets are drawn in list order, so later ones are on top.
"""
import json
import os
import re
import secrets
import threading

import bdf
from components import COMPONENTS

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(ROOT, 'data', 'display.json')
VERSION = 1
MAX_SCREENS = 50
MAX_WIDGETS = 100
_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')


def default_config():
    from prebuilt import PREBUILT  # imported here because prebuilt.py imports this module
    skogafoss = next(p for p in PREBUILT if p['id'] == 'skogafoss')
    return {
        'version': VERSION,
        'screens': [
            {
                'id': 'skogafoss',
                'name': skogafoss['name'],
                'duration': 15,
                'enabled': True,
                'widgets': [{**w, 'id': f"skogafoss-{i}"} for i, w in enumerate(skogafoss['widgets'])],
            },
            {
                'id': 'main',
                'name': 'Classic',
                'duration': 15,
                'enabled': False,
                'widgets': [
                    {'id': 'clock', 'type': 'clock', 'x': 8, 'y': 1},
                    {'id': 'date', 'type': 'date', 'x': 1, 'y': 24},
                    {'id': 'weather', 'type': 'weather', 'x': 32, 'y': 0},
                ],
            },
        ],
    }


def new_id(prefix):
    return prefix + secrets.token_hex(4)


def _int(value, default, low, high):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(high, number))


def normalize(raw, strict=True):
    """A clean copy of a layout: every field present and valid. Raises ValueError for
    layouts that can't be fixed up. With strict=False (reading the file), widgets of
    unknown types are dropped instead, e.g. after a component is removed from the code."""
    if not isinstance(raw, dict) or not isinstance(raw.get('screens'), list):
        raise ValueError("layout needs a list of screens")
    if not raw['screens']:
        raise ValueError("layout needs at least one screen")
    if len(raw['screens']) > MAX_SCREENS:
        raise ValueError(f"at most {MAX_SCREENS} screens")

    seen = set()

    def unique_id(value, prefix):
        value = value if isinstance(value, str) and _ID.fullmatch(value) and value not in seen else new_id(prefix)
        seen.add(value)
        return value

    screens = []
    for i, screen in enumerate(raw['screens']):
        if not isinstance(screen, dict):
            raise ValueError("each screen must be an object")
        name = str(screen.get('name') or '').strip()[:40] or f"Screen {i + 1}"
        widgets = screen.get('widgets', [])
        if not isinstance(widgets, list):
            raise ValueError(f"screen {name}: widgets must be a list")
        if len(widgets) > MAX_WIDGETS:
            raise ValueError(f"screen {name}: at most {MAX_WIDGETS} components")
        screens.append({
            'id': unique_id(screen.get('id'), 's'),
            'name': name,
            'duration': _int(screen.get('duration'), 15, 1, 24 * 3600),
            'enabled': screen.get('enabled', True) is not False,
            'widgets': [w for w in (normalize_widget(w, strict, unique_id) for w in widgets) if w is not None],
        })
    return {'version': VERSION, 'screens': screens}


def upgrade_widget(raw):
    """A widget saved by an older version, in today's form. "Weather details" and
    "forecast" used to be components of their own; they're now things the weather
    component can show, placed so they light the same LEDs as before."""
    if not isinstance(raw, dict) or raw.get('type') not in ('weather_details', 'forecast'):
        return raw
    old = raw.get('options') if isinstance(raw.get('options'), dict) else {}
    options = {k: v for k, v in old.items() if k in ('color', 'hours', 'outline')}
    widget = {**raw, 'type': 'weather', 'options': options}
    if raw['type'] == 'forecast':
        options.update({k: v for k, v in old.items() if k in ('count', 'start', 'temps')})
        options['show'] = 'forecast_hours' if old.get('mode') == 'hours' else 'forecast_days'
        options['forecast_font'] = old.get('font', '4x6')
        return widget
    field = old.get('field', 'feels_like')
    font = old.get('font', '5x7')
    options.update(show='temperature' if field == 'temp' else field, label=old.get('label', True) is not False,
                   align='right', font=font)
    if options['show'] in ('temperature', 'feels_like'):
        # These leave room for a minus sign now; keep the value's right edge where it was
        try:
            x = int(raw.get('x', 0))
        except (TypeError, ValueError):
            x = 0
        widget['x'] = x - bdf.get_font(font).text_width('-')
    return widget


def normalize_widget(raw, strict=True, unique_id=None):
    if not isinstance(raw, dict):
        raise ValueError("each component must be an object")
    raw = upgrade_widget(raw)
    component = COMPONENTS.get(raw.get('type'))
    if component is None:
        if strict:
            raise ValueError(f"unknown component type {raw.get('type')!r}")
        print(f"Layout: dropping a component of unknown type {raw.get('type')!r}", flush=True)
        return None
    widget_id = raw.get('id')
    if unique_id is not None:
        widget_id = unique_id(widget_id, 'w')
    elif not (isinstance(widget_id, str) and _ID.fullmatch(widget_id)):
        widget_id = new_id('w')
    return {
        'id': widget_id,
        'type': component.type,
        'x': _int(raw.get('x'), 0, -512, 512),
        'y': _int(raw.get('y'), 0, -512, 512),
        'hidden': raw.get('hidden') is True,
        'options': component.clean_options(raw.get('options')),
    }


class LayoutStore:
    """The layout file. `config` is always a complete, valid layout; saving swaps in a new
    one, so the display thread can read it without locking."""

    def __init__(self, path=None):
        self.path = path or os.environ.get('LED_LAYOUT_FILE') or DEFAULT_PATH
        self._lock = threading.Lock()
        self.config = self._load()

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                raw = json.load(f)
        except FileNotFoundError:
            return normalize(default_config())
        except (OSError, ValueError) as e:
            print(f"Layout: couldn't read {self.path} ({e}); showing the default layout", flush=True)
            return normalize(default_config())
        try:
            return normalize(raw, strict=False)
        except ValueError as e:
            print(f"Layout: {self.path} isn't a valid layout ({e}); showing the default layout", flush=True)
            return normalize(default_config())

    def save(self, raw):
        """Validates and saves a layout from the management page; returns the cleaned copy"""
        config = normalize(raw)
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Write a new file and swap it in, so a crash mid-write can't leave half a layout
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self.config = config
        return config
