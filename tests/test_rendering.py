import os
import unittest
from datetime import datetime

from PIL import Image

import bdf
from components import COMPONENTS
from layout import default_config, normalize, normalize_widget
from renderer import render_screen, render_widget
from tests.helpers import context, lit

WHITE = (255, 255, 255)
TIMES = [
    datetime(2026, 11, 24, 9, 5),    # Tue
    datetime(2026, 11, 29, 12, 59),  # Sun
    datetime(2026, 1, 1, 0, 0),      # Thu, midnight shows as 12
    datetime(2026, 7, 15, 23, 47),   # Wed
]
WEATHER = [
    {'icon': '01d', 'temp': 72, 'wind_speed': 5},
    {'icon': '13n', 'temp': 105, 'wind_speed': 120},
    {'icon': '50d', 'temp': 3, 'wind_speed': 12},
    {'icon': '10n', 'temp': 100, 'wind_speed': 99},
    None,  # not fetched yet
]


def legacy_frame(now, weather):
    """The display as the components drew it before the management page: Clock(8, 1),
    Date(0, 24) and Weather(32, 0), with the coordinates they passed to DrawText"""
    frame = Image.new('RGB', (64, 32))
    big, font, small = bdf.get_font('8x13B'), bdf.get_font('6x10'), bdf.get_font('5x8')

    hour = now.hour % 12 or 12
    big.draw_at_baseline(frame, 8, 1 + 10, str(hour).zfill(2), WHITE)
    big.draw_at_baseline(frame, 8, 1 + 21, str(now.minute).zfill(2), WHITE)

    font.draw_at_baseline(frame, 0 + 1, 24 + 7, now.strftime('%a'), WHITE)
    font.draw_at_baseline(frame, 0 + 20, 24 + 7, now.strftime('%d'), WHITE)

    if weather is not None:
        icons = os.path.join(bdf.ROOT, 'icons')
        frame.paste(Image.open(os.path.join(icons, weather['icon'] + '.png')).convert('RGB'), (32, 0))
        frame.paste(Image.open(os.path.join(icons, 'wind.png')).convert('RGB'), (32, 16))
        degree_font, x_temp, x_wind, y_temp, y_wind = font, 19, 19, 12, 27
        if weather['temp'] > 99:
            degree_font, x_temp, y_temp = small, 16, 11
        if weather['wind_speed'] > 99:
            x_wind, y_wind = 16, 26
        temp = f" {weather['temp']}" if int(weather['temp']) < 10 else str(weather['temp'])
        wind = f" {weather['wind_speed']}" if int(weather['wind_speed']) < 10 else str(weather['wind_speed'])
        degree_font.draw_at_baseline(frame, 32 + x_temp, 0 + y_temp, temp, WHITE)
        degree_font.draw_at_baseline(frame, 32 + x_wind, 0 + y_wind, wind, WHITE)
    return frame


class DefaultLayoutTest(unittest.TestCase):
    def test_matches_the_display_before_the_management_page(self):
        screen = normalize(default_config())['screens'][0]
        for now in TIMES:
            for weather in WEATHER:
                with self.subTest(now=now, weather=weather):
                    expected = legacy_frame(now, weather)
                    self.assertGreater(lit(expected), 50)
                    actual = render_screen(screen, context(now=now, weather=weather))
                    self.assertEqual(actual.tobytes(), expected.tobytes())


