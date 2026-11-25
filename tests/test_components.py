"""The countdown, forecast and weather details components"""
import calendar
import unittest
from datetime import date, datetime, timedelta

from components.base import Option
from components.countdown import time_left
from components.openweathermap import summarize_forecast
from layout import normalize_widget
from renderer import render_widget
from tests.helpers import FakeSource, context, lit

NOW = datetime(2026, 11, 24, 9, 5, 7)  # a Tuesday


def widget(type, **options):
    return normalize_widget({'type': type, 'options': options})


def countdown(**options):
    return widget('countdown', **options)['options']


class CountdownTest(unittest.TestCase):
    def test_days(self):
        self.assertEqual(time_left(countdown(date='2026-12-06'), NOW), '12d')
        self.assertEqual(time_left(countdown(date='2026-11-25'), NOW), '1d')  # all of the day before
        self.assertEqual(time_left(countdown(date='2026-11-25', format='days_words'), NOW), '1 day')
        self.assertEqual(time_left(countdown(date='2026-12-06', format='days_words'), NOW), '12 days')

    def test_days_then_hours_then_minutes(self):
        opts = countdown(date='2026-11-25', time='11:15', format='auto')
        self.assertEqual(time_left(opts, NOW), '1d 2h')
        self.assertEqual(time_left(opts, datetime(2026, 11, 25, 9, 0)), '2h 15m')
        self.assertEqual(time_left(opts, datetime(2026, 11, 25, 11, 9, 30)), '5m 30s')

    def test_arrived(self):
        self.assertIsNone(time_left(countdown(date='2026-11-24'), NOW))
        self.assertIsNone(time_left(countdown(date='2026-01-01'), NOW))
        image, _ = render_widget(widget('countdown', date='2026-11-24', label=''), context(now=NOW))
        done, _ = render_widget(widget('text', text='Today!'), context())
        self.assertEqual(lit(image), lit(done))

    def test_default_fits_the_display(self):
        image, _ = render_widget(widget('countdown'), context(now=NOW))
        self.assertLessEqual(image.width, 64)

    def test_box_stays_the_same_size(self):
        sizes = {render_widget(widget('countdown', date=d), context(now=NOW))[0].size
                 for d in ('2026-11-25', '2026-12-06', '2027-06-01', '2026-11-24')}
        self.assertEqual(len(sizes), 1)

    def test_stacked_is_two_lines(self):
        one, _ = render_widget(widget('countdown', layout='inline'), context(now=NOW))
        two, _ = render_widget(widget('countdown', layout='stacked'), context(now=NOW))
        self.assertGreater(two.height, one.height * 2 - 1)
        self.assertLess(two.width, one.width)


def weather(**options):
    return widget('weather', **options)


class ForecastTest(unittest.TestCase):
    def forecast(self):
        today = NOW.date()
        return {
            'days': [{'date': (today + timedelta(days=i)).isoformat(), 'high': 70 + i, 'low': 50 + i, 'icon': '01d'}
                     for i in range(5)],
            'hours': [{'time': (NOW + timedelta(hours=h)).timestamp(), 'hour': (NOW + timedelta(hours=h)).hour,
                       'temp': 60 + h, 'icon': '10n'} for h in (-1, 2, 5, 8, 11)],
        }

    def render(self, weather_data=None, show='forecast_days', **options):
        from components import COMPONENTS
        ctx = context(now=NOW, weather=weather_data)
        ctx.sources['forecast'] = FakeSource(self.forecast())
        w = weather(show=show, **options)
        return COMPONENTS['weather'].forecast_columns(w['options'], self.forecast(), ctx), render_widget(w, ctx)[0]

    def test_days(self):
        columns, image = self.render()
        self.assertEqual(columns, [('Tue', '01d', '70/50'), ('Wed', '01d', '71/51'), ('Thu', '01d', '72/52')])
        self.assertEqual(image.width, 64)  # the automatic font is small enough for three columns
        self.assertLessEqual(image.height, 32)
        self.assertGreater(lit(image), 0)

    def test_starting_tomorrow_with_highs_only(self):
        columns, _ = self.render(start='tomorrow', temps='high', count=2)
        self.assertEqual(columns, [('Wed', '01d', '71°'), ('Thu', '01d', '72°')])

    def test_today_includes_temperatures_seen_earlier(self):
        weather_data = {'temp': 65, 'observed': {'date': NOW.date().isoformat(), 'high': 80, 'low': 40}}
        columns, _ = self.render(weather_data=weather_data, count=1)
        self.assertEqual(columns[0][2], '80/40')

    def test_hours(self):
        columns, _ = self.render(show='forecast_hours')
        self.assertEqual([c[0] for c in columns], ['11a', '2p', '5p'])  # skips the hour already gone
        columns, _ = self.render(show='forecast_hours', hours='24', count=1)
        self.assertEqual(columns[0][0], '11:00')

    def test_blank_on_the_display_until_it_loads(self):
        image, note = render_widget(weather(show='forecast_days'), context(now=NOW))
        self.assertEqual(lit(image), 0)

    def test_summarize_openweathermap(self):
        # Two days of 3-hourly forecasts, in a place 5 hours behind UTC
        offset = -5 * 3600
        start = calendar.timegm(datetime(2026, 11, 24, 0, 0).timetuple()) - offset  # local midnight
        entries = [{'dt': start + 3 * 3600 * i,
                    'main': {'temp': 50 + i, 'temp_min': 49 + i, 'temp_max': 51 + i},
                    'weather': [{'icon': '04n' if i % 8 < 2 else f'{10 + i:02}d'}]} for i in range(16)]
        summary = summarize_forecast({'city': {'timezone': offset}, 'list': entries})
        self.assertEqual([d['date'] for d in summary['days']], ['2026-11-24', '2026-11-25'])
        self.assertEqual((summary['days'][0]['high'], summary['days'][0]['low']), (58, 49))
        self.assertEqual(summary['days'][0]['icon'], '14d')  # the 12pm forecast, nearest 1pm
        self.assertEqual(summary['hours'][1]['hour'], 3)


