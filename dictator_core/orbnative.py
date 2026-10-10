"""The native indicator: build it, start it, stop it.

Kept apart from the older Tkinter orb so that one stays as a fallback on a
machine with no Swift toolchain. The native one is preferred because it can
verify the microphone rather than take the daemon's word for it: it reads
CoreAudio for whether a device is capturing and an flock for whether the open
device is ours, so it cannot sit showing "idle" while a mic is open.

Its settings live in STATE_DIR/indicator.json:

    {"position": "top",
     "idle": "hover",                 # hover | always | hide
     "controls": ["dictate", "notetaker", "scratchpad"],
     "shortcuts": {"notetaker": true, "scratchpad": true},
     "hide_idle": false}              # kept for older readers: idle == "hide"

`idle` is what the pill does while nobody is dictating. "hover" (the default)
draws nothing at all until the pointer comes to its place, then shows it with
the buttons in `controls`; "always" keeps the small faint pill on screen, as
before; "hide" shows it only while dictating, with no buttons. `shortcuts`
says which of the app's global shortcuts (Option-M for the Notetaker, Option-S
for the Scratchpad) are on; the app registers them and the pill prints them in
its labels.

The helper reads that file on start and watches it, so a change from the app
or from `dictator indicator` takes effect without a restart; dragging the pill
writes the position back into the same file.
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
IDLE = ("hover", "always", "hide")
CONTROLS = ("dictate", "notetaker", "scratchpad")
SHORTCUTS = ("notetaker", "scratchpad")
DEFAULTS = {"position": "top", "idle": "hover", "controls": list(CONTROLS),
            "shortcuts": {k: True for k in SHORTCUTS}, "hide_idle": False}


def settings() -> dict:
    """What indicator.json says, with anything missing or unknown replaced by
    the default. A file a person broke by hand must not stop the pill."""
    out = json.loads(json.dumps(DEFAULTS))
    try:
        raw = json.loads(SETTINGS.read_text())
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    if raw.get("position") in POSITIONS:
        out["position"] = raw["position"]
    if raw.get("idle") in IDLE:
        out["idle"] = raw["idle"]
    elif raw.get("hide_idle") is True:
        # Written before there was a choice of three: hidden meant hidden.
        out["idle"] = "hide"
    if isinstance(raw.get("controls"), list):
        out["controls"] = [c for c in CONTROLS if c in raw["controls"]]
    if isinstance(raw.get("shortcuts"), dict):
        for k in SHORTCUTS:
            if isinstance(raw["shortcuts"].get(k), bool):
                out["shortcuts"][k] = raw["shortcuts"][k]
    out["hide_idle"] = out["idle"] == "hide"
    return out


def save(**changes) -> dict:
    """Change some settings and write the file atomically, keeping any key
    this version does not know about. Raises ValueError on a bad value rather
    than writing it. `hide_idle=True/False` is the old spelling of
    idle="hide"/"hover"; `shortcuts` may name only the ones to change."""
    if "position" in changes and changes["position"] not in POSITIONS:
        raise ValueError(f"position must be one of: {', '.join(POSITIONS)}")
    if "hide_idle" in changes:
        if not isinstance(changes["hide_idle"], bool):
            raise ValueError("hide_idle must be true or false")
        changes["idle"] = "hide" if changes.pop("hide_idle") else "hover"
    if "idle" in changes and changes["idle"] not in IDLE:
        raise ValueError(f"idle must be one of: {', '.join(IDLE)}")
    if "controls" in changes:
        c = changes["controls"]
        if not isinstance(c, (list, tuple)) or any(x not in CONTROLS for x in c):
            raise ValueError(f"controls must be some of: {', '.join(CONTROLS)}")
        changes["controls"] = [x for x in CONTROLS if x in c]
    now = settings()
    if "shortcuts" in changes:
        sc = changes["shortcuts"]
        if not isinstance(sc, dict) or any(
                k not in SHORTCUTS or not isinstance(v, bool) for k, v in sc.items()):
            raise ValueError("shortcuts must map notetaker/scratchpad to true or false")
        merged = dict(now["shortcuts"])
        merged.update(sc)
        changes["shortcuts"] = merged
    try:
        raw = json.loads(SETTINGS.read_text())
        if not isinstance(raw, dict):
            raw = {}
    except Exception:
        raw = {}
    raw.update(now)
    raw.update(changes)
    raw["hide_idle"] = raw["idle"] == "hide"
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_name(SETTINGS.name + ".tmp")
    tmp.write_text(json.dumps(raw, indent=1))
    os.replace(tmp, SETTINGS)
    return settings()


def command(exe: str, key: str = "fn") -> "tuple[list, dict]":
    """The argv and environment the helper is started with.

    The helper used to find its files at a hardcoded ~/.dictator, so with
    DICTATOR_STATE pointing anywhere else it watched a different mic.lock
    and hud.json from the loop that started it. The directory is now passed
    down, and the helper reads indicator.json from the same place. The hold
    key is passed for the Dictate button's label."""
    env = dict(os.environ)
    env["DICTATOR_STATE"] = str(core.STATE_DIR)
    env["DICTATOR_KEY"] = key
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


def show(key: str = "fn") -> bool:
    """Start it if it is not already up. True if it is now running."""
    if os.environ.get("VB_NO_ORB"):
        return False
    if running():
        return True
    exe = build()
    if not exe:
        return False
    try:
        argv, env = command(exe, key)
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
