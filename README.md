## Managing the display

Open `http://<the Pi's address>:5000` in a browser on your network (for example http://192.168.1.31:5000). It has no login, so only run it on a network you trust.

- **Screens**: the display shows one screen at a time. Screens with "Take turns" on are shown in order, each for its time. "Show on display" puts the screen you're editing on now.
- **Components**: drag them from the list onto the display, then drag them around. Click one to change its settings (font, color, format, and so on). Arrow keys nudge it one LED at a time. There are clocks, the date, a countdown, the weather (now, details such as feels-like or sunset, and a forecast), text that can scroll, images and boxes.
- **Images**: drop an image file onto the display, or upload one in an Image component's settings. PNG, JPG, GIF and WebP work, and animated GIFs play on the display. The weather icons are there to use too, in any color.
- **Right-click** a component, an empty spot on the display, or a screen for shortcuts: copy and paste (also between screens), layer order, centering, hide, delete, or adding a component at that spot.
- **Live view**: the top bar shows what the display is showing right now, and has the brightness control.

Changes save as you make them, and the display picks them up right away. ⌘Z / Ctrl+Z undoes them. The editor previews are drawn by the same code that drives the LEDs, so they match the panel pixel for pixel.

The layout is saved in `data/display.json` and uploaded images in `data/images/`. Git ignores `data/`, so deploys don't touch it. Delete `data/display.json` to go back to the original layout (clock, date and weather).

The weather, weather details and forecast components all use the OpenWeatherMap settings in `.env`. Until weather has loaded, the editor shows sample weather so you can lay things out, and the display leaves those spots blank.

### Running it on your computer

You can run the dashboard without a Pi or LED panel to work on the page or try out layouts. Frames then only show in the page.

```bash
python3 -m venv .venv && .venv/bin/pip install flask pillow requests python-dotenv
```

```bash
LED_EMULATOR=1 PORT=5050 .venv/bin/python main.py
```

Then open http://localhost:5050. (On macOS port 5000 is taken by AirPlay.) Set `LED_LAYOUT_FILE=/some/file.json` to keep your experiments out of `data/`.

### Adding a component

Each component is a class in `components/` (see `components/base.py`). It says how big its box is and draws into a Pillow image of that size, and it lists its settings as `Option`s. The page builds its settings form from those, so a new component only needs its class added to `COMPONENTS` in `components/__init__.py`. Data that's slow to get, like the weather, goes in a `PollingSource` (see `components/weather.py`) so drawing never waits on the network.

Tests are in `tests/` and run before every deploy:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

## Setting up a Pi

Works on Raspberry Pi OS Bookworm or newer (the LED driver needs Python 3.11+). The same steps set up another Pi.

1. Clone this repo on the Pi as your normal user (not root).
2. Create `.env` in the project folder with your weather settings:

   ```
   OPENWEATHERMAP_API_KEY=your-key
   LAT=12.34
   LON=-56.78
   ```

3. From the project folder, run:

   ```bash
   sudo deploy/install.sh
   ```

`install.sh` installs the system packages it needs, installs `requirements.txt` into a venv (building the LED driver from the commit pinned there, which takes a few minutes), and starts the app. It's safe to re-run.

The app runs as root under supervisor, so the LED library can set up precise timing. Right after setup the app switches to the user who owns the project folder.

## The LED driver

The display uses [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix). It has no releases, so `requirements.txt` pins it to an exact commit, and every Pi builds that same commit.

To move to the latest upstream version, run this on your computer:

```bash
deploy/pin-driver.sh
```

It updates `requirements.txt` and prints a link to what changed upstream. Commit and push it like any other change. The Pi builds the new driver while the app keeps running, and rolls back if the app doesn't come up (see below). To pin a specific commit instead, pass its full SHA: `deploy/pin-driver.sh <sha>`.

The driver is compiled against the C headers of the Pillow version pinned in `requirements.txt` (its `SetImage()` reads Pillow's memory directly), so keep pillow pinned with `==`.

## Automatic deploys

`install.sh` also turns on automatic deploys: every 2 minutes the Pi checks GitHub, and when `main` has a new commit it:

1. installs its `requirements.txt` into a new venv, if that changed, while the app keeps running
2. tests it in a scratch copy: everything compiles, `main.py` imports, and unit tests in `tests/` pass (if that folder exists)
3. fast-forwards the checkout, switches to the new venv and restarts the app
4. checks `http://127.0.0.1:5000/health`, and rolls back to the previous commit and venv if the app doesn't come up

A commit that fails is skipped until something newer is pushed.

Each version of `requirements.txt` gets its own venv in `.venvs/`, and `.venv` is a link to the one in use. Deploys keep the current and previous venvs and delete older ones.

- Deploy logs: `journalctl -u led-deploy -f`
- App logs: `/var/log/led_matrix_dashboard.out.log` and `.err.log`
- Deploy right now: `sudo deploy/deploy.sh` (add `--force` to redeploy or retry a failed commit)
- Pause auto-deploys: `sudo systemctl disable --now led-deploy.timer`
