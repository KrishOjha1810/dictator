#!/usr/bin/env bash
# Build the Dictator app executable: tools/build_app.sh OUT_DIR -> OUT_DIR/Dictator
#
# Every .swift file in native/app, compiled together with swiftc, for Apple
# silicon. No Xcode project: the app is a handful of files and swiftc is what
# already builds the five helpers. Assembling the bundle around it and signing
# it are tools/build_dmg.sh's job, not this one's.
#
# Run the result with DICTATOR_FAKE=1 to see the windows against the canned
# data, without starting dictation. A bare binary needs
# DICTATOR_FIXTURES=native/app/Fixtures; inside a bundle they are in
# Contents/Resources/Fixtures. In fake mode only, for looking at one screen:
#   DICTATOR_SHOW=home|words|snippets|style|review|meetings|settings|help|move
#   DICTATOR_ONBOARDING=1 DICTATOR_CARD=0..5
#   DICTATOR_SNAPSHOT=out.png   draw the front window into a PNG, then quit
#                               (needs no Screen Recording permission)
#
# The app icon is drawn by tools/make_icon.swift into native/app/AppIcon.icns,
# which tools/build_dmg.sh copies into the bundle.
#
# Plain swiftc from the Command Line Tools has no SwiftUI macro plugin, so the
# views avoid @State (a macro in the macOS 27 SDK); see the top of Hub.swift.
set -eu

if [ $# -ne 1 ]; then
    echo "usage: tools/build_app.sh OUT_DIR" >&2
    exit 2
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$1
mkdir -p "$OUT"

# The same floor as the helpers (tools/build_native.sh): 14.0, because the orb
# helper needs CADisplayLink. The app itself would run on 13, the oldest macOS
# with NavigationSplitView and SMAppService, but not usefully without its orb.
MIN_MACOS=${DICTATOR_MIN_MACOS:-14.0}
# Sparkle, the updater (native/app/Updater.swift). Fetched once into the
# build cache and checked against the digest GitHub publishes for the
# release. Without it the app still builds and Updater does nothing, which is
# what a repo install wants.
SPARKLE_VERSION="2.10.0"
SPARKLE_SHA256="c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c"
SPARKLE_DIR="$ROOT/build/cache/sparkle"
SPARKLE_TAR="$ROOT/build/cache/Sparkle-$SPARKLE_VERSION.tar.xz"
if [ "${DICTATOR_NO_SPARKLE:-}" != "1" ] && [ ! -d "$SPARKLE_DIR/Sparkle.framework" ]; then
    mkdir -p "$ROOT/build/cache"
    if [ ! -f "$SPARKLE_TAR" ]; then
        curl -fsSL -o "$SPARKLE_TAR.part" \
            "https://github.com/sparkle-project/Sparkle/releases/download/$SPARKLE_VERSION/Sparkle-$SPARKLE_VERSION.tar.xz"
        mv "$SPARKLE_TAR.part" "$SPARKLE_TAR"
    fi
    got=$(shasum -a 256 "$SPARKLE_TAR" | awk '{print $1}')
    if [ "$got" != "$SPARKLE_SHA256" ]; then
        echo "Sparkle archive SHA256 mismatch: $got" >&2
        rm -f "$SPARKLE_TAR"
        exit 1
    fi
    mkdir -p "$SPARKLE_DIR"
    tar -xJf "$SPARKLE_TAR" -C "$SPARKLE_DIR"
fi
SPARKLE_FLAGS=()
if [ "${DICTATOR_NO_SPARKLE:-}" != "1" ] && [ -d "$SPARKLE_DIR/Sparkle.framework" ]; then
    # Found next to the executable in OUT (for fake-mode runs of the bare
    # binary) and in ../Frameworks inside the app.
    SPARKLE_FLAGS=(-F "$SPARKLE_DIR" -framework Sparkle
                   -Xlinker -rpath -Xlinker @executable_path/../Frameworks
                   -Xlinker -rpath -Xlinker @executable_path)
    rm -rf "$OUT/Sparkle.framework"
    cp -R "$SPARKLE_DIR/Sparkle.framework" "$OUT/Sparkle.framework"
fi

swiftc -O \
    -target "arm64-apple-macos$MIN_MACOS" \
    -module-name Dictator \
    "$ROOT"/native/app/*.swift \
    ${SPARKLE_FLAGS[@]+"${SPARKLE_FLAGS[@]}"} \
    -o "$OUT/Dictator"

echo "$OUT/Dictator"
