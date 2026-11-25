"""Weather data for the weather components, from OpenWeatherMap's free APIs (current
weather, and the 5 day / 3 hour forecast). Needs OPENWEATHERMAP_API_KEY, LAT and LON in
.env (see README)."""
import os
from datetime import datetime, time, timedelta, timezone

import requests
from dotenv import load_dotenv
from PIL import Image

import bdf
from components.sources import PollingSource

load_dotenv()

ICON_DIR = os.path.join(bdf.ROOT, 'icons')
_icons = {}
SAMPLE_NOTE = "Showing sample weather: none has loaded yet. Check the .env settings (see README)."


def icon(name):
    """icons/<name>.png as a mask (the icons are white on black), or None if there's no such icon"""
    if name not in _icons:
        try:
            _icons[name] = Image.open(os.path.join(ICON_DIR, os.path.basename(name) + '.png')).convert('L')
        except OSError:
            print(f"Weather: no icon icons/{name}.png", flush=True)
            _icons[name] = None
    return _icons[name]


def get(endpoint):
    api_key = os.getenv('OPENWEATHERMAP_API_KEY')
    url = f"http://api.openweathermap.org/data/2.5/{endpoint}"
    params = {'lat': os.getenv('LAT'), 'lon': os.getenv('LON'), 'appid': api_key, 'units': 'imperial'}
    try:
        # Without a timeout, a connection that drops mid-request can block this thread forever
        response = requests.get(url, params=params, timeout=10)
    except requests.RequestException as e:
        # requests includes the full URL in its errors; keep the API key out of the logs
        message = str(e).replace(api_key, "<api key>") if api_key else str(e)
        raise RuntimeError(f"weather request failed: {message}") from None
    if response.status_code != 200:
        # e.g. 429 rate limit or 5xx; the body is a short JSON error from OpenWeatherMap
        raise RuntimeError(f"OpenWeatherMap returned HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


class WeatherSource(PollingSource):
    """The weather now. Also keeps today's highest and lowest temperatures seen, since the
    free forecast only covers the rest of the day."""
    interval = 900

    def __init__(self):
        super().__init__()
        self._observed = None

    def fetch(self):
        print("Fetching weather data", flush=True)
        data = get('weather')
        temp = round(data['main']['temp'])
        today = datetime.now().date().isoformat()
        seen = self._observed
        if seen is None or seen['date'] != today:
            seen = {'date': today, 'high': temp, 'low': temp}
        else:
            seen = {'date': today, 'high': max(seen['high'], temp), 'low': min(seen['low'], temp)}
        self._observed = seen
        main, wind, sun = data['main'], data.get('wind', {}), data.get('sys', {})
        return {
            'icon': data['weather'][0]['icon'],
            'temp': temp,
            'wind_speed': round(wind.get('speed', 0)),
            'wind_deg': wind.get('deg'),
            'feels_like': round(main.get('feels_like', main['temp'])),
            'humidity': main.get('humidity'),
            'sunrise': sun.get('sunrise'),
            'sunset': sun.get('sunset'),
            'observed': seen,
        }


def summarize_forecast(data):
    """OpenWeatherMap's 3-hourly forecast as {'hours': [...], 'days': [...]}, in the
    location's own time zone. A day's icon is the one forecast nearest 1pm."""
    offset = data.get('city', {}).get('timezone', 0)
    hours, days = [], {}
    for entry in data['list']:
        local = datetime.fromtimestamp(entry['dt'] + offset, timezone.utc)
        main = entry['main']
        code = entry['weather'][0]['icon']
        hours.append({'time': entry['dt'], 'hour': local.hour, 'temp': round(main['temp']), 'icon': code})
        day = days.setdefault(local.date().isoformat(), {
            'date': local.date().isoformat(), 'high': main['temp_max'], 'low': main['temp_min'],
            'icon': code[:2] + 'd', 'distance': 24,
        })
        day['high'] = max(day['high'], main['temp_max'])
        day['low'] = min(day['low'], main['temp_min'])
        if abs(local.hour - 13) < day['distance']:
            day['distance'] = abs(local.hour - 13)
            day['icon'] = code[:2] + 'd'
    return {
        'hours': hours,
        'days': [{'date': d['date'], 'high': round(d['high']), 'low': round(d['low']), 'icon': d['icon']}
                 for d in sorted(days.values(), key=lambda d: d['date'])],
    }


class ForecastSource(PollingSource):
    interval = 1800

    def fetch(self):
        print("Fetching the weather forecast", flush=True)
        return summarize_forecast(get('forecast'))


WEATHER = WeatherSource()
FORECAST = ForecastSource()


def sample_weather(now):
    day = now.date()
    return {
        'icon': '02d', 'temp': 72, 'wind_speed': 8, 'wind_deg': 45, 'feels_like': 70, 'humidity': 45,
        'sunrise': datetime.combine(day, time(6, 52)).timestamp(),
        'sunset': datetime.combine(day, time(17, 1)).timestamp(),
        'observed': {'date': day.isoformat(), 'high': 75, 'low': 60},
    }


def sample_forecast(now):
    icons = ['02d', '01d', '10d', '03d', '13d', '01d']
    start = now.replace(minute=0, second=0, microsecond=0)
    return {
        'hours': [{'time': (start + timedelta(hours=3 * i)).timestamp(), 'hour': (start + timedelta(hours=3 * i)).hour,
                   'temp': 72 - 3 * i, 'icon': icons[i % len(icons)]} for i in range(1, 9)],
        'days': [{'date': (now.date() + timedelta(days=i)).isoformat(), 'high': 75 - 2 * i, 'low': 60 - i,
                  'icon': icons[i]} for i in range(6)],
    }


def data_or_sample(ctx, name):
    """(data, note): the source's data, or sample data in the editor if there's none yet
    (data is None on the display then, so the component stays blank)"""
    data = ctx.data(name)
    if data is not None:
        return data, None
    if not ctx.preview:
        return None, None
    return (sample_weather if name == 'weather' else sample_forecast)(ctx.now), SAMPLE_NOTE


def today_high_low(ctx, weather=None, forecast=None):
    """(high, low) for today: the forecast for the rest of the day, plus what's been seen so
    far and right now. None if there's no data."""
    today = ctx.now.date().isoformat()
    temps = []
    if weather:
        temps.append(weather['temp'])
        seen = weather.get('observed')
        if seen and seen['date'] == today:
            temps += [seen['high'], seen['low']]
    for day in (forecast or {}).get('days', []):
        if day['date'] == today:
            temps += [day['high'], day['low']]
    return (max(temps), min(temps)) if temps else None


def compass(degrees):
    return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][round(degrees / 45) % 8]
