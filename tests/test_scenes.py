"""The scene backgrounds and the prebuilt screens that use them"""
import unittest
from datetime import datetime, timedelta

from components.scene import THEMES, moon_phase, sun_phase
from layout import normalize, normalize_widget
from prebuilt import PREBUILT, prebuilt_screens
from renderer import render_screen, render_widget
from tests.helpers import context

SUN = {'sunrise': datetime(2026, 11, 24, 6, 50).timestamp(), 'sunset': datetime(2026, 11, 24, 17, 0).timestamp()}
NOON = datetime(2026, 11, 24, 12, 30, 5)
MIDNIGHT = datetime(2026, 11, 24, 23, 59, 5)


def weather(icon='01d', **extra):
    return {'icon': icon, 'temp': 40, 'wind_speed': 8, **SUN, **extra}


def scene(**options):
    return normalize_widget({'type': 'scene', 'options': options})


def draw(widget, now=NOON, weather_data=None, size=(64, 32)):
    image, note = render_widget(widget, context(now=now, weather=weather_data or weather(), size=size))
    return image


def brightness(image):
    return sum(image.convert('L').getdata()) / (image.width * image.height)


class SceneTest(unittest.TestCase):
    def test_every_theme_and_weather_fills_the_display(self):
        for theme in THEMES:
            for icon in ('01d', '02d', '03d', '04d', '09d', '10d', '11d', '13d', '50d'):
                for now in (NOON, MIDNIGHT, datetime(2026, 11, 24, 17, 5)):
                    image = draw(scene(theme=theme), now, weather(icon))
                    self.assertEqual(image.size, (64, 32), (theme, icon, now))
                    # Opaque everywhere: it's a background
                    self.assertEqual(image.getchannel('A').getextrema(), (255, 255), (theme, icon, now))

    def test_fills_bigger_displays_too(self):
        image = draw(scene(theme='city'), size=(128, 64))
        self.assertEqual(image.size, (128, 64))

    def test_same_moment_same_picture(self):
        a = draw(scene(theme='blossom'), NOON)
        b = draw(scene(theme='blossom'), NOON)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_it_moves(self):
        for theme, icon in (('blossom', '01d'), ('lake', '01d'), ('city', '10d'), ('skogafoss', '04d')):
            a = draw(scene(theme=theme), NOON, weather(icon))
            b = draw(scene(theme=theme), NOON + timedelta(seconds=1.5), weather(icon))
            self.assertNotEqual(a.tobytes(), b.tobytes(), theme)

    def test_night_is_darker_than_day(self):
        for theme in THEMES:
            self.assertLess(brightness(draw(scene(theme=theme), MIDNIGHT)), brightness(draw(scene(theme=theme), NOON)) * 0.6)

    def test_city_windows_light_up_at_night(self):
        night = draw(scene(theme='city', weather='01'), MIDNIGHT).convert('RGB')
        warm = sum(1 for r, g, b in night.getdata() if r > 200 and g > 140 and b < 140)
        self.assertGreater(warm, 15)

    def test_skogafoss_rainbow_and_northern_lights(self):
        def colorful(image):
            # How saturated the spray to the left of the falls is, where the rainbow hangs
            return sum(max(p[:3]) - min(p[:3]) for p in image.crop((18, 18, 30, 26)).getdata())

        sunny = draw(scene(theme='skogafoss', weather='01', time='1'))
        grey = draw(scene(theme='skogafoss', weather='03', time='1'))
        self.assertGreater(colorful(sunny), colorful(grey) * 1.3)
        clear_night = draw(scene(theme='skogafoss', weather='01', time='-1')).convert('RGB')
        cloudy_night = draw(scene(theme='skogafoss', weather='10', time='-1')).convert('RGB')
        # The aurora is green: green well above red and blue, unlike moonlit clouds and sky
        green = lambda image: sum(max(0, g - max(r, b)) for r, g, b in image.crop((0, 0, 64, 8)).getdata())
        self.assertGreater(green(clear_night), 200)
        self.assertGreater(green(clear_night), green(cloudy_night) * 3)

    def test_weather_and_time_can_be_fixed(self):
        fixed = scene(theme='lake', weather='13', time='-1')
        # It ignores the real weather and time, so no sample-weather note in the editor
        image, note = render_widget(fixed, context(now=NOON, weather=None, preview=True))
        self.assertIsNone(note)
        self.assertLess(brightness(image), brightness(draw(scene(theme='lake'), NOON)))

    def test_brightness_option(self):
        full = draw(scene(theme='blossom'))
        dim = draw(scene(theme='blossom', brightness=30))
        self.assertLess(brightness(dim), brightness(full) * 0.4)

    def test_shows_before_the_weather_loads(self):
        image, note = render_widget(scene(), context(now=NOON, weather=None))
        self.assertGreater(brightness(image), 5)

    def test_sun_phase(self):
        self.assertEqual(sun_phase(NOON, SUN), 1)
        self.assertEqual(sun_phase(MIDNIGHT, SUN), -1)
        self.assertAlmostEqual(sun_phase(datetime(2026, 11, 24, 17, 0), SUN), 0, places=2)
        self.assertAlmostEqual(sun_phase(datetime(2026, 11, 24, 6, 50), SUN), 0, places=2)
        self.assertTrue(0 < sun_phase(datetime(2026, 11, 24, 7, 10), SUN) < 1)
        self.assertEqual(sun_phase(NOON, None), 1)  # default sunrise and sunset

    def test_moon_phase(self):
        new = moon_phase(datetime(2026, 11, 9, 12))  # just after a new moon
        self.assertLess(min(new, 1 - new), 0.03)
        self.assertAlmostEqual(moon_phase(datetime(2026, 11, 24, 12)), 0.5, delta=0.04)  # full moon


