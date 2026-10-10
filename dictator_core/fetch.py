"""Download the speech models, from inside the app.

The repo install gets its models from scripts/install.sh, with curl. The app has no
installer: somebody drags it into Applications and opens it, so the first
launch has to fetch them itself, or the app installs, asks for every
permission, and then cannot turn a single word into text.

Each file is checked against the SHA256 Hugging Face publishes for it, and
the size, before it is moved into place. A model is 74 MB to 1.5 GB of
numbers that whisper will load without complaint whatever they are, so a
truncated or swapped file would not fail here; it would fail later, as
nonsense text, which reads as the product being bad at listening.

The English models come first and in order, then the Hinglish one, so English
works as soon as it can, the same order scripts/install.sh uses. One download at a
time, across every process: the app and the dictation loop can both ask, and
two writers on one .part file would make a model that passes no check.
"""
import fcntl
import hashlib
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import core, stt

# name -> (url, bytes, sha256). Sizes and hashes are the LFS object Hugging
# Face serves for each file, read from its API on 8 October 2026. If upstream
# replaces a file the check fails and the old one, if any, is kept: better a
# clear "could not verify" than a silent model change.
SOURCES = {
    "ggml-tiny.bin": (
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        77691713,
        "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21"),
    "ggml-parakeet-tdt-0.6b-v3-q8_0.bin": (
        "https://huggingface.co/ggml-org/parakeet-GGUF/resolve/main/"
        "ggml-parakeet-tdt-0.6b-v3-q8_0.bin",
        668757119,
        "4d64e9e96c2792186d072fde0034df0ad670cf680a2f53069052ead827fd600e"),
    "ggml-large-v3-turbo.bin": (
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
        "ggml-large-v3-turbo.bin",
        1624555275,
        "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"),
}

CHUNK = 1 << 20


class Mismatch(Exception):
    pass


def _order() -> list:
    """Missing models, the ones English needs first. A model the user removed
    is not missing, it is gone on purpose, and is left out."""
    gone = stt.removed()
    todo = [m for m in stt.missing() if m[0] not in gone]
    return ([m[0] for m in todo if m[3]]
            + [m[0] for m in todo if not m[3]])


def fetch(name: str, timeout: float = 60.0) -> None:
    """Download one model into the model directory, verified.

    Writes to <name>.part, which is what stt.model_status reads progress
    from, and renames it into place only once size and hash match.

    A .part left by an earlier run is continued with a Range request rather
    than started again: on the first real install the Hinglish model was
    started five times in three seconds, each run killed by the next. A file
    that arrives and does not match is removed, so a bad one is never
    continued; an interrupted one is kept, because it is only unfinished."""
    url, size, sha = SOURCES[name]
    d = stt.MODEL_DIR
    d.mkdir(parents=True, exist_ok=True)
    final, part = d / name, d / (name + ".part")
    h = hashlib.sha256()
    have = 0
    try:
        have = part.stat().st_size
    except OSError:
        pass
    if not 0 < have < size:
        have = 0
    headers = {"User-Agent": "dictator"}
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if have and getattr(r, "status", 200) != 206:
            have = 0          # the server sent the whole file again
        if have:
            with open(part, "rb") as f:
                for block in iter(lambda: f.read(CHUNK), b""):
                    h.update(block)
        got = have
        with open(part, "ab" if have else "wb") as out:
            while True:
                block = r.read(CHUNK)
                if not block:
                    break
                out.write(block)
                h.update(block)
                got += len(block)
    if got != size or h.hexdigest() != sha:
        try:
            part.unlink()
        except FileNotFoundError:
            pass
        if got != size:
            raise Mismatch(f"{name}: got {got} bytes, expected {size}")
        raise Mismatch(f"{name}: SHA256 does not match the published one")
    os.replace(part, final)


def fetch_missing(names: "list|None" = None, wait: bool = False) -> list:
    """Download every missing model, one process at a time.

    Returns what was downloaded. If another process holds the lock it is
    already doing this, so returns [] at once rather than waiting behind it,
    unless `wait`: a Retry the user pressed while another model is arriving
    queues behind it instead of being dropped.

    Naming a model is asking for it, so it is no longer "removed". A model
    that fails is recorded (stt.note_failure, for the app's Retry) and
    reported through surface_error, and the rest are still tried: no
    Hinglish is no reason for no English."""
    d = stt.MODEL_DIR
    d.mkdir(parents=True, exist_ok=True)
    for name in names or ():
        stt._set_removed(name, False)
    lock = open(d / ".fetch.lock", "w")
    pidfile = d / ".fetch.pid"
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            return []
        done = []
        for name in (names if names is not None else _order()):
            if name not in SOURCES or (d / name).exists():
                continue
            core.log(f"fetch: downloading {name}")
            pidfile.write_text(f"{os.getpid()} {name}")
            stt.note_failure(name, None)
            try:
                fetch(name)
                done.append(name)
                core.log(f"fetch: {name} verified and in place")
            except Exception as e:
                stt.note_failure(name, str(e))
                core.surface_error(
                    "models", f"could not download {name}: {e}",
                    hint="press Retry in Settings, or run "
                         f"`dictator models fetch {name}`")
        return done
    finally:
        try:
            pidfile.unlink()
        except FileNotFoundError:
            pass
        lock.close()


def in_background(names: "list|None" = None) -> "subprocess.Popen|None":
    """Start `dictator models fetch` as its own process, if anything is missing.

    Its own process and its own session, not a thread of the dictation loop:
    the app restarts the loop whenever the key changes, and a thread died
    with it, mid-download. The lock in fetch_missing keeps a second one from
    doing anything, so starting it again is harmless. With `names` (a Retry,
    or a download of a removed model) only those are fetched, and the process
    waits for any download already running instead of giving up."""
    if names is None and not _order():
        return None
    cli = Path(__file__).resolve().parent.parent / "bin" / "dictator"
    try:
        with open(core.LOG_FILE, "a") as log:
            return subprocess.Popen(
                [sys.executable, str(cli), "models", "fetch"] + list(names or []),
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True)
    except Exception as e:
        core.log(f"fetch: could not start the download: {e}")
        return None
