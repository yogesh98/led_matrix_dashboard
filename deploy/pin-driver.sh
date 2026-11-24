#!/usr/bin/env bash
# Pins the LED driver (hzeller/rpi-rgb-led-matrix) in requirements.txt to an exact commit.
# The driver has no releases, so a commit is the only way to say which version to use.
#
# Run it on your computer, then commit and push requirements.txt. The Pi builds the new
# driver on its next deploy, and rolls back if the app doesn't come up healthy.
#
#   deploy/pin-driver.sh              pin to the latest commit on upstream master
#   deploy/pin-driver.sh <commit>     pin to a specific commit (its full 40-character SHA)

set -euo pipefail

DRIVER_REPO=https://github.com/hzeller/rpi-rgb-led-matrix
REQS=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/requirements.txt

if [[ $# -gt 0 ]]; then
    new=$1
    if ! [[ $new =~ ^[0-9a-f]{40}$ ]]; then
        echo "Give the commit's full 40-character SHA (on GitHub: the copy button next to it)" >&2
        exit 1
    fi
else
    new=$(git ls-remote "$DRIVER_REPO" refs/heads/master | cut -f1)
    if [[ -z $new ]]; then
        echo "Couldn't look up the latest commit of $DRIVER_REPO" >&2
        exit 1
    fi
fi

old=$(sed -n 's|^rgbmatrix @ git+.*@\([0-9a-f]\{40\}\).*|\1|p' "$REQS")
if [[ $old == "$new" ]]; then
    echo "The LED driver is already pinned to ${new:0:10}"
    exit 0
fi

# Replace the rgbmatrix line (or add one), leaving the rest of the file as it is
line="rgbmatrix @ git+$DRIVER_REPO@$new"
updated=$(awk -v line="$line" '
    /^rgbmatrix @/ { if (!done) print line; done = 1; next }
    { print }
    END { if (!done) print line }
' "$REQS")
printf '%s\n' "$updated" > "$REQS"

if [[ -n $old ]]; then
    echo "Pinned the LED driver to ${new:0:10} (was ${old:0:10})"
    echo "Upstream changes: $DRIVER_REPO/compare/$old...$new"
else
    echo "Pinned the LED driver to ${new:0:10}"
fi
echo "Next: commit and push requirements.txt. The Pi builds the new driver on its next deploy."
