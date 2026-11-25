import json
import os
import tempfile
import unittest

from layout import LayoutStore, default_config, normalize
from renderer import Rotation


def layout(*screens):
    return {'screens': list(screens)}


class NormalizeTest(unittest.TestCase):
    def test_fills_in_defaults_and_is_stable(self):
        config = normalize(default_config())
        clock = config['screens'][1]['widgets'][0]  # the classic screen's clock
        self.assertEqual(clock['options'], {'color': '#ffffff', 'font': '8x13B', 'hours': '12', 'spacing': 1, 'outline': False})
        self.assertFalse(clock['hidden'])
        self.assertEqual(normalize(config), config)

    def test_fixes_bad_values(self):
        config = normalize(layout({
            'id': 'a', 'name': '  ', 'duration': 0, 'enabled': 'yes',
            'widgets': [{'id': 'bad id!', 'type': 'text', 'x': 'left', 'y': 9.6,
                         'options': {'color': '#ABC', 'font': 'nope', 'scroll': 'true', 'speed': 1000,
                                     'unknown': 1}}],
        }))
        screen = config['screens'][0]
        self.assertEqual((screen['name'], screen['duration'], screen['enabled']), ('Screen 1', 1, True))
        widget = screen['widgets'][0]
        self.assertNotEqual(widget['id'], 'bad id!')
        self.assertEqual((widget['x'], widget['y']), (0, 10))
        self.assertEqual(widget['options']['color'], '#aabbcc')
        self.assertEqual(widget['options']['font'], '6x10')
        self.assertIs(widget['options']['scroll'], False)
        self.assertEqual(widget['options']['speed'], 100)
        self.assertNotIn('unknown', widget['options'])

    def test_duplicate_ids_get_new_ones(self):
        config = normalize(layout(
            {'id': 'x', 'widgets': [{'id': 'x', 'type': 'box'}, {'id': 'x', 'type': 'box'}]},
            {'id': 'x'},
        ))
        ids = [config['screens'][0]['id'], config['screens'][1]['id']]
        ids += [w['id'] for w in config['screens'][0]['widgets']]
        self.assertEqual(len(set(ids)), 4)

    def test_unknown_components(self):
        raw = layout({'widgets': [{'type': 'toaster'}, {'type': 'box'}]})
        with self.assertRaises(ValueError):
            normalize(raw)
        self.assertEqual([w['type'] for w in normalize(raw, strict=False)['screens'][0]['widgets']], ['box'])

    def test_rejects_layouts_without_screens(self):
        for raw in (None, [], {}, {'screens': []}, {'screens': 'main'}, {'screens': [1]}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize(raw)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'data', 'display.json')

    def tearDown(self):
        self.dir.cleanup()

    def test_default_until_saved(self):
        store = LayoutStore(self.path)
        self.assertEqual(store.config, normalize(default_config()))
        self.assertFalse(os.path.exists(self.path))

    def test_save_and_load(self):
        saved = LayoutStore(self.path).save(layout({'name': 'Night', 'widgets': [{'type': 'time'}]}))
        self.assertEqual(LayoutStore(self.path).config, saved)
        self.assertEqual(saved['screens'][0]['name'], 'Night')

    def test_invalid_save_changes_nothing(self):
        store = LayoutStore(self.path)
        store.save(layout({'name': 'Keep'}))
        with self.assertRaises(ValueError):
            store.save({'screens': []})
        self.assertEqual(store.config['screens'][0]['name'], 'Keep')
        self.assertEqual(LayoutStore(self.path).config['screens'][0]['name'], 'Keep')

    def test_unreadable_file_shows_the_default(self):
        os.makedirs(os.path.dirname(self.path))
        for content in ('{not json', json.dumps({'screens': []})):
            with open(self.path, 'w') as f:
                f.write(content)
            self.assertEqual(LayoutStore(self.path).config, normalize(default_config()))


