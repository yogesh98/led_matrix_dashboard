import calendar

import bdf
from components.base import Component, Option, color_option, font_option, line_rows, outline_option, rgba

# Each format is a list of parts, drawn left to right with `gap` pixels between them
FORMATS = {
    'day_date': ('day', 'date'),
    'month_date': ('month', 'date'),
    'day_month_date': ('day', 'month', 'date'),
    'date_month': ('date', 'month'),
    'numeric': ('numeric',),
}


def part_values(part):
    """Every text a part can show, to size its slot so the date doesn't shift around"""
    if part == 'day':
        return list(calendar.day_abbr)
    if part == 'month':
        return list(calendar.month_abbr)[1:]
    if part == 'date':
        return [f"{d:02}" for d in range(1, 32)]
    return [f"{m}/{d}" for m in range(1, 13) for d in range(1, 32)]


def part_text(part, now):
    if part == 'day':
        return now.strftime('%a')
    if part == 'month':
        return now.strftime('%b')
    if part == 'date':
        return now.strftime('%d')
    return f"{now.month}/{now.day}"


class Date(Component):
    type = 'date'
    label = 'Date'
    description = 'Day, month and date'
    options = (
        color_option(),
        font_option('6x10'),
        Option('format', 'Format', 'select', 'day_date', choices=[
            ('day_date', 'Tue 24'),
            ('month_date', 'Nov 24'),
            ('day_month_date', 'Tue Nov 24'),
            ('date_month', '24 Nov'),
            ('numeric', '11/24'),
        ]),
        Option('gap', 'Gap', 'number', 1, min=0, max=16, unit='px'),
        outline_option(),
    )

    def __init__(self):
        self._slots = {}

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        parts = FORMATS[opts['format']]
        key = (font.name, opts['format'])
        if key not in self._slots:  # measuring every possible date is slow enough to do once
            values = {part: part_values(part) for part in parts}
            slots = [max(font.text_width(v) for v in values[part]) for part in parts]
            self._slots[key] = slots, line_rows(font, ''.join(''.join(v) for v in values.values()))
        slots, (top, height) = self._slots[key]
        width = sum(slots) + opts['gap'] * (len(parts) - 1)
        return font, parts, slots, top, height, width

    def size(self, opts, ctx):
        font, parts, slots, top, height, width = self._layout(opts)
        return width, height

    def draw(self, image, opts, ctx):
        font, parts, slots, top, height, width = self._layout(opts)
        color = rgba(opts['color'])
        x = 0
        for part, slot in zip(parts, slots):
            font.draw(image, x, -top, part_text(part, ctx.now), color)
            x += slot + opts['gap']
