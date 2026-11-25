"""Renders the animations and pictures in README.md, with the same code that drives the
panel, drawn to look like LEDs. Run it from the project folder after changing a scene:

    .venv/bin/python docs/render_media.py

It writes into docs/. Weather and times are fixed here, so the pictures don't depend on
when you run it or on the weather settings in .env.
"""
import os
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.base import RenderContext  # noqa: E402
from components.scene import lightning  # noqa: E402
from prebuilt import prebuilt_screens  # noqa: E402
from renderer import render_screen  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 64, 32
BACKGROUND, UNLIT, CAPTION = (10, 11, 13), (24, 27, 31), (200, 204, 210)
DAY = datetime(2026, 11, 24)
SUN = {'sunrise': datetime(2026, 11, 24, 6, 50).timestamp(), 'sunset': datetime(2026, 11, 24, 17, 0).timestamp()}
SCREENS = {screen['id']: screen for screen in prebuilt_screens()}


class Source:
    def __init__(self, data):
        self.data = data

    def current(self):
        return self.data


def weather(icon, temp, wind=7):
    return {'icon': icon, 'temp': temp, 'feels_like': temp, 'wind_speed': wind, 'humidity': 60, **SUN}


def frame(screen_id, now, data):
    ctx = RenderContext(now=now, sources={'weather': Source(data), 'forecast': Source(None)}, display_size=(W, H))
    return render_screen(SCREENS[screen_id], ctx)


_dots = {}


def leds(image, pitch):
    """image (one pixel per LED) drawn as round LEDs, pitch pixels apart"""
    if pitch not in _dots:
        cell = Image.new('L', (pitch, pitch), 0)
        r = pitch * 0.42
        ImageDraw.Draw(cell).ellipse([pitch / 2 - r, pitch / 2 - r, pitch / 2 + r - 1, pitch / 2 + r - 1], fill=255)
        mask = Image.new('L', (W * pitch, H * pitch))
        for y in range(H):
            for x in range(W):
                mask.paste(cell, (x * pitch, y * pitch))
        _dots[pitch] = mask
    lit = image.copy()
    px = lit.load()
    for y in range(H):
        for x in range(W):
            if px[x, y] == (0, 0, 0):
                px[x, y] = UNLIT
    big = lit.resize((W * pitch, H * pitch), Image.NEAREST)
    out = Image.new('RGB', big.size, BACKGROUND)
    out.paste(big, (0, 0), _dots[pitch])
    return out


