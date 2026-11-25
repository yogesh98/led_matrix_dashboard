"""Prebuilt screens: ready-made layouts you can add from the management page's + menu.

Once added, a prebuilt screen is an ordinary screen: everything on it can be moved,
changed or deleted, and changing it doesn't change the prebuilt one. They're laid out
for a 64x32 display.

Each is a name, a short description and the widgets to put on the new screen, in the
same form as the layout file (see layout.py). Options left out get their defaults.
"""
from layout import normalize_widget

PREBUILT = [
    {
        'id': 'blossom',
        'name': 'Cherry blossom',
        'description': 'The time and temperature under a cherry tree, with drifting petals',
        'widgets': [
            {'type': 'scene', 'x': 0, 'y': 0, 'options': {'theme': 'blossom'}},
            {'type': 'time', 'x': 1, 'y': 1, 'options': {'font': '7x13B', 'color': '#ffffff', 'outline': True}},
            {'type': 'weather', 'x': 1, 'y': 14,
             'options': {'show': 'temperature', 'font': '5x7', 'color': '#ffc4d8', 'outline': True}},
        ],
    },
    {
        'id': 'lake',
        'name': 'Mountain lake',
        'description': 'The time and temperature over snowy peaks and a lake that reflects the sky',
        'widgets': [
            {'type': 'scene', 'x': 0, 'y': 0, 'options': {'theme': 'lake'}},
            {'type': 'time', 'x': 1, 'y': 1, 'options': {'font': '7x13B', 'color': '#ffffff', 'outline': True}},
            {'type': 'weather', 'x': 35, 'y': 1,
             'options': {'show': 'temperature', 'align': 'right', 'font': '5x7', 'color': '#cfe8ff', 'outline': True}},
        ],
    },
    {
        'id': 'city',
        'name': 'City skyline',
        'description': 'The time and temperature over a skyline whose windows light up after dark',
        'widgets': [
            {'type': 'scene', 'x': 0, 'y': 0, 'options': {'theme': 'city'}},
            {'type': 'time', 'x': 1, 'y': 1, 'options': {'font': '7x13B', 'color': '#ffffff', 'outline': True}},
            {'type': 'weather', 'x': 42, 'y': 1,
             'options': {'show': 'temperature', 'align': 'right', 'font': '5x7', 'color': '#ffd58a', 'outline': True}},
        ],
    },
    {
        'id': 'skogafoss',
        'name': 'Skógafoss',
        'description': "Hours over minutes by Iceland's great waterfall, with rainbows by day and the northern lights at night",
        'widgets': [
            {'type': 'scene', 'x': 0, 'y': 0, 'options': {'theme': 'skogafoss'}},
            {'type': 'clock', 'x': 1, 'y': 1, 'options': {'font': '8x13B', 'color': '#ffffff', 'outline': True}},
            {'type': 'weather', 'x': 37, 'y': 20,
             'options': {'show': 'temperature', 'align': 'right', 'font': '6x10', 'color': '#c8f0ff', 'outline': True}},
        ],
    },
    {
        'id': 'dynjandi',
        'name': 'Dynjandi',
        'description': "The time and temperature by the Westfjords' great fan of a waterfall, with sheep on its ledges by day and the northern lights at night",
        'widgets': [
            {'type': 'scene', 'x': 0, 'y': 0, 'options': {'theme': 'dynjandi'}},
            {'type': 'time', 'x': 1, 'y': 1, 'options': {'font': '7x13B', 'color': '#ffffff', 'outline': True}},
            {'type': 'weather', 'x': 1, 'y': 14,
             'options': {'show': 'temperature', 'font': '5x7', 'color': '#c6f0d2', 'outline': True}},
        ],
    },
]


def prebuilt_screens():
    """The prebuilt screens with every widget's options filled in, as screens (see layout.py)"""
    screens = []
    for template in PREBUILT:
        widgets = [normalize_widget({**w, 'id': f"{template['id']}-{i}"}) for i, w in enumerate(template['widgets'])]
        screens.append({
            'id': template['id'],
            'name': template['name'],
            'description': template['description'],
            'duration': 15,
            'enabled': True,
            'widgets': widgets,
        })
    return screens
