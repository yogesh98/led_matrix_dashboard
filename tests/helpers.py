from datetime import datetime

from components.base import RenderContext


class FakeSource:
    def __init__(self, data):
        self.data = data

    def current(self):
        return self.data


def context(now=None, weather=None, preview=False, size=(64, 32)):
    return RenderContext(
        now=now or datetime(2026, 11, 24, 9, 5, 7),
        sources={'weather': FakeSource(weather)},
        preview=preview,
        display_size=size,
    )


def lit(image):
    """How many pixels of an RGB or RGBA image are lit"""
    if image.mode == 'RGBA':
        return sum(1 for a in image.getchannel('A').tobytes() if a)
    return sum(1 for p in zip(*[iter(image.tobytes())] * 3) if any(p))
