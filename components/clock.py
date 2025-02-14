
from components.basecomponent import BaseComponent
from rgbmatrix import graphics
import time
import copy

class Clock(BaseComponent):
    def __init__(self, pos_x, pos_y, swap_frame):
        super().__init__(pos_x, pos_y, 15, 21, swap_frame, 1)
        self.font = graphics.Font()
        self.font.LoadFont("fonts/8x13B.bdf")
        self.textColor = graphics.Color(255, 255, 255)
    
    def draw_frame(self, canvas):
        newCanvas = self.clear_area(canvas)
        graphics.DrawText(newCanvas, self.font, self.pos_x, self.pos_y + 10, self.textColor, str(self.data['hour']))
        graphics.DrawText(newCanvas, self.font, self.pos_x, self.pos_y + 21, self.textColor, str(self.data['minute']))
        return newCanvas
    
    def data_eq(self, data, newData):
        if data is None or newData is None:
            return False
        return (data['hour'] == newData['hour'] and data['minute'] == newData['minute'])
    
    def fetch_new_data(self):
        data = {'hour': 0, 'minute': 0}
        current_time = time.localtime()
        hour = current_time.tm_hour
        minute = current_time.tm_min
    
        hour = hour % 12
        if hour == 0:
            hour = 12
        
        data['hour'] = str(hour).zfill(2)
        data['minute'] = str(minute).zfill(2)
        return data


    