Install library - https://github.com/hzeller/rpi-rgb-led-matrix/tree/master
create venv and install python bindings inside the venv - https://github.com/hzeller/rpi-rgb-led-matrix/tree/master/bindings/python

## Running and deploying on the Pi

One-time setup (safe to re-run), from the project folder on the Pi:

```bash
sudo deploy/install.sh
```

This runs the app under supervisor as root, so the LED library can set up precise timing. Right after setup the app switches to the user who owns the project folder. It also turns on automatic deploys: every 2 minutes the Pi checks GitHub, and when `main` has a new commit it:

1. tests it in a scratch copy: everything compiles, `main.py` imports, and unit tests in `tests/` pass (if that folder exists)
2. fast-forwards the checkout and restarts the app
3. checks `http://127.0.0.1:5000/health`, and rolls back to the previous commit if the app doesn't come up

A commit that fails is skipped until something newer is pushed.

- Deploy logs: `journalctl -u led-deploy -f`
- App logs: `/var/log/led_matrix_dashboard.out.log` and `.err.log`
- Deploy right now: `sudo deploy/deploy.sh` (add `--force` to redeploy or retry a failed commit)
- Pause auto-deploys: `sudo systemctl disable --now led-deploy.timer`
