"""Paying the first hold's costs before the first hold.

Issue #1 says dictation is slow and unreliable for the first few minutes after
an install and settles down later. Two things in this pipeline are only slow
the first time, and both were being paid in the middle of somebody's first
sentence.

**The model file.** whisper.cpp does not mmap: `whisper-cli` reads the whole
model into memory before it can encode anything, and it is a new process every
hold, so every hold pays that read. What the read costs is decided by whether
macOS still has the file in its page cache. Measured here on the 1.62GB
multilingual model:

    off the disk    1.68s    (0.97 GB/s)
    out of memory   0.30s    (5.36 GB/s)

A machine that has just installed this has never read the file, so the first
holds pay the disk.

**The helper binaries.** A Swift binary that has never been executed pays dyld,
the frameworks it links, and the kernel checking its signature. Measured on a
freshly compiled recorder and paste helper:

    recorder, first execution ever   695ms      every one after it   5ms
    paste helper, first execution    547ms      every one after it   5ms

The installer already compiles them, which was the fix for the five swiftc runs
that used to land on the first holds. But compiling is not running, so the
first EXECUTION still landed on a real hold. For the recorder that half second
is not latency somebody waits through, it is the beginning of their sentence
never reaching the file: the corpus has holds that start "Checkmone again" and
then say "check once" correctly a few words later.

So both are moved to where they are free. The model read starts when the key
goes DOWN and runs while the user is still talking, which is time being spent
anyway; it is the same trick as sizing the audio window to the utterance. The
helpers are run once when the listener starts, when nobody is waiting.

Deliberately NOT a resident whisper server, which was measured and rejected: it
holds a GPU context and made the same hold slower (3.2s against 5.8s) by
contending for the GPU. Nothing here holds a model, a GPU context or any memory
of its own, and nothing here is a cache. It asks the kernel to keep bytes it
would otherwise fetch twice, and the kernel is free to say no: if macOS evicts
the file the next hold simply reads it again, which is what happens today.
"""
import subprocess
import threading
import time

from . import core

# 8MB at a time, into one buffer that is reused. The obvious version, reading
# in chunks and letting each chunk be a new bytes object, allocates 1.6GB of
# short-lived objects and runs at a fifth of the speed, which turns a warm read
# from something free into something worth avoiding.
_CHUNK = 8 << 20

# One read at a time. Two holds in quick succession would otherwise have two
# threads pulling the same 1.6GB through the disk at once, which is slower than
# one and buys nothing.
_lock = threading.Lock()

# The helpers a HOLD uses. The key listener and the indicator are deliberately
# not here: the listener starts both of them for real a moment later, so
# running them first would start two of each.
_HELPERS = ("dictator-rec", "dictator-paste")


def read_through(path) -> float:
    """Read a file so macOS keeps it in memory. Seconds, or 0.0 if it could not
    be read, because a warm-up that fails must never stop a hold."""
    t0 = time.time()
    try:
        buf = memoryview(bytearray(_CHUNK))
        with open(str(path), "rb", buffering=0) as f:
            while f.readinto(buf):
                pass
    except Exception as e:
        core.log(f"warmup: could not read {path}: {e}")
        return 0.0
    return time.time() - t0


def models_for_next_hold() -> list:
    """The model files the next hold will actually open.

    Asked of stt rather than decided here, because the routing between English
    and Hinglish has changed more than once and a second copy of it would
    quietly warm the wrong file. The fallback path, where Parakeet drops speech
    and the multilingual model answers instead, is deliberately not warmed: it
    is the rare case, and warming for it would read 1.6GB on every English hold
    to help one in a hundred."""
    from . import stt
    out = []
    if stt.language() != "hinglish" and stt.parakeet_ready():
        out.append(stt._PARAKEET)
    else:
        out.append(stt.stt_lang_mode()[0])
        # The detector runs first on the auto path, and the hold waits for it
        # before the real model is even started.
        tiny = stt.MODEL_DIR / stt._DETECT_MODEL
        if tiny.exists():
            out.append(tiny)
    return [p for p in out if p and p.exists()]


def models(background: bool = True) -> None:
    """Get the next hold's model into memory. Never raises, and never blocks a
    caller that asked for the background version."""
    def go():
        if not _lock.acquire(blocking=False):
            return          # already reading; a second pass buys nothing
        try:
            for path in models_for_next_hold():
                took = read_through(path)
                if took > 0.5:
                    # Only worth a line when it really came off the disk. A
                    # warm read takes a third of a second, and logging that on
                    # every hold would bury the interesting case.
                    core.log(f"warmup: read {path.name} in {took:.2f}s")
        except Exception as e:
            core.log(f"warmup: the model warm-up failed: {e}")
        finally:
            _lock.release()

    _run(go, background)


def helpers() -> None:
    """Run each helper once, so its first execution is not a real hold.

    With no arguments, which is what makes this safe: both of them print their
    usage and exit. The recorder does not reach the microphone and the paste
    helper does not touch the clipboard. What gets paid here is exactly the
    part that is expensive once, and nothing else happens."""
    for name in _HELPERS:
        exe = core.STATE_DIR / "bin" / name
        if not exe.exists():
            continue
        try:
            t0 = time.time()
            subprocess.run([str(exe)], capture_output=True, timeout=30)
            took = time.time() - t0
            if took > 0.2:
                core.log(f"warmup: first run of {name} took {took:.2f}s, "
                         f"which a hold no longer pays")
        except Exception as e:
            core.log(f"warmup: could not warm {name}: {e}")


def at_startup(background: bool = True) -> None:
    """Everything the first hold would otherwise pay for, done at the moment
    the listener starts, when nobody is waiting for anything."""
    def go():
        helpers()
        models(background=False)

    _run(go, background)


def _run(fn, background: bool) -> None:
    if background:
        threading.Thread(target=fn, daemon=True).start()
    else:
        fn()
