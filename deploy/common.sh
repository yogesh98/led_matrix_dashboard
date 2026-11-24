# Shared by install.sh and deploy.sh, which source it after setting REPO.
#
# Python packages live in one venv per version of requirements.txt, in .venvs/, and
# .venv is a symlink to the one in use. Building the next venv never touches the one
# the app is running from, and rolling back is just pointing .venv back at the old one.

VENVS=$REPO/.venvs
OWNER=$(stat -c %U "$REPO")
OWNER_GID=$(id -g "$OWNER")
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)

log() { echo "[$(date '+%F %T')] $*"; }

# git, pip and the checks run as whoever owns the checkout, so nothing in it ends up owned by root.
# (setpriv rather than runuser: runuser logs a login session to the journal on every call)
as_owner() { setpriv --reuid="$OWNER" --regid="$OWNER_GID" --init-groups env HOME="$OWNER_HOME" "$@"; }

# The venv for requirements file $1, named after a hash of the file and the Python
# version (so an OS upgrade to a newer Python gets fresh venvs)
venv_for() {
    echo "$VENVS/$({ cat "$1"; python3 --version; } | sha256sum | cut -c1-12)"
}

# The LED driver's SetImage() reads Pillow's image data straight from memory, so the
# driver has to be compiled against the C headers of the same Pillow version the venv
# runs (Pillow 12 changed that layout). Upstream's build picks up whatever Pillow headers
# the OS has, so instead this downloads the ones for the pillow pinned in requirements
# file $1 into folder $2, following their #includes.
fetch_pillow_headers() {
    local reqs=$1 dir=$2 version base file inc todo
    version=$(sed -n 's/^[Pp]illow *== *\([0-9][0-9.]*\).*/\1/p' "$reqs")
    if [[ -z $version ]]; then
        log "requirements.txt has to pin pillow to an exact version (pillow == x.y.z): the LED driver is built against its headers"
        return 1
    fi
    base=https://raw.githubusercontent.com/python-pillow/Pillow/$version/src/libImaging
    todo=(Imaging.h)
    as_owner mkdir -p "$dir"
    while (( ${#todo[@]} )); do
        file=${todo[0]}
        todo=("${todo[@]:1}")
        [[ -f $dir/$file ]] && continue
        as_owner curl -fsS --retry 3 -o "$dir/$file" "$base/$file" || return 1
        for inc in $(sed -n 's/^#include "\(.*\)"/\1/p' "$dir/$file"); do
            [[ $inc == Python.h ]] || todo+=("$inc")
        done
    done
}

# Builds venv $1 from requirements file $2, unless it's already built
build_venv() {
    local venv=$1 reqs=$2
    [[ -f $venv/.complete ]] && return 0
    log "Installing requirements.txt into .venvs/${venv##*/} (building the LED driver takes a few minutes)"
    rm -rf "$venv"
    as_owner mkdir -p "$VENVS"
    # CPATH puts the Pillow headers ahead of any the OS has. --no-cache-dir because pip
    # would otherwise reuse a driver it built against an older Pillow's headers.
    if as_owner python3 -m venv "$venv" &&
        fetch_pillow_headers "$reqs" "$venv/pillow-headers" &&
        as_owner CPATH="$venv/pillow-headers" "$venv/bin/pip" install --quiet \
            --disable-pip-version-check --no-cache-dir -r "$reqs"; then
        as_owner touch "$venv/.complete"
        return 0
    fi
    rm -rf "$venv"
    return 1
}

# The venv .venv points at (empty if there isn't one)
current_venv() {
    if [[ -L $REPO/.venv ]]; then readlink -f "$REPO/.venv"; fi
}

# Points .venv at venv $1, swapping the symlink in one step so it's never missing
use_venv() {
    as_owner ln -sfn ".venvs/${1##*/}" "$REPO/.venv.new"
    mv -T "$REPO/.venv.new" "$REPO/.venv"
}

# Before .venvs/ existed, .venv was a folder set up by hand. Moves it into .venvs/ and
# points .venv at it, so the app keeps running as it was and a rollback can return to it.
adopt_handmade_venv() {
    [[ -d $REPO/.venv && ! -L $REPO/.venv ]] || return 0
    local dest=$VENVS/handmade
    [[ -e $dest ]] && dest=$VENVS/handmade-$(date +%s)
    log "Moving the existing .venv to .venvs/${dest##*/}"
    as_owner mkdir -p "$VENVS"
    mv "$REPO/.venv" "$dest"
    use_venv "$dest"
}

# Deletes every venv except the ones given
prune_venvs() {
    local venv keep
    for venv in "$VENVS"/*; do
        [[ -d $venv ]] || continue
        for keep in "$@"; do
            [[ -n $keep && ${venv##*/} == "${keep##*/}" ]] && continue 2
        done
        log "Removing the old .venvs/${venv##*/}"
        rm -rf "$venv"
    done
}
