
from components.basecomponent import BaseComponent
from rgbmatrix import graphics
import time

class Boundary(BaseComponent):
    def __init__(self, pos_x, pos_y, size_x, size_y, swap_frame):
        super().__init__(pos_x, pos_y, size_x, size_y, swap_frame, 1)
    
    def draw_frame(self, canvas):
        newCanvas = self.draw_boundary(canvas)
        return newCanvas
    
    def data_eq(self, data, newData):
        return True
    
    def fetch_new_data(self):
        return False

        


    