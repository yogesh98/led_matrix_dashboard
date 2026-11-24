#!/usr/bin/env bash
# One-time setup on the Pi (safe to re-run):
#   - runs the app as root under supervisor, so the LED library can set up precise
#     timing (matrixbase.py switches back to the project's owner right after)
#   - turns on automatic deploys: a systemd timer runs deploy.sh every 2 minutes
#
# Usage: sudo deploy/install.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PROGRAM=led_matrix_dashboard
CONF=/etc/supervisor/conf.d/$PROGRAM.conf

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
supervisorctl update   # restarts the app if its config changed

echo "Setting up automatic deploys (led-deploy.timer)"
cat > /etc/systemd/system/led-deploy.service <<EOF
[Unit]
Description=Deploy new commits of the LED matrix dashboard
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $REPO/deploy/deploy.sh
TimeoutStartSec=10min
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
