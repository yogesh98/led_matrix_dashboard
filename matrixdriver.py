from matrixbase import MatrixBase
from components.clock import Clock
# from components.fonttest import FontTest
# from components.boundary import Boundary
from components.weather import Weather
from components.date import Date
import threading
import os

class MatrixDriver(MatrixBase):
    def __init__(self, *args, **kwargs):
        super(MatrixDriver, self).__init__(*args, **kwargs)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.queued_swap = True

        self.components = [
            # FontTest(0, 0, self.queue_swap)
            # Boundary(0, 0, 32, 32, self.queue_swap)
            Clock(8, 2, self.queue_swap),
            Date(0, 26, self.queue_swap),
            Weather(0, 34, self.queue_swap),
        ]

    def run(self):
        while True:
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

    def clear_frame(self):
        # for component in self.components:
        #     component.stop()
        self.offscreen_canvas.Clear()
        self.matrix.SwapOnVSync(self.offscreen_canvas)
