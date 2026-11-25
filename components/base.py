"""What every component on the display shares.

A component is a kind of thing you can place on a screen (a clock, the weather, some
text). It doesn't keep any state: each placed copy has its own options, and the
component draws one of them into a transparent Pillow image the size of its box.
The renderer then places that image on the screen at the copy's x and y.

To add a component: subclass Component in a module in this folder, describe its
settings in `options`, and add it to COMPONENTS in components/__init__.py. The
management page builds its settings form from `options`, so it needs no changes.
"""
import functools
import re
from datetime import date, datetime

import bdf
from images import IMAGE_ID

ASCII = ''.join(chr(c) for c in range(32, 127))


class Option:
    """One setting of a component, shown as a field on the management page.

    kind is one of: text, number, bool, color, font, select, date (YYYY-MM-DD), time (HH:MM),
    image (an id from images.py), or align and valign (see align_options). `show_if` hides the
    field unless other options have the given values: {'scroll': True}, a list of allowed values,
    or a prefix ending in *.
    """

    def __init__(self, key, label, kind, default, choices=None, min=None, max=None,
                 maxlength=200, unit=None, show_if=None):
        self.key = key
        self.label = label
        self.kind = kind
        self.default = default
        self.choices = choices or []  # [(value, label), ...] for select
        self.min = min
        self.max = max
        self.maxlength = maxlength
        self.unit = unit
        self.show_if = show_if

    def clean(self, value):
        """value made valid for this option, or the default if it can't be"""
        if value is None:
            return self.default
        kind = self.kind
        if kind == 'bool':
            return value if isinstance(value, bool) else self.default
        if kind == 'number':
            try:
                number = int(round(float(value)))
            except (TypeError, ValueError, OverflowError):
                return self.default
            if self.min is not None:
                number = max(self.min, number)
            if self.max is not None:
                number = min(self.max, number)
            return number
        if kind == 'text':
            return str(value)[:self.maxlength]
        if kind == 'color':
            return normalize_color(value) or self.default
        if kind == 'font':
            return value if value in bdf.available_fonts() else self.default
        if kind in ('select', 'align', 'valign'):
            return value if value in [c[0] for c in self.choices] else self.default
        if kind == 'date':
            try:
                return date.fromisoformat(str(value)).isoformat()
            except ValueError:
                return self.default
        if kind == 'time':
            return value if isinstance(value, str) and re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', value) else self.default
        if kind == 'image':
            return value if isinstance(value, str) and IMAGE_ID.fullmatch(value) else self.default
        raise ValueError(f"unknown option kind {kind}")

    def to_json(self):
        data = {'key': self.key, 'label': self.label, 'type': self.kind, 'default': self.default}
        if self.choices:
            data['choices'] = [{'value': v, 'label': l} for v, l in self.choices]
        for name in ('min', 'max', 'unit', 'show_if'):
            if getattr(self, name) is not None:
                data[name] = getattr(self, name)
        if self.kind == 'text':
            data['maxlength'] = self.maxlength
        return data


def color_option(default='#ffffff'):
    return Option('color', 'Color', 'color', default)


def font_option(default):
    return Option('font', 'Font', 'font', default)


def outline_option():
    """A dark edge around the text (and any icons), so it reads over a busy or bright
    background like a scene. Every component that draws text has one. The renderer draws
    it (see renderer.outlined), making the box a pixel bigger on each side."""
    return Option('outline', 'Dark outline', 'bool', False)


def hours_option():
    return Option('hours', 'Hours', 'select', '12', choices=[('12', '12-hour'), ('24', '24-hour')])


def align_options(align='left', valign='top', align_if=None, valign_if=None):
    """Where what's showing sits in its box: left, center or right, and top, middle or bottom.
    Boxes are sized for the biggest thing a component can show, and things line up by the
    pixels they light, so right-aligned text ends exactly at the box's right edge. In the editor
    it's also the side that stays put when the box changes size (a bigger font, a longer label).
    The management page shows the two together as one grid. Draw with draw_lines or draw_labeled."""
    return (
        Option('align', 'Align', 'align', align, choices=[('left', 'Left'), ('center', 'Center'), ('right', 'Right')],
               show_if=align_if),
        Option('valign', 'Align vertically', 'valign', valign,
               choices=[('top', 'Top'), ('middle', 'Middle'), ('bottom', 'Bottom')], show_if=valign_if),
    )


def normalize_color(value):
    """'#abc' or '#AABBCC' -> '#aabbcc'; None if it isn't a color"""
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if re.fullmatch(r'#[0-9a-f]{3}', value):
        value = '#' + ''.join(c * 2 for c in value[1:])
    return value if re.fullmatch(r'#[0-9a-f]{6}', value) else None


def rgba(color):
    """'#rrggbb' -> (r, g, b, 255), the fill Pillow wants for an RGBA image"""
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), 255)


class RenderContext:
    """What components can know while drawing: the time, the data sources (weather...),
    and whether this is the management page's editor preview rather than the display."""

    def __init__(self, now=None, sources=None, preview=False, display_size=(64, 32)):
        self.now = now or datetime.now()
        self.sources = sources or {}
        self.preview = preview
        self.display_size = display_size

    def data(self, name):
        source = self.sources.get(name)
        return source.current() if source is not None else None


