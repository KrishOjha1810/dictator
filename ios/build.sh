#!/usr/bin/env bash
# Generate the Xcode project and build it.
#
#   ios/build.sh            build for the simulator (no Apple account needed)
#   ios/build.sh device     build for a connected phone (needs a team id)
#
# The simulator build proves it compiles. It cannot answer the question this
# target exists for, because a simulator has no microphone sandbox of its own
# and will happily do things a real extension is refused.
set -euo pipefail
cd "$(dirname "$0")"

if ! xcodebuild -version >/dev/null 2>&1; then
    cat >&2 <<'MSG'
Xcode is not installed, only the Command Line Tools.

  1. Install Xcode from the App Store (it is large, about 10GB).
  2. sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  3. Run this script again.

Nothing else here needs it: the sources are complete and the project file is
generated from project.yml.
MSG
    exit 1
fi

if ! command -v xcodegen >/dev/null 2>&1; then
    echo "xcodegen is missing. Installing it with Homebrew."
    brew install xcodegen
fi

[ -f team.xcconfig ] || cp team.xcconfig.example team.xcconfig

xcodegen generate

TARGET="${1:-simulator}"
if [ "$TARGET" = "device" ]; then
    if ! grep -qE '^DEVELOPMENT_TEAM *= *[A-Z0-9]' team.xcconfig; then
        echo "Set DEVELOPMENT_TEAM in ios/team.xcconfig first (a free Apple ID works)." >&2
        exit 1
    fi
    xcodebuild -project Dictator.xcodeproj -scheme Dictator \
        -destination 'generic/platform=iOS' build
else
    # Whichever iPhone simulator is installed, newest first. Hard-coding a
    # model name is the usual reason a build script stops working.
    DEST=$(xcrun simctl list devices available \
        | grep -oE 'iPhone [0-9A-Za-z ]+\(' | tr -d '(' | tail -1 | sed 's/ *$//')
    [ -n "$DEST" ] || { echo "No iPhone simulator installed." >&2; exit 1; }
    echo "Building for $DEST"
    xcodebuild -project Dictator.xcodeproj -scheme Dictator \
        -destination "platform=iOS Simulator,name=$DEST" build
fi
