from datetime import date, datetime, time

import bdf
from components.base import (ASCII, Component, Option, align_options, color_option, draw_labeled, draw_lines,
                             font_option, ink_width, labeled_width, line_rows, outline_option, rgba, widest)

NEXT_NEW_YEAR = date(date.today().year + 1, 1, 1).isoformat()

# The widest each format gets, so the box doesn't change size as the days go by
SAMPLES = {'days': ['000d'], 'days_words': ['000 days'], 'auto': ['00d 00h', '00h 00m', '00m 00s']}


def time_left(opts, now):
    """The countdown text, or None once the date (and time) has arrived"""
    target_day = date.fromisoformat(opts['date'])
    if opts['format'] in ('days', 'days_words'):
        days = (target_day - now.date()).days  # calendar days, so it's "1d" all of the day before
        if days <= 0:
            return None
        if opts['format'] == 'days':
            return f"{days}d"
        return f"{days} day" if days == 1 else f"{days} days"
    left = int((datetime.combine(target_day, time.fromisoformat(opts['time'])) - now).total_seconds())
    if left <= 0:
        return None
    days, left = divmod(left, 86400)
    hours, left = divmod(left, 3600)
    minutes, seconds = divmod(left, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"


class Countdown(Component):
    type = 'countdown'
    label = 'Countdown'
    description = 'Days (or hours) to go until a date'
    options = (
        Option('label', 'Label', 'text', 'New Year', maxlength=40),
        Option('date', 'Date', 'date', NEXT_NEW_YEAR),
        Option('format', 'Show', 'select', 'days', choices=[
            ('days', '12d'),
            ('days_words', '12 days'),
            ('auto', '12d 4h, then 4h 20m, then 20m 15s'),
        ]),
        Option('time', 'Time', 'time', '00:00', show_if={'format': 'auto'}),
        Option('done', 'When it arrives', 'text', 'Today!', maxlength=40),
        # Label above by default: "New Year 000d" on one line is wider than the display
        Option('layout', 'Layout', 'select', 'stacked', choices=[('stacked', 'Label above'), ('inline', 'One line')]),
        color_option(),
        font_option('6x10'),
        *align_options(),
        outline_option(),
    )

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        extra = ''.join(sorted(set(opts['label'] + opts['done']) - set(ASCII)))
        top, height = line_rows(font, ASCII + extra)
        value_width = max(widest(font, *SAMPLES[opts['format']]), ink_width(font, opts['done']))
        label = opts['label']
        if not label:
            width, lines = value_width, 1
        elif opts['layout'] == 'stacked':
            width, lines = max(ink_width(font, label), value_width), 2
        else:
            width, lines = labeled_width(font, label + ' ', value_width), 1
        return font, top, height, max(1, width), lines

    def size(self, opts, ctx):
        font, top, height, width, lines = self._layout(opts)
        return width, lines * height + (lines - 1)

    def draw(self, image, opts, ctx):
        font, top, height, width, lines = self._layout(opts)
        value = time_left(opts, ctx.now) or opts['done']
        color = rgba(opts['color'])
        label = opts['label']
        align, valign = opts['align'], opts['valign']
        if not label:
            draw_lines(image, font, [(value, -top)], color, align, valign)
        elif lines == 2:
            draw_lines(image, font, [(label, -top), (value, height + 1 - top)], color, align, valign)
        else:
            draw_labeled(image, font, label + ' ', value, color, align, valign)
