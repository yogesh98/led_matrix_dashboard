#!/usr/bin/env bash
# Continuous deployment for the LED matrix dashboard. Runs on the Pi itself.
#
# Each run checks GitHub for new commits on main. If there is one, it:
#   1. tests it in a scratch copy: everything compiles, main.py imports, and
#      unit tests in tests/ pass (if that folder exists)
#   2. fast-forwards this checkout to it and restarts the app under supervisor
#   3. checks the app comes back up healthy, and rolls back if it doesn't
# A commit that fails is skipped until something newer is pushed (or --force).
#
# install.sh sets up a systemd timer that runs this every 2 minutes. By hand:
#   sudo deploy/deploy.sh            deploy if main has new commits
#   sudo deploy/deploy.sh --force    redeploy even if up to date, or retry a failed commit
# Logs from the timer: journalctl -u led-deploy

set -euo pipefail
PATH=$PATH:/usr/sbin:/sbin   # runuser lives here; not on every user's PATH

BRANCH=main
PROGRAM=led_matrix_dashboard                 # supervisor program name
HEALTH_URL=http://127.0.0.1:5000/health
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-60}         # seconds to wait for the app to come up
SCRATCH=""

log() { echo "[$(date '+%F %T')] $*"; }

# git, pip and the checks run as whoever owns the checkout, so nothing in it ends up owned by root
as_owner() { runuser -u "$OWNER" -- env HOME="$OWNER_HOME" "$@"; }

fail() {
    as_owner git config deploy.failedcommit "$1"   # don't retry this commit every 2 minutes
    log "$2"
    exit 1
}

run_checks() {
    local dir=$1 current=$2 target=$3
    if ! as_owner git diff --quiet "$current" "$target" -- requirements.txt; then
        log "requirements.txt changed; installing"
        as_owner "$REPO/.venv/bin/pip" install --quiet -r "$dir/requirements.txt" || return 1
    fi
    log "Check: everything compiles"
    as_owner "$PY" -m compileall -q "$dir" || return 1
    log "Check: main.py imports"
    as_owner env -C "$dir" "$PY" -c "import main" || return 1
    if [[ -d $dir/tests ]]; then
        log "Check: unit tests"
        as_owner env -C "$dir" "$PY" -m unittest discover -s tests -t . || return 1
    fi
}

wait_healthy() {
    local deadline=$((SECONDS + HEALTH_TIMEOUT))
    while (( SECONDS < deadline )); do
        if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
            sleep 5   # make sure it stays up past the first few frames
            curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1 && return 0
        fi
        sleep 2
    done
    return 1
}

main() {
    local force=0
    [[ ${1:-} == --force ]] && force=1
    if [[ $EUID -ne 0 ]]; then
        echo "Run as root: sudo $0 $*" >&2
        exit 1
    fi

    REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
    OWNER=$(stat -c %U "$REPO")
    OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
    PY=$REPO/.venv/bin/python
    cd "$REPO"

    # Only one deploy at a time (the timer and a manual run could overlap)
    exec 9>/run/led-deploy.lock
    flock -n 9 || { log "Another deploy is already running"; exit 0; }

    if ! as_owner timeout 60 git fetch --quiet origin "$BRANCH"; then
        log "Couldn't reach GitHub; will try again next run"
        exit 0
    fi
    local current target
    current=$(as_owner git rev-parse HEAD)
    target=$(as_owner git rev-parse "origin/$BRANCH")

    if (( ! force )); then
        [[ $current == "$target" ]] && exit 0                      # nothing new
        [[ $target == "$(as_owner git config --get deploy.failedcommit || true)" ]] && exit 0   # already failed
    fi

    if [[ $(as_owner git symbolic-ref --short HEAD) != "$BRANCH" ]]; then
        log "Not deploying: $REPO isn't on $BRANCH"
        exit 1
    fi
    if [[ -n $(as_owner git status --porcelain --untracked-files=no) ]]; then
        log "Not deploying: $REPO has local changes (see git status there)"
        exit 1
    fi
    if ! as_owner git merge-base --is-ancestor HEAD "$target"; then
        log "Not deploying: local $BRANCH has commits that aren't on GitHub"
        exit 1
    fi

    log "New commit ${target:0:7}: $(as_owner git log -1 --format=%s "$target")"
    SCRATCH=$(mktemp -d /tmp/led-deploy.XXXXXX)
    trap 'rm -rf "$SCRATCH"' EXIT
    chown "$OWNER" "$SCRATCH"
    as_owner git archive "$target" | as_owner tar -x -C "$SCRATCH"
    if ! run_checks "$SCRATCH" "$current" "$target"; then
        fail "$target" "Checks failed for ${target:0:7}; not deploying it"
    fi

    log "Deploying ${target:0:7} (was ${current:0:7})"
    as_owner git merge --ff-only --quiet "$target"
    supervisorctl restart "$PROGRAM" >/dev/null || true   # wait_healthy decides if it worked
    if wait_healthy; then
        as_owner git config --unset deploy.failedcommit || true
        log "Deployed ${target:0:7}"
        exit 0
    fi

    log "App didn't come up healthy; rolling back to ${current:0:7}"
    as_owner git reset --hard --quiet "$current"
    supervisorctl restart "$PROGRAM" >/dev/null || true
    if wait_healthy; then
        log "Rolled back; app is healthy again"
    else
        log "Rolled back, but the app still isn't healthy; see /var/log/$PROGRAM.err.log"
    fi
    fail "$target" "Deploy of ${target:0:7} failed"
}

# Everything runs inside main() so bash has read the whole script before
# a deploy rewrites this file
main "$@"; exit
