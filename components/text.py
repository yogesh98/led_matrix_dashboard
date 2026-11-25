import bdf
from components.base import ASCII, Component, Option, color_option, font_option, line_rows, outline_option, rgba


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
        outline_option(),
    )
    resize = {'w': 'width'}
    resize_when = {'scroll': True}

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        # Size the box for any text in this font, so it doesn't jump as you type
        extra = ''.join(sorted(set(opts['text']) - set(ASCII)))
        top, height = line_rows(font, ASCII + extra)
        return font, top, height, font.text_width(opts['text'])

    def size(self, opts, ctx):
        font, top, height, text_width = self._layout(opts)
        return (opts['width'] if opts['scroll'] else max(1, text_width)), height

    def draw(self, image, opts, ctx):
        font, top, height, text_width = self._layout(opts)
        x = 0
        if opts['scroll'] and not ctx.preview:
            # Enter from the right edge, leave past the left one, repeat
            cycle = opts['width'] + text_width
            x = opts['width'] - int(ctx.now.timestamp() * opts['speed']) % cycle
        font.draw(image, x, -top, opts['text'], rgba(opts['color']))