class ComponentTest(unittest.TestCase):
    def widget(self, type, **options):
        return normalize_widget({'type': type, 'options': options})

    def test_every_component_draws_with_its_defaults(self):
        for type in COMPONENTS:
            with self.subTest(type=type):
                image, note = render_widget(self.widget(type), context(preview=True))
                self.assertGreater(lit(image), 0)

    def test_every_component_fits_the_display_as_added(self):
        for type in COMPONENTS:
            with self.subTest(type=type):
                image, _ = render_widget(self.widget(type), context(preview=True))
                self.assertLessEqual(image.width, 64)
                self.assertLessEqual(image.height, 32)

    def test_boxes_fit_the_text_exactly(self):
        # Boxes are trimmed to the rows text can light; check nothing gets cut off
        now = datetime(2026, 8, 30, 20, 38, 59)  # Aug and Sun have descenders/tall letters
        for font in bdf.available_fonts():
            f = bdf.get_font(font)
            for type, options, lines in [
                ('clock', {'hours': '24'}, ['20', '38']),
                ('time', {'seconds': True, 'hours': '24'}, ['20:38:59']),
                ('date', {'format': 'day_month_date', 'gap': 0}, [now.strftime('%a%b%d')]),
                ('text', {'text': 'Jqy|_^gW'}, ['Jqy|_^gW']),
            ]:
                with self.subTest(font=font, type=type):
                    image, _ = render_widget(self.widget(type, font=font, **options), context(now=now))
                    big = Image.new('RGB', (600, 200))
                    for i, line in enumerate(lines):
                        f.draw(big, 0, 60 * i + 10, line, WHITE)
                    self.assertEqual(lit(image), lit(big))

    def test_weather_shows_sample_data_only_in_the_editor(self):
        widget = self.widget('weather')
        image, note = render_widget(widget, context(weather=None, preview=False))
        self.assertEqual(lit(image), 0)
        image, note = render_widget(widget, context(weather=None, preview=True))
        self.assertGreater(lit(image), 0)
        self.assertIn('sample', note)

    def test_weather_temperature_only_is_half_height(self):
        image, _ = render_widget(self.widget('weather', show='temp'), context(weather=WEATHER[0]))
        self.assertEqual(image.size, (32, 16))

    def test_scrolling_text_moves_on_the_display_but_not_in_the_editor(self):
        widget = self.widget('text', text='Hello there', scroll=True, width=40, speed=20)
        a, _ = render_widget(widget, context(now=datetime(2026, 1, 1, 0, 0, 0)))
        b, _ = render_widget(widget, context(now=datetime(2026, 1, 1, 0, 0, 1)))
        self.assertEqual(a.width, 40)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        a, _ = render_widget(widget, context(now=datetime(2026, 1, 1, 0, 0, 0), preview=True))
        b, _ = render_widget(widget, context(now=datetime(2026, 1, 1, 0, 0, 1), preview=True))
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_blinking_colon(self):
        widget = self.widget('time', blink=True)
        on, _ = render_widget(widget, context(now=datetime(2026, 1, 1, 10, 10, 0)))
        off, _ = render_widget(widget, context(now=datetime(2026, 1, 1, 10, 10, 1)))
        self.assertEqual(lit(on) - lit(off), lit(render_widget(self.widget('text', text=':'), context())[0]))

    def test_widgets_hanging_off_the_display_are_clipped(self):
        screen = {'widgets': [
            normalize_widget({'type': 'text', 'x': -7, 'y': -3, 'options': {'text': 'Hello'}}),
            normalize_widget({'type': 'box', 'x': 60, 'y': 30, 'options': {'width': 10, 'height': 10}}),
        ]}
        frame = render_screen(screen, context())
        self.assertGreater(lit(frame), 0)
        self.assertEqual(frame.getpixel((63, 31)), (85, 85, 85))

    def test_hidden_widgets_and_broken_ones_are_skipped(self):
        broken = normalize_widget({'type': 'text'})
        broken['options'] = {}  # draw() will hit a KeyError
        hidden = normalize_widget({'type': 'box', 'hidden': True})
        frame = render_screen({'widgets': [broken, hidden]}, context())
        self.assertEqual(lit(frame), 0)

    def test_later_widgets_draw_on_top(self):
        red = normalize_widget({'type': 'box', 'options': {'color': '#ff0000', 'width': 4, 'height': 4}})
        blue = normalize_widget({'type': 'box', 'options': {'color': '#0000ff', 'width': 4, 'height': 4}})
        self.assertEqual(render_screen({'widgets': [red, blue]}, context()).getpixel((1, 1)), (0, 0, 255))


if __name__ == '__main__':
    unittest.main()
