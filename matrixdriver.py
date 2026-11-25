import os
import threading
import time

from PIL import Image

import images
from components import default_sources
from components.base import RenderContext
from layout import LayoutStore
from matrixbase import MatrixBase
from renderer import Rotation, errors, render_screen


class MatrixDriver(MatrixBase):
    # Often enough for scrolling text. A frame only goes to the panel when it changed.
    fps = 20

    def __init__(self, *args, **kwargs):
        super(MatrixDriver, self).__init__(*args, **kwargs)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.size = (self.matrix.width, self.matrix.height)
        # Set up after MatrixBase has switched away from root, so the layout file
        # the management page saves is owned by the project's user
        self.layout = LayoutStore()
        # Uploaded images live next to the layout file
        images.library.directory = os.path.join(os.path.dirname(self.layout.path), 'images')
        self.sources = default_sources()
        self.rotation = Rotation()
        self.frame = Image.new('RGB', self.size)  # what the panel is showing
        self.showing = (None, 0.0)                # (screen, seconds left on it)
        self.keep_alive = True
        self._stopped = threading.Event()
        self._sent = None                         # (frame, brightness) last sent to the panel

    def run(self):
        super().run()
        try:
            while self.keep_alive:
                started = time.monotonic()
                try:
                    self.generate_frame()
                except Exception as e:
                    errors.report(f"Couldn't draw a frame: {type(e).__name__}: {e}")
                time.sleep(max(0.0, 1 / self.fps - (time.monotonic() - started)))
        finally:
            self._stopped.set()

    def context(self, preview=False):
        return RenderContext(sources=self.sources, preview=preview, display_size=self.size)

    def generate_frame(self):
        screen, left = self.rotation.current(self.layout.config['screens'])
        frame = render_screen(screen, self.context())
        self.frame = frame
        self.showing = (screen, left)
        # The panel applies brightness as pixels are set, so a new brightness needs the frame sent again
        sent = (frame.tobytes(), self.matrix.brightness)
        if sent != self._sent:
            self.offscreen_canvas.SetImage(frame)
            self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)
            self._sent = sent

    def show(self, screen_id):
        self.rotation.show(screen_id)

    def kill(self):
        self.keep_alive = False
        self._stopped.wait(timeout=2)  # let the frame being drawn finish, so it can't land after Clear()
        self.matrix.Clear()
        time.sleep(1)
