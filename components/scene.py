"""Scenes: animated pixel-art backgrounds that fill the display.

A scene is a little landscape that follows the real weather and time of day: the sky
changes color through sunrise, day, sunset and night, the sun sets behind the hills, the
moon shows its actual phase, stars twinkle, and clouds, rain, snow, fog and lightning come
and go with the weather. Each theme adds its own life: petals drifting off a cherry tree,
ripples and a cabin's chimney smoke on a mountain lake, a city's windows lighting up, a
waterfall with a rainbow in its spray and the northern lights above it. The
prebuilt screens in screens.py put a clock and the temperature on top.

Everything moves with the clock (ctx.now), not a frame counter, so the editor and the
display agree on what a moment looks like. The parts that barely change (sky, scenery,
sun or moon) are drawn once and cached; each frame only adds what moves, so it stays cheap
enough for a Pi at 20 frames a second.
"""
import math
from datetime import datetime, timezone

from PIL import Image, ImageChops

from components.base import Component, Option
from components.openweathermap import data_or_sample

# ---------- Small helpers ----------


def clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


def mix(a, b, t):
    """The color t of the way from a to b"""
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def scale(color, factors):
    """color with each channel multiplied, e.g. by the light falling on it"""
    return tuple(int(clamp(c * f, 0, 255)) for c, f in zip(color, factors))


def hash01(*args):
    """A repeatable pseudo-random number in [0, 1) for any tuple of integers"""
    h = 2166136261
    for a in args:
        h = ((h ^ (int(a) & 0xffffffff)) * 16777619) & 0xffffffff
    h ^= h >> 15
    h = (h * 0x2c1b3c6d) & 0xffffffff
    h ^= h >> 12
    h = (h * 0x297a2d39) & 0xffffffff
    h ^= h >> 15
    return h / 4294967296


def noise(x, y, size, seed=0):
    """Smooth value noise in [0, 1): blobs about `size` pixels across"""
    x, y = x / size, y / size
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = hash01(x0, y0, seed), hash01(x0 + 1, y0, seed)
    c, d = hash01(x0, y0 + 1, seed), hash01(x0 + 1, y0 + 1, seed)
    top = a + (b - a) * fx
    return top + (c + (d - c) * fx - top) * fy


def keyframes(frames, s):
    """Interpolates [(s, values), ...] (s ascending) at s"""
    if s <= frames[0][0]:
        return frames[0][1]
    for (s0, v0), (s1, v1) in zip(frames, frames[1:]):
        if s <= s1:
            t = (s - s0) / (s1 - s0)
            return tuple(a + (b - a) * t for a, b in zip(v0, v1))
    return frames[-1][1]


def line(x0, y0, x1, y1):
    """The pixels from (x0, y0) to (x1, y1)"""
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    return [(round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)) for i in range(steps + 1)]


class Pixels:
    """Pixel access with blending and bounds checks, over an RGBA image"""

    def __init__(self, image):
        self.image = image
        self.w, self.h = image.size
        self.px = image.load()

    def get(self, x, y):
        return self.px[x, y][:3]

    def put(self, x, y, color, alpha=1.0):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h and alpha > 0:
            if alpha >= 1:
                self.px[x, y] = (*color[:3], 255)
            else:
                self.px[x, y] = (*mix(self.px[x, y][:3], color, alpha), 255)

    def add(self, x, y, color, amount=1.0):
        """Adds light, like a glow"""
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h and amount > 0:
            r, g, b = self.px[x, y][:3]
            self.px[x, y] = (min(255, int(r + color[0] * amount)), min(255, int(g + color[1] * amount)),
                             min(255, int(b + color[2] * amount)), 255)


def draw_map(px, x0, y0, rows, palette):
    """Draws a little pixel map: each character is a palette key, others are see-through"""
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch in palette:
                px.put(x0 + dx, y0 + dy, palette[ch])


# ---------- Weather and time of day ----------

# What each OpenWeatherMap icon code means for a scene: (condition, cloud cover, gloom)
CONDITIONS = {
    '01': ('clear', 0.0, 0.0),
    '02': ('clouds', 0.3, 0.0),
    '03': ('clouds', 0.55, 0.15),
    '04': ('clouds', 0.85, 0.5),
    '09': ('rain', 0.9, 0.65),
    '10': ('rain', 0.9, 0.6),
    '11': ('storm', 1.0, 0.85),
    '13': ('snow', 0.85, 0.45),
    '50': ('fog', 0.3, 0.5),
}
WEATHER_CHOICES = [
    ('live', 'Follow the weather'),
    ('01', 'Always clear'),
    ('03', 'Cloudy'),
    ('10', 'Rain'),
    ('11', 'Thunderstorm'),
    ('13', 'Snow'),
    ('50', 'Fog'),
]
# Where the sun is, roughly: 1 is daytime, 0 is sunrise or sunset, -1 is full night
TIME_CHOICES = [
    ('live', 'Follow the time'),
    ('1', 'Day'),
    ('0', 'Sunset'),
    ('-0.45', 'Dusk'),
    ('-1', 'Night'),
]
DEFAULT_SUNRISE, DEFAULT_SUNSET = 7 * 60, 17 * 60 + 30   # minutes after midnight, until weather loads
TWILIGHT = 50  # minutes from sunrise or sunset to full day or night


def minutes(dt):
    return dt.hour * 60 + dt.minute + dt.second / 60


def sun_phase(now, weather):
    """1 in the day, 0 at sunrise and sunset, -1 at night, smoothly in between"""
    rise, sset = DEFAULT_SUNRISE, DEFAULT_SUNSET
    if weather and weather.get('sunrise') and weather.get('sunset'):
        rise = minutes(datetime.fromtimestamp(weather['sunrise']))
        sset = minutes(datetime.fromtimestamp(weather['sunset']))
    m = minutes(now)
    return clamp(min(m - rise, sset - m) / TWILIGHT, -1, 1)


def moon_phase(now):
    """0 new moon, 0.25 first quarter, 0.5 full, 0.75 last quarter"""
    known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc).timestamp()
    return ((now.timestamp() - known_new) / 86400 / 29.530588853) % 1


