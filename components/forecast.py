import calendar
from datetime import timedelta

import bdf
from components.base import Component, Option, color_option, font_option, line_rows, rgba, widest_digits
from components.openweathermap import data_or_sample, icon, today_high_low

ICON_SIZE = 16
GAP = 2  # between columns


def hour_label(hour, hours):
    if hours == '24':
        return f"{hour:02}:00"
    return f"{hour % 12 or 12}{'a' if hour < 12 else 'p'}"


class Forecast(Component):
    """Columns of label (day or time), weather icon and temperature"""
    type = 'forecast'
    label = 'Forecast'
    description = 'The next few days, or the next few hours'
    options = (
        Option('mode', 'Show', 'select', 'days', choices=[('days', 'Days'), ('hours', 'Every 3 hours')]),
        Option('count', 'Columns', 'number', 3, min=1, max=5),
        Option('start', 'Starting', 'select', 'today', choices=[('today', 'Today'), ('tomorrow', 'Tomorrow')],
               show_if={'mode': 'days'}),
        Option('temps', 'Temperatures', 'select', 'high_low', choices=[('high_low', 'High/low'), ('high', 'High only')],
               show_if={'mode': 'days'}),
        Option('hours', 'Hours', 'select', '12', choices=[('12', '12-hour'), ('24', '24-hour')],
               show_if={'mode': 'hours'}),
        color_option(),
        font_option('4x6'),
    )

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        if opts['mode'] == 'days':
            labels = list(calendar.day_abbr)
            sample = '00/00' if opts['temps'] == 'high_low' else '00°'
        else:
            labels = [hour_label(h, opts['hours']) for h in range(24)]
            sample = '00°'
        label_top, label_height = line_rows(font, ''.join(labels))
        value_top, value_height = line_rows(font, '0123456789/°-')
        column = max(ICON_SIZE, max(font.text_width(l) for l in labels), font.text_width(widest_digits(font, sample)))
        return font, column, label_top, label_height, value_top, value_height

    def size(self, opts, ctx):
        font, column, label_top, label_height, value_top, value_height = self._layout(opts)
        return opts['count'] * (column + GAP) - GAP, label_height + 1 + ICON_SIZE + 1 + value_height

    def columns(self, opts, forecast, ctx):
        """[(label, icon, temperature), ...] for each column there's data for"""
        if opts['mode'] == 'hours':
            now = ctx.now.timestamp()
            upcoming = [h for h in forecast['hours'] if h['time'] > now][:opts['count']]
            return [(hour_label(h['hour'], opts['hours']), h['icon'], f"{h['temp']}°") for h in upcoming]

        today = ctx.now.date()
        first = today if opts['start'] == 'today' else today + timedelta(days=1)
        days = {d['date']: d for d in forecast['days']}
        result = []
        for i in range(opts['count']):
            date = first + timedelta(days=i)
            day = days.get(date.isoformat())
            if day is None:
                break
            high, low = day['high'], day['low']
            if date == today:
                # The forecast only covers the rest of today; add what's been seen so far
                high, low = today_high_low(ctx, ctx.data('weather'), forecast) or (high, low)
            temps = f"{high}/{low}" if opts['temps'] == 'high_low' else f"{high}°"
            result.append((date.strftime('%a'), day['icon'], temps))
        return result

    def draw(self, image, opts, ctx):
        forecast, note = data_or_sample(ctx, 'forecast')
        if forecast is None:
            return None
        font, column, label_top, label_height, value_top, value_height = self._layout(opts)
        color = rgba(opts['color'])
        icon_y = label_height + 1
        value_y = icon_y + ICON_SIZE + 1
        for i, (label, code, temps) in enumerate(self.columns(opts, forecast, ctx)):
            x = i * (column + GAP)
            font.draw(image, x + (column - font.text_width(label)) // 2, -label_top, label, color)
            mask = icon(code)
            if mask is not None:
                image.paste(color, (x + (column - ICON_SIZE) // 2, icon_y), mask)
            font.draw(image, x + (column - font.text_width(temps)) // 2, value_y - value_top, temps, color)
        return note