def grid(panels, pitch, columns, captions=None, gap=None):
    """Panels (64x32 frames) side by side as LEDs, with a caption under each"""
    gap = gap if gap is not None else pitch * 3
    font = ImageFont.load_default(size=max(12, pitch * 2 + 2))
    caption_h = (font.size + gap // 2) if captions else 0
    rows = (len(panels) + columns - 1) // columns
    pw, ph = W * pitch, H * pitch
    sheet = Image.new('RGB', (columns * pw + (columns + 1) * gap, rows * (ph + caption_h) + (rows + 1) * gap), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for i, panel in enumerate(panels):
        x = gap + (i % columns) * (pw + gap)
        y = gap + (i // columns) * (ph + caption_h + gap)
        sheet.paste(leds(panel, pitch), (x, y))
        if captions:
            draw.text((x + pw / 2, y + ph + gap // 3), captions[i], fill=CAPTION, font=font, anchor='mt')
    return sheet


def save_gif(name, frames, ms):
    """An animated GIF with one palette for every frame, so still parts stay still"""
    sample = Image.new('RGB', (frames[0].width, frames[0].height * 4))
    for i, k in enumerate(range(0, len(frames), max(1, len(frames) // 4))):
        if i < 4:
            sample.paste(frames[k], (0, i * frames[0].height))
    palette = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    path = os.path.join(OUT, name)
    quantized[0].save(path, save_all=True, append_images=quantized[1:], duration=ms, loop=0, optimize=True,
                      disposal=1)
    print(f"{name}: {len(frames)} frames, {os.path.getsize(path) // 1024} KB")


def clip(screen_id, start, data, seconds=4, fps=20, pitch=7):
    frames = [leds(frame(screen_id, start + timedelta(seconds=k / fps), data), pitch)
              for k in range(int(seconds * fps))]
    return frames, round(1000 / fps)


def storm_start(around):
    """A moment a little before a lightning flash, so the clip catches one"""
    t = around
    while lightning(t.timestamp() + 1.6)[0] < 1:
        t += timedelta(seconds=0.05)
    return t


def main():
    # Each prebuilt screen, moving
    for name, screen_id, start, data in (
        ('blossom.gif', 'blossom', DAY.replace(hour=12, minute=41), weather('01d', 72, wind=16)),
        ('lake.gif', 'lake', DAY.replace(hour=16, minute=54), weather('01d', 41)),
        ('city.gif', 'city', DAY.replace(hour=21, minute=30), weather('01n', 51)),
        ('skogafoss.gif', 'skogafoss', DAY.replace(hour=13, minute=10), weather('01d', 48)),
        ('skogafoss-night.gif', 'skogafoss', DAY.replace(hour=22, minute=15), weather('01n', 34)),
        ('dynjandi.gif', 'dynjandi', DAY.replace(hour=11, minute=5), weather('01d', 46)),
        ('dynjandi-night.gif', 'dynjandi', DAY.replace(hour=22, minute=40), weather('01n', 30)),
    ):
        save_gif(name, *clip(screen_id, start, data))

    # The weather, in four scenes at once
    panels = [
        ('lake', DAY.replace(hour=15, minute=30), weather('10d', 48, wind=12), 'Rain'),
        ('blossom', DAY.replace(hour=9, minute=30), weather('13d', 28), 'Snow'),
        ('city', storm_start(DAY.replace(hour=21, minute=40)), weather('11n', 58, wind=18), 'Thunderstorm'),
        ('skogafoss', DAY.replace(hour=10, minute=40), weather('50d', 45), 'Fog'),
    ]
    fps = 20
    frames = [grid([frame(s, start + timedelta(seconds=k / fps), data) for s, start, data, _ in panels], 5, 2,
                   [caption for *_, caption in panels]) for k in range(4 * fps)]
    save_gif('weather.gif', frames, round(1000 / fps))

    # A day, from before sunrise to late at night, in four of the scenes (a 2x2 grid)
    start, steps = DAY.replace(hour=5, minute=30), 76
    frames = []
    for k in range(steps):
        now = start + timedelta(minutes=15 * k)
        frames.append(grid([frame(s, now, weather('01d', 60)) for s in ('blossom', 'lake', 'city', 'skogafoss')], 4, 2))
    frames += [frames[-1]] * 8  # rest on the night before it starts again
    save_gif('day.gif', frames, 110)

    # Every scene in every kind of weather, as one picture
    ids = list(SCREENS)
    columns = [
        ('Clear day', DAY.replace(hour=12, minute=41, second=3), '01d', 72),
        ('Sunset', DAY.replace(hour=17, minute=0, second=3), '02d', 64),
        ('Night', DAY.replace(hour=22, minute=7, second=9), '01n', 51),
        ('Rain', DAY.replace(hour=15, minute=30, second=7), '10d', 48),
        ('Snow', DAY.replace(hour=9, minute=30, second=1), '13d', 28),
    ]
    panels, captions = [], []
    for screen_id in ids:
        for label, now, icon, temp in columns:
            panels.append(frame(screen_id, now, weather(icon, temp, wind=9)))
            captions.append(f"{SCREENS[screen_id]['name']} · {label}")
    path = os.path.join(OUT, 'gallery.png')
    grid(panels, 4, len(columns), captions).save(path, optimize=True)
    print(f"gallery.png: {os.path.getsize(path) // 1024} KB")


if __name__ == '__main__':
    main()
