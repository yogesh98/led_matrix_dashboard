"""Lining up what a component shows inside its box, and boxes sized for the biggest it can show"""
import unittest
from datetime import datetime

import bdf
from layout import normalize_widget
from renderer import render_widget
from tests.helpers import context

WEATHER = {'icon': '01d', 'temp': 5, 'feels_like': 3, 'humidity': 7, 'wind_speed': 4, 'wind_deg': 0,
           'sunrise': datetime(2026, 11, 24, 6, 52).timestamp(), 'sunset': datetime(2026, 11, 24, 17, 1).timestamp()}
# Something narrower or shorter than its box, for each component that can be lined up
EXAMPLES = [
    ('clock', {}, datetime(2026, 11, 24, 11, 10)),
    ('time', {}, datetime(2026, 11, 24, 9, 5)),
    ('date', {'format': 'numeric'}, datetime(2026, 1, 5)),
    ('date', {'format': 'month_date'}, datetime(2026, 11, 24)),
    ('countdown', {'label': 'Go', 'date': '2026-11-30'}, datetime(2026, 11, 24)),
    ('countdown', {'label': 'Go', 'date': '2026-11-30', 'layout': 'inline'}, datetime(2026, 11, 24)),
    ('weather', {'show': 'temperature'}, datetime(2026, 11, 24)),
    ('weather', {'show': 'wind', 'label': True}, datetime(2026, 11, 24)),
    ('weather', {'show': 'sunrise', 'font': '6x10'}, datetime(2026, 11, 24)),
    ('text', {'text': 'ace'}, datetime(2026, 11, 24)),
]
SIDES = {'left': 0, 'right': 2, 'top': 1, 'bottom': 3}


def draw(type, now, **options):
    widget = normalize_widget({'type': type, 'options': options})
    return render_widget(widget, context(now=now, weather=WEATHER))[0]


def ink(image):
    """(left, top, right, bottom) of the lit pixels, right and bottom inclusive"""
    box = image.getchannel('A').getbbox()
    return box[0], box[1], box[2] - 1, box[3] - 1


class AlignTest(unittest.TestCase):
    def test_every_text_component_can_be_lined_up_all_nine_ways(self):
        for type, options, now in EXAMPLES:
            for align in ('left', 'center', 'right'):
                for valign in ('top', 'middle', 'bottom'):
                    with self.subTest(type=type, options=options, align=align, valign=valign):
                        image = draw(type, now, align=align, valign=valign, **options)
                        left, top, right, bottom = ink(image)
                        w, h = image.size
                        labeled = options.get('layout') == 'inline' or options.get('label') is True
                        if align == 'left' or labeled:  # labels stay at the left
                            self.assertEqual(left, 0)
                        if align == 'right':
                            self.assertEqual(right, w - 1)
                        elif align == 'center' and not labeled:
                            self.assertLessEqual(abs(left - (w - 1 - right)), 1)
                        if valign == 'top':
                            self.assertEqual(top, 0)
                        elif valign == 'bottom':
                            self.assertEqual(bottom, h - 1)
                        else:
                            self.assertLessEqual(abs(top - (h - 1 - bottom)), 1)

    def test_lines_are_lined_up_one_by_one(self):
        # "Go" over "6d": each line on its own, not the two as a block
        for align in ('left', 'right'):
            image = draw('countdown', datetime(2026, 11, 24), label='Go', date='2026-11-30', align=align)
            line = image.height // 2
            top = ink(image.crop((0, 0, image.width, line)))
            bottom = ink(image.crop((0, line + 1, image.width, image.height)))
            side = SIDES[align]
            self.assertEqual(top[side], bottom[side])

    def test_a_label_stays_put_while_the_value_moves(self):
        now = datetime(2026, 11, 24)
        left = draw('weather', now, show='wind', label=True)
        right = draw('weather', now, show='wind', label=True, align='right')
        label = bdf.get_font('5x7').text_width('Wind') - 1
        self.assertEqual(left.crop((0, 0, label, left.height)).tobytes(),
                         right.crop((0, 0, label, right.height)).tobytes())
        self.assertEqual(ink(right)[2], right.width - 1)

    def test_single_digit_hours_go_all_the_way_left(self):
        for font in ('6x10', '7x13B', '5x7', '8x13B'):
            with self.subTest(font=font):
                nine = draw('time', datetime(2026, 11, 24, 9, 5), font=font)
                twelve = draw('time', datetime(2026, 11, 24, 12, 5), font=font)
                self.assertEqual(nine.size, twelve.size)
                self.assertEqual(ink(nine)[0], 0)
                self.assertEqual(ink(twelve)[0], 0)

    def test_old_saved_alignment_still_works(self):
        widget = normalize_widget({'type': 'weather', 'options': {'show': 'temperature', 'align': 'right'}})
        self.assertEqual((widget['options']['align'], widget['options']['valign']), ('right', 'top'))


class BoxSizeTest(unittest.TestCase):
    """Boxes are as big as the biggest thing the component can show, and no bigger"""

    def widest(self, type, times, **options):
        images = [draw(type, now, **options) for now in times]
        self.assertEqual(len({i.size for i in images}), 1)
        return images[0].size, max(ink(i)[2] - ink(i)[0] + 1 for i in images), max(ink(i)[3] + 1 for i in images)

    def test_time(self):
        # Every hour, and minutes and seconds with every digit in each place they can have
        days = [datetime(2026, 11, 24, h, m, m) for h in range(24) for m in (0, 11, 22, 33, 44, 55, 6, 17, 28, 39)]
        for font in bdf.available_fonts():
            for options in ({}, {'hours': '24'}, {'seconds': True}):
                with self.subTest(font=font, options=options):
                    (w, h), widest, _ = self.widest('time', days, font=font, **options)
                    self.assertEqual(w, widest)

    def test_temperature(self):
        for font in ('5x7', '6x10', '7x13B', '9x15B'):
            with self.subTest(font=font):
                images = []
                for temp in range(-99, 130):
                    widget = normalize_widget({'type': 'weather', 'options': {'show': 'temperature', 'font': font}})
                    images.append(render_widget(widget, context(weather={**WEATHER, 'temp': temp}))[0])
                self.assertEqual(len({i.size for i in images}), 1)
                width, height = images[0].size
                self.assertEqual(width, max(ink(i)[2] - ink(i)[0] + 1 for i in images))
                self.assertEqual(height, max(ink(i)[3] - ink(i)[1] + 1 for i in images))

    def test_clock_and_date(self):
        days = [datetime(2026, m, d, h, (d * 7 + m) % 60) for m in range(1, 13) for d in (1, 18, 28) for h in range(24)]
        for font in ('6x10', '8x13B', '5x7'):
            with self.subTest(font=font):
                (w, _), widest, _ = self.widest('clock', days, font=font)
                self.assertEqual(w, widest)
                (w, _), widest, _ = self.widest('date', days, font=font, format='day_month_date')
                self.assertEqual(w, widest)


if __name__ == '__main__':
    unittest.main()
