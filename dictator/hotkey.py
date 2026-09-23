"""Hold-to-talk on a single key, and a hands free session on a chord.

The listener itself is a tiny Swift binary (native/hotkey.swift) because only
a CGEventTap can see the Fn/Globe key, and only an event tap gives us the key
RELEASE that hold-to-talk is built on. Our existing hotkeys go through skhd,
which fires on key-press only and so cannot do this at all.

It speaks a one-line-per-gesture protocol on stdout:

    READY <key> toggle=<latch|off> cap=<ms>
                      armed, and saying how it is configured. `cap` is the
                      longest hands free session it will allow, so a caller
                      can size its recorder from it instead of guessing.
    DOWN              key down: warm the mic NOW
    UP <held_ms>      key up: stop and transcribe
    CANCEL <held_ms>  another key joined, or the press was too short to be
                      speech. Discard whatever was warmed.

                      Note the second case is NOT invisible to the user. A
                      release that short is a clean tap, which is exactly the
                      gesture macOS acts on, so with the Globe key set to Show
                      Emoji (the common default) an aborted press opens the
                      emoji palette. We are listen-only and cannot prevent
                      that. The floor decides only whether WE transcribe.
    LOCKED            the screen locked mid-hold

    LATCH <ms>        the hold just became a HANDS FREE session. The mic that
                      DOWN opened keeps running, and the key release that
                      follows deliberately emits nothing at all, so a caller
                      that does nothing with LATCH keeps recording, which is
                      the correct fallback.
    LISTENING <ms>    heartbeat, every 5s, only while a session is open
    UP <ms> toggle    the user tapped the chord again: stop and transcribe
    CANCEL <ms> cap|tap|exit
                      the session ended without the user asking for it. Stop
                      and DISCARD: the reasons are a hard cap, a dead event
                      tap, and our own exit.
    LOCKED <ms> lock  the screen locked mid-session. Stop and DISCARD.
    BYE               exiting, any open hold or session already closed

The trailing reason word is always last and always optional to read, so the
older parser (token 0 is the verb, token 1 is milliseconds) is still correct.

Why hold, plus a MODIFIER chord to latch, and not fn+space: macOS runs the
Globe key's own action (emoji picker, input-source switch) on the release of a
clean TAP and ignores a HOLD, so a hold collides with nothing. fn+space is a
different story. fn is not a translation modifier, so fn+space produces U+0020
exactly as space alone does, and a listen-only tap cannot swallow it: it would
type a space into your document, scroll a browser, open Quick Look in the
Finder and press whichever button has focus in a dialog. A modifier tap
(shift, by default) produces no character and triggers nothing by itself,
which is the same property that makes the hold safe. `--toggle-key space` is
still available for anyone who wants it knowing that.
"""
import os
import shutil
import subprocess
import time
from collections import namedtuple
from pathlib import Path

from . import core

SRC = Path(__file__).resolve().parent.parent / "native" / "hotkey.swift"
BIN = core.STATE_DIR / "bin" / "dictator-hotkey"

KEYS = ("fn", "rightcmd", "rightopt", "leftcmd")

# "off" restores the hold-only listener exactly.
TOGGLE_KEYS = ("shift", "control", "option", "command", "rightcmd", "space", "off")
# OFF by default, and this is not caution, it is a measurement. With it on,
# a hold that was meant to be ordinary dictation latched into a hands free
# session, ended immediately, and the user's actual sentence was thrown away.
# The log filled with "Thank you." and "[MUSIC PLAYING]", which is what
# whisper returns for the silence that follows. It ate several dictations in a
# row before anyone worked out what it was, which is the worst kind of feature:
# one that breaks the thing people came for, invisibly.
#
# Turn it on with `dictator gesture shift` when you want it.
DEFAULT_TOGGLE = "off"

# Generous but bounded. Five minutes of hands free dictation is a long
# utterance; a microphone open for five minutes that nobody remembers opening
# is a different kind of event. Whoever calls listen() must give its recorder
# at least this long, or the mic will stop while the session still says it is
# listening, which is the same lie in the other direction.
DEFAULT_MAX_SESSION_MS = 300_000

#: Lines that end a take. UP means transcribe it, the other two mean throw it
#: away.
STOP_VERBS = ("UP", "CANCEL", "LOCKED")
#: Lines that only ever appear inside a hands free session.
SESSION_VERBS = ("LATCH", "LISTENING")

Event = namedtuple("Event", "verb ms why fields raw")


def parse(line):
    """Turn one protocol line into an Event, or None if there is nothing in it.

    Deliberately total: a listener that garbles a line, or a future one that
    invents a verb, must not take the dictation loop down with it. Unknown
    verbs come back intact so the caller can log them and carry on.
    """
    if not isinstance(line, str):
        return None
    parts = line.strip().split()
    if not parts:
        return None
    verb = parts[0]
    ms = None
    why = ""
    fields = {}
    for i, tok in enumerate(parts[1:]):
        if "=" in tok:
            k, _, v = tok.partition("=")
            if k:
                fields[k] = v
            continue
        if i == 0:
            try:
                ms = float(tok)
                continue
            except ValueError:
                pass
        # A bare word that is not the duration: the reason the take ended, or
        # the key name on READY. Last one wins, because it is always last.
        why = tok
    return Event(verb, ms, why, fields, line.strip())


