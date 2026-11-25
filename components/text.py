import bdf
from components.base import (ASCII, Component, Option, align_options, color_option, draw_lines, font_option, ink_width,
                             line_rows, outline_option, rgba, shift)


class Text(Component):
    type = 'text'
    label = 'Text'
    description = 'Your own text, still or scrolling'
    options = (
        Option('text', 'Text', 'text', 'Hello', maxlength=200),
        color_option(),
        font_option('6x10'),
        Option('scroll', 'Scroll', 'bool', False),
        Option('width', 'Width', 'number', 64, min=4, max=512, unit='px', show_if={'scroll': True}),
        Option('speed', 'Speed', 'number', 15, min=1, max=100, unit='px/s', show_if={'scroll': True}),
        # Still text's box fits it, so left, center or right is the side that stays put as you type
        *align_options(align_if={'scroll': False}),
        outline_option(),
    )
    resize = {'w': 'width'}
    resize_when = {'scroll': True}

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        # Size the box for any text in this font, so it doesn't jump as you type
        extra = ''.join(sorted(set(opts['text']) - set(ASCII)))
        top, height = line_rows(font, ASCII + extra)
        return font, top, height

    def size(self, opts, ctx):
        font, top, height = self._layout(opts)
        return (opts['width'] if opts['scroll'] else max(1, ink_width(font, opts['text']))), height

    def draw(self, image, opts, ctx):
        font, top, height = self._layout(opts)
        color = rgba(opts['color'])
        if not opts['scroll']:
            draw_lines(image, font, [(opts['text'], -top)], color, opts['align'], opts['valign'])
            return
        box = font.ink_box(opts['text'])
        if box is None:
            return
        x = 0
        if not ctx.preview:
            # Enter from the right edge, leave past the left one, repeat
            cycle = opts['width'] + font.text_width(opts['text'])
            x = opts['width'] - int(ctx.now.timestamp() * opts['speed']) % cycle
        font.draw(image, x, shift(image.height, box[1], box[3], opts['valign']), opts['text'], color)
