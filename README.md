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