def is_session(ev):
    """Did this line come from a hands free session rather than a hold?

    A session's ending carries a reason word; a hold's does not. That is the
    whole difference, and it is why the reason is not decoration.
    """
    if ev is None:
        return False
    if ev.verb in SESSION_VERBS:
        return True
    return ev.verb in STOP_VERBS and bool(ev.why)


def stops(ev):
    """Does this line mean the microphone is now closed?"""
    return ev is not None and ev.verb in STOP_VERBS


def transcribes(ev):
    """...and should what was captured be transcribed and pasted?

    Only UP. Every other ending happened without the user asking for it, and
    pasting minutes of whatever the room was saying into the frontmost app is
    not a mistake you can take back.
    """
    return ev is not None and ev.verb == "UP"


def build(force: bool = False) -> str:
    """Compile the listener if needed. Returns a path, or "" with a reason
    logged. Rebuilds when the source is newer than the binary."""
    if not SRC.exists():
        core.log(f"hotkey: source missing at {SRC}")
        return ""
    if BIN.exists() and not force and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return str(BIN)
    if not shutil.which("swiftc"):
        core.log("hotkey: swiftc not found (install Xcode command line tools)")
        return ""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["swiftc", "-O", str(SRC), "-o", str(BIN)],
                       check=True, capture_output=True, timeout=180)
        return str(BIN)
    except subprocess.CalledProcessError as e:
        core.log(f"hotkey: build failed: {e.stderr.decode()[:400]}")
    except Exception as e:
        core.log(f"hotkey: build failed: {e}")
    return ""


def listen(key: str = "fn", min_hold_ms: int = 0,
           toggle_key: "str | None" = None,
           max_session_ms: int = DEFAULT_MAX_SESSION_MS):
    """Start the listener. Returns a Popen whose stdout yields the protocol

    min_hold_ms defaults to 0, i.e. no mis-press floor. A very short hold
    transcribes to nothing and inserts nothing, which is genuinely silent,
    whereas a floor buys nothing (the OS has already acted on the tap) and
    costs us a real utterance whenever someone speaks faster than the
    threshold. Raise it only with data.
    above, or None. The caller owns the process and MUST terminate it; the
    listener closes any open hold on SIGTERM so we can never be left believing
    the key is still down.

    toggle_key is the key tapped cleanly INSIDE a hold to leave the mic open
    hands free, and tapped again to stop. "off" gives back the hold-only
    listener. See the module docstring for why it is a modifier and not space.

    max_session_ms bounds a session that nobody ever stops. The caller's
    recorder must be allowed to run at least this long, or the mic closes
    while we are still reporting a session.
    """
    exe = build()
    if not exe:
        return None
    if toggle_key is None:
        # What the user chose, if they chose. The default is off, because with
        # it on it ate dictations, so this only ever turns something on.
        try:
            toggle_key = (core.STATE_DIR / "gesture").read_text().strip()
        except Exception:
            toggle_key = DEFAULT_TOGGLE
    if toggle_key not in TOGGLE_KEYS:
        core.log(f"hotkey: unknown toggle key {toggle_key!r}, using {DEFAULT_TOGGLE}")
        toggle_key = DEFAULT_TOGGLE
    try:
        return subprocess.Popen(
            [exe, "--key", key, "--min-hold", str(min_hold_ms),
             "--toggle-key", toggle_key, "--max-session", str(int(max_session_ms))],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except Exception as e:
        core.log(f"hotkey: launch failed: {e}")
        return None


def measure(key: str = "fn", secs: int = 30, toggle_key: str = DEFAULT_TOGGLE) -> dict:
    """Run a self-serve trial so you can see the gestures land and learn your
    own natural hold duration. Prints as it goes; returns the summary."""
    p = listen(key, toggle_key=toggle_key)
    if not p:
        print("could not start the listener; see `dictator log`")
        return {}

    holds, cancels, sessions = [], [], []
    deadline = time.time() + secs
    print(f"hold {key} and speak, as you normally would. Tap {toggle_key} while")
    print(f"holding it to stay listening without holding. {secs}s.\n")
    try:
        os.set_blocking(p.stdout.fileno(), False)
        while time.time() < deadline:
            line = p.stdout.readline()
            if not line:
                time.sleep(0.02)
                continue
            ev = parse(line)
            if ev is None:
                continue
            print("  " + ev.raw)
            if ev.verb == "UP" and ev.ms is not None:
                (sessions if is_session(ev) else holds).append(int(ev.ms))
            elif ev.verb == "CANCEL" and ev.ms is not None:
                cancels.append(int(ev.ms))
    finally:
        p.terminate()
        try:
            p.wait(timeout=2)
        except Exception:
            p.kill()

    print()
    if holds:
        s = sorted(holds)
        print(f"real holds: n={len(s)}  shortest={s[0]}ms  "
              f"median={s[len(s)//2]}ms  longest={s[-1]}ms")
        print("  " + ", ".join(f"{x}ms" for x in s))
    else:
        print("no completed holds recorded (was the key actually held?)")
    if sessions:
        print(f"hands free sessions: {', '.join(f'{x}ms' for x in sessions)}")
    if cancels:
        print(f"cancelled (chord or too short): {', '.join(f'{c}ms' for c in cancels)}")
    return {"holds": holds, "cancels": cancels, "sessions": sessions}
