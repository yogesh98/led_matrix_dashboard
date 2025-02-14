import threading
import time
import os

class BaseComponent(object):
    def __init__(self, pos_x, pos_y, size_x, size_y, swap_frame, sleep_interval = 1):
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.size_x = size_x - 1
        self.size_y = size_y - 1
        self.swap_frame = swap_frame
        self.data_updated = False
        self.data = None
        self.data = self.fetch_new_data()
        self.sleep_interval = sleep_interval

        # Start a background thread that periodically updates self.data.
        self._stop_thread = False
        self._thread = threading.Thread(target=self._update_data_loop, daemon=True)
        self._thread.start()
    
    def _update_data_loop(self):
        while not self._stop_thread:
            new_data = self.fetch_new_data()
            if(not self.data_eq(self.data, new_data)):
                # print(f"Thread {threading.current_thread().name} (PID: {os.getpid()}):\n\told data: {self.data}\n\tnew data: {new_data}\n")
                self.data = new_data
                self.data_updated = True
            
            time.sleep(self.sleep_interval)

    def stop(self):
        self._stop_thread = True
        self._thread.join()

    def get_frame(self, canvas):
        canvas = self.draw_frame(canvas)
        if self.data_updated:
            self.data_updated = False
            self.swap_frame()
        
        # return self.draw_boundary(canvas)
        return canvas

    
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