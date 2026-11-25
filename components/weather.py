"""The Weather component: everything about the weather in one place. Its "Show" setting picks
what it draws: the original icon, temperature and wind; just the temperature; one detail
such as feels-like or sunset; or a forecast of the next few days or hours.

Temperatures are in °F and wind in mph (see openweathermap.py). Layouts saved before
these were one component (as "weather details" and "forecast") are converted by
layout.upgrade_widget."""
import calendar
from datetime import datetime, timedelta

import bdf
from components.base import (Component, Option, align_options, color_option, draw_labeled, labeled_width, line_rows,
                             outline_option, rgba, sample_chars, widest, widest_digits)
from components.openweathermap import compass, data_or_sample, icon, today_high_low

ICONS = ['both', 'temp']  # the original look: the weather icon with the temperature (and wind)
VALUES = ['temperature', 'feels_like', 'high_low', 'humidity', 'wind', 'sunrise', 'sunset']
FORECASTS = ['forecast_days', 'forecast_hours']
SHOW = [
    ('both', 'Icon, temperature and wind'),
    ('temp', 'Icon and temperature'),
    ('temperature', 'Temperature'),
    ('feels_like', 'Feels like'),
    ('high_low', 'High / low today'),
    ('humidity', 'Humidity'),
    ('wind', 'Wind speed and direction'),
    ('sunrise', 'Sunrise'),
    ('sunset', 'Sunset'),
    ('forecast_days', 'Forecast: the next few days'),
    ('forecast_hours', 'Forecast: every 3 hours'),
]
LABELS = {'temperature': 'Temp', 'feels_like': 'Feels', 'high_low': 'H/L', 'humidity': 'Hum', 'wind': 'Wind',
          'sunrise': 'Rise', 'sunset': 'Set'}
# The widest each value gets, so the box doesn't change size with the weather. Each 0 is any
# digit and [12] is a 1 or a 2 (see base.widest).
DIRECTIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
SAMPLES = {
    'temperature': ['-00°', '100°'],
    'feels_like': ['-00°', '100°'],
    'high_low': ['00°/00°'],
    'humidity': ['00%', '100%'],
    'wind': [f"00 {d}" for d in DIRECTIONS],
}
CLOCK_SAMPLES = {'12': ['0:[012345]0', '1[012]:[012345]0'], '24': ['[012]0:[012345]0']}  # for sunrise and sunset
ICON_SIZE = 16
GAP = 2  # between forecast columns


def hour_label(hour, hours):
    if hours == '24':
        return f"{hour:02}:00"
    return f"{hour % 12 or 12}{'a' if hour < 12 else 'p'}"


