import io
import os
import tempfile
import unittest
from datetime import datetime

from flask import Flask
from PIL import Image

import api
import images
from images import ImageLibrary
from layout import normalize_widget
from renderer import render_widget
from tests.helpers import context, lit
from tests.test_api import FakeDriver


def png(size, color=(255, 0, 0, 255)):
    out = io.BytesIO()
    Image.new('RGBA', size, color).save(out, format='PNG')
    return out.getvalue()


def gif(frames, durations):
    out = io.BytesIO()
    images_ = [Image.new('RGB', (8, 4), color) for color in frames]
    images_[0].save(out, format='GIF', save_all=True, append_images=images_[1:], duration=durations, loop=0)
    return out.getvalue()


class TempLibrary(unittest.TestCase):
    """Points the shared image library at a scratch folder for the test"""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.saved_directory = images.library.directory
        images.library.directory = self.dir.name
        self.library = images.library

    def tearDown(self):
        images.library.directory = self.saved_directory
        self.dir.cleanup()


class LibraryTest(TempLibrary):
    def test_uploads_are_shrunk_and_listed_before_the_icons(self):
        info = self.library.save(png((300, 150)), 'My Cat!.PNG')
        self.assertEqual((info['width'], info['height'], info['frames']), (128, 64, 1))
        self.assertEqual(info['name'], 'my cat')
        listed = self.library.list()
        self.assertEqual(listed[0]['id'], info['id'])
        self.assertIn('icons/01d', [i['id'] for i in listed if i['builtin']])

    def test_small_pixel_art_is_kept_as_it_is(self):
        info = self.library.save(png((16, 8)), 'sprite.png')
        self.assertEqual((info['width'], info['height']), (16, 8))

    def test_animations_keep_their_frames_and_timing(self):
        info = self.library.save(gif([(255, 0, 0), (0, 255, 0), (0, 0, 255)], [100, 200, 300]), 'blink.gif')
        self.assertEqual(info['frames'], 3)
        asset = self.library.asset(info['id'])
        self.assertEqual(asset.durations, [100, 200, 300])
        colors = [asset.frame(8, at_ms=t).getpixel((0, 0))[:3] for t in (0, 150, 400, 650)]
        self.assertEqual(colors, [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 0)])

    def test_rejects_files_that_arent_images(self):
        with self.assertRaises(ValueError):
            self.library.save(b'not an image', 'notes.png')

    def test_ids_cant_reach_outside_the_folders(self):
        for bad in ('uploads/../x', '../display', 'uploads/a.b', 'uploads/', 'other/x', None):
            self.assertIsNone(self.library.path(bad), bad)

    def test_delete_only_removes_uploads(self):
        info = self.library.save(png((4, 4)), 'dot.png')
        self.assertTrue(self.library.delete(info['id']))
        self.assertFalse(os.path.exists(self.library.path(info['id'])))
        self.assertFalse(self.library.delete(info['id']))
        self.assertFalse(self.library.delete('icons/01d'))


class ImageComponentTest(TempLibrary):
    def widget(self, **options):
        return normalize_widget({'type': 'image', 'options': options})

    def test_icons_are_drawn_in_the_components_color(self):
        image, _ = render_widget(self.widget(image='icons/01d', color='#ff0000'), context())
        colors = {p for p in zip(*[iter(image.tobytes())] * 4) if p[3]}
        self.assertEqual(colors, {(255, 0, 0, 255)})

    def test_height_follows_the_width(self):
        info = self.library.save(png((40, 20)), 'wide.png')
        image, _ = render_widget(self.widget(image=info['id'], width=30), context())
        self.assertEqual(image.size, (30, 15))
        self.assertEqual(lit(image), 30 * 15)

    def test_missing_images_say_so(self):
        image, note = render_widget(self.widget(image='uploads/gone-1234'), context())
        self.assertEqual(lit(image), 0)
        self.assertIn('missing', note)

    def test_animations_play_on_the_display_but_not_in_the_editor(self):
        info = self.library.save(gif([(255, 0, 0), (0, 255, 0)], [500, 500]), 'blink.gif')
        widget = self.widget(image=info['id'], width=8)
        first = lambda ctx: render_widget(widget, ctx)[0].getpixel((0, 0))[:3]
        a, b = datetime(2026, 1, 1, 0, 0, 0), datetime(2026, 1, 1, 0, 0, 0, 600000)
        self.assertNotEqual(first(context(now=a)), first(context(now=b)))
        self.assertEqual(first(context(now=a, preview=True)), first(context(now=b, preview=True)))


class ImageApiTest(TempLibrary):
    def setUp(self):
        super().setUp()
        self.driver = FakeDriver(os.path.join(self.dir.name, 'display.json'))
        app = Flask(__name__)
        app.register_blueprint(api.bp)
        app.config['DRIVER'] = self.driver
        self.client = app.test_client()

    def upload(self, data, name='cat.png', content_type='application/octet-stream'):
        return self.client.post('/api/images', data=data, content_type=content_type, headers={'X-Filename': name})

    def test_upload_list_get_and_delete(self):
        response = self.upload(png((200, 50)))
        self.assertEqual(response.status_code, 201)
        image = response.get_json()['image']
        self.assertEqual(image['fit_width'], 64)  # 128x32 after shrinking; 64 wide fits the display

        listed = self.client.get('/api/images').get_json()['images']
        self.assertEqual(listed[0]['id'], image['id'])

        file = self.client.get(f"/api/images/file/{image['id']}")
        self.assertEqual(file.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(file.data)).size, (128, 32))
        file.close()

        self.assertEqual(self.client.delete(f"/api/images/{image['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/images/file/{image['id']}").status_code, 404)
        self.assertEqual(self.client.delete('/api/images/icons/01d').status_code, 404)

    def test_upload_needs_raw_bytes(self):
        # A form upload could come from a page on another site, so it isn't accepted
        response = self.client.post('/api/images', data={'file': (io.BytesIO(png((4, 4))), 'x.png')},
                                    content_type='multipart/form-data')
        self.assertEqual(response.status_code, 415)

    def test_upload_rejects_non_images(self):
        response = self.upload(b'hello')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.get_json())


if __name__ == '__main__':
    unittest.main()
