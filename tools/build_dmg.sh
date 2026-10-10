#!/bin/bash
# Build Dictator.app and the .dmg it ships in, end to end, on the maintainer's
# Mac or on CI. Nothing here installs anything outside build/.
#
#   tools/build_dmg.sh [VERSION]  ->  build/Dictator-<VERSION>.dmg
#
# The order of the steps matters for one reason: signing. A signature covers the bytes of
# everything nested inside, so the innermost code is signed first and the app
# last. Anything changed after its parent was signed breaks the parent.
#
# Environment:
#   DICTATOR_SIGN_ID     codesign identity. "-" (the default) is ad-hoc, which
#                        runs here and nowhere else useful; a release uses the
#                        one self-signed "Dictator Release" certificate, so
#                        Microphone and Accessibility grants survive updates.
#   DICTATOR_NATIVE_DIR  prebuilt output of tools/build_native.sh (CI builds it
#                        in a job of its own). Unset: built here.
#   DICTATOR_APP_DIR     prebuilt output of tools/build_app.sh. Unset: built here.
#   DICTATOR_BUILD_NUMBER  CFBundleVersion. Unset: the commit count.
#   DICTATOR_MIN_MACOS   oldest macOS, default 14.0. Passed on to the two build
#                        scripts and written into LSMinimumSystemVersion.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
CACHE="$BUILD/cache"
STAGE="$BUILD/stage"
APP="$STAGE/Dictator.app"
C="$APP/Contents"
SIGN_ID="${DICTATOR_SIGN_ID:--}"
MIN_MACOS="${DICTATOR_MIN_MACOS:-14.0}"
export DICTATOR_MIN_MACOS="$MIN_MACOS"

VERSION="${1:-$(git -C "$ROOT" describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')}"
VERSION="${VERSION:-0.0.0}"
BUILD_NUMBER="${DICTATOR_BUILD_NUMBER:-$(git -C "$ROOT" rev-list --count HEAD 2>/dev/null || echo 1)}"

# --- pinned inputs -----------------------------------------------------------
# python-build-standalone, the stripped install-only CPython for Apple silicon.
# The SHA256 was computed from the downloaded file and matches the release's
# own SHA256SUMS. Moving to another release means changing all three lines and
# checking the new sum the same way, not deleting the check.
PY_RELEASE="20260924"
PY_VERSION="3.12.14"
PY_SHA256="c2edb321cd32ec2b170df208db0446dccc4398db602ca27cf2079098fb1f7d9d"
PY_FILE="cpython-${PY_VERSION}+${PY_RELEASE}-aarch64-apple-darwin-install_only_stripped.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RELEASE}/${PY_FILE//+/%2B}"

# The one third-party Python package. vocab.py degrades without it, so a
# bundle that silently lost it would still run, and match names worse.
# Pinned by the hash of the one wheel this runtime takes (cp312, macOS arm64),
# the same as the Python archive above: a version number alone lets PyPI, or
# whatever index this Mac is pointed at, hand over a different file, and it
# would be signed with the release identity and shipped. The hash is PyPI's
# own for that file. Another version or another Python means a new hash.
JELLYFISH="jellyfish==1.2.1"
JELLYFISH_SHA256="675ab43840488944899ca87f02d4813c1e32107e56afaba7489705a70214e8aa"

# Nuitka compiles the dictator package to native extension modules, so the app
# ships .so and not readable .py. It compiles what we then sign and ship, so
# the source archive is pinned and checked the same way the Python runtime is:
# downloaded, its SHA256 matched, and installed from that one verified file.
# A version number alone would let the index hand over a different sdist, and
# it would end up compiling every module in the release. The sum is PyPI's own
# for nuitka-<ver>.tar.gz; another version means a new URL and a new sum.
NUITKA_VERSION="4.2.2"
NUITKA_SHA256="29c1bfb6f53154e620b38cf6167cbb03f54043f6e08ef7d3f2d5080a95df7e0d"
NUITKA_FILE="nuitka-${NUITKA_VERSION}.tar.gz"
NUITKA_URL="https://files.pythonhosted.org/packages/75/27/9fef9381e967c333c808d8b087ca2cca713d608647a638d962f34ea22a45/${NUITKA_FILE}"

