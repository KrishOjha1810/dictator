"""Hold one key, speak, and the words land wherever you were typing.

Everywhere on the Mac: a terminal, Slack, a browser, a text field in an app
nobody has heard of. There is no integration per app, because there is nothing
to integrate with: the text is pasted into whatever has the cursor, the same
way you would have typed it.

Why this is allowed to paste into anything, when the old voice assistant's paste refused to:
that refusal exists because a caller which was never told where to aim would
otherwise type your speech into whatever happened to be in front. Here the
press IS the aim. You held a key while looking at a window, which is a clearer
statement of intent than any target string a caller could have passed.

Two rules make that safe rather than merely convenient:

  * The app is captured on key DOWN and checked again before the paste. If you
    alt-tabbed mid-sentence, the words are dropped rather than typed into
    whatever you switched to. That is the mechanism behind every "it pasted
    into the wrong window" story in this category.

  * Return is never pressed. Dictation puts words in a field; deciding to send
    them is yours. This is also what makes a misfire harmless: the worst case
    is text you can delete, not a message somebody received.
"""
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

from . import (core, history, hotkey, learn, mac, orbnative, paste, readback,
               roman, shape, stt, vocab)

# Anything shorter is a mis-press, not speech. Kept low because a short real
# utterance ("yes", "ship it") is common and losing it is worse than
# transcribing a click into nothing.
MIN_MS = 250
MAX_SECS = 120


FORMAT_FILE = core.STATE_DIR / "format.json"


def _format_flags() -> dict:
    """Which shaping rules are on. Defaults are the conservative ones.

    Kept in a file rather than in code because the user has to be able to turn
    this off without editing anything, which is the single most common
    complaint about every tool that reshapes dictated text."""
    flags = {"enabled": True, "punctuation": True, "lists": False,
             "sentences": True}
    try:
        import json
        flags.update(json.loads(FORMAT_FILE.read_text()))
    except Exception:
        pass
    return {k: bool(v) for k, v in flags.items() if k in
            ("enabled", "punctuation", "lists", "sentences")}


