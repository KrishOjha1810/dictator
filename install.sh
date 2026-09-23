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

step "1/6  Command line tools"
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Installing Apple's command line tools. Accept the dialog, then run this again."
  xcode-select --install || true
  exit 1
fi
echo "ok"

step "2/6  Recording and speech"
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

step "3/6  Word matching"
# jellyfish does the phonetic matching that makes one correction cover its
# variants. It was never installed by this script and never checked by doctor,
# and without it vocab.py sets it to None and the entire vocabulary and
# learning feature does nothing at all, silently. Same family of bug as a
# function with no callers: everything looks installed and one feature is
# simply absent.
if python3 -c "import jellyfish" 2>/dev/null; then
  echo "  jellyfish already there"
else
  echo "  installing jellyfish (phonetic matching)"
  python3 -m pip install --user --quiet jellyfish 2>/dev/null \
    || pip3 install --user --quiet jellyfish 2>/dev/null \
    || echo "  could not install it. Corrections and learning will not work;
  everything else will. Try: python3 -m pip install --user jellyfish"
fi

step "4/6  Speech models"
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

# The multilingual model is 1.5GB on its own, and nothing about English needs
# it. Waiting for it before the first word is ten minutes of a progress bar
# before the product has proved it does anything, so it comes down in the
# background and Hinglish starts working when it lands.
TURBO="$MODEL_DIR/ggml-large-v3-turbo.bin"
TURBO_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
if [ -s "$TURBO" ]; then
  echo "  ggml-large-v3-turbo.bin already here"
elif [ "${DICTATOR_ENGLISH_ONLY:-}" = "1" ]; then
  echo "  skipping the multilingual model (DICTATOR_ENGLISH_ONLY=1)."
  echo "  Hindi and Hinglish will not work without it."
else
  echo "  fetching ggml-large-v3-turbo.bin (1.5GB) in the background."
  echo "  English works as soon as this installer finishes. Hindi and Hinglish"
  echo "  start working when this lands; check with: dictator doctor"
  nohup sh -c "curl -fsSL -o '$TURBO.part' '$TURBO_URL' && mv '$TURBO.part' '$TURBO' \
               || rm -f '$TURBO.part'" >/dev/null 2>&1 &
fi

"$HERE/bin/dictator" build >/dev/null || true

step "5/6  Make the command reachable"
# Without this every command in the README fails for a new user, because the
# repo's bin directory is not on anyone's PATH. Deliberately does NOT ask for
# an admin password: Ollama does, and being asked to authenticate before a
# tool has done anything is a bad first impression.
LINKED=""
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
  if [ -d "$d" ] && [ -w "$d" ]; then
    ln -sf "$HERE/bin/dictator" "$d/dictator" && LINKED="$d" && break
  fi
done
if [ -n "$LINKED" ]; then
  echo "  dictator -> $LINKED/dictator"
  case ":$PATH:" in
    *":$LINKED:"*) : ;;
    *) echo "  ($LINKED is not on your PATH yet; open a new terminal tab)" ;;
  esac
else
  mkdir -p "$HOME/.local/bin" && ln -sf "$HERE/bin/dictator" "$HOME/.local/bin/dictator"
  echo "  dictator -> ~/.local/bin/dictator"
  echo "  Add this to your shell profile, then open a new tab:"
  echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

step "6/6  Turn it on"
"$HERE/bin/dictator" on

# The last step used to be a paragraph asking the user to go and do something.
# Telling somebody to open System Settings and find a pane is the step people
# give up on, and it is also the step a script can simply do. So it does it,
# and then watches, so re-running this installer is a complete answer to "it
# is not working" rather than the same paragraph again.
# stdout, not stdin: the one line people actually run is "curl ... | bash",
# where stdin is the pipe and only stdout is still the terminal. Checking
# stdin meant the one invocation this was written for took the other branch.
if [ -t 1 ]; then
  echo
  "$HERE/bin/dictator" permissions || true
else
  cat <<'MSG'

One more thing, and it is the only part that needs you.

macOS will ask to allow "Dictator" to use the microphone and to use
Accessibility. Say yes to both. If the app is not in the Accessibility list at
all, run this and it will open the right place and add it:

  dictator permissions

MSG
fi

cat <<'MSG'

  dictator doctor      checks everything and says what is wrong
  dictator permissions if the key does nothing, start here
  dictator off         stops it

MSG
