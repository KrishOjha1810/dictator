"""The microphone, without Homebrew.

Recording used to be sox's `rec`. sox is GPL-2.0-or-later, so it can never be
shipped inside the app this wants to become, and `brew install sox` pulls in
nine libraries (flac, lame, libogg, libpng, libsndfile, libvorbis, mad, opus,
opusfile) to capture one mono stream that macOS has always known how to
capture. native/record.swift does the same job with AVAudioRecorder, in one
65KB binary that compiles in under two seconds, and it hands us a real input
level instead of a number inferred from the file on disk.

sox stays as the fallback for a machine with no Swift toolchain, because a
recorder that cannot be built has to degrade to one that works rather than to
nothing. See stt.record_hold for the choice between them.
"""
import os
import time
from pathlib import Path

from . import core, swiftbuild

SRC = Path(__file__).resolve().parent.parent / "native" / "record.swift"
BIN = core.STATE_DIR / "bin" / "dictator-rec"


def build(force: bool = False) -> str:
    """Compile it if needed. Returns a path, or "" with the reason logged."""
    return swiftbuild.compile_if_needed(
        SRC, BIN, "recorder", force=force, timeout=240,
        hint="falling back to sox")


def start(wav: str, max_secs: int = 120, errf=None):
    """Start recording to `wav` as a Popen, or None if it could not start.

    The Popen is the whole interface: the caller polls it and terminates it
    when the key comes up. Terminate, never kill: the WAV's header is written
    at stop, so a SIGKILLed recorder leaves a file that claims to hold no
    audio. native/record.swift handles SIGTERM for exactly that reason.
    """
    import subprocess

    exe = build()
    if not exe:
        return None
    try:
        return subprocess.Popen([exe, str(wav), str(max_secs)],
                                stdout=subprocess.DEVNULL,
                                stderr=errf or subprocess.DEVNULL)
    except Exception as e:
        core.log(f"recorder: could not start: {e}")
        return None


# How old a level may be and still be believed. The recorder writes one every
# 0.05s, so anything older than this means it has stopped, and a meter showing
# the last thing it heard before it stopped is a meter that says the mic is
# open when it is not.
_LEVEL_STALE_S = 0.5


def level(wav: str):
    """The live input level, 0..1, or None if this recording is not ours.

    None is not zero. Zero means silence, which is a claim about the room;
    None means nobody is publishing a level for this file, which sends the
    caller to its own measurement instead of showing a dead meter.
    """
    try:
        p = str(wav) + ".lvl"
        if time.time() - os.path.getmtime(p) > _LEVEL_STALE_S:
            return None
        with open(p) as f:
            return max(0.0, min(1.0, float(f.read().strip())))
    except Exception:
        return None
