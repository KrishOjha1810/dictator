#!/usr/bin/env bash
# Build and install the Android keyboard.
#
#   android/build.sh            build the debug apk
#   android/build.sh install    build it and push it to a plugged in phone
#   android/build.sh setup      install the toolchain and stop
#
# No Android Studio. It is about 10GB and this is a two screen app; the
# command line tools are 146MB and the SDK pieces another 400 or so.
# No NDK either: this build ships no model of its own and uses the phone's
# recogniser, so there is nothing to compile for the device.
set -euo pipefail
cd "$(dirname "$0")"

JDK="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"

# Where the SDK is, asked rather than assumed.
#
# Homebrew's android-commandlinetools keeps the whole SDK under its own
# prefix, and sdkmanager installs platform-tools and the platforms beside
# itself, following the real path through any symlink. Pointing a symlink at
# it from ~/Library/Android/sdk therefore gets you a directory holding one
# symlink and nothing else, which is exactly what happened the first time.
sdk_root() {
    for d in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" \
             "$(brew --prefix 2>/dev/null)/share/android-commandlinetools" \
             "$HOME/Library/Android/sdk"; do
        [ -n "$d" ] && [ -x "$d/cmdline-tools/latest/bin/sdkmanager" ] && { echo "$d"; return; }
    done
    echo "$(brew --prefix 2>/dev/null)/share/android-commandlinetools"
}
SDK="$(sdk_root)"

need() { command -v "$1" >/dev/null 2>&1; }

setup() {
    if [ ! -x "$JDK/bin/java" ]; then
        echo "Installing a JDK (brew openjdk@17)"
        brew install openjdk@17
    fi
    if [ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
        echo "Installing the Android command line tools"
        brew install --cask android-commandlinetools
        SDK="$(sdk_root)"
    fi
    export JAVA_HOME="$JDK" ANDROID_HOME="$SDK" ANDROID_SDK_ROOT="$SDK"
    yes | "$SDK/cmdline-tools/latest/bin/sdkmanager" --licenses >/dev/null 2>&1 || true
    "$SDK/cmdline-tools/latest/bin/sdkmanager" \
        "platform-tools" "platforms;android-35" "build-tools;35.0.0" 2>&1 | tail -1
    echo "toolchain ready at $SDK"
}

if [ "${1:-}" = "setup" ]; then setup; exit 0; fi
[ -x "$JDK/bin/java" ] && [ -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ] || setup

export JAVA_HOME="$JDK" ANDROID_HOME="$SDK" ANDROID_SDK_ROOT="$SDK"
echo "sdk.dir=$SDK" > local.properties

# Gradle, fetched once into a cache rather than installed.
#
# `brew install gradle` pulls a second JDK beside the one above and puts a
# third version of Java on the machine for a build that needs none of them.
# The distribution zip is self contained and the wrapper needs a jar this
# repo would otherwise have to carry, so neither is worth it.
GRADLE_VERSION=8.11.1
CACHE="${DICTATOR_ANDROID_CACHE:-$HOME/.cache/dictator-android}"
GRADLE="$CACHE/gradle-$GRADLE_VERSION/bin/gradle"
if [ ! -x "$GRADLE" ]; then
    echo "Fetching gradle $GRADLE_VERSION (about 130MB, once)"
    mkdir -p "$CACHE"
    curl -fsSL -o "$CACHE/gradle.zip" \
        "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip"
    unzip -q -o "$CACHE/gradle.zip" -d "$CACHE"
    rm -f "$CACHE/gradle.zip"
fi

"$GRADLE" --console=plain --no-daemon assembleDebug

APK=app/build/outputs/apk/debug/app-debug.apk
echo
echo "$APK"

if [ "${1:-}" = "install" ]; then
    ADB="$SDK/platform-tools/adb"
    if [ -z "$("$ADB" devices | sed -n '2p')" ]; then
        cat >&2 <<'MSG'

No phone. On the phone: Settings, About, tap Build number seven times, then
Settings, System, Developer options, USB debugging. Plug it in and accept the
prompt that appears on its screen.
MSG
        exit 1
    fi
    "$ADB" install -r "$APK"
    "$ADB" shell am start -n com.dictator.ime/.SetupActivity
    echo "installed, and the setup screen is open on the phone"
fi