class Dictation:
    """One hold: record while down, transcribe on release, paste where you were."""

    def __init__(self, key: str = "fn", send: bool = False):
        self.key = key
        self.send = send
        self.proc = None            # the recorder
        self.wav = ""
        self.app = ""               # what was in front when you pressed
        self.started = 0.0

    # ---- the two edges ----------------------------------------------------

    def down(self):
        if self.proc:
            return
        self.app = mac.frontmost_app()
        self.wav = f"/tmp/dictator-rec-{os.getpid()}.wav"
        # No silence detection: you are holding a key, so you are the
        # boundary. sox's `silence` effect would trim your first word (you
        # start speaking as you press) and end the take at your first pause.
        self.proc = stt.record_hold(self.wav, max_secs=MAX_SECS)
        self.started = time.time()
        core.set_hud("hearing", 0.0)
        # An indicator that does not move tells you the mic is open and nothing
        # else. Moving with your voice is what tells you it is hearing YOU, and
        # it is the difference between a light and a meter: a stuck light and a
        # silent room look identical.
        self._pump = threading.Thread(target=self._levels, daemon=True)
        self._pump.start()

    def _levels(self):
        """Publish the live level while the key is held.

        Read from the same file being transcribed, so there is no second
        microphone: a second open input would both lie about what is being
        heard and, on a Bluetooth headset, collapse your audio to narrowband."""
        wav = self.wav
        # A running minimum, not the first reading. The first reading is taken
        # before any audio has been written, so it is zero, and using it as the
        # floor subtracts nothing and leaves the room reading as speech.
        # A minimum that follows the quietest thing heard so far adapts to the
        # room instead of assuming one.
        floor = 1.0
        while self.proc and self.proc.poll() is None:
            try:
                raw = stt.live_level(wav)
                if raw > 0.0:
                    floor = min(floor, raw)
                    span = max(0.15, 1.0 - floor)
                    core.set_hud("hearing", min(1.0, max(0.0, (raw - floor) / span)))
            except Exception:
                pass
            time.sleep(0.08)

    def up(self, held_ms: float):
        p, self.proc = self.proc, None
        if not p:
            return
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        if held_ms < MIN_MS:
            core.set_hud("listening", 0.0)
            return
        core.set_hud("thinking", 0.0)
        threading.Thread(target=self._finish,
                         args=(self.wav, self.app, held_ms / 1000.0),
                         daemon=True).start()

    def cancel(self):
        """Another key joined the hold, so you were typing a chord, not talking."""
        p, self.proc = self.proc, None
        if p:
            try:
                p.terminate()
            except Exception:
                pass
        core.set_hud("listening", 0.0)

    # ---- off the key thread -----------------------------------------------

    def _learn_from_last(self, app, say):
        """See what you did to the words pasted last time, and learn from it.

        Read before this utterance is pasted, while the previous one is still
        the last thing on screen. Only ever reads, and keeps the difference
        rather than the document."""
        last = getattr(self, "last", None)
        if not last:
            return
        row_id, shown, last_app = last
        self.last = None
        # Only compare inside the app the text was actually put into.
        if not shown or not row_id or (app and last_app and app != last_app):
            return
        try:
            d = readback.field()
            if not d.get("ok") or not isinstance(d.get("value"), str):
                return
            kept = learn.locate(shown, d["value"])
            if not kept:
                return
            history.kept(row_id, kept)
            for term in learn.observe(shown, kept):
                say(f'learned "{term}"')
        except Exception as e:
            core.log(f"dictate: learning from the last one failed: {e}")

    def _finish(self, wav, app, secs: float = 0.0):
        say = getattr(self, "note", lambda m: None)
        self._learn_from_last(app, say)
        try:
            size = os.path.getsize(wav)
        except Exception:
            size = 0
        if size < 2000:
            why = ""
            try:
                why = (core.STATE_DIR / "rec.err").read_text().strip()[:200]
            except Exception:
                pass
            say(f"no audio captured ({size} bytes)."
                + (f" sox said: {why}" if why else " sox said nothing."))
        conf = 0.0
        try:
            text, conf = stt.transcribe_ex(wav)
            text = (text or "").strip()
        except Exception as e:
            core.log(f"dictate: transcribe failed: {e}")
            say(f"transcription failed: {e}")
            text = ""
        finally:
            # Keep the last one. When a transcription comes out wrong the
            # audio is the only evidence that matters, and deleting it means
            # every investigation starts by asking the user to say it again.
            try:
                keep = core.STATE_DIR / "last-dictation.wav"
                os.replace(wav, keep)
            except Exception:
                try:
                    os.unlink(wav)
                except Exception:
                    pass
        # Whisper writes Hindi in Devanagari, which is unusable in a terminal
        # or an editor. Converting here rather than steering the model keeps
        # English untouched: this only ever rewrites characters that are
        # already Devanagari.
        if stt.language() == "hinglish" and roman.has_devanagari(text):
            before = text
            text = roman.to_latin(text)
            say(f"romanised: {before[:40]}")
        core.set_hud("listening", 0.0)
        if not text:
            say("nothing was transcribed")
            return
        say(f'heard: "{text[:70]}"')

        # Apply the words this user has taught it. This runs after the model,
        # not as a prompt to the model, because the model gets one 223 token
        # window and a growing personal vocabulary would eat all of it.
        heard = text
        try:
            fixed = vocab.shared().fix(text)
            if fixed != text:
                say(f'vocabulary: "{text[:40]}" became "{fixed[:40]}"')
                text = fixed
        except Exception as e:
            core.log(f"dictate: vocabulary failed: {e}")

        # Punctuation you said out loud, and sentence casing. List rebuilding
        # is off unless asked for: every loud complaint about tools that do
        # this is about one that could not be turned off.
        try:
            text = shape.shape(text, **_format_flags())
        except Exception as e:
            core.log(f"dictate: shaping failed: {e}")

        # Record what was heard and what was shown, so a correction later has
        # something to compare against. Text only: no audio, no screenshots,
        # and `dictator forget` removes it.
        try:
            row = history.add(heard=heard, shown=text, app=app or "",
                               lang=stt.language(), engine=stt.LAST_ENGINE,
                               secs=secs, conf=conf)
            self.last = (row, text, app or "")
        except Exception as e:
            core.log(f"dictate: history failed: {e}")
        now = mac.frontmost_app()
        if app and now and now != app:
            say(f"you moved from {app} to {now}, so I did not paste")
            # You moved. Typing here would put your sentence somewhere you were
            # not looking, which is the one failure that is not recoverable by
            # pressing undo, because you may not even see where it went.
            core.log(f"dictate: focus moved {app!r} -> {now!r}, not pasting")
            return
        say(f"pasting into {now or 'the front app'}")
        if self.send:
            # This path presses Return, which paste.deliver deliberately never
            # does, so it keeps the original single shot behaviour.
            _paste_where_you_are(text, send=True)
        elif not paste.deliver(text, now or app or ""):
            # Deliberately no retry. A long transcript is delivered in pieces,
            # so if one failed some of the text is already in the field and
            # pasting the whole thing again would duplicate it.
            say("some of that did not paste. Nothing was pasted again, "
                "to avoid duplicating what did land.")