step() { printf '\n== %s\n' "$*"; }
kb() { du -sk "$1" | awk '{print $1}'; }
mb() { awk -v k="$1" 'BEGIN{printf "%.1f MB", k/1024}'; }

# --- 1. fetch and verify -----------------------------------------------------
step "Python $PY_VERSION ($PY_RELEASE)"
mkdir -p "$CACHE"
if [ -f "$CACHE/$PY_FILE" ] && [ "$(shasum -a 256 "$CACHE/$PY_FILE" | awk '{print $1}')" = "$PY_SHA256" ]; then
    echo "  cached, SHA256 ok"
else
    echo "  downloading $PY_FILE"
    curl -fL --retry 3 -o "$CACHE/$PY_FILE.part" "$PY_URL"
    got="$(shasum -a 256 "$CACHE/$PY_FILE.part" | awk '{print $1}')"
    if [ "$got" != "$PY_SHA256" ]; then
        # Kept aside, not deleted, so the mismatch can be looked at.
        mv "$CACHE/$PY_FILE.part" "$CACHE/$PY_FILE.bad"
        echo "  SHA256 mismatch: expected $PY_SHA256, got $got" >&2
        exit 1
    fi
    mv "$CACHE/$PY_FILE.part" "$CACHE/$PY_FILE"
    echo "  SHA256 ok"
fi

# --- 2. assemble -------------------------------------------------------------
step "Assemble $APP"
rm -rf "$STAGE"
mkdir -p "$C/MacOS" "$C/Helpers" "$C/Frameworks" "$C/Resources/bin" "$C/Resources/site-packages"

tar -xzf "$CACHE/$PY_FILE" -C "$C/Resources"     # the archive's top level is python/
PY="$C/Resources/python/bin/python3"
"$PY" -I -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'

# The package as it is in the repo, without bytecode left over from whichever
# Python ran it last. tests/ is beside dictator/, not in it, so it never comes.
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
    "$ROOT/dictator_core/" "$C/Resources/dictator_core/"
cp "$ROOT/bin/dictator" "$C/Resources/bin/dictator"
chmod +x "$C/Resources/bin/dictator"

# -I so a PYTHONPATH or user site-packages on the build machine cannot leak in.
echo "$JELLYFISH --hash=sha256:$JELLYFISH_SHA256" > "$BUILD/jellyfish.req"
"$PY" -I -m pip install --quiet --disable-pip-version-check --no-cache-dir \
    --only-binary :all: --require-hashes -r "$BUILD/jellyfish.req" \
    --target "$C/Resources/site-packages"
rm -rf "$C/Resources/site-packages/bin"

# --- 2b. compile the package to native modules -------------------------------
# The dictator package ships as .so, not readable .py, so the shipped app does
# not carry its own source. Done here, before the trim below, because Nuitka
# needs the Python.h headers under Resources/python/include that the trim
# removes. The bundle's own interpreter builds the modules, so each .so matches
# the ABI (cp312) it will be imported under at run time.
#
# __init__.py is the one file left as source: Nuitka will not compile a
# package's __init__ as a lone --module, and it only re-exports the public api
# names the README already documents. It is precompiled to .pyc by the
# compileall step below, so the first run never writes into the signed bundle.
step "Compile dictator to native modules (nuitka $NUITKA_VERSION)"
NUITKA_DIR="$CACHE/nuitka-$NUITKA_VERSION"
if [ -f "$CACHE/$NUITKA_FILE" ] && \
   [ "$(shasum -a 256 "$CACHE/$NUITKA_FILE" | awk '{print $1}')" = "$NUITKA_SHA256" ]; then
    echo "  sdist cached, SHA256 ok"
else
    echo "  downloading $NUITKA_FILE"
    curl -fL --retry 3 -o "$CACHE/$NUITKA_FILE.part" "$NUITKA_URL"
    got="$(shasum -a 256 "$CACHE/$NUITKA_FILE.part" | awk '{print $1}')"
    if [ "$got" != "$NUITKA_SHA256" ]; then
        mv "$CACHE/$NUITKA_FILE.part" "$CACHE/$NUITKA_FILE.bad"
        echo "  SHA256 mismatch: expected $NUITKA_SHA256, got $got" >&2
        exit 1
    fi
    mv "$CACHE/$NUITKA_FILE.part" "$CACHE/$NUITKA_FILE"
    echo "  SHA256 ok"
