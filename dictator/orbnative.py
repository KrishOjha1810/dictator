"""The native indicator: build it, start it, stop it.

Kept apart from the older Tkinter orb so that one stays as a fallback on a
machine with no Swift toolchain. The native one is preferred because it can
verify the microphone rather than take the daemon's word for it: it reads
CoreAudio for whether a device is capturing and an flock for whether the open
device is ours, so it cannot sit showing "idle" while a mic is open.

Where it sits and whether it shows while nobody is dictating live in
STATE_DIR/indicator.json: {"position": "top", "hide_idle": false}. The helper
reads that file on start and watches it, so a change from the app or from
`dictator indicator` moves the running pill without a restart; dragging the
pill writes the position back into the same file.
"""
import json
import os
import signal
import subprocess
from pathlib import Path

from . import core, swiftbuild

SRC = Path(__file__).resolve().parent.parent / "native" / "orb.swift"
BIN = core.helper_path("dictator-orb")
PID = core.STATE_DIR / "orb.pid"
SETTINGS = core.STATE_DIR / "indicator.json"

# The eight places the pill can snap to. The same names, in the same order, as
# `Spot` in native/orb.swift and the picker in the app's Settings.
POSITIONS = ("top", "bottom", "left", "right",
             "top-left", "top-right", "bottom-left", "bottom-right")
DEFAULTS = {"position": "top", "hide_idle": False}


def settings() -> dict:
    """What indicator.json says, with anything missing or unknown replaced by
    the default. A file a person broke by hand must not stop the pill."""
    out = dict(DEFAULTS)
    try:
        raw = json.loads(SETTINGS.read_text())
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    if raw.get("position") in POSITIONS:
        out["position"] = raw["position"]
    if isinstance(raw.get("hide_idle"), bool):
        out["hide_idle"] = raw["hide_idle"]
    return out


def save(**changes) -> dict:
    """Change one or both settings and write the file atomically, keeping
    any key this version does not know about. Raises ValueError on a bad
    value rather than writing it."""
    if "position" in changes and changes["position"] not in POSITIONS:
        raise ValueError(f"position must be one of: {', '.join(POSITIONS)}")
    if "hide_idle" in changes and not isinstance(changes["hide_idle"], bool):
        raise ValueError("hide_idle must be true or false")
    try:
        raw = json.loads(SETTINGS.read_text())
        if not isinstance(raw, dict):
            raw = {}
    except Exception:
        raw = {}
    raw.update(settings())
    raw.update(changes)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_name(SETTINGS.name + ".tmp")
    tmp.write_text(json.dumps(raw, indent=1))
    os.replace(tmp, SETTINGS)
    return settings()


def command(exe: str) -> "tuple[list, dict]":
    """The argv and environment the helper is started with.

    The helper used to find its files at a hardcoded ~/.dictator, so with
    DICTATOR_STATE pointing anywhere else it watched a different mic.lock
    and hud.json from the loop that started it. The directory is now passed
    down, and the helper reads indicator.json from the same place."""
    env = dict(os.environ)
    env["DICTATOR_STATE"] = str(core.STATE_DIR)
    return [exe], env


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
        argv, env = command(exe)
        p = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL,
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
