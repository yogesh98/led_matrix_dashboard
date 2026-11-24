#!/usr/bin/env bash
# Sets up a Pi to run the dashboard. Use it for a new Pi, and re-run it any time (it's safe).
#   - installs the system packages needed to build the LED driver and run the app
#   - installs requirements.txt into a venv, building the LED driver from the commit pinned there
#   - runs the app as root under supervisor, so the LED library can set up precise
#     timing (matrixbase.py switches back to the project's owner right after)
#   - turns on automatic deploys: a systemd timer runs deploy.sh every 2 minutes
#
# Usage: clone the project as your normal user, add a .env (see README), then from the project:
#   sudo deploy/install.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$REPO/deploy/common.sh"   # log, as_owner and the venv helpers
PROGRAM=led_matrix_dashboard
CONF=/etc/supervisor/conf.d/$PROGRAM.conf
# To build the LED driver (git, compiler, cmake, Python headers), make venvs, run the
# app under supervisor, and health-check it during deploys (curl)
APT_PACKAGES=(git build-essential cmake python3-dev python3-venv supervisor curl)

missing=()
for pkg in "${APT_PACKAGES[@]}"; do
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing+=("$pkg")
done
if (( ${#missing[@]} )); then
    log "Installing system packages: ${missing[*]}"
    apt-get update -qq
    # dpkg's progress lines go to stdout even with -qq; errors still show on stderr
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${missing[@]}" >/dev/null
fi

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo "The LED driver needs Python 3.11 or newer ($(python3 --version) here)." >&2
    echo "Use Raspberry Pi OS Bookworm or newer." >&2
    exit 1
fi
if [[ ! -f $REPO/.env ]]; then
    log "Warning: no $REPO/.env, so the weather won't load (see README)"
fi

# Wait for a deploy that's running, so we don't both change .venv at once
exec 9>/run/led-deploy.lock
flock -n 9 || { log "Waiting for a running deploy to finish"; flock 9; }

adopt_handmade_venv
old_venv=$(current_venv)
new_venv=$(venv_for "$REPO/requirements.txt")
if ! build_venv "$new_venv" "$REPO/requirements.txt"; then
    echo "Couldn't install requirements.txt (see the errors above)" >&2
    exit 1
fi
use_venv "$new_venv"

echo "Setting up supervisor program '$PROGRAM' ($CONF)"
[[ -f $CONF ]] && cp "$CONF" "$CONF.bak"
cat > "$CONF" <<EOF
[program:$PROGRAM]
command=$REPO/.venv/bin/python $REPO/main.py
directory=$REPO
; Root so the LED library can set up precise timing; matrixbase.py then
; switches to the user who owns $REPO
user=root
autostart=true
autorestart=true
; Unbuffered so prints reach the log right away; no .pyc files, so root
; doesn't leave root-owned files in the project
environment=PYTHONUNBUFFERED="1",PYTHONDONTWRITEBYTECODE="1"
stdout_logfile=/var/log/$PROGRAM.out.log
stderr_logfile=/var/log/$PROGRAM.err.log
EOF
supervisorctl reread
supervisorctl update   # starts the app, or restarts it if its config changed
if [[ $new_venv != "$old_venv" ]]; then
    supervisorctl restart "$PROGRAM"   # pick up the new packages
fi
prune_venvs "$new_venv" "$old_venv"

echo "Setting up automatic deploys (led-deploy.timer)"
cat > /etc/systemd/system/led-deploy.service <<EOF
[Unit]
Description=Deploy new commits of the LED matrix dashboard
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $REPO/deploy/deploy.sh
# Long enough to build a newly pinned LED driver on a slow Pi
TimeoutStartSec=30min
EOF

cat > /etc/systemd/system/led-deploy.timer <<EOF
[Unit]
Description=Check for new LED matrix dashboard commits every 2 minutes

[Timer]
OnBootSec=2min
OnUnitInactiveSec=2min

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now led-deploy.timer

cat <<EOF

Done. Pushes to main now deploy here automatically within ~2 minutes.
  Deploy logs:      journalctl -u led-deploy -f
  App logs:         /var/log/$PROGRAM.out.log, /var/log/$PROGRAM.err.log
  Deploy now:       sudo $REPO/deploy/deploy.sh
  Pause deploys:    sudo systemctl disable --now led-deploy.timer
EOF
