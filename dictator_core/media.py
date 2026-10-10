"""Quiet other audio while the microphone is open (native/media.swift).

Music from the speakers reaches the microphone and lands in the transcript.
So while a hold or a hands free session is open, the player is paused, or
when it cannot be paused, the output is muted, and either is undone when the
microphone closes.

Never on the critical path. The microphone opens first and this runs on a
thread after it, a short beat later: a tap of the key or a chord that is
cancelled at once should not make somebody's music stutter. Every failure is
logged and ignored; music that keeps playing is a worse transcript, a key
that stops working is a broken product.

A mute is the one thing here that would hurt if it were left behind: a Mac
that stays silent after a crash. So the mute is written down before it is
made, and the next start of the loop undoes one it finds.
"""
import subprocess
import threading
import time
from pathlib import Path

from . import core, swiftbuild

SRC = Path(__file__).resolve().parent.parent / "native" / "media.swift"
BIN = core.helper_path("dictator-media")

# Long enough that a stray tap or a chord never pauses anything, short enough
# that the first words are not spoken over the music.
DELAY_S = 0.2


def _setting() -> Path:
    return core.STATE_DIR / "quiet-media"


def enabled() -> bool:
    """On unless the user turned it off."""
    try:
        return _setting().read_text().strip() != "off"
    except Exception:
        return True


def set_enabled(on: bool) -> None:
    f = _setting()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("on" if on else "off")


def _marker() -> Path:
    return core.STATE_DIR / "media-quieted"


def build(force: bool = False) -> str:
    return swiftbuild.compile_if_needed(SRC, BIN, "media", force=force,
                                        timeout=180)


def _run(*args, timeout: float = 4.0) -> str:
    exe = build()
    if not exe:
        return ""
    r = subprocess.run([exe, *args], capture_output=True, text=True,
                       timeout=timeout)
    return (r.stdout or "").strip()


class Quieting:
    """One open microphone's worth of quiet. start() when it opens, stop()
    when it closes; stop() is safe to call before the delay has passed, in
    which case nothing was ever paused."""

    def __init__(self):
        self._done = threading.Event()      # stop() was called
        self._lock = threading.Lock()
        self.result = "none"                # "paused", "muted" or "none"
        self._t = None
        self._r = None

    def start(self) -> "Quieting":
        if enabled():
            self._t = threading.Thread(target=self._quiet, daemon=True)
            self._t.start()
        return self

    def _quiet(self):
        if self._done.wait(DELAY_S):
            return
        try:
            with self._lock:
                if self._done.is_set():
                    return
                # Written before the helper runs: if it mutes and the loop
                # dies before reading the answer, the next start still knows.
                _marker().write_text("pending")
                self.result = _run("quiet") or "none"
                if self.result == "none":
                    _marker().unlink(missing_ok=True)
                else:
                    _marker().write_text(self.result)
                    core.log(f"media: {self.result} other audio while listening")
        except Exception as e:
            core.log(f"media: could not quiet other audio: {e}")

    def stop(self):
        """Put back whatever start() did. Returns at once; the work is on a
        thread, so letting go of the key never waits for a player."""
        self._done.set()
        self._r = threading.Thread(target=self._restore, daemon=True)
        self._r.start()

    def wait(self, timeout: float = 5.0):
        """For tests: until both threads have finished."""
        for t in (self._t, self._r):
            if t:
                t.join(timeout)

    def _restore(self):
        with self._lock:
            what = self.result
            self.result = "none"
        if what == "none":
            return
        try:
            _run("restore", what)
            _marker().unlink(missing_ok=True)
        except Exception as e:
            core.log(f"media: could not restore other audio: {e}")


def recover() -> None:
    """At the start of the loop: undo a mute a previous run left behind.
    A pause is not resumed: music starting by itself, minutes or days after
    the hold that paused it, would be stranger than staying paused."""
    try:
        what = _marker().read_text().strip()
    except Exception:
        return
    try:
        # Only a mute the helper confirmed. "pending" cannot tell our mute
        # from one the user made, and theirs is not ours to undo.
        if what == "muted":
            _run("restore", "muted")
            core.log("media: undid a mute an earlier run left behind")
        _marker().unlink(missing_ok=True)
    except Exception as e:
        core.log(f"media: could not undo an earlier mute: {e}")
