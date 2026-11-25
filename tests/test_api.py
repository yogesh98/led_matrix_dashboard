import base64
import os
import tempfile
import unittest

from flask import Flask
from PIL import Image

import api
from layout import LayoutStore
from tests.helpers import FakeSource, context


class FakeMatrix:
    brightness = 100


class FakeDriver:
    """Just what the API uses of MatrixDriver, without a panel or a render thread"""

    def __init__(self, path):
        self.size = (64, 32)
        self.matrix = FakeMatrix()
        self.layout = LayoutStore(path)
        self.frame = Image.new('RGB', self.size, (10, 20, 30))
        self.showing = (self.layout.config['screens'][0], 4.25)
        self.shown = None

    def context(self, preview=False):
        return context(preview=preview, weather={'icon': '01d', 'temp': 70, 'wind_speed': 3})

    def show(self, screen_id):
        self.shown = screen_id

    def set_brightness(self, value):
        self.matrix.brightness = value


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.driver = FakeDriver(os.path.join(self.dir.name, 'display.json'))
        app = Flask(__name__)
        app.register_blueprint(api.bp)
        app.config['DRIVER'] = self.driver
        self.client = app.test_client()

    def tearDown(self):
        self.dir.cleanup()

    def test_state(self):
        data = self.client.get('/api/state').get_json()
        self.assertEqual(data['display'], {'width': 64, 'height': 32})
        self.assertEqual(data['config'], self.driver.layout.config)
        clock = next(c for c in data['components'] if c['type'] == 'clock')
        self.assertEqual((clock['thumbnail']['w'], clock['thumbnail']['h']), (16, 21))
        self.assertIn('8x13B', data['fonts'])

    def test_save(self):
        config = self.client.get('/api/state').get_json()['config']
        config['screens'][0]['name'] = 'Renamed'
        response = self.client.put('/api/config', json=config)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LayoutStore(self.driver.layout.path).config['screens'][0]['name'], 'Renamed')

        response = self.client.put('/api/config', json={'screens': []})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.get_json())

    def test_save_needs_json(self):
        # A web page on another site can't send JSON here without CORS allowing it
        response = self.client.put('/api/config', data='{"screens": []}', content_type='text/plain')
        self.assertEqual(response.status_code, 415)

    def test_render_skips_pixels_the_page_already_has(self):
        widgets = [{'id': 'w1', 'type': 'box', 'options': {'width': 3, 'height': 2}}]
        sprite = self.client.post('/api/render', json={'widgets': widgets}).get_json()['sprites']['w1']
        self.assertEqual((sprite['w'], sprite['h']), (3, 2))
        self.assertEqual(len(base64.b64decode(sprite['rgba'])), 3 * 2 * 4)
        again = self.client.post('/api/render', json={'widgets': widgets, 'known': {'w1': sprite['hash']}})
        self.assertNotIn('rgba', again.get_json()['sprites']['w1'])

    def test_render_reports_bad_widgets(self):
        sprites = self.client.post('/api/render', json={'widgets': [{'id': 'w1', 'type': 'nope'}]}).get_json()
        self.assertIn('error', sprites['sprites']['w1'])

    def test_live(self):
        data = self.client.get('/api/live').get_json()
        self.assertEqual(data['screen'], {'id': 'main', 'name': 'Main'})
        self.assertEqual(data['remaining'], 4.2)
        self.assertEqual(base64.b64decode(data['rgb'])[:3], bytes([10, 20, 30]))

    def test_show(self):
        self.assertEqual(self.client.post('/api/show', json={'screen_id': 'nope'}).status_code, 404)
        self.assertEqual(self.client.post('/api/show', json={'screen_id': 'main'}).status_code, 200)
        self.assertEqual(self.driver.shown, 'main')

    def test_brightness(self):
        self.assertEqual(self.client.put('/api/brightness', json={'value': 140}).get_json(), {'brightness': 100})
        self.assertEqual(self.client.put('/api/brightness', json={'value': '30'}).get_json(), {'brightness': 30})
        self.assertEqual(self.client.put('/api/brightness', json={}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
