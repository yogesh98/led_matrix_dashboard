"""The components you can place on the display. See components/base.py to add one."""
from components import openweathermap
from components.box import Box
from components.clock import Clock, Time
from components.countdown import Countdown
from components.date import Date
from components.forecast import Forecast
from components.image import Image
from components.text import Text
from components.weather import Weather, WeatherDetails

# In the order the management page lists them
COMPONENTS = {c.type: c for c in (
    Clock(), Time(), Date(), Countdown(),
    Weather(), WeatherDetails(), Forecast(),
    Text(), Image(), Box(),
)}


def default_sources():
    """The shared data sources components read through RenderContext.data()"""
    return {'weather': openweathermap.WEATHER, 'forecast': openweathermap.FORECAST}
