#!/usr/bin/env bash
# Build every native binary the app bundle carries, into OUT_DIR.
#
#   tools/build_native.sh OUT_DIR
#
# Leaves:
#   OUT_DIR/Helpers/dictator-hotkey, dictator-rec, dictator-paste, dictator-orb,
#                   dictator-readback        the Swift helpers, native/*.swift
#   OUT_DIR/Helpers/Dictator Meeting.app     the meeting recorder, its own bundle
#   OUT_DIR/Helpers/whisper-server, whisper-cli, parakeet-cli
#   OUT_DIR/Frameworks/                      empty when ggml links static
#
# Today the user's Mac compiles the helpers on first use (swiftbuild.py) and
# whisper comes from Homebrew. In the .dmg neither can be assumed, so this does
# both once, on the maintainer's Mac, and the binaries ship prebuilt.
#
# Nothing here installs anything. whisper.cpp is cloned and built under build/
# in this tree, keyed by its tag, so a rerun only redoes what changed.
#
# Environment:
#   DICTATOR_SIGN_ID     codesign identity, default "-" (ad-hoc). Everything
#                        is signed here so it runs straight out of OUT_DIR;
#                        build_dmg.sh signs again with the release identity.
#   DICTATOR_MIN_MACOS   deployment target, default 14.0: orb.swift uses
#                        CADisplayLink, which macOS 13 does not have.
#                        build_dmg.sh writes the same value into the app's
#                        LSMinimumSystemVersion. The meeting recorder is built
#                        for the floor its own Info.plist declares (15.0).
#   WHISPER_TAG          whisper.cpp release, default the pinned one below.

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 OUT_DIR" >&2
    exit 2
fi

REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$1"
OUT="$(cd "$1" && pwd)"
HELPERS="$OUT/Helpers"
FRAMEWORKS="$OUT/Frameworks"
mkdir -p "$HELPERS" "$FRAMEWORKS"

SIGN_ID="${DICTATOR_SIGN_ID:--}"
MIN_MACOS="${DICTATOR_MIN_MACOS:-14.0}"
TARGET="arm64-apple-macos$MIN_MACOS"

# Pinned to the release every number in docs/findings.md was measured on (the
# Homebrew 1.9.1 on this machine). The commit is checked as well as the tag,
# because a tag can be moved and a commit cannot.
WHISPER_TAG="${WHISPER_TAG:-v1.9.1}"
WHISPER_COMMIT_v1_9_1="f049fff95a089aa9969deb009cdd4892b3e74916"

BUILD="$REPO/build"
SRC_DIR="$BUILD/src/whisper.cpp-$WHISPER_TAG"
CMAKE_DIR="$BUILD/whisper.cpp-$WHISPER_TAG"

CMAKE="$(command -v cmake || true)"
[ -n "$CMAKE" ] || CMAKE=/opt/homebrew/bin/cmake
JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"

say() { echo "build_native: $*" >&2; }


# ---- Swift helpers ---------------------------------------------------------

# source file -> binary name. The names are the ones dictator/*.py looks for
# (hotkey.BIN, recorder.BIN, paste._HELPER, orbnative.BIN, readback.BIN).
SWIFT_HELPERS="
hotkey.swift   dictator-hotkey
record.swift   dictator-rec
paste.swift    dictator-paste
orb.swift      dictator-orb
readback.swift dictator-readback
"

# Rebuild when the source, or this script (its flags), is newer than the
# binary. Compiled beside the target and renamed over it, the same reason
# swiftbuild.py does: a half written binary is never left at the real path.
swift_build() {
    local src="$1" out="$2" target="${3:-$TARGET}"
    if [ -x "$out" ] && [ "$out" -nt "$src" ] && [ "$out" -nt "$0" ]; then
        return 0
    fi
    say "swiftc $(basename "$src") -> $(basename "$out")"
    swiftc -O -target "$target" "$src" -o "$out.new"
    mv -f "$out.new" "$out"
}

echo "$SWIFT_HELPERS" | while read -r src name; do
    [ -n "$src" ] || continue
    swift_build "$REPO/native/$src" "$HELPERS/$name"
done

# The meeting recorder is its own bundle so its Screen Recording grant lands on
# its own identifier (see meeting.py). Built the way meeting.build_app does:
# one swiftc, the Info.plist beside it. meeting.py rewrites the identifier per
# account at build time; a prebuilt bundle cannot know the account, so it
# ships with the identifier in native/meetingapp/Info.plist as is.
MEET="$HELPERS/Dictator Meeting.app"
mkdir -p "$MEET/Contents/MacOS"
MEET_MIN="$(plutil -extract LSMinimumSystemVersion raw "$REPO/native/meetingapp/Info.plist")"
swift_build "$REPO/native/meeting.swift" "$MEET/Contents/MacOS/DictatorMeeting" \
    "arm64-apple-macos$MEET_MIN"
cp -f "$REPO/native/meetingapp/Info.plist" "$MEET/Contents/Info.plist"


# ---- whisper.cpp -----------------------------------------------------------

