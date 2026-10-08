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
import threading
import time
from pathlib import Path

# DICTATOR_STATE points every command at a different installation's files.
# The case it is for: one Mac, two user accounts, and the dictation that
# matters happening in the one you are not sitting in. Without it there is no
# way to read another installation's log at all, so "why did it do that over
# there" could only be answered by logging out and back in.
#
# It is read once, here, because every module computes its own paths from this
# at import time. Reading a second installation is what it is for; pointing a
# LIVE listener at somebody else's directory would have it write there, so the
# variable belongs on a one-off command and not in a shell profile.
def state_dir(override: "str|None" = None) -> Path:
    """Where this run keeps its files. A function so it can be tested without
    reloading the module, which leaks into every other test that has already
    imported it."""
    where = override if override is not None else os.environ.get("DICTATOR_STATE")
    # An empty string is what `DICTATOR_STATE=` in a shell profile gives, and
    # treating it as a path puts the state at the filesystem root.
    return Path(os.path.expanduser(where.strip() if where and where.strip()
                                   else "~/.dictator"))


STATE_DIR = state_dir()


# Running from the downloadable app rather than from a checkout. The app sets
# DICTATOR_BUNDLE to its own path before it starts Python, and that is the only
# way this is ever decided: guessing from where this file sits would call a
# checkout that happens to be named Dictator.app a bundle.
#
# What changes in bundle mode is where the compiled helpers come from. In a
# checkout they are built on this Mac into STATE_DIR/bin. In the app they were
# built and signed before the .dmg was made, and they live inside the bundle,
# where nothing on the user's Mac may compile or re-sign them: either would
# change the signature the user's Microphone and Accessibility grants are
# pinned to.
def bundle_root(value: "str|None" = None) -> "Path|None":
    """The app bundle this runs from, or None for a checkout. A function for
    the same reason state_dir is one: tested without reloading the module."""
    where = value if value is not None else os.environ.get("DICTATOR_BUNDLE")
    if not where or not where.strip():
        return None
    return Path(os.path.expanduser(where.strip()))


BUNDLE = bundle_root()


def helper_path(name: str) -> Path:
    """Where the compiled helper called `name` is, for this kind of install.

    One place, because every module that runs a helper used to spell out
    STATE_DIR/bin/name for itself, and one copy left behind would keep
    looking there after the app moved the helpers into the bundle. Read at
    call time, so a test can redirect either STATE_DIR or BUNDLE and every
    caller follows."""
    if BUNDLE is not None:
        return BUNDLE / "Contents" / "Helpers" / name
    return STATE_DIR / "bin" / name


def bundle_id(base: str = "com.dictator.dictation") -> str:
    """The identifier the app is signed with, which is per ACCOUNT, not global.

    Accessibility lives in the system-wide TCC database, at
    /Library/Application Support/com.apple.TCC/TCC.db, and it holds exactly one
    row per bundle identifier. Each account here builds its own app and signs
    it with its own self-signed certificate, so two accounts sharing one
    identifier share one row that can only pin one certificate. Whichever
    account granted last wins and the other is silently untrusted, forever,
    with a tick showing in System Settings the whole time. Granting it again in
    the broken one simply flips the breakage back.

    Measured on a real two-account Mac: the same row read
    `certificate leaf = H"8501b12c..."` from one account and
    `H"cbd3aabe..."` from the other, and each one's doctor reported the other's
    certificate as the one macOS remembered.

    The suffix is a hash of the home directory, not the user's name, so no
    account name is written into a file. It is short because it ends up in the
    designated requirement that people read in `dictator permissions`.

    Inside the downloadable app the identifier is whatever the release was
    signed with, read from the bundle's own Info.plist, because that is the
    one macOS keyed the grants to. Computing a per-account one here would send
    the permission checks looking for a row that cannot exist."""
    if BUNDLE is not None and base == "com.dictator.dictation":
        try:
            import plistlib
            info = plistlib.loads(
                (BUNDLE / "Contents" / "Info.plist").read_bytes())
            if info.get("CFBundleIdentifier"):
                return str(info["CFBundleIdentifier"])
        except Exception:
            pass
    import hashlib
    who = hashlib.sha256(
        str(Path.home().resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{base}.{who}"
LOG_FILE = STATE_DIR / "log"
HUD_FILE = STATE_DIR / "hud.json"
ERRORS_FILE = STATE_DIR / "errors.jsonl"
STATUS_FILE = STATE_DIR / "status.json"


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


# What the app's menu bar and windows show. The app never imports Python, so
# this file is the whole of what it knows about the dictation loop: whether it
# is ready, listening, transcribing, waiting for a permission or broken, and
# how far each model has got. hud.json is the same idea for the orb, and stays
# separate because it is rewritten several times a second while this changes
# only when the state does.
_status_lock = threading.Lock()

STATUS_STATES = ("ready", "listening", "transcribing", "downloading",
                 "paused", "needs_permission", "error")


def write_status(state: str, models: "dict|None" = None,
                 error: "str|None" = None) -> bool:
    """Publish the loop's state for the app to read. True if it was written.

    Atomic for the same reason set_hud is: the app polls this and must never
    read half a file. An unknown state is refused rather than written, because
    the app maps each one to a word and an icon, and a state it has never
    heard of would show as nothing at all. Never raises."""
    if state not in STATUS_STATES:
        log(f"status: refusing unknown state {state!r}")
        return False
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "state": state,
            "models": models or {},
            # One line: it goes into a menu item, and a traceback there is
            # worse than nothing.
            "error": (" ".join(str(error).split())[:200] or None)
                     if error else None,
            "updated": int(time.time()),
        })
        # Three threads of the loop write this, so a temporary name per
        # process was shared between them: two writers truncated and filled
        # the same file, and the one that was renamed into place held the
        # shorter payload with the tail of the longer one, which is not JSON.
        # The app then showed "Starting" until the next state change. A name
        # per thread keeps the files apart, and the lock makes the last
        # caller the one whose state is left in the file.
        tmp = (str(STATUS_FILE)
               + f".{os.getpid()}.{threading.get_ident()}.tmp")
        with _status_lock:
            with open(tmp, "w") as f:
                f.write(payload)
            os.replace(tmp, STATUS_FILE)
        return True
    except Exception:
        return False


def read_status() -> dict:
    """What write_status last wrote, or {} if nothing has."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


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