class Env:
    """Everything a scene needs to know about this moment"""

    def __init__(self, now, weather, opts):
        self.t = now.timestamp()
        code = opts['weather'] if opts['weather'] != 'live' else ((weather or {}).get('icon') or '01d')[:2]
        self.condition, self.clouds, self.gloom = CONDITIONS.get(code, CONDITIONS['01'])
        self.heavy = code in ('10', '11')  # steady rain, not just showers
        self.s = float(opts['time']) if opts['time'] != 'live' else sun_phase(now, weather)
        self.wind = clamp((weather or {}).get('wind_speed', 6) / 25, 0, 1.5)
        self.temp = (weather or {}).get('temp', 60)
        self.moon = moon_phase(now)
        self.night = clamp(-self.s * 1.6 - 0.1)                  # 0 by day, 1 when it's fully dark
        self.starry = self.night * clamp(1 - self.clouds * 1.15)  # stars hide behind clouds
        self.lights_on = clamp(-self.s * 1.5 + 0.2)               # windows and lanterns
        self.light = ambient(self.s, self.gloom)                  # for things drawn each frame


SKY = [  # (sun phase, (top r, g, b, horizon r, g, b))
    (-1.0, (0, 0, 8, 6, 8, 30)),
    (-0.45, (6, 4, 30, 64, 26, 74)),
    (0.0, (28, 30, 96, 214, 96, 52)),
    (0.45, (34, 92, 186, 214, 178, 150)),
    (1.0, (24, 104, 212, 136, 194, 240)),
]
AMBIENT = [  # (sun phase, light on the scenery as r, g, b multipliers)
    (-1.0, (0.22, 0.25, 0.44)),
    (-0.45, (0.4, 0.34, 0.56)),
    (0.0, (1.0, 0.78, 0.66)),
    (0.45, (1.0, 0.95, 0.9)),
    (1.0, (1.0, 1.0, 1.0)),
]


def sky_colors(s, gloom):
    """(top, horizon) colors of the sky, grayed and darkened by bad weather"""
    v = keyframes(SKY, s)
    top, horizon = v[:3], v[3:]
    if gloom:
        def gray(c, keep):
            level = sum(c) / 3 * keep
            return mix(c, (level, level, level * 1.1), gloom)
        top, horizon = gray(top, 0.9), gray(horizon, 0.75 - 0.25 * gloom)
    return tuple(map(int, top)), tuple(map(int, horizon))


def ambient(s, gloom):
    light = keyframes(AMBIENT, s)
    dim = 1 - 0.35 * gloom
    level = sum(light) / 3
    return tuple((c + (level - c) * gloom * 0.6) * dim for c in light)


# ---------- Themes ----------


