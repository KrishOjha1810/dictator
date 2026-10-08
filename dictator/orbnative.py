"""The native indicator: build it, start it, stop it.

Kept apart from the older Tkinter orb so that one stays as a fallback on a
machine with no Swift toolchain. The native one is preferred because it can
verify the microphone rather than take the daemon's word for it: it reads
CoreAudio for whether a device is capturing and an flock for whether the open
device is ours, so it cannot sit showing "idle" while a mic is open.
"""
import os
import signal
import subprocess
from pathlib import Path

from . import core, swiftbuild

SRC = Path(__file__).resolve().parent.parent / "native" / "orb.swift"
BIN = core.helper_path("dictator-orb")
PID = core.STATE_DIR / "orb.pid"


def build(force: bool = False) -> str:
    """Compile if needed. Returns a path, or "" with the reason logged."""
    return swiftbuild.compile_if_needed(
        SRC, BIN, "orb", force=force, timeout=240,
        hint="falling back to the Tkinter orb")


def running() -> bool:
    try:
        os.kill(int(PID.read_text().strip()), 0)
        return True
    except Exception:
        return False


def show() -> bool:
    """Start it if it is not already up. True if it is now running."""
    if os.environ.get("VB_NO_ORB"):
        return False
    if running():
        return True
    exe = build()
    if not exe:
        return False
    try:
        p = subprocess.Popen([exe], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        core.STATE_DIR.mkdir(parents=True, exist_ok=True)
        PID.write_text(str(p.pid))
        return True
    except Exception as e:
        core.log(f"orb: launch failed: {e}")
        return False


def hide() -> None:
    try:
        os.kill(int(PID.read_text().strip()), signal.SIGTERM)
    except Exception:
        pass
    try:
        PID.unlink()
    except Exception:
        pass
