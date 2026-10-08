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
import subprocess
import threading
import time

from . import core, hotkey, mac, orbnative, paste, stt, warmup
from .api import Dictator

# When a hold that produced nothing is worth telling the user about.
#
# Loudness alone cannot do it, and the corpus says so plainly. A 0.67s hold
# measuring 0.0020 RMS is silence, and the model hallucinated Japanese at it. A
# 1.01s hold measuring 0.0026 is a real "Yeah." that transcribed correctly.
# Those two are adjacent, so any floor that reports the first stays silent on
# the second, and the other way round.
#
# Duration separates them where loudness cannot: the first is a brush of the
# key and the second is somebody answering. So both, and neither alone:
#
#   under a second          a mis-press, say nothing
#   quieter than this       there was nothing to hear, say nothing
#   otherwise, and empty    they spoke and we lost it, say so
QUIET = 0.002
TOO_BRIEF = 1.0


# Anything shorter is a mis-press, not speech. Kept low because a short real
# utterance ("yes", "ship it") is common and losing it is worse than
# transcribing a click into nothing.
MIN_MS = 250
MAX_SECS = 120


def publish(state: str, error: "str|None" = None) -> None:
    """Tell the app what the loop is doing, through status.json.

    Called on state changes only, never from the level pump or the
    still-working loop, so it costs a few stat calls and one small write per
    hold. "ready" turns into "downloading" while a model English needs is
    still arriving, because a ready that cannot transcribe is not ready; the
    Hinglish model arriving in the background leaves it ready, since English
    works without it. Never raises."""
    try:
        models = stt.model_status()
    except Exception:
        models = {}
    if state == "ready":
        try:
            if any(stt.arriving(m[0]) for m in stt.missing(essential_only=True)):
                state = "downloading"
        except Exception:
            pass
    core.write_status(state, models=models, error=error)


def _engine_name(engine: str) -> str:
    """The engine, as something a person can hold in their head.

    `cli:ggml-large-v3-turbo.bin` is the filename of a thing, not an answer to
    "why was that one bad"."""
    e = engine or ""
    if e == "parakeet":
        return "the fast English engine"
    if "parakeet" in e:
        return "the fast English engine"
    if "small.en" in e:
        return "the small English model"
    if "turbo" in e or "large" in e:
        return "the multilingual model"
    return e or "an unknown engine"


