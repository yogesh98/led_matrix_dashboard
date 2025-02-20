from matrixbase import MatrixBase
from components.clock import Clock
# from components.fonttest import FontTest
# from components.boundary import Boundary
from components.weather import Weather
from components.date import Date
import time

class MatrixDriver(MatrixBase):
    def __init__(self, *args, **kwargs):
        super(MatrixDriver, self).__init__(*args, **kwargs)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.queued_swap = True
        self.keep_alive = True

        self.components = [
            Clock(8, 1, self.queue_swap),
            Date(0, 24, self.queue_swap),
            Weather(32, 0, self.queue_swap),
        ]

    def run(self):
        super().run()
        while self.keep_alive:
            self.generate_frame()
    
    def generate_frame(self):
        for component in self.components:
            self.offscreen_canvas = component.get_frame(self.offscreen_canvas)
        self.swap_frame()

    def queue_swap(self):
        # print(f"Thread {threading.current_thread().name} (PID: {os.getpid()}): queued_swap")
        self.queued_swap = True

    def swap_frame(self):
        if self.queued_swap:
            # print(f"Thread {threading.current_thread().name} (PID: {os.getpid()}): swapping")
            self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)
            self.queued_swap = False
    
    def set_brightness(self, value):
        super().set_brightness(value)
        for component in self.components:
            component.refresh_frame()
        self.queue_swap()

    def kill(self):
        for component in self.components:
            component.stop()
        self.keep_alive = False
        self.matrix.Clear()
        time.sleep(1)

