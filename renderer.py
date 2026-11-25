"""Turns a screen of placed components into a frame (a Pillow RGB image), and decides
which screen is on the display. Used for the display itself and for the management
page's previews, so the preview shows exactly what the LEDs will."""
import threading
import time

from PIL import Image

from components import COMPONENTS

MAX_SIZE = 512


class ErrorLog:
    """Prints each distinct error at most once a minute, so a broken component on a 20 fps
    display doesn't fill the log"""

    def __init__(self, every=60):
        self.every = every
        self._last = {}

    def report(self, message):
        now = time.monotonic()
        if now - self._last.get(message, -self.every) >= self.every:
            self._last[message] = now
            print(message, flush=True)


errors = ErrorLog()


def render_widget(widget, ctx):
    """(image, note): the widget drawn into a transparent RGBA image the size of its box"""
    component = COMPONENTS[widget['type']]
    width, height = component.size(widget['options'], ctx)
    image = Image.new('RGBA', (max(1, min(MAX_SIZE, width)), max(1, min(MAX_SIZE, height))), (0, 0, 0, 0))
    note = component.draw(image, widget['options'], ctx)
    return image, note


def render_screen(screen, ctx):
    frame = Image.new('RGB', ctx.display_size)
    if screen is None:
        return frame
    for widget in screen['widgets']:
        if widget['hidden']:
            continue
        try:
            image, _ = render_widget(widget, ctx)
        except Exception as e:
            # One broken component shouldn't take the rest of the display down with it
            errors.report(f"Couldn't draw {widget['type']} {widget['id']}: {type(e).__name__}: {e}")
            continue
        frame.paste(image, (widget['x'], widget['y']), image)
    return frame


class Rotation:
    """Which screen is showing. Enabled screens take turns, each for its duration;
    show() puts a screen on now (even a disabled one) for its duration."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._current = None
        self._started = 0.0
        self._requested = False

    def show(self, screen_id):
        with self._lock:
            self._current = screen_id
            self._started = self._clock()
            self._requested = True

    def current(self, screens):
        """(screen, seconds left on it); (None, 0) if no screen is enabled"""
        now = self._clock()
        with self._lock:
            ids = [s['id'] for s in screens]
            if self._current in ids:
                screen = screens[ids.index(self._current)]
                if screen['enabled'] or self._requested:
                    left = screen['duration'] - (now - self._started)
                    if left > 0:
                        return screen, left
                # Its turn is over: the next enabled screen after it (wrapping around)
                start = ids.index(self._current) + 1
                order = screens[start:] + screens[:start]
            else:
                order = screens
            for screen in order:
                if screen['enabled']:
                    self._current = screen['id']
                    self._started = now
                    self._requested = False
                    return screen, float(screen['duration'])
            self._current = None
            return None, 0.0
