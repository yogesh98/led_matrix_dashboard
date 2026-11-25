import bdf
from components.base import Component, Option, color_option, font_option, hours_option, line_rows, rgba

DIGITS = '0123456789'


def hour_text(now, hours, pad):
    hour = now.hour
    if hours == '12':
        hour = hour % 12 or 12
    return f"{hour:02}" if pad else str(hour)


def digit_width(font):
    return max(font.text_width(d) for d in DIGITS)


class Clock(Component):
    type = 'clock'
    label = 'Clock'
    description = 'Hours above minutes'
    options = (
        color_option(),
        font_option('8x13B'),
        hours_option(),
        Option('spacing', 'Line spacing', 'number', 1, min=0, max=16, unit='px'),
    )

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        top, height = line_rows(font, DIGITS)
        return font, top, height

    def size(self, opts, ctx):
        font, top, height = self._layout(opts)
        return 2 * digit_width(font), 2 * height + opts['spacing']

    def draw(self, image, opts, ctx):
        font, top, height = self._layout(opts)
        color = rgba(opts['color'])
        font.draw(image, 0, -top, hour_text(ctx.now, opts['hours'], pad=True), color)
        font.draw(image, 0, height + opts['spacing'] - top, f"{ctx.now.minute:02}", color)


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
    )

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        top, height = line_rows(font, DIGITS + ':')
        digits, colons = (6, 2) if opts['seconds'] else (4, 1)
        width = digits * digit_width(font) + colons * font.text_width(':')
        return font, top, height, width

    def size(self, opts, ctx):
        font, top, height, width = self._layout(opts)
        return width, height

    def draw(self, image, opts, ctx):
        font, top, height, width = self._layout(opts)
        now = ctx.now
        # 12-hour times drop the leading zero ("9:41"), so right-align to keep the minutes still
        text = f"{hour_text(now, opts['hours'], pad=opts['hours'] == '24')}:{now.minute:02}"
        if opts['seconds']:
            text += f":{now.second:02}"
        hidden = ':' if opts['blink'] and now.second % 2 else ''
        font.draw(image, width - font.text_width(text), -top, text, rgba(opts['color']), hidden)
