
from components.basecomponent import BaseComponent
from rgbmatrix import graphics
import time

class FontTest(BaseComponent):
    def __init__(self, pos_x, pos_y, swap_frame):
        self.fonts = [    
            # "fonts/4x6.bdf",
            # "fonts/5x7.bdf",
            # "fonts/5x8.bdf",
            # "fonts/6x9.bdf",
            # "fonts/6x10.bdf",
            # "fonts/6x12.bdf",
            # "fonts/6x13.bdf",
            # "fonts/6x13B.bdf",
            # "fonts/6x13O.bdf",
            # "fonts/7x13.bdf",
            # "fonts/7x13B.bdf",
            # "fonts/7x13O.bdf",
            # "fonts/7x14.bdf",
            # "fonts/7x14B.bdf",
            # "fonts/8x13.bdf",
            "fonts/8x13B.bdf",
            # "fonts/8x13O.bdf",
            # "fonts/9x15.bdf",
            # "fonts/9x15B.bdf",
            # "fonts/9x18.bdf",
            # "fonts/9x18B.bdf",
            # "fonts/10x20.bdf",
            # "fonts/clR6x12.bdf",
            # "fonts/helvR12.bdf",
            # "fonts/texgyre-27.bdf",
            # "fonts/tom-thumb.bdf"
        ]
        super().__init__(pos_x, pos_y, 64, 32, swap_frame, 10)
        self.font = graphics.Font()
        self.textColor = graphics.Color(255, 255, 255)
    
    def draw_frame(self, canvas):
        newCanvas = self.clear_area(canvas)
        self.font.LoadFont(self.fonts[self.data])

        graphics.DrawText(newCanvas, self.font, self.pos_x, self.pos_y + self.size_y, self.textColor, "1234567890:")

        return newCanvas
    
    def data_eq(self, data, newData):
        return data == newData
    
    def fetch_new_data(self):
        old_data = self.data
        if(old_data is None or old_data == len(self.fonts)-1):
            data = 0
        else:
            data = old_data + 1
        
        print(self.fonts[data])
        return data


        


    