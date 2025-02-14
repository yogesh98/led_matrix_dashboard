from components.basecomponent import BaseComponent
from rgbmatrix import graphics
from PIL import Image
import os
import requests
from dotenv import load_dotenv

load_dotenv()

class Weather(BaseComponent):
    def __init__(self, pos_x, pos_y, swap_frame):
        super().__init__(pos_x, pos_y, 32, 32, swap_frame, 600)
        self.font = graphics.Font()
        self.font.LoadFont("fonts/6x10.bdf")
        self.degreeFont = graphics.Font()
        self.degreeFont.LoadFont("fonts/5x8.bdf")
        self.textColor = graphics.Color(255, 255, 255)
    
    def draw_frame(self, canvas):
        icon = Image.open('icons/' + self.data['icon'] + '.png')
        windIcon = Image.open('icons/wind.png')
        newCanvas = self.clear_area(canvas)
        newCanvas.SetImage(icon.convert('RGB'), self.pos_x, self.pos_y)
        newCanvas.SetImage(windIcon.convert('RGB'), self.pos_x, self.pos_y + 16)

        degreeFont = self.font
        xoffset_temp = 19
        xoffset_wind = 19
        yoffset_temp = 12
        yoffset_wind = 27
        if self.data['temp'] > 99:
            degreeFont = self.degreeFont
            xoffset_temp = 16
            yoffset_temp = 11

        if self.data['wind_speed'] > 99:
            xoffset_wind = 16
            yoffset_wind = 26

        temp_str = f" {self.data['temp']}" if int(self.data['temp']) < 10 else str(self.data['temp'])
        wind_speed_str = f" {self.data['wind_speed']}" if int(self.data['wind_speed']) < 10 else str(self.data['wind_speed'])

        graphics.DrawText(newCanvas, degreeFont, self.pos_x + xoffset_temp, self.pos_y + yoffset_temp, self.textColor, temp_str)
        graphics.DrawText(newCanvas, degreeFont, self.pos_x + xoffset_wind, self.pos_y + yoffset_wind, self.textColor, wind_speed_str)
        return newCanvas
    
    def data_eq(self, data, newData):
        return data['icon'] == newData['icon'] and data['temp'] == newData['temp'] and data['wind_speed'] == newData['wind_speed']
    
    def fetch_new_data(self):
        api_key = os.getenv('OPENWEATHERMAP_API_KEY')
        lat = os.getenv('LAT')
        lon = os.getenv('LON')
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
        
        response = requests.get(url)
        weather_data = response.json()
        
        icon = weather_data['weather'][0]['icon']
        temp = round(weather_data['main']['temp'])
        wind_speed = round(weather_data['wind']['speed'])
        
        data = {'icon': icon, 'temp': temp, 'wind_speed': wind_speed}
        return data