fi
# nuitka lives in a build-local --target dir and goes on the path explicitly.
# -s, not -I: -I ignores PYTHONPATH outright, so nuitka would not be found;
# -s honors an explicit PYTHONPATH while still disabling the build machine's
# user site-packages, and the variable is set to exactly NUITKA_DIR here, so
# nothing from the build machine's own environment can leak into the compile.
if ! PYTHONPATH="$NUITKA_DIR" "$PY" -s -c 'import nuitka' 2>/dev/null; then
    rm -rf "$NUITKA_DIR"
    "$PY" -I -m pip install --quiet --disable-pip-version-check --no-cache-dir \
        --target "$NUITKA_DIR" "$CACHE/$NUITKA_FILE"
fi
PYTHONPATH="$NUITKA_DIR" "$PY" -s -c 'import nuitka' \
    || { echo "  nuitka unavailable; refusing to ship readable .py" >&2; exit 1; }

D="$C/Resources/dictator_core"
n=0
for f in "$D"/*.py; do
    [ "$(basename "$f")" = "__init__.py" ] && continue
    PYTHONPATH="$NUITKA_DIR" "$PY" -s -m nuitka --module "$f" \
        --output-dir="$D" >/dev/null 2>"$BUILD/nuitka.err" \
        || { echo "  nuitka failed on $f:" >&2; cat "$BUILD/nuitka.err" >&2; exit 1; }
    n=$((n + 1))
done
# The sources and Nuitka's leftovers go; __init__.py and data/ stay.
find "$D" -maxdepth 1 -name '*.py' ! -name '__init__.py' -delete
rm -f "$D"/*.pyi
rm -rf "$D"/*.build
# Nothing readable may survive but the one __init__ stub.
rem="$(find "$D" -maxdepth 1 -name '*.py' ! -name '__init__.py')"
[ -z "$rem" ] && [ "$n" -gt 0 ] \
    || { echo "  source left behind or nothing compiled: '$rem' (n=$n)" >&2; exit 1; }
echo "  $n modules compiled to .so, sources removed"

# Trim the runtime. Each of these is something the dictation loop never
# imports: the stdlib's own tests, the IDLE editor, Tk (and the Tcl/Tk
# libraries it drags in), the pip bootstrapper and pip itself, which was only
# needed for the line above. Headers and man pages go too.
before="$(kb "$C/Resources/python")"
L="$C/Resources/python/lib/python3.12"
rm -rf "$L/test" "$L/idlelib" "$L/tkinter" "$L/turtledemo" "$L/turtle.py" \
       "$L/ensurepip" "$L/lib2to3" "$L/pydoc_data" \
       "$L/site-packages/pip" "$L"/site-packages/pip-*.dist-info \
       "$L"/lib-dynload/_tkinter*.so \
       "$L"/config-3.12-darwin \
       "$C/Resources/python/include" "$C/Resources/python/share" \
       "$C"/Resources/python/lib/libtcl* "$C"/Resources/python/lib/libtk* \
       "$C"/Resources/python/lib/tcl* "$C"/Resources/python/lib/tk* \
       "$C"/Resources/python/lib/itcl* "$C"/Resources/python/lib/thread[0-9]* \
       "$C/Resources/python/lib/pkgconfig" \
       "$C"/Resources/python/bin/idle3* "$C"/Resources/python/bin/pydoc3* \
       "$C"/Resources/python/bin/2to3* "$C"/Resources/python/bin/pip* \
       "$C"/Resources/python/bin/python3*-config
find "$L" -type d \( -name tests -o -name test \) -prune -exec rm -rf {} +
# libpython is for programs that embed Python. The interpreter here is linked
# statically and its extension modules resolve symbols from it at load time,
# so the dylib is 17 MB nobody opens. Kept if that ever stops being true.
# Collected first and searched after: piped straight into `grep -q`, grep
# exits at the first match, otool dies of SIGPIPE, pipefail turns that into a
# failure and the `!` into "nothing links it", which deleted the dylib in
# exactly the case it was meant to be kept.
links="$(find "$C/Resources" -name '*.so' -print0 | xargs -0 otool -L;
         otool -L "$C/Resources/python/bin/python3.12")"
if ! grep -q libpython <<<"$links"; then
    rm -f "$C"/Resources/python/lib/libpython3*.dylib
fi
find "$C/Resources" -name '__pycache__' -type d -prune -exec rm -rf {} +
after="$(kb "$C/Resources/python")"
echo "  runtime trimmed: $(mb "$before") -> $(mb "$after"), saved $(mb $((before - after)))"

# Bytecode, compiled now rather than at the user's first run. Python writes a
# missing .pyc next to the source, which here is inside the signed bundle, and
# one written file is enough for the signature to stop verifying. Unchecked
# hashes are valid whatever the file dates are after a copy or a drag.
"$PY" -I -m compileall -q -j 0 --invalidation-mode unchecked-hash \
    "$C/Resources/python/lib" "$C/Resources/dictator_core" "$C/Resources/site-packages" >/dev/null

# Does the bundle's Python find its own package and jellyfish, the way the app
# will start it? -P, or the current directory, which is this repo, answers the
# import and the check passes for the wrong reason (it did, once). -B and a
# throwaway state dir, so this neither writes into the bundle nor touches the
# real ~/.dictator.
SMOKE="$(mktemp -d "$BUILD/smoke.XXXXXX")"
env -i HOME="$SMOKE" DICTATOR_STATE="$SMOKE/state" DICTATOR_BUNDLE="$APP" \
    PYTHONPATH="$C/Resources:$C/Resources/site-packages" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -B -P -c 'import dictator_core.core, dictator_core.vocab, dictator_core.cli, dictator_core.roman, jellyfish, sys
assert dictator_core.vocab.jellyfish is not None, "jellyfish did not load"
assert dictator_core.__file__.startswith(sys.argv[1]), dictator_core.__file__
# The compiled modules, not source: Nuitka reports __file__ as the original
# name, so the proof the module came from a .so and not a .py is its loader.
assert type(dictator_core.core.__loader__).__name__ == "nuitka_module_loader", \
    type(dictator_core.core.__loader__).__name__
# Path(__file__) data lookup still resolves beside the compiled module.
assert dictator_core.roman._LEX.exists(), "data file not found beside compiled module"' "$C/Resources"
rm -rf "$SMOKE"
echo "  bundled python imports the compiled dictator package and jellyfish"

# --- 3. native helpers and the app executable --------------------------------
step "Native helpers"
NATIVE="${DICTATOR_NATIVE_DIR:-$BUILD/native}"
if [ -z "${DICTATOR_NATIVE_DIR:-}" ]; then
    rm -rf "$NATIVE"
    bash "$ROOT/tools/build_native.sh" "$NATIVE"
fi
cp -R "$NATIVE/Helpers/." "$C/Helpers/"
[ -d "$NATIVE/Frameworks" ] && cp -R "$NATIVE/Frameworks/." "$C/Frameworks/"
for h in dictator-hotkey dictator-rec dictator-paste dictator-orb dictator-readback dictator-media \
         whisper-server whisper-cli parakeet-cli "Dictator Meeting.app"; do
    [ -e "$C/Helpers/$h" ] || echo "  WARNING: helper missing: $h" >&2
done

step "App executable"
APPBIN="${DICTATOR_APP_DIR:-$BUILD/appbin}"
if [ -z "${DICTATOR_APP_DIR:-}" ]; then
    rm -rf "$APPBIN"
    bash "$ROOT/tools/build_app.sh" "$APPBIN"
fi
cp "$APPBIN/Dictator" "$C/MacOS/Dictator"
# Sparkle, the updater, linked by build_app.sh. The app loads it from
# ../Frameworks; an app that links it and lacks it does not start at all.
if otool -L "$C/MacOS/Dictator" | grep -q Sparkle.framework; then
    [ -d "$APPBIN/Sparkle.framework" ] \
        || { echo "the app links Sparkle but $APPBIN has no Sparkle.framework" >&2; exit 1; }
    rm -rf "$C/Frameworks/Sparkle.framework"
    ditto "$APPBIN/Sparkle.framework" "$C/Frameworks/Sparkle.framework"
fi

# --- 4. Info.plist -----------------------------------------------------------
step "Info.plist ($VERSION, build $BUILD_NUMBER)"
cp "$ROOT/native/app/Info.plist" "$C/Info.plist"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$C/Info.plist"
plutil -replace CFBundleVersion -string "$BUILD_NUMBER" "$C/Info.plist"
# The orb uses CADisplayLink, which macOS 13 does not have. Built on the
# user's own Mac that never showed, since swiftc targets the Mac it runs on.
# A prebuilt bundle has to say the truth, or 13 opens it and the orb fails.
# The same variable sets the target in build_native.sh and build_app.sh.
plutil -replace LSMinimumSystemVersion -string "$MIN_MACOS" "$C/Info.plist"
# The per-machine build writes where the CLI and the log are into the plist.
# In a bundle both are fixed relative to the app, so a stale path here could
# only ever point at somebody else's install.
plutil -remove DictatorCLI "$C/Info.plist" 2>/dev/null || true
plutil -remove DictatorLog "$C/Info.plist" 2>/dev/null || true
# Where the app checks for updates, from the environment or .env (repository
# variables in CI). Releases are served from the R2 bucket
# (DICTATOR_DOWNLOAD_BASE). With the website in front of it
# (DICTATOR_SITE_URL) the feed is the website's /appcast.xml, which redirects
# into the bucket, so the storage can move later without a release that moves
# every app; without the website it is the bucket's own. With neither, the
# app keeps the address native/app/Info.plist has (a local test build).
. "$ROOT/tools/env.sh"
if [ -n "${DICTATOR_DOWNLOAD_BASE:-}" ]; then
    if [ -n "${DICTATOR_SITE_URL:-}" ]; then
        FEED_URL="${DICTATOR_SITE_URL%/}/appcast.xml"
    else
        FEED_URL="${DICTATOR_DOWNLOAD_BASE%/}/appcast.xml"
    fi
fi
if [ -n "${FEED_URL:-}" ]; then
    plutil -replace SUFeedURL -string "$FEED_URL" "$C/Info.plist"
    echo "  update feed: $FEED_URL"
fi
if [ -f "$ROOT/native/app/AppIcon.icns" ]; then
    cp "$ROOT/native/app/AppIcon.icns" "$C/Resources/AppIcon.icns"
    plutil -replace CFBundleIconFile -string AppIcon "$C/Info.plist"
else
    echo "  WARNING: native/app/AppIcon.icns missing; run: swift tools/make_icon.swift native/app/AppIcon.icns" >&2
fi
# The canned data DICTATOR_FAKE=1 draws from. Inside the bundle, so fake mode
# never reaches for the source tree, which on a user's Mac is not there and on
# the maintainer's is on the Desktop, behind a privacy prompt.
cp -R "$ROOT/native/app/Fixtures" "$C/Resources/Fixtures"
plutil -lint "$C/Info.plist" >/dev/null

# --- 5. sign, inside out -----------------------------------------------------
step "Sign with identity '$SIGN_ID'"
# Quiet unless it fails: every file already carries a linker signature, and a
# "replacing existing signature" line for each of them buries the one error.
sign() {
    local out
    out="$(codesign --force --timestamp=none --sign "$SIGN_ID" "$@" 2>&1)" \
        || { echo "$out" >&2; return 1; }
}
is_macho() { file -b "$1" | grep -q 'Mach-O'; }

# Libraries and Python extension modules first: everything else loads them.
n=0
while IFS= read -r -d '' f; do
    sign "$f"; n=$((n + 1))
done < <(find "$C/Frameworks" "$C/Resources" -type f \( -name '*.dylib' -o -name '*.so' \) -print0)
echo "  $n libraries"

# Then executables: the helpers, and the Python interpreter, which is a plain
# Mach-O file under Resources and is not sealed as code unless signed itself.
n=0
while IFS= read -r -d '' f; do
    is_macho "$f" && { sign "$f"; n=$((n + 1)); }
done < <(find "$C/Helpers" -maxdepth 1 -type f -print0; \
         find "$C/Resources/python/bin" -type f -print0)
echo "  $n executables"

# Nested apps as bundles, so their Info.plist is bound into their signature.
for a in "$C"/Helpers/*.app; do
    [ -d "$a" ] || continue
    sign "$a"; echo "  $(basename "$a")"
done

# Sparkle, inside out as its documentation asks: the two XPC services (the
# downloader keeps its entitlements), the Autoupdate tool, the Updater app,
# then the framework. Same identity as everything else, so the installer it
# runs is trusted exactly as far as the app is.
SP="$C/Frameworks/Sparkle.framework/Versions/B"
if [ -d "$SP" ]; then
    sign "$SP/XPCServices/Installer.xpc"
    sign --preserve-metadata=entitlements "$SP/XPCServices/Downloader.xpc"
    sign "$SP/Autoupdate"
    sign "$SP/Updater.app"
    sign "$C/Frameworks/Sparkle.framework"
    echo "  Sparkle.framework"
fi

# The app last. Never --deep here: it signs in whatever order it finds things
# and is deprecated for signing. It is only right for verifying.
sign "$APP"
codesign --verify --deep --strict --verbose=1 "$APP"

# Now run the bundled Python the way the app does, without -B, importing every
# module and the CLI, and verify again. If anything still writes bytecode into
# the bundle this is where it shows, rather than on a user's Mac as an app
# that stopped verifying after its first launch.
SMOKE="$(mktemp -d "$BUILD/smoke.XXXXXX")"
run_bundled() {
    (cd "$SMOKE" && env -i HOME="$SMOKE" DICTATOR_STATE="$SMOKE/state" DICTATOR_BUNDLE="$APP" \
        PYTHONPATH="$C/Resources:$C/Resources/site-packages" "$PY" "$@")
}
run_bundled -P -c 'import importlib, pkgutil, dictator_core
for m in pkgutil.iter_modules(dictator_core.__path__):
    importlib.import_module("dictator_core." + m.name)'
run_bundled "$C/Resources/bin/dictator" help >/dev/null
rm -rf "$SMOKE"
codesign --verify --deep --strict "$APP"
echo "  still valid after running the bundled CLI"

# --- 6. the disk image -------------------------------------------------------
step "Disk image"
ln -s /Applications "$STAGE/Applications"
DMG="$BUILD/Dictator-$VERSION.dmg"
rm -f "$DMG"
# hdiutil create prints a deprecation notice on macOS 27 pointing at
# `diskutil image create`. It still works; switch when it stops.
hdiutil create -quiet -volname "Dictator" -srcfolder "$STAGE" -ov \
    -format UDZO -imagekey zlib-level=9 "$DMG"
# The disk image itself is deliberately NOT signed. Signed with the release
# certificate, which no Mac but ours trusts, a downloaded .dmg is refused
# outright ("Dictator.dmg Not Opened"), before the app inside is ever looked
# at; unsigned, it mounts, and Gatekeeper judges the app, which gets the one
# Open Anyway it is meant to. Measured on macOS 27.0.1 with the same app in
# both images (9 October 2026). The app inside stays signed: that is what
# keeps permissions across updates. Updates are protected separately, by the
# Sparkle signature over the whole file (tools/appcast.sh).
SHA="$(shasum -a 256 "$DMG" | awk '{print $1}')"
echo "$SHA  $(basename "$DMG")" > "$DMG.sha256"

app_kb="$(kb "$APP")"
dmg_bytes="$(stat -f %z "$DMG")"
printf '\n'
printf '  app        %s\n' "$(mb "$app_kb")"
printf '    python   %s\n' "$(mb "$(kb "$C/Resources/python")")"
printf '    site-pkg %s\n' "$(mb "$(kb "$C/Resources/site-packages")")"
printf '    dictator %s\n' "$(mb "$(kb "$C/Resources/dictator_core")")"
printf '    helpers  %s\n' "$(mb "$(kb "$C/Helpers")")"
printf '    frmwrks  %s\n' "$(mb "$(kb "$C/Frameworks")")"
printf '  dmg        %s (%s bytes)\n' "$(mb $((dmg_bytes / 1024)))" "$dmg_bytes"
printf '  sha256     %s\n' "$SHA"
printf '  file       %s\n' "$DMG"