class Dictation:
    """One hold: record while down, transcribe on release, paste where you were."""

    def __init__(self, key: str = "fn", send: bool = False,
                 sdk: "Dictator | None" = None):
        self.sdk = sdk or Dictator()
        self.key = key
        # The pipeline. Shared with every other caller by construction.
        self.send = send
        self.proc = None            # the recorder
        self.wav = ""
        self._n = 0
        self.app = ""               # what was in front when you pressed
        self.started = 0.0
        # Set when the listener says it cannot see the keyboard. Kept, so
        # that the end of a hold does not report "ready" over the top of it.
        self.blocked = ""

    def _publish(self, state: str) -> None:
        if state == "ready" and self.blocked:
            publish("needs_permission", self.blocked)
        else:
            publish(state)

    # ---- the two edges ----------------------------------------------------

    def down(self):
        if self.proc:
            return
        self.app = mac.frontmost_app()
        # A path per HOLD, not per process. It used to be the pid, which does
        # not change, so a second hold started recording over the file the
        # first one was still transcribing. Both were lost, silently: no
        # transcript, no error, just a hold that produced nothing. The log
        # showed it as "could not keep the recording: No such file".
        self._n += 1
        self.wav = f"/tmp/dictator-rec-{os.getpid()}-{self._n}.wav"
        # No silence detection: you are holding a key, so you are the
        # boundary. Automatic trimming would eat your first word (you
        # start speaking as you press) and end the take at your first pause.
        self.proc = stt.record_hold(self.wav, max_secs=MAX_SECS)
        self.started = time.time()
        # After the recorder, never before: the microphone opening is the one
        # thing here that must not wait for anything. From this point the model
        # is read from disk WHILE you talk, so that when you let go the only
        # thing left is the work that needs the audio. See warmup.py.
        warmup.models()
        core.set_hud("hearing", 0.0)
        self._publish("listening")
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
        # Why it ended, read before anything else touches the file. A recorder
        # that lost its input has already exited, so the terminate above was a
        # no-op and the code waiting here is its own rather than ours.
        # Imported here rather than at the top because this is the only place
        # in this module that needs it, and it is already in sys.modules by the
        # time a key can be released.
        cut = ""
        try:
            from . import recorder as _rec
            cut = _rec.why_it_stopped(p)
        except Exception:
            pass
        if held_ms < MIN_MS:
            core.set_hud("listening", 0.0)
            self._publish("ready")
            return
        core.set_hud("thinking", 0.0)
        self._publish("transcribing")
        threading.Thread(target=self._finish,
                         args=(self.wav, self.app, held_ms / 1000.0, cut),
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
        self._publish("ready")

    # ---- off the key thread -----------------------------------------------

    def _finish(self, wav, app, secs: float = 0.0, cut: str = ""):
        """One hold, delivered, and then the app told it is over. The work
        is in _deliver; this only makes sure "transcribing" cannot outlive
        it, whichever of its many returns it leaves by."""
        try:
            self._deliver(wav, app, secs, cut)
        finally:
            # Unless another hold has started meanwhile: that one is
            # listening, and saying ready over it would be the app showing a
            # closed microphone while it is open.
            if not self.proc:
                self._publish("ready")

    def _deliver(self, wav, app, secs: float = 0.0, cut: str = ""):
        """One hold, from the recording to the words being on screen.

        The pipeline itself lives in api.py and this calls it. It used to live
        here, which meant anything else wanting the same result had to
        reproduce the order, and a reproduction drifts.

        `cut` is set when the recording ended early. What is in the file is
        still transcribed and still delivered, because losing what somebody
        said is the failure this product is least allowed to have and part of
        a sentence is worth more than none of it. What must not happen is
        delivering it as though nothing went wrong, so the reason is said
        first and written where `dictator errors` can repeat it."""
        say = getattr(self, "note", lambda m: None)
        if cut:
            # Before the transcript rather than after. The user is about to be
            # handed part of their own sentence, punctuated and capitalised
            # exactly like a whole one, and a warning that arrives once they
            # have read it is not a warning. Surfaced as well as said: `note`
            # only prints in the foreground, and a listener under launchd has
            # no terminal for anyone to be watching.
            core.surface_error("record", cut, "Run: dictator doctor")
            say(cut)
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
                + (f" the recorder said: {why}" if why
                   else " the recorder said nothing."))

        # Keep saying "thinking" for as long as it is true. The indicator only
        # trusts a state written in the last second, and transcription takes
        # several, so a single write meant the orb vanished one second after
        # the key came up and the user was left watching nothing happen.
        done = threading.Event()

        def still_working():
            while not done.wait(0.4):
                core.set_hud("thinking", 0.0)

        threading.Thread(target=still_working, daemon=True).start()
        try:
            # ours: this is the listener's own temporary recording, and it is
            # the one caller that should have it cleaned up afterwards.
            said = self.sdk.transcribe(wav, app=app or "", ours=True)
        finally:
            done.set()
        core.set_hud("listening", 0.0)
        for term in self.sdk.last_learned:
            say(f'learned "{term}"')
        if not said.text:
            say("nothing was transcribed")
            # A hold that produced nothing is invisible: `say` only prints to a
            # terminal and the listener runs under launchd, so the user pressed
            # the key, spoke, and watched nothing happen with no indication
            # anywhere. It happened 24 times in 151 holds in one real log.
            #
            # Not every empty hold is worth reporting. A brief press with
            # nothing said is an ordinary thing to do and should stay silent.
            # The two are told apart by whether there was anything to hear:
            # `stt.loudness` is one pass over samples we already have, and
            # until now it had no callers at all.
            try:
                level = stt.loudness(wav)
                held = stt.audio_seconds(wav)
            except Exception:
                level, held = -1.0, 0.0
            if level >= QUIET and held >= TOO_BRIEF:
                core.surface_error(
                    "transcribe",
                    "You spoke, and nothing could be made of it.",
                    hint="Said again more slowly it usually lands. "
                         "`dictator log` says which engine answered.")
            return
        # Which engine answered. The two behave very differently and the user
        # cannot currently tell them apart, so "it is excellent sometimes and
        # poor sometimes" is as precise as any report can be. Measured over
        # 270 real holds: the English engine 0.78% gibberish, the multilingual
        # one it falls through to 7.27%. Knowing which answered is the first
        # thing anybody needs to say something useful about a bad hold.
        say(f"answered by {_engine_name(said.engine)}")
        if said.heard != said.text:
            say(f'heard: "{said.heard[:60]}"')
            say(f'wrote: "{said.text[:60]}"')
        else:
            say(f'heard: "{said.text[:70]}"')

        now = mac.frontmost_app()
        if app and now and now != app:
            say(f"you moved from {app} to {now}, so I did not paste")
            # You moved. Typing here would put your sentence somewhere you were
            # not looking, which is the one failure that is not recoverable by
            # pressing undo, because you may not even see where it went.
            core.log(f"dictate: focus moved {app!r} to {now!r}, not pasting")
            return
        say(f"pasting into {now or 'the front app'}")
        if self.send:
            # This path presses Return, which paste.deliver deliberately never
            # does, so it keeps the original single shot behaviour.
            _paste_where_you_are(said.text, send=True)
        elif not paste.deliver(said.text, now or app or ""):
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


