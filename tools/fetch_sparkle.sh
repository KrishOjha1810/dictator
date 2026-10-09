#!/usr/bin/env bash
# Fetch Sparkle once into build/cache/sparkle and print that directory.
#
#   SPARKLE=$(tools/fetch_sparkle.sh)
#
# One place for the version and its SHA256 (GitHub's published digest for the
# release archive), used by build_app.sh to link the updater and by appcast.sh
# to sign updates, so the two can never use different Sparkles.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPARKLE_VERSION="2.10.0"
SPARKLE_SHA256="c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c"
DIR="$ROOT/build/cache/sparkle"
TAR="$ROOT/build/cache/Sparkle-$SPARKLE_VERSION.tar.xz"

if [ ! -d "$DIR/Sparkle.framework" ] || [ ! -x "$DIR/bin/sign_update" ]; then
    mkdir -p "$ROOT/build/cache"
    if [ ! -f "$TAR" ]; then
        curl -fsSL -o "$TAR.part" \
            "https://github.com/sparkle-project/Sparkle/releases/download/$SPARKLE_VERSION/Sparkle-$SPARKLE_VERSION.tar.xz"
        mv "$TAR.part" "$TAR"
    fi
    got=$(shasum -a 256 "$TAR" | awk '{print $1}')
    if [ "$got" != "$SPARKLE_SHA256" ]; then
        echo "Sparkle archive SHA256 mismatch: $got" >&2
        rm -f "$TAR"
        exit 1
    fi
    rm -rf "$DIR"
    mkdir -p "$DIR"
    tar -xJf "$TAR" -C "$DIR"
fi
echo "$DIR"