class Layout:
    """A theme's picture for one display size. scenery is RGBA in daylight colors and is
    transparent where the sky shows; the rest are spots the animation uses."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.scenery = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.horizon = h - 4            # where the sky meets the land (for the sky gradient)
        self.water = None               # first row of water, which reflects what's above it
        self.surface = [h - 4] * w      # where rain and snow land, per column
        self.sun = (w // 2, h // 3, h)  # x, y when high, y when it has set
        self.lights = []                # (x, y, color, glow): lit as it gets dark


class Theme:
    name = None
    label = None

    def build(self, w, h):
        raise NotImplementedError

    def frozen(self, lay):
        """The scenery after it snows"""
        return snow_cover(lay.scenery, lay.water)

    def sky(self, px, sky, env, lay, body):
        """Draws what moves in this theme's sky, behind clouds and scenery (sky[x, y] is
        true where the sky shows)"""

    def animate(self, px, env, lay):
        """Draws what moves in this theme, in front of the scenery"""


def snow_cover(scenery, water=None):
    """Whitens the top edge of everything in the scenery (above any water), as if it snowed"""
    w, h = scenery.size
    px = scenery.load()
    out = scenery.copy()
    opx = out.load()
    for x in range(w):
        for y in range(water if water is not None else h):
            if px[x, y][3] and (y == 0 or not px[x, y - 1][3]):
                opx[x, y] = (*mix(px[x, y][:3], (225, 232, 245), 0.85), 255)
                if y + 1 < h and px[x, y + 1][3] and hash01(x, y, 77) < 0.45:
                    opx[x, y + 1] = (*mix(px[x, y + 1][:3], (200, 210, 230), 0.5), 255)
    return out


class Blossom(Theme):
    """A cherry tree in bloom, a torii gate and a stone lantern; petals drift on the wind"""
    name = 'blossom'
    label = 'Cherry blossom'

    PINKS = [(120, 18, 62), (186, 40, 96), (236, 84, 140), (255, 140, 182), (255, 206, 222)]
    TORII = [
        'K.........K',
        'KKKKKKKKKKK',
        '.RRRRRRRRR.',
        '..D..R..D..',
        'RRRRRRRRRRR',
        '..R.....R..',
        '..R.....R..',
        '..R.....R..',
        '..R.....R..',
        '.SSS...SSS.',
    ]
    LANTERN = ['.s.', 'sss', 'sLs', '.s.', '.s.', 'SSS']

    def build(self, w, h):
        lay = Layout(w, h)
        px = Pixels(lay.scenery)
        ground = h - 4
        lay.horizon = ground

        def surface(x):
            hill = 3 * max(0.0, 1 - ((x - 2) / 12) ** 2)           # a hill on the left
            mound = 1.5 * max(0.0, 1 - ((x - (w - 11)) / 9) ** 2)  # under the tree
            return ground - int(round(hill + mound))

        lay.surface = [surface(x) for x in range(w)]
        # Grass, with lighter tufts and fallen petals
        for x in range(w):
            top = lay.surface[x]
            for y in range(top, h):
                depth = y - top
                color = (44, 118, 48) if depth == 0 else (28, 82, 38) if depth < 2 else (17, 54, 28)
                if depth <= 1 and hash01(x, y, 1) < 0.18:
                    color = (74, 150, 62)
                px.put(x, y, color)
            if hash01(x, 3) < (0.55 if x > w - 26 else 0.12):
                px.put(x, top + (hash01(x, 4) < 0.5), self.PINKS[3 if hash01(x, 5) < 0.5 else 2])

        # A small flowering bush on the hill
        for y in range(ground - 8, ground):
            for x in range(0, 9):
                d = math.hypot((x - 3.5) / 5, (y - (ground - 4)) / 3.2)
                if d + (noise(x, y, 2, 9) - 0.5) * 0.5 < 0.85:
                    light = clamp(0.55 - (y - (ground - 7)) * 0.08 + (noise(x, y, 1.5, 11) - 0.5) * 0.7)
                    px.put(x, y, self.PINKS[1 + int(light * 3.99)])

        gate_x = int(w * 0.36)
        draw_map(px, gate_x, ground - 10, self.TORII,
                 {'K': (34, 22, 24), 'R': (214, 40, 30), 'D': (150, 26, 22), 'S': (90, 90, 96)})
        lantern_x = gate_x + 13
        draw_map(px, lantern_x, ground - 6, self.LANTERN, {'s': (128, 126, 120), 'S': (96, 94, 92), 'L': (70, 60, 40)})
        lay.lights.append((lantern_x + 1, ground - 4, (255, 170, 70), True))

        # The cherry tree: trunk and branches, then the canopy around them
        tx = w - 11
        bark, shade = (78, 42, 36), (46, 24, 22)
        for y in range(ground - 13, ground + 1):
            width = 3 if y > ground - 6 else 2
            for dx in range(width):
                px.put(tx - 1 + dx, y, shade if dx == width - 1 else bark)
        for x0, y0, x1, y1 in ((tx - 1, ground - 9, tx - 8, ground - 15), (tx + 1, ground - 10, tx + 6, ground - 16),
                               (tx, ground - 12, tx - 2, ground - 21)):
            for x, y in line(x0, y0, x1, y1):
                px.put(x, y, bark)

        blobs = [(tx - 1, ground - 17, 8.5), (tx - 9, ground - 15, 6), (tx + 7, ground - 16, 6.5),
                 (tx - 5, ground - 23, 6.5), (tx + 5, ground - 24, 6), (tx, ground - 28, 5.5),
                 (tx - 13, ground - 11, 3.2), (tx + 10, ground - 9, 3.5)]
        for y in range(h):
            for x in range(w):
                best, normal = -9.0, (0.0, 0.0)
                for cx, cy, r in blobs:
                    dx, dy = (x - cx) / r, (y - cy) / r
                    cover = 1 - math.hypot(dx, dy)
                    if cover > best:
                        best, normal = cover, (dx, dy)
                if best + (noise(x, y, 2.2, 21) - 0.5) * 0.55 < 0.08:
                    if best > -0.2 and hash01(x, y, 23) < 0.07:  # a few stray blossoms by the edge
                        px.put(x, y, self.PINKS[3])
                    continue
                if best > 0.25 and noise(x, y, 1.6, 25) < 0.16:
                    continue  # a gap where the branches show through
                lit = -0.6 * normal[0] - 0.8 * normal[1]  # light from the upper left
                level = clamp(0.48 + 0.3 * lit + 0.6 * (noise(x, y, 2.5, 27) - 0.5) - 0.15 * best)
                px.put(x, y, self.PINKS[int(level * 4.99)])

        lay.sun = (int(w * 0.47), 13, ground + 3)
        lay.tree = (tx - 14, tx + 12, ground - 26, ground - 12)  # where petals start from
        return lay

    def animate(self, px, env, lay):
        if env.condition == 'snow':
            return
        x_low, x_high, y_low, y_high = lay.tree
        count = 3 if env.condition in ('rain', 'storm') else 9
        drift = 0.35 + env.wind * 0.9
        fall = lay.h + 6
        for i in range(count):
            phase = env.t * (2.2 + 2.0 * hash01(i, 1)) / fall + hash01(i, 2)
            cycle = math.floor(phase)
            y0 = y_low + hash01(i, cycle, 3) * (y_high - y_low)
            x0 = x_low + hash01(i, cycle, 4) * (x_high - x_low)
            y = y0 + (phase - cycle) * fall
            x = x0 - (y - y0) * drift + math.sin(env.t * 1.6 + i * 2.1) * 1.3
            xi, yi = int(round(x)) % lay.w, int(y)
            if yi >= lay.surface[xi]:
                continue  # landed
            px.put(xi, yi, self.PINKS[4] if i % 3 == 0 else self.PINKS[3])
            if math.sin(env.t * 4.3 + i) > 0.35:  # tumbling: sometimes seen flat
                px.put(xi + 1, yi, self.PINKS[2])


class Lake(Theme):
    """Snowy peaks over a still lake, a pine forest and a cabin whose window glows at night"""
    name = 'lake'
    label = 'Mountain lake'

    CABIN = [
        '....c..',
        '..rRRc.',
        '.rRRRRR',
        'rRRRRRRR',
        '.WWWWLW',
        '.WWWWWW',
    ]

    def build(self, w, h):
        lay = Layout(w, h)
        px = Pixels(lay.scenery)
        water = h - 8
        lay.water = lay.horizon = water
        lay.surface = [water] * w

        # The range: each peak is (x, top row, steepness); light comes from the right
        peaks = [(0.84 * w, 8, 0.62), (0.62 * w, 12, 0.75), (0.35 * w, 13, 0.55), (0.08 * w, 14, 0.6),
                 (0.48 * w, 15, 0.9)]
        for x in range(w):
            ridge, peak_x = min((top + abs(x - cx) * k, cx) for cx, top, k in peaks)
            ridge += (noise(x, 0, 2.5, 31) - 0.5) * 2
            ridge = int(round(min(ridge, water - 3)))
            lit = x >= peak_x
            snowline = 15 + (noise(x, 1, 3, 33) - 0.5) * 3
            for y in range(ridge, water):
                crevice = noise(x, y, 1.8, 35) < 0.25
                if y < snowline:
                    color = (228, 234, 246) if lit else (164, 176, 212)
                    if crevice:
                        color = (134, 144, 186)
                else:
                    color = (112, 124, 172) if lit else (72, 80, 128)
                    if crevice:
                        color = (56, 62, 104)
                px.put(x, y, color)

        # Forested hills along the shore, with pines standing above them
        for x in range(w):
            top = water - 2 - int(noise(x, 2, 6, 37) * 2.5)
            for y in range(top, water):
                px.put(x, y, (32, 84, 58) if y > top else (48, 110, 68))
        x = 1
        while x < w:
            if not (0.1 * w < x < 0.24 * w):  # leave room for the cabin
                height = 3 + int(hash01(x, 39) * 4) - (1 if 0.4 * w < x < 0.7 * w else 0)
                base = water - 1
                for k in range(height):
                    half = (k + 1) // 2 if k < height - 1 else 0
                    y = base - height + 1 + k
                    for dx in range(-half, half + 1):
                        px.put(x + dx, y, (22, 66, 42) if dx > 0 else (42, 118, 64))
                px.put(x, base, (72, 50, 36))
            x += 3 + int(hash01(x, 40) * 3)

        cabin_x = int(0.13 * w)
        draw_map(px, cabin_x, water - 6, self.CABIN,
                 {'R': (128, 48, 36), 'r': (84, 30, 24), 'W': (150, 104, 62), 'L': (52, 40, 32), 'c': (80, 74, 70)})
        lay.lights.append((cabin_x + 5, water - 2, (255, 178, 80), True))
        lay.chimney = (cabin_x + 5, water - 6)

        for x in range(w):  # the water, filled in from the reflection
            for y in range(water, h):
                px.put(x, y, (0, 0, 0))
        lay.sun = (int(w * 0.9), 5, water + 1)
        return lay

    def animate(self, px, env, lay):
        # Chimney smoke on cold days
        if env.temp > 55 or env.condition in ('rain', 'storm'):
            return
        cx, cy = lay.chimney
        color = mix((150, 150, 160), (40, 40, 52), env.night)
        for i in range(5):
            age = (env.t * 0.9 + i / 5) % 1
            y = cy - 1 - age * 7
            x = cx + age * (2 + env.wind * 4) + math.sin(env.t * 1.3 + i * 2) * 0.6
            px.put(round(x), round(y), color, 0.75 * (1 - age))


class City(Theme):
    """A city skyline by a river; windows light up one by one as night falls"""
    name = 'city'
    label = 'City skyline'

    BODIES = [(92, 102, 138), (150, 104, 90), (116, 126, 152), (78, 96, 128), (136, 134, 148), (106, 96, 122)]
    # x, width, top row on a 64x32 display (scaled for others)
    BUILDINGS = [(0, 5, 17), (5, 4, 20), (9, 6, 15), (15, 5, 18), (20, 7, 14), (27, 4, 19), (31, 6, 16),
                 (37, 7, 10), (44, 5, 15), (49, 6, 12), (55, 5, 17), (60, 4, 14)]

    def build(self, w, h):
        lay = Layout(w, h)
        px = Pixels(lay.scenery)
        river = h - 5
        lay.water = lay.horizon = river
        lay.surface = [river] * w
        sx, sy = w / 64, h / 32

        # Far buildings, dim, filling the gaps
        for x in range(w):
            top = int(river - 9 * sy - noise(x, 0, 3, 51) * 6 * sy)
            for y in range(top, river):
                px.put(x, y, (92, 108, 146))  # hazy in the distance
        # Near buildings with windows
        lay.windows = []
        for i, (bx, bw, top) in enumerate(self.BUILDINGS):
            bx, bw, top = int(bx * sx), max(3, int(bw * sx)), int(top * sy)
            body = self.BODIES[i % len(self.BODIES)]
            for x in range(bx, min(w, bx + bw)):
                for y in range(top, river):
                    edge = x == bx
                    px.put(x, y, mix(body, (200, 210, 230), 0.3) if edge else body)
            glass = hash01(i, 58) < 0.5  # by day, some windows show the sky and some look dark
            pane = mix(body, (170, 206, 245), 0.55) if glass else mix(body, (30, 36, 54), 0.5)
            for x in range(bx + 1, bx + bw - 1, 2):
                for y in range(top + 2, river - 1, 2):
                    px.put(x, y, pane)
                    lay.windows.append((x, y, i))
            for x in range(bx, min(w, bx + bw)):
                px.put(x, top, mix(body, (210, 216, 230), 0.35))  # the roof's edge
            if top < 12 * sy:  # the tallest one has a warning light on top
                lay.beacon = (bx + bw // 2, top - 1)
                px.put(bx + bw // 2, top - 1, (130, 130, 144))
        # The embankment
        for x in range(w):
            px.put(x, river - 1, (118, 116, 122))
        for x in range(w):
            for y in range(river, h):
                px.put(x, y, (0, 0, 0))
        lay.sun = (int(w * 0.68), 4, river + 1)
        return lay

    def window_on(self, k, x, y, env):
        """Whether window k is lit: most are once it's dark, and they change now and then"""
        period = 25 + 50 * hash01(k, 52)
        slot = int(env.t / period + hash01(k, 53))
        return hash01(k, slot, 54) < 0.25 + 0.4 * env.lights_on

    def animate(self, px, env, lay):
        if env.lights_on > 0:
            warm = [(255, 196, 110), (255, 226, 160), (255, 170, 80), (170, 200, 255)]
            for k, (x, y, building) in enumerate(lay.windows):
                if not self.window_on(k, x, y, env):
                    continue
                color = warm[int(hash01(k, 55) * 4)] if hash01(k, 56) < 0.9 else warm[3]
                px.put(x, y, color, env.lights_on * 0.9)
                # Its reflection in the river, wobbling
                ry = 2 * lay.water - 1 - y
                if ry < lay.h:
                    wobble = round(math.sin(env.t * 2 + ry * 1.7 + x) * 0.8)
                    px.put(x + wobble, ry, color, env.lights_on * 0.45)
        if hasattr(lay, 'beacon') and (env.t % 1.6) < 0.5:
            x, y = lay.beacon
            px.put(x, y, (255, 40, 30))
            px.add(x, y + 1, (255, 40, 30), 0.2)


