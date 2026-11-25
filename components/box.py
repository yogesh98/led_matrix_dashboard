from PIL import ImageDraw

from components.base import Component, Option, color_option, rgba


class Box(Component):
    type = 'box'
    label = 'Box'
    description = 'A rectangle or line, for dividers and frames'
    options = (
        color_option('#555555'),
        Option('width', 'Width', 'number', 16, min=1, max=512, unit='px'),
        Option('height', 'Height', 'number', 1, min=1, max=512, unit='px'),
        Option('fill', 'Filled', 'bool', True),
    )
    resize = {'w': 'width', 'h': 'height'}

    def size(self, opts, ctx):
        return opts['width'], opts['height']

    def draw(self, image, opts, ctx):
        color = rgba(opts['color'])
        ImageDraw.Draw(image).rectangle(
            [0, 0, opts['width'] - 1, opts['height'] - 1],
            fill=color if opts['fill'] else None,
            outline=color,
        )
