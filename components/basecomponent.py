import threading
import time
import os

class BaseComponent(object):
    # After a failed fetch, try again after this many seconds (or sleep_interval, if shorter)
    retry_interval = 60

    def __init__(self, pos_x, pos_y, size_x, size_y, swap_frame, sleep_interval = 1):
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.size_x = size_x - 1
        self.size_y = size_y - 1
        self.swap_frame = swap_frame
        self.sleep_interval = sleep_interval
        self.data_updated = False
        # None if the first fetch failed (e.g. network not up yet at boot); the loop below keeps trying
        self.data = self._try_fetch()

        # Start a background thread that periodically updates self.data.
        self._stop_thread = False
        self._thread = threading.Thread(target=self._update_data_loop, daemon=True)
        self._thread.start()

    def _try_fetch(self):
        # An uncaught error here used to end the update thread for good, freezing the
        # component on its last value until restart. Log it and return None instead.
        try:
            return self.fetch_new_data()
        except Exception as e:
            print(f"{type(self).__name__}: fetch failed: {type(e).__name__}: {e}", flush=True)
            return None

    def _update_data_loop(self):
        while not self._stop_thread:
            new_data = self._try_fetch()
            if new_data is None:
                # Keep showing the last good data and retry sooner than the normal interval
                time.sleep(min(self.sleep_interval, self.retry_interval))
                continue

            if self.data is None or not self.data_eq(self.data, new_data):
                # print(f"Thread {threading.current_thread().name} (PID: {os.getpid()}):\n\told data: {self.data}\n\tnew data: {new_data}\n")
                self.data = new_data
                self.data_updated = True

            time.sleep(self.sleep_interval)

    def stop(self):
        self._stop_thread = True
        # self._thread.join()

    def get_frame(self, canvas):
        if self.data is None:
            # Nothing fetched yet: leave this area blank rather than crash the render loop
            canvas = self.clear_area(canvas)
        else:
            canvas = self.draw_frame(canvas)
        if self.data_updated:
            self.data_updated = False
            self.swap_frame()
        if self._stop_thread:
            canvas.Clear()
            self.swap_frame()
        # return self.draw_boundary(canvas)
        return canvas

    def refresh_frame(self):
        self.data_updated = True
        
    def draw_frame(self, canvas):
        raise Exception("getFrame needs to be overwridden - after the frame is drawn using data make data_updated as False")
    
    def data_eq(self, data, newData):
        raise Exception("data_eq function must be overridden")
    
    def fetch_new_data(self):
        raise Exception("fetch_new_data must be overridden")
    
    def draw_boundary(self, canvas):
        # Draw top boundary
        for x in range(self.pos_x, self.pos_x + self.size_x + 1):
            if(x != 0):
                canvas.SetPixel(x, self.pos_y, 255, 255, 255)

        # Draw bottom boundary
        for x in range(self.pos_x, self.pos_x + self.size_x + 1):
            canvas.SetPixel(x, self.pos_y + self.size_y, 255, 255, 255)

        # Draw left boundary
        for y in range(self.pos_y, self.pos_y + self.size_y + 1):
            canvas.SetPixel(self.pos_x, y, 255, 255, 255)

        # Draw right boundary
        for y in range(self.pos_y, self.pos_y + self.size_y + 1):
            canvas.SetPixel(self.pos_x + self.size_x, y, 255, 255, 255)

        canvas.SetPixel(self.pos_x, self.pos_y, 255, 0, 0)
        return canvas
    
    def clear_area(self, canvas):
        for x in range(self.pos_x, self.pos_x + self.size_x + 1):
            for y in range(self.pos_y, self.pos_y + self.size_y + 1):
                canvas.SetPixel(x, y, 0, 0, 0)
        
        return canvas