def _paste_where_you_are(text: str, send: bool = False) -> bool:
    """Paste into the frontmost app, and put the clipboard back afterwards.

    Deliberately not the voice assistant's paste: that one refused when no target was
    named, which is correct for a caller that might be guessing. A held key is
    not a guess.

    The restore waits for a READ RECEIPT rather than a fixed delay. The obvious
    version (copy, paste, sleep, restore) is wrong in a way that only shows up
    when the machine is busy: the target has not read the pasteboard when the
    timer fires, so the restore lands first and the user gets their OLD
    clipboard pasted instead of what they just said. A fixed delay is a guess
    about somebody else's scheduling. The helper publishes the text as a
    promise, so the pasteboard calls back when something actually asks for it,
    and that callback is proof rather than hope."""
    exe = _paste_helper()
    if exe:
        try:
            args = [exe, text] + (["--send"] if send else [])
            subprocess.run(args, capture_output=True, timeout=10)
            return True
        except Exception as e:
            core.log(f"dictate: paste helper failed: {e}")
    # Fallback: the timing-guess version, which is worse but better than
    # dropping what the user said.
    saved = mac._pbpaste()
    mac._pbcopy(text)
    time.sleep(0.05)
    mac._osa('tell application "System Events" to keystroke "v" using command down')
    time.sleep(0.15)
    if send:
        mac._osa('tell application "System Events" to key code 36')
    time.sleep(0.4)
    mac._pbcopy(saved)
    return True


_PASTE_BIN = core.STATE_DIR / "bin" / "dictator-paste"
_PASTE_SRC = Path(__file__).resolve().parent.parent / "native" / "paste.swift"


def _paste_helper() -> str:
    """Build it once, then reuse."""
    try:
        if _PASTE_BIN.exists() and _PASTE_BIN.stat().st_mtime >= _PASTE_SRC.stat().st_mtime:
            return str(_PASTE_BIN)
        if not _PASTE_SRC.exists() or not shutil.which("swiftc"):
            return ""
        _PASTE_BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", str(_PASTE_SRC), "-o", str(_PASTE_BIN)],
                       check=True, capture_output=True, timeout=240)
        return str(_PASTE_BIN)
    except Exception as e:
        core.log(f"dictate: could not build the paste helper: {e}")
        return ""


def run(key: str = "fn", send: bool = False, debug: bool = True) -> int:
    """Listen until stopped. Returns an exit code.

    Deliberately noisy by default. The first version printed one banner and
    then nothing at all, so a press that never arrived, a recorder that failed
    to start and a transcription that came back empty were all the same
    experience: silence. For a feature whose whole promise is that it works
    everywhere, "nothing happened" is the least useful thing it can say."""
    import select

    d = Dictation(key, send)
    p = hotkey.listen(key, min_hold_ms=0)
    if not p:
        print("Could not start the key listener. See `dictator log`.")
        print("If this is the first run, grant Accessibility and try again:")
        print("  System Settings > Privacy & Security > Accessibility")
        print("macOS only honours a fresh grant for a NEW process, so quit")
        print("and reopen your terminal after granting.")
        return 1

    # The listener writes its diagnosis to stderr: whether it is trusted,
    # whether the tap receives anything, what to grant if not. That went into a
    # pipe nobody read, so the single most useful message in the system was the
    # one thing guaranteed never to be seen. Drain it.
    def _drain():
        try:
            for ln in iter(p.stderr.readline, ""):
                if ln.strip():
                    print(f"  {ln.rstrip()}", flush=True)
        except Exception:
            pass
    threading.Thread(target=_drain, daemon=True).start()

    def note(msg):
        if debug:
            print(f"  {msg}", flush=True)
    d.note = note

    # Without this the only way to know the mic is open is to have been
    # watching the terminal you started this from, which defeats the point of
    # a key that works everywhere.
    try:
        if not orbnative.show():
            print("  (no orb: see `dictator log`)", flush=True)
    except Exception as e:
        print(f"  (no orb: {e})", flush=True)

    print(f"Hold {key} anywhere and talk. The words land where your cursor is.")
    print("Ctrl-C to stop.\n")
    armed = False
    try:
        while True:
            # readline() rather than `for line in p.stdout`: iterating a pipe
            # goes through a hidden read-ahead buffer that waits for it to fill,
            # so events arrive late or in a clump. select gives us Ctrl-C too.
            r, _, _ = select.select([p.stdout], [], [], 0.25)
            if not r:
                if p.poll() is not None:
                    print("The key listener exited.")
                    return 1
                continue
            line = p.stdout.readline()
            if not line:
                break
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == "READY":
                armed = True
                note(f"listening for {key}. Press it and I will say so.")
            elif parts[0] == "DOWN":
                note("heard the key go down, recording...")
                d.down()
            elif parts[0] == "UP":
                held = float(parts[1]) if len(parts) > 1 else 0.0
                note(f"released after {held:.0f}ms")
                d.up(held)
            elif parts[0] in ("CANCEL", "LOCKED"):
                note("cancelled (another key joined, or the screen locked)")
                d.cancel()
            elif parts[0] == "BYE":
                break
    except KeyboardInterrupt:
        pass
    finally:
        if not armed:
            print("\nThe listener never armed, so no key press could reach it.")
        d.cancel()
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            pass
        try:
            orbnative.hide()
        except Exception:
            pass
    return 0