def _paste_helper() -> str:
    """Build it once, then reuse.

    The same helper paste.py delivers with, found and built the same way. This
    used to carry its own copy of the swiftc call, which would have gone on
    compiling into ~/.dictator inside the app, where the helper is prebuilt
    and nothing may be compiled."""
    return paste.helper()


def run(key: str = "fn", send: bool = False, debug: bool = True) -> int:
    """Listen until stopped. Returns an exit code.

    Deliberately noisy by default. The first version printed one banner and
    then nothing at all, so a press that never arrived, a recorder that failed
    to start and a transcription that came back empty were all the same
    experience: silence. For a feature whose whole promise is that it works
    everywhere, "nothing happened" is the least useful thing it can say."""
    import select

    d = Dictation(key, send)
    # The listener's session cap and the recorder's cap have to be the same
    # number. If the listener ran longer, it would keep reporting that it is
    # listening after the recorder had already stopped, which is the exact
    # failure this product cannot have: a microphone the user believes is open
    # and is not, or the reverse.
    p = hotkey.listen(key, min_hold_ms=0, max_session_ms=int(MAX_SECS * 1000))
    if not p:
        publish("error", "Could not start the key listener.")
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
                # The two lines that mean no key press will ever arrive.
                # Everything else it says is advice around them.
                if ("trusted = false" in ln
                        or "could not create an event tap" in ln):
                    d.blocked = ("Dictator needs Accessibility to see the "
                                 "key. Allow it in Privacy & Security.")
                    d._publish("ready")
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

    # The very first hold is the one somebody judges this on, and it is the
    # only one with no head start: the model has never been read and the
    # helpers have never been executed. Both are paid here, while nobody is
    # waiting, and cost nothing on a machine that has already paid them.
    warmup.at_startup()

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
                    publish("error", "The key listener exited.")
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
                d._publish("ready")
                note(f"listening for {key}. Press it and I will say so.")
            elif parts[0] == "DOWN":
                note("heard the key go down, recording...")
                d.down()
            elif parts[0] == "UP":
                held = float(parts[1]) if len(parts) > 1 else 0.0
                note("hands free session ended" if "toggle" in parts
                     else f"released after {held:.0f}ms")
                d.up(held)
            elif parts[0] == "LATCH":
                # Hands free. The microphone opened by DOWN keeps running, and
                # the key release that follows emits nothing, so there is
                # nothing to do here except say so. Saying so matters: the
                # user has taken their hand off the key and the only thing
                # telling them the mic is still open is the indicator.
                note("hands free now. Tap the chord again to stop.")
                core.set_hud("hearing", 0.0)
            elif parts[0] == "LISTENING":
                # A heartbeat, so a listener that died quietly is not mistaken
                # for one that is patiently waiting.
                core.set_hud("hearing", 0.0)
            elif parts[0] in ("CANCEL", "LOCKED"):
                why = parts[2] if len(parts) > 2 else ""
                note({
                    "cap": "that hit the time limit, so I threw it away rather "
                           "than pasting minutes of whatever the room said",
                    "tap": "I lost sight of the keyboard, so I stopped and "
                           "threw it away",
                    "exit": "stopping, so I threw that away",
                    "lock": "the screen locked, so I threw that away",
                }.get(why, "cancelled (another key joined, or the screen locked)"))
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
        # Stopped on purpose, or the listener said goodbye. Either way nothing
        # is listening now, and leaving "ready" in the file would have the app
        # promise a key that does nothing. An error written above stays.
        if core.read_status().get("state") != "error":
            publish("paused")
        try:
            orbnative.hide()
        except Exception:
            pass
    return 0