class Skogafoss(Theme):
    """Iceland's Skógafoss: a curtain of water falling off a mossy basalt cliff into a cloud
    of spray. A rainbow hangs in the mist on sunny days, the northern lights dance on clear
    nights, and a tent by the river glows after dark."""
    name = 'skogafoss'
    label = 'Skógafoss'

    TENT = ['..t..', '.tTt.', 'tTTTt', 'tTLTt']
    PERIOD = 24  # rows before the falling water's pattern repeats

    def build(self, w, h):
        lay = Layout(w, h)
        px = Pixels(lay.scenery)
        sx = w / 64
        lip = 9                  # the top of the cliff, where the water goes over
        base = h - 7             # the pool at the foot of the falls
        x0, x1 = int(28 * sx), int(37 * sx)
        cx = (x0 + x1) / 2
        lay.horizon = lip
        lay.surface = [h] * w

        tops = []
        for x in range(w):
            top = lip - (0 if x0 - 2 <= x <= x1 + 2 else int(round(noise(x, 0, 5, 101) * 1.6)))
            tops.append(top)
            for y in range(top, base + 1):
                if y - top < 2:  # grass on top
                    color = (66, 136, 58) if y == top else (46, 100, 48)
                else:
                    # Basalt in vertical columns, with moss hanging down from the top
                    streak = noise(x * 1.6, y * 0.22, 2.5, 102)
                    color = mix((34, 34, 44), (82, 80, 92), streak)
                    moss = noise(x * 1.3, y * 0.6, 2.5, 103) + 0.4 * clamp(1 - (y - top - 2) / 4)
                    if moss > 0.8:
                        color = (70, 124, 58) if moss > 0.95 else (46, 90, 50)
                    if x0 - 1 <= x <= x1 + 1:
                        color = (28, 32, 42)  # wet rock behind the water
                px.put(x, y, color)

        # The path of steps up the right side of the cliff
        stairs_x = int(52 * sx)
        for i, y in enumerate(range(base - 1, lip + 1, -1)):
            step = (i // 3) % 2
            x = stairs_x + (i % 3 if step == 0 else 2 - i % 3) + (base - y) // 5
            px.put(x, y, (150, 140, 122))

        # Black gravel and grass in front, the river running out toward you, a few boulders
        lay.river = []
        for y in range(base, h):
            half = (x1 - x0) / 2 + 2 + (y - base) * 1.6
            for x in range(w):
                if abs(x - cx) <= half:
                    lay.river.append((x, y))
                    px.put(x, y, (52, 92, 120))
                elif abs(x - cx) <= half + 2 + (y - base):
                    px.put(x, y, mix((40, 38, 44), (66, 64, 70), hash01(x, y, 104)))
                else:
                    px.put(x, y, (48, 104, 46) if hash01(x, y, 105) > 0.2 else (68, 128, 56))
        for bx, by in ((int(20 * sx), h - 2), (int(46 * sx), h - 3), (int(14 * sx), h - 5)):
            draw_map(px, bx, by, ['.rr.', 'rRRr'], {'r': (96, 96, 104), 'R': (70, 70, 78)})

        tent_x = int(5 * sx)
        draw_map(px, tent_x, base - 1, self.TENT, {'t': (226, 112, 42), 'T': (180, 80, 30), 'L': (60, 36, 24)})
        lay.lights.append((tent_x + 2, base + 2, (255, 186, 90), True))

        # The falling water's pattern: streaks that scroll down, the same every PERIOD rows
        lay.falls = (x0, x1, lip, base)
        lay.texture = []
        for x in range(x0, x1 + 1):
            column_light = noise(x, 0, 1.4, 106)
            column = []
            for y in range(self.PERIOD):
                t = y / self.PERIOD
                v = noise(x * 1.7, y, 4, 107) * (1 - t) + noise(x * 1.7, y - self.PERIOD, 4, 107) * t
                column.append(clamp(0.2 + 0.6 * v + 0.35 * (column_light - 0.5)))
            lay.texture.append(column)
        lay.sun = (int(54 * sx), 3, lip + 2)
        return lay

    def sky(self, px, sky, env, lay, body):
        """The northern lights, on clear nights; brighter some nights than others"""
        strength = env.night * clamp(1 - env.clouds * 1.4) * (0.55 + 0.45 * hash01(int(env.t // 86400), 95))
        if strength < 0.05:
            return
        bx, by = body[:2] if body else (-99, -99)
        for x in range(lay.w):
            edge = 4.5 + 1.6 * math.sin(x * 0.13 + env.t * 0.21) + (noise(x + env.t * 0.6, 0, 7, 96) - 0.5) * 3
            ray = 0.3 + 0.7 * noise(x * 1.3 + env.t * 1.1, 0, 2.2, 97)
            for y in range(min(lay.h, int(edge) + 2)):
                if not sky[x, y] or (abs(x - bx) <= 4 and abs(y - by) <= 4):
                    continue
                above = edge - y
                glow = ray * (math.exp(-above / 3.5) if above >= 0 else 0.45)
                color = mix((40, 255, 150), (150, 70, 220), clamp(above / 7))
                px.add(x, y, color, glow * strength * 1.15)

    def animate(self, px, env, lay):
        x0, x1, lip, base = lay.falls
        light = env.light
        cx = (x0 + x1) / 2

        # The falling water
        dark, bright = scale((70, 100, 128), light), scale((234, 242, 252), light)
        scroll = env.t * 14
        sparkle = int(env.t * 8)
        for i, column in enumerate(lay.texture):
            x = x0 + i
            edge = i == 0 or i == len(lay.texture) - 1
            for y in range(lip, base):
                v = column[int(y - scroll) % self.PERIOD]
                if edge and v < 0.45:
                    continue  # ragged sides
                if hash01(x, y, sparkle, 108) < 0.06:
                    v = 1
                px.put(x, y, mix(dark, bright, v))

        # Churning foam in the pool, and the river running off it
        foam, pool = scale((240, 244, 250), light), scale((110, 146, 172), light)
        for y in range(base, base + 3):
            spread = (x1 - x0) / 2 + 2 + (y - base)
            for x in range(int(cx - spread), int(cx + spread) + 1):
                v = noise(x * 1.2 + math.sin(env.t * 2 + y) * 1.5, y * 2 + env.t * 1.5, 2, 109)
                px.put(x, y, mix(pool, foam, clamp(v * 1.3 - 0.1)))
        highlight = scale((170, 206, 228), light)
        for x, y in lay.river:
            if y >= base + 3 and noise(x * 0.8, y * 2 - env.t * 5, 2.5, 110) > 0.62:
                px.put(x, y, highlight, 0.8)

        # Spray rising off the pool
        mist = scale((214, 222, 232), light)
        for y in range(base - 6, base + 2):
            for x in range(int(cx - 8), int(cx + 9)):
                d = math.hypot((x - cx) / 9, (y - base) / 6)
                if d < 1:
                    px.add(x, y, mist, 0.16 * (1 - d))
        for i in range(16):
            phase = env.t * 0.35 + hash01(i, 111)
            cycle, age = math.floor(phase), phase - math.floor(phase)
            x = cx + (hash01(i, cycle, 112) - 0.5) * (x1 - x0 + 10) + age * (1 + env.wind * 4)
            y = base + 1 - age * 9
            px.put(x, y, mist, 0.6 * (1 - age) * clamp(age * 4))

        # A rainbow in the spray when the sun is out
        if env.condition in ('clear', 'clouds') and env.s > 0.25 and env.clouds < 0.5:
            strength = clamp((env.s - 0.25) * 2) * (1 - env.clouds * 1.5)
            colors = [(255, 60, 60), (255, 160, 40), (255, 236, 70), (70, 220, 90), (70, 140, 255), (150, 90, 235)]
            done = set()
            for k, color in enumerate(colors):
                r = 12 - k * 0.9
                for step in range(40):
                    a = math.radians(100 + step * 1.7)
                    spot = (round(cx + r * math.cos(a)), round(lay.h - 1 - r * math.sin(a)))
                    if spot not in done and spot[1] < base + 2:
                        done.add(spot)
                        px.put(*spot, color, 0.38 * strength)


THEMES = {theme.name: theme for theme in (Blossom(), Lake(), City(), Skogafoss())}


# ---------- Sky and weather ----------


def draw_sky(image, top, horizon, horizon_y):
    px = image.load()
    w, h = image.size
    for y in range(h):
        color = (*mix(top, horizon, clamp(y / max(1, horizon_y)) ** 1.6), 255)
        for x in range(w):
            px[x, y] = color


def draw_moon(px, cx, cy, phase, brightness):
    r = 3
    lit_color = mix((0, 0, 0), (236, 232, 200), brightness)
    dark_color = mix((0, 0, 0), (26, 28, 44), brightness)
    for dy in range(-r, r + 1):
        half = math.sqrt(max(0, (r + 0.4) ** 2 - dy * dy))
        terminator = half * math.cos(2 * math.pi * phase)
        for dx in range(-r, r + 1):
            if abs(dx) > half:
                continue
            lit = dx >= terminator if phase < 0.5 else dx <= -terminator
            px.put(cx + dx, cy + dy, lit_color if lit else dark_color)
    return lit_color


def draw_sun(px, cx, cy, s):
    core = mix((255, 150, 60), (255, 236, 170), clamp(s * 2))
    glow = mix((255, 90, 40), (255, 200, 110), clamp(s * 2))
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            d = math.hypot(dx, dy)
            if d <= 2.2:
                px.put(cx + dx, cy + dy, core)
            elif d <= 4.2:
                px.add(cx + dx, cy + dy, glow, 0.28 * (4.2 - d) / 2)
    return core


def reflect(image, lay):
    """Fills the water with a dimmed, bluer mirror image of what's above it"""
    px = image.load()
    for y in range(lay.water, lay.h):
        src = max(0, 2 * lay.water - 1 - y)
        depth = (y - lay.water) / max(1, lay.h - lay.water)
        f = (0.62 - 0.15 * depth, 0.7 - 0.12 * depth, 0.84 - 0.1 * depth)
        for x in range(lay.w):
            r, g, b = px[x, src][:3]
            px[x, y] = (int(r * f[0]), int(g * f[1]) + 2, int(b * f[2]) + 8, 255)


def ripple(pixels, env, lay, body):
    """Water moves: rows sway a pixel side to side, and the sun or moon glitters on it"""
    w = lay.w
    calm = 1 - 0.5 * clamp(env.wind)
    for y in range(lay.water, lay.h):
        shift = round(math.sin(env.t * 1.4 + y * 1.3) * (0.6 + 0.5 * (y - lay.water) / (lay.h - lay.water)) / calm)
        if shift:
            row = [pixels.px[x, y] for x in range(w)]
            for x in range(w):
                pixels.px[x, y] = row[(x - shift) % w]
    if body is not None:
        bx, color, strength = body
        tick = int(env.t * 5)
        for y in range(lay.water, lay.h):
            spread = 1 + (y - lay.water) // 3
            for x in range(bx - spread, bx + spread + 1):
                if hash01(x, y, tick, 91) < 0.4:
                    pixels.put(x, y, color, 0.75 * strength)


def cloud_sprite(seed, width, height, lit, shade):
    """A puffy cloud as an RGBA image: lit on top, shaded underneath"""
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    px = image.load()
    puffs = [(width * (0.2 + 0.6 * hash01(seed, i)), height * (0.35 + 0.3 * hash01(seed, i, 1)),
              height * (0.35 + 0.25 * hash01(seed, i, 2))) for i in range(4)]
    puffs.append((width / 2, height * 0.62, height * 0.42))
    for y in range(height):
        for x in range(width):
            cover = max(1 - math.hypot((x - cx) / (r * 1.6), (y - cy) / r) for cx, cy, r in puffs)
            cover += (noise(x, y, 2, seed) - 0.5) * 0.4
            if cover > 0:
                px[x, y] = (*mix(lit, shade, clamp((y / height) * 1.3 - 0.1)), int(255 * clamp(cover * 3)))
    return image


def cloud_colors(s, gloom):
    lit = keyframes([(-1, (30, 30, 42)), (-0.45, (70, 44, 80)), (0, (236, 140, 110)), (0.45, (240, 226, 214)),
                     (1, (236, 240, 248))], s)
    shade = keyframes([(-1, (14, 14, 22)), (-0.45, (36, 24, 50)), (0, (120, 60, 80)), (0.45, (164, 156, 170)),
                       (1, (156, 168, 192))], s)
    dark = 1 - 0.45 * gloom
    return tuple(int(c * dark) for c in lit), tuple(int(c * dark) for c in shade)


_clouds = {}


def draw_clouds(image, sky_mask, env, w, h):
    if env.clouds <= 0:
        return
    lit, shade = cloud_colors(round(env.s * 20) / 20, env.gloom)
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    speed = 0.25 + env.wind * 0.7  # pixels a second
    for i in range(max(1, round(env.clouds * 5))):
        cw = int(14 + 12 * hash01(i, 31) + env.clouds * 6)
        ch = int(5 + 3 * hash01(i, 32) + env.clouds * 2)
        key = (i, cw, ch, lit, shade)
        sprite = _clouds.get(key)
        if sprite is None:
            if len(_clouds) > 64:
                _clouds.clear()
            sprite = _clouds[key] = cloud_sprite(i * 7 + 3, cw, ch, lit, shade)
        span = w + cw
        x = int((hash01(i, 33) * span - env.t * speed * (0.7 + 0.5 * hash01(i, 34))) % span) - cw
        y = int(-2 + hash01(i, 35) * h * 0.25)
        layer.paste(sprite, (x, y), sprite)
    layer.putalpha(ImageChops.multiply(layer.getchannel('A'), sky_mask))
    image.alpha_composite(layer)


_stars = {}


def draw_stars(px, sky, env, w, h, body):
    if env.starry <= 0.02:
        return
    stars = _stars.get((w, h))
    if stars is None:
        stars = _stars[(w, h)] = [(int(hash01(i, 41) * w), int(hash01(i, 42) ** 1.4 * h * 0.75), 0.8 + 2.2 * hash01(i, 43),
                           i * 1.7, 0.35 + 0.65 * hash01(i, 44) ** 2,
                           (200, 210, 255) if hash01(i, 45) < 0.7 else (255, 230, 190)) for i in range(w * h // 38)]
    bx, by = body[:2] if body else (-99, -99)
    for x, y, rate, phase, base, tint in stars:
        if sky[x, y] and not (abs(x - bx) <= 4 and abs(y - by) <= 4):
            px.put(x, y, tint, clamp(base * (0.55 + 0.45 * math.sin(env.t * rate + phase)) * env.starry))
    # Now and then a shooting star
    window = int(env.t // 40)
    if hash01(window, 46) < 0.4:
        at = env.t - window * 40 - hash01(window, 47) * 30
        if 0 <= at < 0.9:
            sx, sy = w * (0.25 + 0.6 * hash01(window, 48)), 1 + hash01(window, 49) * h * 0.2
            for k in range(5):
                x, y = int(sx - at * 30 + k), int(sy + at * 10 - k / 3)
                if 0 <= x < w and 0 <= y < h and sky[x, y]:
                    px.put(x, y, (255, 255, 230), env.starry * (1 - k / 5))


def draw_rain(px, env, w, h, surface):
    count = int(w * h / (64 if env.heavy else 110) * (1.4 if env.condition == 'storm' else 1))
    slant = 0.2 + env.wind * 0.3
    color, head = (70, 104, 160), (150, 190, 245)
    for i in range(count):
        speed = 24 + 12 * hash01(i, 51)
        length = 3 + int(hash01(i, 52) * 2)
        span = h + length
        y = (env.t * speed + hash01(i, 53) * span) % span - length
        x0 = hash01(i, 54) * w
        for k in range(length):
            yy = y + k
            x = int(x0 - yy * slant) % w
            if yy >= surface[x]:
                break
            px.put(x, int(yy), head if k == length - 1 else color, 0.5 + 0.5 * (k + 1) / length)
    for i in range(w // 6):  # splashes
        cycle = int(env.t * 3 + hash01(i, 55) * 7)
        if hash01(i, cycle, 56) < 0.35:
            x = int(hash01(i, cycle, 57) * w)
            px.put(x, surface[x] - 1, head, 0.6)


def draw_snow(px, env, w, h, surface):
    for i in range(w * h // 70):
        speed = 2.5 + 3 * hash01(i, 61)
        span = h + 2
        y = (env.t * speed + hash01(i, 62) * span) % span - 1
        x = hash01(i, 63) * w - y * env.wind * 0.4 + math.sin(env.t * (0.6 + hash01(i, 64)) + i) * 1.6
        xi = int(round(x)) % w
        if y < surface[xi]:
            px.put(xi, int(y), (235, 240, 255), 0.55 + 0.45 * hash01(i, 65))


_fog = {}


def fog_texture(w, h):
    """Two bands of mist as 'L' images twice the display's width, seamless side to side,
    and how much mist each row gets (thicker low down)"""
    texture = _fog.get((w, h))
    if texture is None:
        layers = []
        for seed, size in ((71, 9), (72, 5)):
            image = Image.new('L', (2 * w, h))
            px = image.load()
            for y in range(h):
                for x in range(2 * w):
                    t = x / (2 * w)
                    v = noise(x, y * 2.5, size, seed) * (1 - t) + noise(x - 2 * w, y * 2.5, size, seed) * t
                    px[x, y] = int(v * 255)
            layers.append(image)
        weight = Image.new('L', (w, h))
        wpx = weight.load()
        for y in range(h):
            for x in range(w):
                wpx[x, y] = int(255 * clamp((y - h * 0.25) / (h * 0.5)) * 0.8)
        texture = _fog[(w, h)] = (layers, weight)
    return texture


def draw_fog(image, env, w, h):
    (slow, fast), weight = fog_texture(w, h)

    def window(texture, offset):
        offset = int(offset) % (2 * w)
        part = texture.crop((offset, 0, offset + w, h))
        if offset + w > 2 * w:
            part.paste(texture.crop((0, 0, offset + w - 2 * w, h)), (2 * w - offset, 0))
        return part

    mist = ImageChops.add(window(slow, env.t * 1.2), window(fast, -env.t * 0.7 + w), scale=2)
    mist = ImageChops.multiply(mist.point(lambda v: int(255 * clamp((v / 255 - 0.3) * 2))), weight)
    color = mix((24, 24, 30), (196, 202, 210), clamp((env.s + 1) / 1.6))
    image.paste((*color, 255), (0, 0), mist)


def lightning(t):
    """How bright a lightning flash is at time t (0 most of the time), and which flash it is"""
    window = int(t // 5)
    if hash01(window, 81) > 0.45:
        return 0, 0
    at = t - window * 5 - hash01(window, 82) * 3.5
    for start, length, strength in ((0, 0.12, 1.0), (0.22, 0.08, 0.6), (0.4, 0.15, 0.8)):
        if start <= at < start + length:
            return strength, window
    return 0, 0


def draw_lightning(image, px, sky_mask, env, w, h, horizon):
    strength, seed = lightning(env.t)
    if not strength:
        return
    flash = Image.new('RGBA', (w, h), (90, 90, 120, 0))
    flash.putalpha(sky_mask.point(lambda a: int(a * 0.55 * strength)))
    image.alpha_composite(flash)
    x, y = w * (0.3 + 0.6 * hash01(seed, 83)), 0
    while y < horizon - 2:
        px.put(x, y, (235, 230, 255))
        y += 1
        x += (hash01(seed, y, 84) - 0.5) * 2.4
        if hash01(seed, y, 85) < 0.12:  # a fork
            fx = x
            for k in range(3):
                fx += 1 if hash01(seed, 86) < 0.5 else -1
                px.put(fx, y + k, (170, 160, 230))


def draw_lights(px, lay, env):
    """Lanterns and windows come on as it gets dark"""
    if env.lights_on <= 0:
        return
    for i, (x, y, color, glow) in enumerate(lay.lights):
        on = env.lights_on * (0.85 + 0.15 * math.sin(env.t * 9 + i * 3) * math.sin(env.t * 5.3 + i))
        px.put(x, y, color, on)
        if glow:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                px.add(x + dx, y + dy, color, 0.22 * on)
        if lay.water is not None and 2 * lay.water - 1 - y < lay.h:
            px.put(x, 2 * lay.water - 1 - y, color, 0.4 * on)


# ---------- The component ----------

# Caches. The display and the management page draw from different threads, so these only
# ever get whole values put in them (or get emptied), never changed in place.
_layouts = {}
_bases = {}


def layout_for(theme, w, h):
    key = (theme.name, w, h)
    lay = _layouts.get(key)
    if lay is None:
        lay = _layouts[key] = theme.build(w, h)
    return lay


def base_for(theme, lay, env):
    """(image, sky mask, sun or moon): the sky, the sun or moon and the scenery lit for the
    time of day. Cached, with the sun's position rounded so it's only redrawn now and then."""
    s = round(env.s * 20) / 20
    moon = round(env.moon * 24) % 24 / 24
    key = (theme.name, lay.w, lay.h, s, env.gloom, env.clouds, env.condition, moon)
    base = _bases.get(key)
    if base is not None:
        return base
    if len(_bases) > 24:
        _bases.clear()
    image = Image.new('RGBA', (lay.w, lay.h))
    draw_sky(image, *sky_colors(s, env.gloom), lay.horizon)
    px = Pixels(image)
    sx, high, low = lay.sun
    body = None
    if s > -0.25 and env.clouds < 0.8:
        y = int(round(low + (high - low) * clamp(s + 0.25)))
        body = (sx, y, draw_sun(px, sx, y, s), clamp(s + 0.3) * (1 - env.clouds))
    elif s < -0.2 and env.clouds < 0.9:
        y = int(round(low + (high - low) * clamp(-s * 1.4 - 0.2)))
        bright = clamp(-s * 1.5 - 0.2) * (1 - env.clouds * 0.6)
        body = (sx, y, draw_moon(px, sx, y, moon, bright), bright * 0.6)
    scenery = theme.frozen(lay) if env.condition == 'snow' else lay.scenery
    r, g, b, a = scenery.split()
    light = ambient(s, env.gloom)
    r, g, b = (band.point(lambda v, f=f: int(v * f)) for band, f in zip((r, g, b), light))
    image.alpha_composite(Image.merge('RGBA', (r, g, b, a)))
    if lay.water is not None:
        reflect(image, lay)
    sky_mask = a.point(lambda v: 255 if v == 0 else 0)
    if body and body[1] >= lay.horizon:
        body = None  # it's set
    base = _bases[key] = (image, sky_mask, body)
    return base


class Scene(Component):
    type = 'scene'
    label = 'Scene'
    description = 'An animated background that follows the weather and time of day'
    background = True
    options = (
        Option('theme', 'Theme', 'select', 'blossom', choices=[(t.name, t.label) for t in THEMES.values()]),
        Option('weather', 'Weather', 'select', 'live', choices=WEATHER_CHOICES),
        Option('time', 'Time of day', 'select', 'live', choices=TIME_CHOICES),
        Option('brightness', 'Brightness', 'number', 100, min=10, max=100, unit='%'),
    )

    def size(self, opts, ctx):
        return ctx.display_size

    def draw(self, image, opts, ctx):
        weather, note = data_or_sample(ctx, 'weather')
        if opts['weather'] != 'live' and opts['time'] != 'live':
            note = None  # it isn't using the weather, so sample weather doesn't matter
        env = Env(ctx.now, weather, opts)
        theme = THEMES[opts['theme']]
        w, h = image.size
        lay = layout_for(theme, w, h)
        base, sky_mask, body = base_for(theme, lay, env)
        frame = base.copy()
        px = Pixels(frame)

        sky = sky_mask.load()
        draw_stars(px, sky, env, w, h, body)
        theme.sky(px, sky, env, lay, body)
        draw_clouds(frame, sky_mask, env, w, h)
        if lay.water is not None:
            ripple(px, env, lay, (body[0], body[2], body[3]) if body else None)
        draw_lights(px, lay, env)
        theme.animate(px, env, lay)
        if env.condition in ('rain', 'storm'):
            draw_rain(px, env, w, h, lay.surface)
        elif env.condition == 'snow':
            draw_snow(px, env, w, h, lay.surface)
        elif env.condition == 'fog':
            draw_fog(frame, env, w, h)
        if env.condition == 'storm':
            draw_lightning(frame, px, sky_mask, env, w, h, lay.horizon)

        if opts['brightness'] < 100:
            f = opts['brightness'] / 100
            r, g, b, a = frame.split()
            frame = Image.merge('RGBA', [band.point(lambda v: int(v * f)) for band in (r, g, b)] + [a])
        image.paste(frame, (0, 0))
        return note