class TemperatureTest(unittest.TestCase):
    def draw(self, temp, **options):
        w = weather(show='temperature', **options)
        return render_widget(w, context(now=NOW, weather={'icon': '01d', 'temp': temp}))[0]

    def test_draws_just_the_temperature(self):
        seventy_two, _ = render_widget(widget('text', text='72°', font='6x10'), context())
        self.assertEqual(lit(self.draw(72)), lit(seventy_two))

    def test_box_fits_three_digits_and_negatives_without_changing_size(self):
        sizes = {self.draw(t).size for t in (5, 72, 104, -12)}
        self.assertEqual(len(sizes), 1)
        self.assertLessEqual(sizes.pop()[0], 64)
        self.assertEqual(lit(self.draw(104)), lit(render_widget(widget('text', text='104°', font='6x10'), context())[0]))

    def test_align(self):
        # Lined up by the pixels it lights: the degree sign ends right at the box's edge
        for temp in (5, 72, -12, 104):
            left, right = self.draw(temp), self.draw(temp, align='right')
            self.assertEqual(left.getchannel('A').getbbox()[0], 0)
            self.assertEqual(right.getchannel('A').getbbox()[2], right.width)

    def test_blank_on_the_display_until_it_loads(self):
        image, _ = render_widget(weather(show='temperature'), context(now=NOW, weather=None))
        self.assertEqual(lit(image), 0)


class WeatherValuesTest(unittest.TestCase):
    WEATHER = {
        'icon': '01d', 'temp': 64, 'feels_like': 61, 'humidity': 82, 'wind_speed': 12, 'wind_deg': 300,
        'sunrise': datetime(2026, 11, 24, 6, 52).timestamp(), 'sunset': datetime(2026, 11, 24, 17, 1).timestamp(),
        'observed': {'date': '2026-11-24', 'high': 66, 'low': 48},
    }

    def value(self, show, hours='12'):
        from components import COMPONENTS
        ctx = context(now=NOW, weather=self.WEATHER)
        return COMPONENTS['weather'].value(show, self.WEATHER, None, ctx, hours)

    def test_values(self):
        self.assertEqual(self.value('temperature'), '64°')
        self.assertEqual(self.value('feels_like'), '61°')
        self.assertEqual(self.value('humidity'), '82%')
        self.assertEqual(self.value('high_low'), '66°/48°')
        self.assertEqual(self.value('sunrise'), '6:52')
        self.assertEqual(self.value('sunset'), '5:01')
        self.assertEqual(self.value('sunset', hours='24'), '17:01')
        self.assertEqual(self.value('wind'), '12 NW')

    def test_everything_it_can_show_fits_the_display(self):
        from components.weather import SHOW
        for show, _ in SHOW:
            for label in (False, True):
                ctx = context(now=NOW, weather=self.WEATHER, preview=True)
                image, _ = render_widget(weather(show=show, label=label), ctx)
                self.assertLessEqual(image.width, 64, show)
                self.assertLessEqual(image.height, 32, show)
                self.assertGreater(lit(image), 0, show)

    def test_label(self):
        plain, _ = render_widget(weather(show='feels_like'), context(now=NOW, weather=self.WEATHER))
        labeled, _ = render_widget(weather(show='feels_like', label=True), context(now=NOW, weather=self.WEATHER))
        self.assertGreater(labeled.width, plain.width)
        self.assertGreater(lit(labeled), lit(plain))

    def test_automatic_font_suits_what_it_shows(self):
        from components import COMPONENTS
        font = lambda **o: COMPONENTS['weather'].font(weather(**o)['options']).name
        self.assertEqual(font(show='temperature'), '6x10')
        self.assertEqual(font(show='humidity'), '5x7')
        self.assertEqual(font(show='forecast_hours'), '4x6')
        self.assertEqual(font(show='temperature', font='8x13B'), '8x13B')
        # A font picked for a value doesn't carry over to the forecast, and the other way round
        self.assertEqual(font(show='forecast_days', font='8x13B'), '4x6')
        self.assertEqual(font(show='humidity', forecast_font='6x10'), '5x7')


class OptionTest(unittest.TestCase):
    def test_new_kinds(self):
        self.assertEqual(Option('d', 'D', 'date', '2027-01-01').clean('2026-02-30'), '2027-01-01')
        self.assertEqual(Option('d', 'D', 'date', '2027-01-01').clean('2026-02-03'), '2026-02-03')
        self.assertEqual(Option('t', 'T', 'time', '00:00').clean('25:00'), '00:00')
        self.assertEqual(Option('t', 'T', 'time', '00:00').clean('07:30'), '07:30')
        self.assertEqual(Option('i', 'I', 'image', 'icons/01d').clean('uploads/../x'), 'icons/01d')
        self.assertEqual(Option('i', 'I', 'image', 'icons/01d').clean('uploads/ab12-cat'), 'uploads/ab12-cat')


if __name__ == '__main__':
    unittest.main()
