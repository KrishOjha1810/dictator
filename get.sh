#!/usr/bin/env bash
# One line to install dictator:
#
#   curl -fsSL https://raw.githubusercontent.com/KrishOjha1810/dictator/main/get.sh | bash
#
# This exists because "git clone, then cd, then run a script" is three steps
# and two of them are bookkeeping. It does nothing the three steps did not do,
# and it is safe to run again: an existing checkout is updated rather than
# replaced, so nothing you have changed is thrown away without warning.
set -euo pipefail

REPO="https://github.com/KrishOjha1810/dictator.git"
DIR="${DICTATOR_DIR:-$HOME/dictator}"

if [ "$(uname)" != "Darwin" ]; then
  echo "dictator is macOS only: the held key, the indicator and the login item"
  echo "are all macOS specific."
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is needed to fetch dictator. macOS offers it through:"
  echo "  xcode-select --install"
  exit 1
fi

if [ -d "$DIR/.git" ]; then
  echo "Updating the copy already in $DIR"
  git -C "$DIR" pull --ff-only || {
    echo
    echo "Could not fast-forward $DIR, which means it has local changes."
    echo "Nothing was touched. Sort that out, or set DICTATOR_DIR to install"
    echo "somewhere else."
    exit 1
  }
elif [ -e "$DIR" ]; then
  echo "$DIR exists and is not a git checkout. Nothing was touched."
  echo "Move it aside, or set DICTATOR_DIR to install somewhere else."
  exit 1
else
  echo "Fetching dictator into $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi

exec "$DIR/install.sh"
