#!/bin/sh
# Build the Dictator app executable: tools/build_app.sh OUT_DIR -> OUT_DIR/Dictator
#
# Every .swift file in native/app, compiled together with swiftc, for Apple
# silicon. No Xcode project: the app is a handful of files and swiftc is what
# already builds the five helpers. Assembling the bundle around it and signing
# it are tools/build_dmg.sh's job, not this one's.
#
# Run the result with DICTATOR_FAKE=1 to see the windows against the canned
# data in native/app/Fixtures, without starting dictation.
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

# 13.0 is LSMinimumSystemVersion in native/app/Info.plist, and the oldest
# macOS with NavigationSplitView and SMAppService.
swiftc -O \
    -target arm64-apple-macos13.0 \
    -module-name Dictator \
    "$ROOT"/native/app/*.swift \
    -o "$OUT/Dictator"

echo "$OUT/Dictator"
