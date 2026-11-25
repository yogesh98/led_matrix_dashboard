from datetime import datetime

import bdf
from components.base import ASCII, Component, Option, color_option, font_option, line_rows, rgba, widest_digits
from components.openweathermap import compass, data_or_sample, icon, today_high_low


class Weather(Component):
    type = 'weather'
    label = 'Weather'
    description = 'Conditions, temperature (°F) and wind speed (mph)'
    options = (
        color_option(),
        Option('show', 'Show', 'select', 'both', choices=[
            ('both', 'Temperature and wind'),
            ('temp', 'Temperature only'),
        ]),
    )

    def size(self, opts, ctx):
        return 32, 32 if opts['show'] == 'both' else 16

    def draw(self, image, opts, ctx):
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


class WeatherDetails(Component):
    """One weather detail on a line: a short label on the left, the value on the right"""
    type = 'weather_details'
    label = 'Weather details'
    description = 'Feels like, humidity, high/low, sunrise, sunset or wind'
    options = (
        Option('field', 'Show', 'select', 'feels_like', choices=[
            ('feels_like', 'Feels like'),
            ('humidity', 'Humidity'),
            ('high_low', 'High / low today'),
            ('sunrise', 'Sunrise'),
            ('sunset', 'Sunset'),
            ('wind', 'Wind speed and direction'),
        ]),
        Option('label', 'Label', 'bool', True),
        Option('hours', 'Hours', 'select', '12', choices=[('12', '12-hour'), ('24', '24-hour')],
               show_if={'field': ['sunrise', 'sunset']}),
        color_option(),
        font_option('5x7'),
    )
    LABELS = {'feels_like': 'Feels', 'humidity': 'Hum', 'high_low': 'H/L', 'sunrise': 'Rise', 'sunset': 'Set', 'wind': 'Wind'}
    # The widest each value gets, so the box doesn't change size as the weather does
    SAMPLES = {'feels_like': '00°', 'humidity': '100%', 'high_low': '00°/00°', 'sunrise': '00:00', 'sunset': '00:00', 'wind': '00 NW'}

    def _layout(self, opts):
        font = bdf.get_font(opts['font'])
        label = self.LABELS[opts['field']] + ' ' if opts['label'] else ''
        top, height = line_rows(font, ASCII + '°')
        width = font.text_width(label) + font.text_width(widest_digits(font, self.SAMPLES[opts['field']]))
        return font, label, top, height, width

    def size(self, opts, ctx):
        font, label, top, height, width = self._layout(opts)
        return width, height

    def value(self, field, weather, forecast, ctx, hours):
        if field == 'high_low':
            high_low = today_high_low(ctx, weather, forecast)
            return f"{high_low[0]}°/{high_low[1]}°" if high_low else None
        if weather is None:
            return None
        if field == 'feels_like':
            return f"{weather['feels_like']}°"
        if field == 'humidity':
            return f"{weather['humidity']}%" if weather.get('humidity') is not None else None
        if field in ('sunrise', 'sunset'):
            if not weather.get(field):
                return None
            at = datetime.fromtimestamp(weather[field])
            return f"{at.hour % 12 or 12}:{at.minute:02}" if hours == '12' else f"{at.hour:02}:{at.minute:02}"
        if field == 'wind':
            direction = weather.get('wind_deg')
            return f"{weather['wind_speed']} {compass(direction)}" if direction is not None else str(weather['wind_speed'])
        return None

    def draw(self, image, opts, ctx):
        font, label, top, height, width = self._layout(opts)
        weather, note = data_or_sample(ctx, 'weather')
        forecast = None
        if opts['field'] == 'high_low':
            forecast, forecast_note = data_or_sample(ctx, 'forecast')
            note = note or forecast_note
        value = self.value(opts['field'], weather, forecast, ctx, opts['hours'])
        if value is None:
            return note
        color = rgba(opts['color'])
        font.draw(image, 0, -top, label, color)
        font.draw(image, width - font.text_width(value), -top, value, color)
        return note
