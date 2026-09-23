#!/usr/bin/env bash
# Dictator: hold a key and talk, anywhere on your Mac.
#
# Safe to run again. Everything here is idempotent, so if it fails halfway
# you can fix the one thing it complained about and run it again.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
step() { printf "\n\033[1m%s\033[0m\n" "$*"; }

if [ "$(uname)" != "Darwin" ]; then
  echo "Dictator is macOS only: the held key, the indicator and the login item"
  echo "are all macOS specific. Nothing here would work elsewhere."
  exit 1
fi

step "1/4  Command line tools"
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Installing Apple's command line tools. Accept the dialog, then run this again."
  xcode-select --install || true
  exit 1
fi
echo "ok"

step "2/4  Recording and speech"
# Homebrew is the only realistic way to get these two on a Mac. Installing it
# silently would be rude, so say what is missing and how to get it.
if ! command -v brew >/dev/null 2>&1; then
  cat <<'MSG'
Homebrew is needed for the recorder and the speech engine.

Install it with the one line from https://brew.sh, then run this again:

  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
MSG
  exit 1
fi
for pkg in sox whisper-cpp; do
  if brew list "$pkg" >/dev/null 2>&1; then
    echo "  $pkg already there"
  else
    echo "  installing $pkg"
    brew install "$pkg"
  fi
done

step "3/4  Speech model"
"$HERE/bin/dictator" build >/dev/null || true
python3 - "$HERE" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from dictator import stt
print(f"  models: {stt.MODEL_DIR}")
if stt.MODEL.exists():
    print(f"  {stt.MODEL.name} already there")
else:
    print(f"  {stt.MODEL.name} will download on first use")
PY

step "4/4  Turn it on"
"$HERE/bin/dictator" on

cat <<'MSG'

One more thing, and it is the only part that needs you.

macOS will ask to allow "Dictator" to use the microphone and to use
Accessibility. Say yes to both. If you miss the pop-ups, go to
Apple menu, System Settings, Privacy & Security, Accessibility, and switch
"Dictator" on there.

It starts working a second or two after you do. There is nothing to restart.

  dictator doctor    checks everything and says what is wrong
  dictator off       stops it

MSG
