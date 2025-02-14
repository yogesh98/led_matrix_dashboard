from components.basecomponent import BaseComponent
from rgbmatrix import graphics
import time
import copy
import datetime

class Date(BaseComponent):
    def __init__(self, pos_x, pos_y, swap_frame):
        super().__init__(pos_x, pos_y, 32, 7, swap_frame, 30)
        self.font = graphics.Font()
        self.font.LoadFont("fonts/6x10.bdf")
        self.textColor = graphics.Color(255, 255, 255)
    
    def draw_frame(self, canvas):
        newCanvas = self.clear_area(canvas)
        graphics.DrawText(newCanvas, self.font, self.pos_x, self.pos_y + 7, self.textColor, self.data['day'])
        graphics.DrawText(newCanvas, self.font, self.pos_x + 20, self.pos_y + 7, self.textColor, self.data['date'])
        # newCanvas = self.draw_boundary(newCanvas)
        return newCanvas
    
    def data_eq(self, data, newData):
        if data is None or newData is None:
            return False
        return (data['day'] == newData['day'] and data['date'] == newData['date'] and data['month'] == newData['month'])
    
    def fetch_new_data(self):
        current_time = datetime.datetime.now()
        day = current_time.strftime('%a')
        month = current_time.strftime('%b')
        date = current_time.strftime('%d')
        
        data = {'day': day, 'month': month, 'date': date}
        # print(data)
        return data


