import calendar

import bdf
from components.base import (Component, Option, align_options, color_option, draw_lines, font_option, line_rows,
                             outline_option, rgba)

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
        *align_options(),
        outline_option(),
    )

    def __init__(self):
        self._slots = {}

    def _layout(self, opts):
        """Each part gets a slot as wide as its widest text, so the parts don't shift around as
        the days go by. The box spans the pixels the widest date can light."""
        font = bdf.get_font(opts['font'])
        parts = FORMATS[opts['format']]
        key = (font.name, opts['format'])
        if key not in self._slots:  # measuring every possible date is slow enough to do once
            values = {part: part_values(part) for part in parts}
            slots = [max(font.text_width(v) for v in values[part]) for part in parts]
            inks = [[b for b in map(font.ink_box, values[part]) if b] for part in parts]
            reach = [(min(b[0] for b in boxes), max(b[2] for b in boxes)) for boxes in inks]
            rows = line_rows(font, ''.join(''.join(v) for v in values.values()))
            self._slots[key] = slots, reach, rows
        slots, reach, (top, height) = self._slots[key]
        starts = [sum(slots[:i]) + opts['gap'] * i for i in range(len(parts))]
        left = min(start + r[0] for start, r in zip(starts, reach))
        right = max(start + r[1] for start, r in zip(starts, reach))
        return font, parts, starts, top, height, right - left + 1

    def size(self, opts, ctx):
        font, parts, starts, top, height, width = self._layout(opts)
        return width, height

    def draw(self, image, opts, ctx):
        font, parts, starts, top, height, width = self._layout(opts)
        runs = [(start, part_text(part, ctx.now)) for part, start in zip(parts, starts)]
        draw_lines(image, font, [(runs, -top)], rgba(opts['color']), opts['align'], opts['valign'])