class RotationTest(unittest.TestCase):
    def setUp(self):
        self.time = 0.0
        self.rotation = Rotation(clock=lambda: self.time)
        self.screens = normalize(layout(
            {'id': 'a', 'duration': 10},
            {'id': 'b', 'duration': 5},
            {'id': 'off', 'duration': 7, 'enabled': False},
            {'id': 'c', 'duration': 3},
        ))['screens']

    def showing(self, at):
        self.time = at
        screen, left = self.rotation.current(self.screens)
        return screen['id'] if screen else None, left

    def test_takes_turns_skipping_disabled_screens(self):
        self.assertEqual(self.showing(0), ('a', 10))
        self.assertEqual(self.showing(9.5), ('a', 0.5))
        self.assertEqual(self.showing(10), ('b', 5))
        self.assertEqual(self.showing(15), ('c', 3))
        self.assertEqual(self.showing(18), ('a', 10))

    def test_show_puts_a_screen_on_now_even_if_disabled(self):
        self.showing(0)
        self.time = 1
        self.rotation.show('off')
        self.assertEqual(self.showing(1), ('off', 7))
        self.assertEqual(self.showing(8), ('c', 3))  # then carries on after it

    def test_one_screen_stays_on(self):
        screens = self.screens[:1]
        for at in (0, 10, 25):
            self.time = at
            self.assertEqual(self.rotation.current(screens)[0]['id'], 'a')

    def test_disabling_or_deleting_the_current_screen_moves_on(self):
        self.showing(0)
        self.screens[0]['enabled'] = False
        self.assertEqual(self.showing(1)[0], 'b')
        del self.screens[1]
        self.assertEqual(self.showing(2)[0], 'c')

    def test_nothing_enabled(self):
        for screen in self.screens:
            screen['enabled'] = False
        self.assertEqual(self.showing(0), (None, 0))


if __name__ == '__main__':
    unittest.main()


class UpgradeTest(unittest.TestCase):
    """Layouts saved when weather details and the forecast were components of their own"""

    def test_weather_details_become_the_weather_component(self):
        old = {'id': 'w1', 'type': 'weather_details', 'x': 43, 'y': 20,
               'options': {'field': 'humidity', 'label': False, 'font': '6x10', 'color': '#c8f0ff', 'outline': True}}
        widget = normalize(layout({'widgets': [old]}))['screens'][0]['widgets'][0]
        self.assertEqual(widget['type'], 'weather')
        self.assertEqual({k: widget['options'][k] for k in ('show', 'label', 'font', 'color', 'outline', 'align')},
                         {'show': 'humidity', 'label': False, 'font': '6x10', 'color': '#c8f0ff', 'outline': True,
                          'align': 'right'})
        self.assertEqual((widget['x'], widget['y']), (43, 20))

    def test_temperature_lights_the_same_leds_as_before(self):
        from renderer import render_screen
        from tests.helpers import context
        old = {'type': 'weather_details', 'x': 43, 'y': 20,
               'options': {'field': 'temp', 'label': False, 'font': '6x10', 'outline': True}}
        # What the old component drew: the value right-aligned in a box as wide as "00°"
        before = {'type': 'text', 'x': 43, 'y': 20, 'options': {'text': '72°', 'font': '6x10', 'outline': True}}
        ctx = context(weather={'icon': '01d', 'temp': 72})
        upgraded = normalize(layout({'widgets': [old]}))['screens'][0]
        expected = normalize(layout({'widgets': [before]}))['screens'][0]
        self.assertEqual(upgraded['widgets'][0]['options']['show'], 'temperature')
        self.assertEqual(render_screen(upgraded, ctx).tobytes(), render_screen(expected, ctx).tobytes())

    def test_forecast_becomes_the_weather_component(self):
        old = {'type': 'forecast', 'x': 0, 'y': 1,
               'options': {'mode': 'hours', 'count': 4, 'hours': '24', 'color': '#ffd60a'}}
        widget = normalize(layout({'widgets': [old]}))['screens'][0]['widgets'][0]
        self.assertEqual(widget['type'], 'weather')
        self.assertEqual({k: widget['options'][k] for k in ('show', 'count', 'hours', 'color', 'forecast_font')},
                         {'show': 'forecast_hours', 'count': 4, 'hours': '24', 'color': '#ffd60a', 'forecast_font': '4x6'})

    def test_saved_file_is_upgraded_not_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'display.json')
            with open(path, 'w') as f:
                json.dump(layout({'name': 'Old', 'widgets': [
                    {'type': 'forecast', 'options': {'mode': 'days'}},
                    {'type': 'weather_details', 'options': {'field': 'sunset'}},
                ]}), f)
            widgets = LayoutStore(path).config['screens'][0]['widgets']
        self.assertEqual([(w['type'], w['options']['show']) for w in widgets],
                         [('weather', 'forecast_days'), ('weather', 'sunset')])
