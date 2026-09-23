"""State, logging, and the indicator's view of what is happening.

This is deliberately small. The dictation stack only ever needed four things
from its old home, and carrying the rest across would have meant carrying a
voice assistant's worth of call state, speech chunks and daemon flags into a
product whose whole job is to turn a held key into text.

Everything here is best-effort and never raises. It runs on the hot path of
the capture loop and inside a launchd agent with no terminal attached, so a
failure to write a log file must never be the reason dictation stops.
"""
import json
import os
import time
from pathlib import Path

STATE_DIR = Path(os.path.expanduser("~/.dictator"))
LOG_FILE = STATE_DIR / "log"
HUD_FILE = STATE_DIR / "hud.json"
ERRORS_FILE = STATE_DIR / "errors.jsonl"


def log(msg: str) -> None:
    """Timestamped debug log, so latency can be read straight off the file
    instead of measured by hand."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
        with open(LOG_FILE, "a") as f:
            f.write(f"{ts} {msg.rstrip()}\n")
    except Exception:
        pass


# The phases the orb shows. This is the honest answer to "is it listening
# right now?", so you never talk to a mic that is not open.
#   listening  mic open, waiting for you to start talking
#   hearing    actively capturing your voice (level drives the bars)
#   thinking   transcribing and pasting
#   away       you switched away, so it stopped
HUD_PHASES = ("listening", "hearing", "thinking", "away")


def set_hud(phase: str, level: float = 0.0, text: str = "") -> None:
    """Publish live state and mic level for the indicator to read.

    Written with an atomic replace because the orb reads this file constantly
    and must never see a half-written one."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "phase": phase,
            "level": round(max(0.0, min(1.0, level)), 3),
            "text": text[:80],
            "ts": time.time(),
        })
        tmp = str(HUD_FILE) + f".{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            f.write(payload)
        os.replace(tmp, HUD_FILE)
    except Exception:
        pass


_last_surfaced: dict = {}


def surface_error(where: str, msg: str, hint: str = "", **_) -> None:
    """Make a failure visible instead of letting it disappear.

    Dictation fails in ways the user cannot see: the key still presses, the orb
    may still appear, and nothing arrives. So every failure gets written where
    `dictator errors` can read it back, and repeats within half a minute are
    dropped so one broken loop cannot bury everything else.

    Extra keyword arguments are accepted and ignored: callers carried over from
    voicebridge pass speak= and ledger=, which meant something there and mean
    nothing to a product that does not talk back."""
    try:
        full = f"{msg} {hint}".strip()
        key = f"{where}|{msg}"
        now = time.time()
        if now - _last_surfaced.get(key, 0.0) < 30.0:
            return
        _last_surfaced[key] = now
        log(f"ERROR [{where}]: {full}")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERRORS_FILE, "a") as f:
            f.write(json.dumps({"at": now, "where": where, "msg": msg,
                                "hint": hint}) + "\n")
    except Exception:
        pass


def errors(limit: int = 20) -> list:
    """The most recent failures, newest last."""
    try:
        lines = ERRORS_FILE.read_text().strip().splitlines()
    except Exception:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out
