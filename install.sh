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

step "3/4  Speech models"
# These are downloaded rather than assumed. ensure_model() existed in the code
# and had no callers anywhere, and would have fetched the wrong model anyway,
# so a fresh machine had nothing to transcribe with and the key simply did
# nothing. Models already on the machine are found, not fetched again.
MODEL_DIR="$(python3 -c "import sys; sys.path.insert(0, '$HERE'); from dictator import stt; print(stt.MODEL_DIR)")"
mkdir -p "$MODEL_DIR"
echo "  models live in $MODEL_DIR"

get_model() {  # name url size why
  local name="$1" url="$2" size="$3" why="$4"
  if [ -s "$MODEL_DIR/$name" ]; then
    echo "  $name already here"
    return 0
  fi
  echo "  fetching $name ($size, one time): $why"
  if curl -fSL --progress-bar -o "$MODEL_DIR/$name.part" "$url"; then
    mv "$MODEL_DIR/$name.part" "$MODEL_DIR/$name"
  else
    # A half written model is worse than none: it looks present and fails at
    # the moment you speak, which reads as the key being broken.
    rm -f "$MODEL_DIR/$name.part"
    echo "  could not download $name. Run this installer again when you have a"
    echo "  connection; everything already downloaded is kept."
    return 1
  fi
}

get_model ggml-tiny.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin \
  74MB "works out which language you just spoke, in 0.2s"

get_model ggml-parakeet-tdt-0.6b-v3-q8_0.bin \
  https://huggingface.co/ggml-org/parakeet-GGUF/resolve/main/ggml-parakeet-tdt-0.6b-v3-q8_0.bin \
  638MB "English, and fast: about half a second"

if [ "${DICTATOR_ENGLISH_ONLY:-}" = "1" ]; then
  echo "  skipping the multilingual model (DICTATOR_ENGLISH_ONLY=1)."
  echo "  Hindi and Hinglish will not work without it."
else
  get_model ggml-large-v3-turbo.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin \
    1.5GB "Hindi, Hinglish, and anything the fast one gets wrong"
fi

"$HERE/bin/dictator" build >/dev/null || true

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
