"""Download the speech models, from inside the app.

The repo install gets its models from install.sh, with curl. The app has no
installer: somebody drags it into Applications and opens it, so the first
launch has to fetch them itself, or the app installs, asks for every
permission, and then cannot turn a single word into text.

Each file is checked against the SHA256 Hugging Face publishes for it, and
the size, before it is moved into place. A model is 74 MB to 1.5 GB of
numbers that whisper will load without complaint whatever they are, so a
truncated or swapped file would not fail here; it would fail later, as
nonsense text, which reads as the product being bad at listening.

The English models come first and in order, then the Hinglish one, so English
works as soon as it can, the same order install.sh uses. One download at a
time, across every process: the app and the dictation loop can both ask, and
two writers on one .part file would make a model that passes no check.
"""
import fcntl
import hashlib
import os
import threading
import urllib.request

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
    """Missing models, the ones English needs first."""
    todo = stt.missing()
    return ([m[0] for m in todo if m[3]]
            + [m[0] for m in todo if not m[3]])


def fetch(name: str, timeout: float = 60.0) -> None:
    """Download one model into the model directory, verified.

    Writes to <name>.part, which is what stt.model_status reads progress
    from, and renames it into place only once size and hash match. On any
    failure the .part is removed: a stale .part would keep the app saying
    "downloading" for a download nobody is doing."""
    url, size, sha = SOURCES[name]
    d = stt.MODEL_DIR
    d.mkdir(parents=True, exist_ok=True)
    final, part = d / name, d / (name + ".part")
    h = hashlib.sha256()
    got = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dictator"})
        with urllib.request.urlopen(req, timeout=timeout) as r, \
                open(part, "wb") as out:
            while True:
                block = r.read(CHUNK)
                if not block:
                    break
                out.write(block)
                h.update(block)
                got += len(block)
        if got != size:
            raise Mismatch(f"{name}: got {got} bytes, expected {size}")
        if h.hexdigest() != sha:
            raise Mismatch(f"{name}: SHA256 does not match the published one")
        os.replace(part, final)
    except BaseException:
        try:
            part.unlink()
        except FileNotFoundError:
            pass
        raise


def fetch_missing(names: "list|None" = None) -> list:
    """Download every missing model, one process at a time.

    Returns what was downloaded. If another process holds the lock it is
    already doing this, so returns [] at once rather than waiting behind it.
    A model that fails is reported through surface_error and the rest are
    still tried: no Hinglish is no reason for no English."""
    d = stt.MODEL_DIR
    d.mkdir(parents=True, exist_ok=True)
    lock = open(d / ".fetch.lock", "w")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return []
        done = []
        for name in (names if names is not None else _order()):
            if name not in SOURCES or (d / name).exists():
                continue
            core.log(f"fetch: downloading {name}")
            try:
                fetch(name)
                done.append(name)
                core.log(f"fetch: {name} verified and in place")
            except Exception as e:
                core.surface_error(
                    "models", f"could not download {name}: {e}",
                    hint="check the connection; it is tried again on the "
                         "next start")
        return done
    finally:
        lock.close()


def in_background() -> "threading.Thread|None":
    """Start fetch_missing on a daemon thread if anything is missing."""
    if not stt.missing():
        return None
    t = threading.Thread(target=fetch_missing, name="fetch", daemon=True)
    t.start()
    return t
