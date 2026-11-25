import bdf
from components.base import (DIGITS, Component, Option, align_options, color_option, draw_lines, font_option,
                             hours_option, line_rows, outline_option, rgba, widest)


def hour_text(now, hours, pad):
    hour = now.hour
    if hours == '12':
        hour = hour % 12 or 12
    return f"{hour:02}" if pad else str(hour)


class Clock(Component):
    type = 'clock'
    label = 'Clock'
    description = 'Hours above minutes'
    options = (
        color_option(),
        font_option('8x13B'),
        hours_option(),
        Option('spacing', 'Line spacing', 'number', 1, min=0, max=16, unit='px'),
        # Right by default: digits end on the same column (a 1 is narrower on its left), so they
        # stay stacked in columns as the time changes
        *align_options(align='right'),
        outline_option(),
    )

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        top, height = line_rows(font, DIGITS)
        return font, top, height

    def size(self, opts, ctx):
        font, top, height = self._layout(opts)
        hours = '[01]0' if opts['hours'] == '12' else '[012]0'
        return widest(font, hours, '[012345]0'), 2 * height + opts['spacing']

    def draw(self, image, opts, ctx):
        font, top, height = self._layout(opts)
        lines = [(hour_text(ctx.now, opts['hours'], pad=True), -top),
                 (f"{ctx.now.minute:02}", height + opts['spacing'] - top)]
        draw_lines(image, font, lines, rgba(opts['color']), opts['align'], opts['valign'])


class Time(Component):
    type = 'time'
    label = 'Time'
    description = 'The time on one line'
    options = (
        color_option(),
        font_option('6x10'),
        hours_option(),
        Option('seconds', 'Show seconds', 'bool', False),
        Option('blink', 'Blink the colon', 'bool', False),
        *align_options(),
        outline_option(),
    )

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        top, height = line_rows(font, DIGITS + ':')
        # 12-hour times drop the leading zero ("9:41"), and only 10 to 12 have two digits
        samples = ('0', '1[012]') if opts['hours'] == '12' else ('[012]0',)
        samples = tuple(s + ':[012345]0' * (2 if opts['seconds'] else 1) for s in samples)
        return font, top, height, widest(font, *samples)

    def size(self, opts, ctx):
        font, top, height, width = self._layout(opts)
        return width, height

    def draw(self, image, opts, ctx):
        font, top, height, width = self._layout(opts)
        now = ctx.now
        text = f"{hour_text(now, opts['hours'], pad=opts['hours'] == '24')}:{now.minute:02}"
        if opts['seconds']:
            text += f":{now.second:02}"
        hidden = ':' if opts['blink'] and now.second % 2 else ''
        draw_lines(image, font, [(text, -top)], rgba(opts['color']), opts['align'], opts['valign'], hidden)
