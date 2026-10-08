#!/bin/bash
# STAND-IN, written by the pipeline lane so tools/build_dmg.sh can run end to
# end before the native lane lands its real version. It keeps the contract and
# nothing more:
#
#   tools/build_native.sh OUT_DIR
#     -> OUT_DIR/Helpers/{dictator-hotkey,dictator-rec,dictator-paste,
#                         dictator-orb,dictator-readback,
#                         whisper-server,whisper-cli,parakeet-cli,
#                         Dictator Meeting.app}
#     -> OUT_DIR/Frameworks/*.dylib (may be empty)
#
# The Swift helpers are compiled for real, the same way swiftbuild.py does on
# the user's Mac today. whisper.cpp is NOT built from source here: the
# binaries are copied from the maintainer's Homebrew install and their
# libraries pulled into Frameworks with @rpath, which is enough to measure
# sizes and exercise signing, and not enough to ship. ggml's backends are
# loaded at run time from a directory Homebrew bakes in, so a copied
# whisper-cli may not find Metal from inside the bundle. The real script
# builds whisper.cpp at a pinned tag with static ggml and replaces all of this.
set -euo pipefail

OUT="${1:?usage: build_native.sh OUT_DIR}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="arm64-apple-macos14.0"

mkdir -p "$OUT/Helpers" "$OUT/Frameworks"

# name in Contents/Helpers, then the source under native/
for pair in dictator-hotkey:hotkey dictator-rec:record dictator-paste:paste \
            dictator-orb:orb dictator-readback:readback; do
    name="${pair%%:*}"; src="${pair#*:}"
    echo "  swiftc $src.swift -> $name"
    swiftc -O -target "$TARGET" "$ROOT/native/$src.swift" -o "$OUT/Helpers/$name"
done

# The meeting recorder is its own app because it holds its own permission
# (Screen Recording), under the name meeting.py already uses for it.
MEET="$OUT/Helpers/Dictator Meeting.app/Contents"
mkdir -p "$MEET/MacOS"
cp "$ROOT/native/meetingapp/Info.plist" "$MEET/Info.plist"
echo "  swiftc meeting.swift -> Dictator Meeting.app"
swiftc -O -target "arm64-apple-macos15.0" "$ROOT/native/meeting.swift" \
    -o "$MEET/MacOS/DictatorMeeting"

# --- whisper.cpp, borrowed from Homebrew (stand-in only) ---------------------
BREW_BIN="${BREW_BIN:-/opt/homebrew/bin}"

# Every library a binary loads that is not part of macOS.
foreign_deps() {
    otool -L "$1" | tail -n +2 | awk '{print $1}' \
        | grep -v -e '^/usr/lib/' -e '^/System/' || true
}

# A dependency named by @rpath, or by a Homebrew path, as a real file.
resolve_dep() {
    local dep="$1" from="$2"
    case "$dep" in
        @rpath/*)
            local base="${dep#@rpath/}" d
            for d in "$(dirname "$from")/../lib" /opt/homebrew/lib \
                     /opt/homebrew/opt/whisper-cpp/lib /opt/homebrew/opt/ggml/lib; do
                [ -e "$d/$base" ] && { echo "$d/$base"; return; }
            done ;;
        *) [ -e "$dep" ] && echo "$dep" ;;
    esac
}

# Copy the foreign libraries of $1 into Frameworks and point $1 at them.
# Repeats over what it copies, so libwhisper's own ggml dependencies land too.
pull_deps() {
    local file="$1" dep base real
    for dep in $(foreign_deps "$file"); do
        base="$(basename "$dep")"
        [ "$dep" = "@rpath/$base" ] && [ -e "$OUT/Frameworks/$base" ] && continue
        if [ ! -e "$OUT/Frameworks/$base" ]; then
            real="$(resolve_dep "$dep" "$file")"
            [ -n "$real" ] || { echo "  cannot find $dep for $file" >&2; exit 1; }
            cp -L "$real" "$OUT/Frameworks/$base"
            chmod u+w "$OUT/Frameworks/$base"
            install_name_tool -id "@rpath/$base" "$OUT/Frameworks/$base" 2>/dev/null
            pull_deps "$OUT/Frameworks/$base"
        fi
        install_name_tool -change "$dep" "@rpath/$base" "$file" 2>/dev/null
    done
}

for name in whisper-server whisper-cli parakeet-cli; do
    src="$BREW_BIN/$name"
    if [ ! -e "$src" ]; then
        echo "  $name not found in $BREW_BIN, left out" >&2
        continue
    fi
    real="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$src")"
    echo "  copy $name from Homebrew (stand-in)"
    cp "$real" "$OUT/Helpers/$name"
    chmod u+w "$OUT/Helpers/$name"
    pull_deps "$OUT/Helpers/$name"
    # Homebrew's rpath points at its own lib directory. Swap it for the
    # bundle's Frameworks, which sits beside Helpers in Contents.
    while read -r rp; do
        install_name_tool -delete_rpath "$rp" "$OUT/Helpers/$name" 2>/dev/null
    done < <(otool -l "$OUT/Helpers/$name" | awk '/LC_RPATH/{f=1} f&&/ path /{print $2; f=0}')
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$OUT/Helpers/$name" 2>/dev/null
done

# Same for the libraries, which find each other through @loader_path.
for lib in "$OUT"/Frameworks/*.dylib; do
    [ -e "$lib" ] || continue
    install_name_tool -add_rpath "@loader_path" "$lib" 2>/dev/null || true
done

echo "  native: $(ls "$OUT/Helpers" | wc -l | tr -d ' ') helpers, $(ls "$OUT/Frameworks" | wc -l | tr -d ' ') libraries"
