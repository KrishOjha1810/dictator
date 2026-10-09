#!/bin/sh
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
swiftc -O \
    -target "arm64-apple-macos$MIN_MACOS" \
    -module-name Dictator \
    "$ROOT"/native/app/*.swift \
    -o "$OUT/Dictator"

echo "$OUT/Dictator"