if [ ! -d "$SRC_DIR/.git" ]; then
    say "fetching whisper.cpp $WHISPER_TAG"
    mkdir -p "$BUILD/src"
    rm -rf "$SRC_DIR"
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$WHISPER_TAG" \
        https://github.com/ggml-org/whisper.cpp "$SRC_DIR"
fi
want_var="WHISPER_COMMIT_$(echo "$WHISPER_TAG" | tr '.-' '__')"
want="${!want_var:-}"
have="$(git -C "$SRC_DIR" rev-parse HEAD)"
if [ -n "$want" ] && [ "$have" != "$want" ]; then
    say "whisper.cpp $WHISPER_TAG is $have, expected $want; refusing to build it"
    exit 1
fi
[ -n "$want" ] || say "warning: no pinned commit for $WHISPER_TAG, building $have unchecked"

# Static ggml, so nothing has to be found at run time: no Frameworks/, no
# install_name_tool. Metal on with the shader library embedded in the binary,
# because otherwise ggml looks for ggml-metal.metal next to the executable.
# GGML_NATIVE off: native means -mcpu of THIS Mac, which can emit instructions
# an older M series chip does not have. OpenMP off because CMake would find
# Homebrew's libomp and link /opt/homebrew into the result; the Homebrew
# prefixes are ignored outright for the same reason.
STAMP="$CMAKE_DIR/.dictator-built"
BINS="whisper-cli whisper-server parakeet-cli"
# The stamp holds the tag and the deployment target, not a date: on CI a fresh
# checkout makes this script newer than any cached build, and a date check
# would throw the cache away every time. Change the flags below, change STAMP_V.
STAMP_V=1
STAMP_KEY="$WHISPER_TAG $MIN_MACOS v$STAMP_V"
if [ "$(cat "$STAMP" 2>/dev/null)" != "$STAMP_KEY" ]; then
    say "building whisper.cpp $WHISPER_TAG (Metal, static ggml, macOS $MIN_MACOS)"
    "$CMAKE" -S "$SRC_DIR" -B "$CMAKE_DIR" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_OSX_ARCHITECTURES=arm64 \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="$MIN_MACOS" \
        -DCMAKE_IGNORE_PREFIX_PATH="/opt/homebrew;/usr/local" \
        -DBUILD_SHARED_LIBS=OFF \
        -DGGML_METAL=ON \
        -DGGML_METAL_EMBED_LIBRARY=ON \
        -DGGML_NATIVE=OFF \
        -DGGML_OPENMP=OFF \
        -DWHISPER_BUILD_EXAMPLES=ON \
        -DWHISPER_BUILD_SERVER=ON \
        -DWHISPER_BUILD_TESTS=OFF \
        -DWHISPER_SDL2=OFF \
        -DWHISPER_CURL=OFF \
        -DWHISPER_COREML=OFF >/dev/null
    "$CMAKE" --build "$CMAKE_DIR" --config Release -j "$JOBS" \
        --target $BINS >/dev/null
    echo "$STAMP_KEY" > "$STAMP"
fi

for b in $BINS; do
    if [ ! -x "$CMAKE_DIR/bin/$b" ]; then
        say "whisper.cpp $WHISPER_TAG did not produce $b"
        exit 1
    fi
    cp -f "$CMAKE_DIR/bin/$b" "$HELPERS/$b"
done

# Only reached if a future tag stops linking ggml static: any dylib the build
# left behind goes to Frameworks/ and the binaries are pointed at it.
shopt -s nullglob
dylibs=("$CMAKE_DIR"/bin/*.dylib "$CMAKE_DIR"/src/*.dylib "$CMAKE_DIR"/ggml/src/*.dylib "$CMAKE_DIR"/ggml/src/*/*.dylib)
shopt -u nullglob
if [ ${#dylibs[@]} -gt 0 ]; then
    say "whisper.cpp left dylibs, copying them into Frameworks/"
    for d in "${dylibs[@]}"; do
        n="$(basename "$d")"
        cp -fL "$d" "$FRAMEWORKS/$n"
        install_name_tool -id "@rpath/$n" "$FRAMEWORKS/$n"
    done
    for b in $BINS; do
        install_name_tool -add_rpath "@executable_path/../Frameworks" "$HELPERS/$b" 2>/dev/null || true
    done
fi


# ---- sign and check --------------------------------------------------------

# install_name_tool and the plist copy both break the linker's ad-hoc
# signature, and an arm64 binary with a broken signature is killed on launch.
for f in "$FRAMEWORKS"/*.dylib "$HELPERS"/*; do
    [ -e "$f" ] || continue
    codesign --force -s "$SIGN_ID" "$f" 2>/dev/null
done

# The point of all of this: a binary that still points into Homebrew works on
# this Mac and on no one else's.
bad=0
for f in "$HELPERS"/* "$MEET/Contents/MacOS/DictatorMeeting" "$FRAMEWORKS"/*.dylib; do
    [ -f "$f" ] || continue
    if otool -L "$f" | tail -n +2 | grep -E -q '/opt/homebrew|/usr/local'; then
        say "$(basename "$f") links outside the system:"
        otool -L "$f" | grep -E '/opt/homebrew|/usr/local' >&2
        bad=1
    fi
done
[ "$bad" = 0 ] || exit 1

say "done, in $OUT"