class Component:
    type = None          # stored in the layout file; don't change it once used
    label = None         # shown on the management page
    description = ''
    options = ()
    # Which options the editor's resize handle changes, e.g. {'w': 'width', 'h': 'height'},
    # and when it's available, e.g. {'scroll': True}
    resize = None
    resize_when = None
    # Backgrounds go under everything else when added, and fill the display
    background = False

    def clean_options(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        return {opt.key: opt.clean(raw.get(opt.key)) for opt in self.options}

    def defaults(self):
        return {opt.key: opt.default for opt in self.options}

    def size(self, opts, ctx):
        """(width, height) of this copy's box, in pixels"""
        raise NotImplementedError

    def draw(self, image, opts, ctx):
        """Draws into `image`, a transparent RGBA image the size of the box. May return a
        short note for the management page, e.g. that it's showing sample data."""
        raise NotImplementedError

    def catalog(self):
        return {
            'type': self.type,
            'label': self.label,
            'description': self.description,
            'options': [opt.to_json() for opt in self.options],
            'defaults': self.defaults(),
            'resize': self.resize,
            'resize_when': self.resize_when,
            'background': self.background,
        }


def line_rows(font, charset):
    """(top, height): the rows of a line of text that any character in charset lights.
    Boxes are trimmed to those rows (fonts leave blank rows above and below most
    characters, and the display only has 32), so draw the line at y = -top."""
    first, last = font.ink_rows(charset)
    return first, last - first + 1


def widest_digits(font, sample):
    """sample with each 0 swapped for the font's widest digit, to size a box for any number"""
    return sample.replace('0', max('0123456789', key=font.text_width))


DIGITS = '0123456789'


def ink_width(font, text):
    """How many columns text spans from the first one it lights to the last"""
    box = font.ink_box(text)
    return box[2] - box[0] + 1 if box else 0


def _positions(sample):
    """'[12]0:' -> ['12', '0123456789', ':']: the characters that can be in each place"""
    positions = []
    i = 0
    while i < len(sample):
        if sample[i] == '[':
            end = sample.index(']', i)
            positions.append(sample[i + 1:end])
            i = end + 1
        else:
            positions.append(DIGITS if sample[i] == '0' else sample[i])
            i += 1
    return positions


def sample_chars(*samples):
    """Every character the samples (as for widest) can show, e.g. to size a box's rows"""
    return ''.join(''.join(_positions(sample)) for sample in samples)


@functools.lru_cache(maxsize=1024)
def widest(font, *samples):
    """The most columns any text the samples stand for can span, from the first one it lights to
    the last. In a sample, 0 stands for any digit and [123] for any one of those characters, so
    '1[012]:[012345]0' is 10:00 to 12:59. A box this wide fits anything a component can show,
    with nothing to spare when it shows the widest (in a font whose characters are all as wide)."""
    most = 0
    for sample in samples:
        pen = 0
        left = right = None
        for options in _positions(sample):
            for option in options:
                ink = font.glyph_ink(option)
                if ink is not None:
                    left = pen + ink[0] if left is None else min(left, pen + ink[0])
                    right = pen + ink[2] if right is None else max(right, pen + ink[2])
            pen += max(font.text_width(c) for c in options)
        if left is not None:
            most = max(most, right - left + 1)
    return most


def shift(size, first, last, side):
    """How far to move something that lights pixels first..last so it sits at `side` (left, top,
    center, middle, right or bottom) of a box `size` pixels across"""
    if side in ('left', 'top'):
        return -first
    if side in ('right', 'bottom'):
        return size - 1 - last
    return (size - (last - first + 1)) // 2 - first


def draw_lines(image, font, lines, color, align, valign, hidden=''):
    """Draws lines of text lined up by the pixels they light: each line on its own to the `align`
    side of the image, and all of them together to the `valign` side, keeping the space between
    them. `lines` is [(text, top)], top being the row the line starts on before lining up. A line
    can also be [(x, text), ...] runs, which move together. Characters in `hidden` keep their
    place but aren't drawn (a blinking colon)."""
    placed = []
    for runs, top in lines:
        if isinstance(runs, str):
            runs = [(0, runs)]
        boxes = [(x + b[0], top + b[1], x + b[2], top + b[3])
                 for x, b in ((x, font.ink_box(text)) for x, text in runs) if b]
        if boxes:
            placed.append((runs, top, boxes))
    if not placed:
        return
    every = [b for _, _, boxes in placed for b in boxes]
    dy = shift(image.height, min(b[1] for b in every), max(b[3] for b in every), valign)
    for runs, top, boxes in placed:
        dx = shift(image.width, min(b[0] for b in boxes), max(b[2] for b in boxes), align)
        for x, text in runs:
            font.draw(image, x + dx, top + dy, text, color, hidden)


def labeled_width(font, label, value_width):
    """The width of a box for draw_labeled, where the widest value spans value_width columns"""
    box = font.ink_box(label)
    if box is None:
        return value_width
    return font.text_width(label) - box[0] + value_width


def draw_labeled(image, font, label, value, color, align, valign):
    """Draws a label and a value on one line: the label at the left, so it doesn't move about,
    and the value lined up in the space after it. Both go to the `valign` side together."""
    label_box = font.ink_box(label)
    value_box = font.ink_box(value)
    boxes = [b for b in (label_box, value_box) if b]
    if not boxes:
        return
    dy = shift(image.height, min(b[1] for b in boxes), max(b[3] for b in boxes), valign)
    start = 0
    if label_box:
        font.draw(image, -label_box[0], dy, label, color)
        start = font.text_width(label) - label_box[0]
    if value_box:
        dx = start + shift(image.width - start, value_box[0], value_box[2], align)
        font.draw(image, dx, dy, value, color)