class PrebuiltTest(unittest.TestCase):
    def test_they_are_valid_screens(self):
        screens = prebuilt_screens()
        self.assertEqual(len(screens), len(PREBUILT))
        normalize({'screens': screens})  # raises if not

    def test_everything_fits_on_the_display(self):
        ctx = context(now=NOON, weather=weather())
        for screen in prebuilt_screens():
            for widget in screen['widgets']:
                image, _ = render_widget(widget, ctx)
                self.assertGreaterEqual(widget['x'], 0, (screen['name'], widget['type']))
                self.assertLessEqual(widget['x'] + image.width, 64, (screen['name'], widget['type']))
                self.assertLessEqual(widget['y'] + image.height, 32, (screen['name'], widget['type']))
            self.assertEqual(screen['widgets'][0]['type'], 'scene')  # the background goes first

    def test_text_is_outlined_so_it_reads_over_a_bright_sky(self):
        for screen in prebuilt_screens():
            for widget in screen['widgets'][1:]:
                self.assertTrue(widget['options']['outline'], (screen['name'], widget['type']))


class OutlineTest(unittest.TestCase):
    def test_dark_edge_around_the_text(self):
        plain, _ = render_widget(normalize_widget({'type': 'time'}), context(now=NOON))
        edged, _ = render_widget(normalize_widget({'type': 'time', 'options': {'outline': True}}), context(now=NOON))
        self.assertEqual(edged.size, (plain.width + 2, plain.height + 2))
        # The text itself is unchanged, a pixel in from the edge...
        inner = edged.crop((1, 1, plain.width + 1, plain.height + 1))
        for before, after in zip(plain.getdata(), inner.getdata()):
            if before[3]:
                self.assertEqual(after, before)
        lit = [p for p in edged.getdata() if p[3] and p[:3] != (0, 0, 0)]
        self.assertEqual(len(lit), sum(1 for p in plain.getdata() if p[3]))
        # ...with opaque black all around it
        black = [p for p in edged.getdata() if p == (0, 0, 0, 255)]
        self.assertGreater(len(black), len(lit))

    def test_off_by_default(self):
        for type in ('clock', 'time', 'date', 'countdown', 'weather_details'):
            self.assertFalse(normalize_widget({'type': type})['options']['outline'], type)