class Weather(Component):
    type = 'weather'
    label = 'Weather'
    description = 'The weather now, one detail of it, or the forecast'
    options = (
        Option('show', 'Show', 'select', 'both', choices=SHOW),
        Option('label', 'Label', 'bool', False, show_if={'show': VALUES}),
        Option('hours', 'Hours', 'select', '12', choices=[('12', '12-hour'), ('24', '24-hour')],
               show_if={'show': ['sunrise', 'sunset', 'forecast_hours']}),
        Option('count', 'Columns', 'number', 3, min=1, max=5, show_if={'show': FORECASTS}),
        Option('start', 'Starting', 'select', 'today', choices=[('today', 'Today'), ('tomorrow', 'Tomorrow')],
               show_if={'show': 'forecast_days'}),
        Option('temps', 'Temperatures', 'select', 'high_low', choices=[('high_low', 'High/low'), ('high', 'High only')],
               show_if={'show': 'forecast_days'}),
        color_option(),
        # "auto" isn't a font, so it's what these fall back to: a size that suits what's shown. The
        # forecast has its own, so switching between a value and a forecast doesn't carry a font
        # that's far too big or small for the other.
        Option('font', 'Font', 'font', 'auto', show_if={'show': VALUES}),
        Option('forecast_font', 'Font', 'font', 'auto', show_if={'show': FORECASTS}),
        *align_options(align_if={'show': VALUES}, valign_if={'show': VALUES}),
        outline_option(),
    )

    def font(self, opts):
        show = opts['show']
        name = opts['forecast_font'] if show in FORECASTS else opts['font']
        if name == 'auto':
            name = '4x6' if show in FORECASTS else '6x10' if show == 'temperature' else '5x7'
        return bdf.get_font(name)

    def size(self, opts, ctx):
        show = opts['show']
        if show in ICONS:
            return 32, 32 if show == 'both' else 16
        if show in FORECASTS:
            font, column, label_top, label_height, value_top, value_height = self._forecast_layout(opts)
            return opts['count'] * (column + GAP) - GAP, label_height + 1 + ICON_SIZE + 1 + value_height
        font, label, top, height, width = self._value_layout(opts)
        return width, height

    def draw(self, image, opts, ctx):
        show = opts['show']
        if show in ICONS:
            return self._draw_icons(image, opts, ctx)
        if show in FORECASTS:
            return self._draw_forecast(image, opts, ctx)
        return self._draw_value(image, opts, ctx)

    # ---------- The original look: icon and temperature, and wind ----------

    def _draw_icons(self, image, opts, ctx):
        data, note = data_or_sample(ctx, 'weather')
        if data is None:
            return None  # nothing fetched yet: leave the area blank

        color = rgba(opts['color'])
        font = bdf.get_font('6x10')
        small_font = bdf.get_font('5x8')
        show_wind = opts['show'] == 'both'

        mask = icon(data['icon'])
        if mask is not None:
            image.paste(color, (0, 0), mask)
        if show_wind:
            image.paste(color, (0, 16), icon('wind'))

        # Same layout as before the management page; three-digit numbers get squeezed in
        temp_font = font
        x_temp, y_temp, x_wind, y_wind = 19, 12, 19, 27
        if data['temp'] > 99:
            temp_font = small_font
            x_temp, y_temp = 16, 11
        if data['wind_speed'] > 99:
            x_wind, y_wind = 16, 26

        temp = f" {data['temp']}" if int(data['temp']) < 10 else str(data['temp'])
        temp_font.draw_at_baseline(image, x_temp, y_temp, temp, color)
        if show_wind:
            wind = f" {data['wind_speed']}" if int(data['wind_speed']) < 10 else str(data['wind_speed'])
            temp_font.draw_at_baseline(image, x_wind, y_wind, wind, color)
        return note

    # ---------- One value on a line, with an optional short label ----------

    def _value_layout(self, opts):
        font = self.font(opts)
        show = opts['show']
        label = LABELS[show] + ' ' if opts['label'] else ''
        samples = CLOCK_SAMPLES[opts['hours']] if show in ('sunrise', 'sunset') else SAMPLES[show]
        # The rows anything it can show lights, so the box is no taller than the value can be
        top, height = line_rows(font, label + sample_chars(*samples))
        width = labeled_width(font, label, widest(font, *samples))
        return font, label, top, height, width

    def value(self, show, weather, forecast, ctx, hours):
        """The text for one of VALUES, or None if there's no data for it"""
        if show == 'high_low':
            high_low = today_high_low(ctx, weather, forecast)
            return f"{high_low[0]}°/{high_low[1]}°" if high_low else None
        if weather is None:
            return None
        if show == 'temperature':
            return f"{weather['temp']}°"
        if show == 'feels_like':
            return f"{weather['feels_like']}°"
        if show == 'humidity':
            return f"{weather['humidity']}%" if weather.get('humidity') is not None else None
        if show in ('sunrise', 'sunset'):
            if not weather.get(show):
                return None
            at = datetime.fromtimestamp(weather[show])
            return f"{at.hour % 12 or 12}:{at.minute:02}" if hours == '12' else f"{at.hour:02}:{at.minute:02}"
        if show == 'wind':
            direction = weather.get('wind_deg')
            return f"{weather['wind_speed']} {compass(direction)}" if direction is not None else str(weather['wind_speed'])
        return None

    def _draw_value(self, image, opts, ctx):
        font, label, top, height, width = self._value_layout(opts)
        weather, note = data_or_sample(ctx, 'weather')
        forecast = None
        if opts['show'] == 'high_low':
            forecast, forecast_note = data_or_sample(ctx, 'forecast')
            note = note or forecast_note
        value = self.value(opts['show'], weather, forecast, ctx, opts['hours'])
        if value is None:
            return note
        draw_labeled(image, font, label, value, rgba(opts['color']), opts['align'], opts['valign'])
        return note

    # ---------- Forecast: columns of day or time, icon and temperature ----------

    def _forecast_layout(self, opts):
        font = self.font(opts)
        if opts['show'] == 'forecast_days':
            labels = list(calendar.day_abbr)
            sample = '00/00' if opts['temps'] == 'high_low' else '00°'
        else:
            labels = [hour_label(h, opts['hours']) for h in range(24)]
            sample = '00°'
        label_top, label_height = line_rows(font, ''.join(labels))
        value_top, value_height = line_rows(font, '0123456789/°-')
        column = max(ICON_SIZE, max(font.text_width(l) for l in labels), font.text_width(widest_digits(font, sample)))
        return font, column, label_top, label_height, value_top, value_height

    def forecast_columns(self, opts, forecast, ctx):
        """[(label, icon, temperature), ...] for each forecast column there's data for"""
        if opts['show'] == 'forecast_hours':
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

    def _draw_forecast(self, image, opts, ctx):
        forecast, note = data_or_sample(ctx, 'forecast')
        if forecast is None:
            return None
        font, column, label_top, label_height, value_top, value_height = self._forecast_layout(opts)
        color = rgba(opts['color'])
        icon_y = label_height + 1
        value_y = icon_y + ICON_SIZE + 1
        for i, (label, code, temps) in enumerate(self.forecast_columns(opts, forecast, ctx)):
            x = i * (column + GAP)
            font.draw(image, x + (column - font.text_width(label)) // 2, -label_top, label, color)
            mask = icon(code)
            if mask is not None:
                image.paste(color, (x + (column - ICON_SIZE) // 2, icon_y), mask)
            font.draw(image, x + (column - font.text_width(temps)) // 2, value_y - value_top, temps, color)
        return note
