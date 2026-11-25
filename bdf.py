"""Bitmap (BDF) fonts, drawn onto Pillow images.

Components draw into Pillow images rather than straight onto the LED canvas, so the
same frame can go to the display and to the management page's preview. This draws text
the way the LED driver's own DrawText does (rpi-rgb-led-matrix lib/bdf-font.cc), so
text lands on the same pixels it did when components used rgbmatrix.graphics.
"""
import os
import threading

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, 'fonts')
DEFAULT_FONT = '6x10'
_REPLACEMENT = 0xFFFD  # the driver draws this for characters a font doesn't have


class Glyph:
    __slots__ = ('advance', 'width', 'height', 'x_offset', 'y_offset', 'rows', '_mask')

    def __init__(self, advance, width, height, x_offset, y_offset, rows):
        self.advance = advance
        self.width = width
        self.height = height
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.rows = rows  # one (bits, bit count) per row, left-aligned like the BDF hex
        self._mask = None

    def mask(self):
        """The glyph's pixels as an 'L' image (255 = lit), or None if it has none"""
        if self._mask is None and self.width > 0 and self.height > 0:
            data = bytearray(self.width * self.height)
            for y, (bits, count) in enumerate(self.rows):
                for x in range(min(self.width, count)):
                    if bits >> (count - 1 - x) & 1:
                        data[y * self.width + x] = 255
            self._mask = Image.frombytes('L', (self.width, self.height), bytes(data))
        return self._mask


class Font:
    def __init__(self, path):
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.glyphs = {}
        self.height = 0    # FONTBOUNDINGBOX height: one line of text
        self.baseline = 0  # rows from the top of a line to the driver's baseline
        self._ink_rows = {}
        self._parse(path)

    def _parse(self, path):
        codepoint = None
        advance = 0
        bbx = None
        rows = None
        with open(path, encoding='latin-1') as f:  # BDF is ASCII; latin-1 never fails to decode
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                keyword = parts[0]
                if rows is not None and keyword != 'ENDCHAR':
                    try:
                        rows.append((int(keyword, 16), 4 * len(keyword)))
                    except ValueError:
                        pass
                elif keyword == 'FONTBOUNDINGBOX' and len(parts) >= 5:
                    self.height = int(parts[2])
                    self.baseline = int(parts[4]) + self.height
                elif keyword == 'ENCODING' and len(parts) >= 2:
                    codepoint = int(parts[1])
                elif keyword == 'DWIDTH' and len(parts) >= 2:
                    advance = int(parts[1])  # like the driver, carries over to glyphs without one
                elif keyword == 'BBX' and len(parts) >= 5:
                    bbx = tuple(int(p) for p in parts[1:5])
                elif keyword == 'BITMAP':
                    rows = []
                elif keyword == 'ENDCHAR':
                    if bbx is not None and rows is not None and codepoint is not None and codepoint >= 0 \
                            and len(rows) >= bbx[1]:
                        width, height, x_offset, y_offset = bbx
                        self.glyphs[codepoint] = Glyph(advance, width, height, x_offset, y_offset, rows[:height])
                    bbx = None
                    rows = None

    def glyph(self, char):
        return self.glyphs.get(ord(char)) or self.glyphs.get(_REPLACEMENT)

    def text_width(self, text):
        return sum(g.advance for g in map(self.glyph, text) if g is not None)

    def draw(self, image, x, top, text, color, hidden=''):
        """Draws text with the top-left of its line at (x, top). Characters in `hidden` take up
        their space but aren't drawn. Returns the width of the text."""
        return self.draw_at_baseline(image, x, top + self.baseline, text, color, hidden)

    def draw_at_baseline(self, image, x, baseline, text, color, hidden=''):
        """Same as the driver's graphics.DrawText(canvas, font, x, baseline, color, text)"""
        start = x
        for char in text:
            g = self.glyph(char)
            if g is None:
                continue
            mask = g.mask()
            if mask is not None and char not in hidden:
                image.paste(color, (x + g.x_offset, baseline - g.height - g.y_offset), mask)
            x += g.advance
        return x - start

    def ink_rows(self, chars):
        """(first, last): the rows, counted from the top of the line, that any of `chars` lights.
        Components use it to size their boxes to the pixels they can actually light."""
        if chars not in self._ink_rows:
            self._ink_rows[chars] = self._find_ink_rows(chars)
        return self._ink_rows[chars]

    def _find_ink_rows(self, chars):
        first = last = None
        for char in set(chars):
            g = self.glyph(char)
            mask = g.mask() if g is not None else None
            box = mask.getbbox() if mask is not None else None
            if box is None:
                continue
            glyph_top = self.baseline - g.height - g.y_offset
            top, bottom = glyph_top + box[1], glyph_top + box[3] - 1
            first = top if first is None else min(first, top)
            last = bottom if last is None else max(last, bottom)
        if first is None:
            return 0, max(self.height, 1) - 1
        return first, last


_fonts = {}
_fonts_lock = threading.Lock()


def available_fonts():
    """Names of the fonts in fonts/, smallest first"""
    def sort_key(name):
        # "6x10" -> (10, 6, name); fonts without a size in their name go last
        try:
            w, h = name.split('x', 1)
            return (int(''.join(c for c in h if c.isdigit())), int(w), name)
        except ValueError:
            return (999, 999, name)
    names = [f[:-4] for f in os.listdir(FONT_DIR) if f.endswith('.bdf')]
    return sorted(names, key=sort_key)


def get_font(name):
    """The font called `name` (a file in fonts/ without .bdf), loaded once and cached"""
    with _fonts_lock:
        font = _fonts.get(name)
        if font is None:
            if name not in available_fonts():
                name = DEFAULT_FONT
                font = _fonts.get(name)
            if font is None:
                font = Font(os.path.join(FONT_DIR, name + '.bdf'))
                _fonts[name] = font
        return font
