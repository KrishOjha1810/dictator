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

from . import control, core, fetch, hotkey, mac, media, orbnative, paste, stt, warmup
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


# What the loop last asked publish() for, so the model watcher can write the
# same state again with fresher model progress. Behind a lock with the write,
# so the watcher can never put back a state the loop has already left.
_published: list = []
_publish_lock = threading.RLock()


def publish(state: str, error: "str|None" = None) -> None:
    """Tell the app what the loop is doing, through status.json.

    Called on state changes, never from the level pump or the still-working
    loop, so it costs a few stat calls and one small write per hold. The one
    other caller is _watch_models, which repeats the last state while a model
    is arriving. "ready" turns into "downloading" while a model English needs
    is still arriving, because a ready that cannot transcribe is not ready;
    the Hinglish model arriving in the background leaves it ready, since
    English works without it. Never raises."""
    with _publish_lock:
        _published[:] = [state, error]
        _write_status(state, error)


def republish() -> None:
    """Write the last state again, with the models as they are now."""
    with _publish_lock:
        if _published:
            _write_status(*_published)


def _write_status(state: str, error: "str|None") -> None:
    try:
        models = stt.model_status()
    except Exception:
        models = {}
    if state == "ready":
        # A ready that cannot transcribe is not ready. While a model English
        # needs is arriving that is "downloading"; when it was removed or its
        # download failed, nothing will bring it back on its own, so it is an
        # error that says where the button is.
        for name, m in models.items():
            if m.get("have") or not m.get("essential"):
                continue
            if m.get("removed") or (m.get("error") and not m.get("downloading")):
                state = "error"
                title = next((f"The {a.capitalize()} model" for a, n in stt.ALIASES.items()
                              if n == name), name)
                error = (f"{title} was removed. Download it in Settings."
                         if m.get("removed")
                         else f"{title} did not download. Retry in Settings.")
                break
            if m.get("downloading") or stt.arriving(name):
                state = "downloading"
    core.write_status(state, models=models, error=error)


def _watch_models(stop: threading.Event, every: float = 1.5) -> None:
    """Keep status.json's models current for as long as the loop runs.

    status.json is otherwise written only when the loop changes state, so a
    download that finished while nobody pressed the key stayed "have": false
    in it, and the app's model card waited for a key press that the card
    itself does not ask for. It also has to see a model the user removes or
    downloads again from Settings, which can happen at any time, so it does
    not stop once everything is here. A few stat calls every 1.5 seconds,
    and a write only when something changed."""
    last = None
    while not stop.wait(every):
        try:
            now = stt.model_status()
        except Exception:
            continue
        if now != last:
            republish()
            last = now


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
        # Holds released and still being transcribed. "ready" is only true
        # when this is zero and no recorder is open, and the check and the
        # write happen under one lock, the same one down() publishes
        # "listening" under, so a hold ending on its own thread cannot say
        # ready over a hold that has just started or is still transcribing.
        self._lock = threading.Lock()
        self._inflight = 0
        # Set once the loop has written its last word. A transcription
        # still finishing after that must not say "ready" over it.
        self._stopped = False
        # A hands free session is open: the listener said LATCH, after a
        # double tap of the key or a click on the pill. The microphone stays
        # open until a press of the key, the pill's check, Escape, the pill's
        # cross or the cap. Written into hud.json (phase "handsfree") so the
        # pill can draw its cross and check; it is appearance only, the pill
        # still decides "listening" from the microphone itself.
        self.hands_free = False
        # Other audio paused or muted while the microphone is open (media.py).
        self._quiet = None

    def _publish(self, state: str) -> None:
        if state == "ready" and self.blocked:
            publish("needs_permission", self.blocked)
        else:
            publish(state)

    def _settle(self) -> None:
        """Say ready, unless it is not true yet. Takes the lock."""
        with self._lock:
            self._settle_locked()

    def _settle_locked(self) -> None:
        if self.proc or self._stopped:
            return
        self._publish("transcribing" if self._inflight else "ready")

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
        # Music from the speakers ends up in the transcript. Paused, or muted,
        # a beat after the microphone opens, and never in its way.
        self._quiet = media.Quieting().start()
        # After the recorder, never before: the microphone opening is the one
        # thing here that must not wait for anything. From this point the model
        # is read from disk WHILE you talk, so that when you let go the only
        # thing left is the work that needs the audio. See warmup.py.
        warmup.models()
        self.hands_free = False
        core.set_hud("hearing", 0.0)
        with self._lock:
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
                    core.set_hud(self.phase(),
                                 min(1.0, max(0.0, (raw - floor) / span)))
            except Exception:
                pass
            time.sleep(0.08)

    def phase(self) -> str:
        """What hud.json says while the microphone is open."""
        return "handsfree" if self.hands_free else "hearing"

    def latch(self):
        """The hold that is recording became a hands free session."""
        if self.proc:
            self.hands_free = True
            core.set_hud("handsfree", 0.0)

    def _unquiet(self):
        q, self._quiet = self._quiet, None
        if q:
            q.stop()

    def up(self, held_ms: float):
        self.hands_free = False
        p, self.proc = self.proc, None
        self._unquiet()
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
            self._settle()
            return
        core.set_hud("thinking", 0.0)
        with self._lock:
            self._inflight += 1
            self._publish("transcribing")
        threading.Thread(target=self._finish,
                         args=(self.wav, self.app, held_ms / 1000.0, cut,
                               time.monotonic()),
                         daemon=True).start()

    def cancel(self, publish: bool = True):
        """Another key joined the hold, so you were typing a chord, not talking.

        `publish` is False when the loop is stopping: it writes its own last
        word, and a "ready" written here first would be the app's last view
        of a loop that is gone."""
        self.hands_free = False
        p, self.proc = self.proc, None
        self._unquiet()
        if p:
            try:
                p.terminate()
            except Exception:
                pass
        core.set_hud("listening", 0.0)
        if publish:
            self._settle()

    # ---- off the key thread -----------------------------------------------

    def _finish(self, wav, app, secs: float = 0.0, cut: str = "",
                released: "float|None" = None):
        """One hold, delivered, and then the app told it is over. The work
        is in _deliver; this only makes sure "transcribing" cannot outlive
        it, whichever of its many returns it leaves by."""
        try:
            self._deliver(wav, app, secs, cut, released)
        finally:
            # Unless another hold has started meanwhile, or is still being
            # transcribed: saying ready over the first would be the app
            # showing a closed microphone while it is open, and over the
            # second, an idle loop while it is working.
            with self._lock:
                self._inflight = max(0, self._inflight - 1)
                self._settle_locked()

    def _deliver(self, wav, app, secs: float = 0.0, cut: str = "",
                 released: "float|None" = None):
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
            # `cut` is read below, but a zero byte file is exactly the
            # case where its reason is the whole story, so it is read here
            # too rather than letting "the recorder said nothing" stand in
            # for an explanation the process already gave us.
            early = ""
            try:
                from . import recorder as _r
                early = _r.why_it_stopped(p)
            except Exception:
                pass
            say(f"no audio captured ({size} bytes)."
                + (f" {early}" if early
                   else (f" the recorder said: {why}" if why
                         else " the recorder said nothing.")))

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

        def took() -> "int|None":
            # From the key coming up to now: what the person waited through.
            return (int((time.monotonic() - released) * 1000)
                    if released is not None else None)

        now = mac.frontmost_app()
        if app and now and now != app:
            core.write_last(said.text, took(), said.engine, now or "")
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
            core.write_last(said.text, took(), said.engine, now or "", True)
        elif not paste.deliver(said.text, now or app or ""):
            core.write_last(said.text, took(), said.engine, now or "")
            # Deliberately no retry. A long transcript is delivered in pieces,
            # so if one failed some of the text is already in the field and
            # pasting the whole thing again would duplicate it.
            say("some of that did not paste. Nothing was pasted again, "
                "to avoid duplicating what did land.")
        else:
            core.write_last(said.text, took(), said.engine, now or "", True)
        # One line per hold, so the wait can be measured from the log over
        # real use rather than guessed at.
        ms = took()
        if ms is not None:
            say(f"{ms} ms from letting go to the words landing")
            core.log(f"timing: {ms}ms release-to-paste, {secs:.1f}s held, "
                     f"{said.engine}")

# Why a take was thrown away, in the words the user is told.
DISCARDED = {
    "cap": "that hit the time limit, so I threw it away rather "
           "than pasting minutes of whatever the room said",
    "tap": "I lost sight of the keyboard, so I stopped and "
           "threw it away",
    "exit": "stopping, so I threw that away",
    "lock": "the screen locked, so I threw that away",
    "esc": "Escape, so I threw that away and pasted nothing",
    "button": "cancelled from the pill, nothing pasted",
}


def handle(d: "Dictation", line: str, note=lambda m: None) -> str:
    """One line from the key listener, acted on. Returns "ready" when it
    armed, "bye" when it is leaving, and "" otherwise.

    Out of run() so the whole state machine can be driven by a test with the
    lines a real listener prints, including the ones the double tap and the
    pill's buttons produce."""
    parts = line.strip().split()
    if not parts:
        return ""
    verb = parts[0]
    if verb == "READY":
        d._publish("ready")
        note(f"listening for {d.key}. Press it and I will say so.")
        return "ready"
    if verb == "DOWN":
        note("heard the key go down, recording...")
        d.down()
    elif verb == "UP":
        held = 0.0
        if len(parts) > 1:
            try:
                held = float(parts[1])
            except ValueError:
                pass
        note("hands free session ended" if "toggle" in parts
             else f"released after {held:.0f}ms")
        d.up(held)
    elif verb == "LATCH":
        # Hands free. The microphone opened by DOWN keeps running, and the
        # key release that follows emits nothing. Saying so matters: the
        # user has taken their hand off the key and the only thing telling
        # them the mic is still open is the indicator.
        note("hands free now. Press the key once to finish, Escape to "
             "throw it away.")
        d.latch()
    elif verb == "LISTENING":
        # A heartbeat, so a listener that died quietly is not mistaken for
        # one that is patiently waiting.
        core.set_hud(d.phase(), 0.0)
    elif verb in ("CANCEL", "LOCKED"):
        why = parts[2] if len(parts) > 2 else ""
        note(DISCARDED.get(why, "cancelled (another key joined, or the screen "
                                "locked)"))
        d.cancel()
    elif verb == "BYE":
        return "bye"
    return ""


# What each command from the pill (control.py) asks of the key listener.
TO_LISTENER = {"toggle": "TOGGLE", "finish": "FINISH", "cancel": "CANCEL"}


def command(p, word: str, note=lambda m: None) -> bool:
    """Pass one command from the pill on to the key listener, which owns the
    session. True if it was passed on."""
    to = TO_LISTENER.get(word)
    if not to:
        return False
    note(f"the pill says {word}")
    return hotkey.tell(p, to)


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
    # The listener's floor is MIN_MS, the same number `up` throws a hold away
    # at. They used to disagree: the listener reported every brush of the key
    # and `up` then discarded anything under 250ms, so the microphone opened,
    # a recorder started and a file was written for a press that had already
    # been decided against.
    #
    # It is not theoretical. In one real log, 19 of 49 holds were under 150ms
    # and 23 were under a second; the key here is fn, which hands and sleeves
    # find on their own. Every one of them opened the microphone.
    #
    # Measured before raising it: a floor at 250ms discards 20 of those 49 and
    # costs zero utterances that had produced words, and the shortest hold in
    # the whole log that produced any text at all was 770ms ("Okay.").
    p = hotkey.listen(key, min_hold_ms=MIN_MS,
                      max_session_ms=int(MAX_SECS * 1000))
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
                    with d._lock:
                        d._publish("ready")
        except Exception:
            pass
    drain = threading.Thread(target=_drain, daemon=True)
    drain.start()

    def note(msg):
        if debug:
            print(f"  {msg}", flush=True)
    d.note = note

    # Without this the only way to know the mic is open is to have been
    # watching the terminal you started this from, which defeats the point of
    # a key that works everywhere.
    try:
        if not orbnative.show(key=key):
            print("  (no orb: see `dictator log`)", flush=True)
    except Exception as e:
        print(f"  (no orb: {e})", flush=True)

    # The very first hold is the one somebody judges this on, and it is the
    # only one with no head start: the model has never been read and the
    # helpers have never been executed. Both are paid here, while nobody is
    # waiting, and cost nothing on a machine that has already paid them.
    warmup.at_startup()
    # A mute an earlier run made and never undid, because it was killed.
    media.recover()

    # Models that are still arriving get their progress written as it moves,
    # not only when a key is pressed.
    stop_watch = threading.Event()
    # The app has no installer to fetch them, so the loop does, English
    # first. A repo install got them from scripts/install.sh and is left alone.
    if core.BUNDLE:
        fetch.in_background()
    threading.Thread(target=_watch_models, args=(stop_watch,),
                     daemon=True).start()

    # The app stops this loop with SIGTERM (Pause, a new key, Quit). Python's
    # default for it is to die where it stands, which skipped everything in
    # the finally below: the recorder was left running with the microphone
    # open until its own time limit, and status.json kept saying "listening".
    # Treated as Ctrl-C instead, which is already a clean stop.
    _old_term = _on_sigterm()
    _write_pid()

    # The pill's buttons, and `dictator hands-free`, reach the loop here.
    ctl = control.Server()
    if not ctl.start():
        ctl = None

    print(f"Hold {key} anywhere and talk. The words land where your cursor is.")
    print("Ctrl-C to stop.\n")
    armed = False
    # What to leave in status.json when the loop ends without being asked
    # to. None means it was asked to (Ctrl-C, SIGTERM, BYE): "paused".
    final = None
    code = 0
    try:
        while True:
            # readline() rather than `for line in p.stdout`: iterating a pipe
            # goes through a hidden read-ahead buffer that waits for it to fill,
            # so events arrive late or in a clump. select gives us Ctrl-C too.
            r, _, _ = select.select([p.stdout] + ([ctl] if ctl else []),
                                    [], [], 0.25)
            if ctl and ctl in r:
                for word in ctl.read():
                    command(p, word, note)
                if p.stdout not in r:
                    continue
            if not r:
                if p.poll() is not None:
                    final, code = ("error", "The key listener exited."), 1
                    break
                continue
            line = p.stdout.readline()
            if not line:
                # End of its output without a BYE is the listener dying, and
                # in practice the only way that is seen: a closed pipe reads
                # as ready, so the branch above almost never runs.
                final, code = ("error", "The key listener exited."), 1
                break
            what = handle(d, line, note)
            if what == "ready":
                armed = True
            elif what == "bye":
                break
    except KeyboardInterrupt:
        pass
    finally:
        if not armed:
            print("\nThe listener never armed, so no key press could reach it.")
        d.cancel(publish=False)
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            pass
        # Its last lines on stderr are often the reason it stopped ("could
        # not create an event tap"), and the thread reading them can still be
        # behind. Once the listener has exited that pipe ends, so this is short.
        drain.join(timeout=2)
        stop_watch.set()
        # One last word, and the most specific one there is. A missing
        # permission is something the user can fix and the app has a button
        # for; a listener that died is an error; anything else was a stop on
        # purpose. Nothing is listening in any of them, so "ready" is never
        # left behind for the app to promise a key that does nothing.
        with d._lock:
            d._stopped = True
            if d.blocked:
                publish("needs_permission", d.blocked)
            elif final:
                print(final[1])
                publish(*final)
            else:
                publish("paused")
        _restore_sigterm(_old_term)
        _remove_pid()
        # Pause and Quit both end here. A model kept in memory for holds
        # that can no longer happen is memory taken from everything else.
        try:
            if stt.release_server():
                core.log("dictate: stopped the resident model server")
        except Exception:
            pass
        if ctl:
            ctl.close()
        try:
            orbnative.hide()
        except Exception:
            pass
    return code


PID_NAME = "dictate.pid"


def _write_pid() -> None:
    """Which process is the loop, for `dictator status` in the app.

    Inside the app there is no login item for launchd to be asked about, so
    the pid is the only way to tell a loop that is running from one that
    stopped and left its last status.json behind. A path computed at call
    time, so a test's state directory is the one written."""
    try:
        core.STATE_DIR.mkdir(parents=True, exist_ok=True)
        (core.STATE_DIR / PID_NAME).write_text(str(os.getpid()))
    except Exception:
        pass


def _remove_pid() -> None:
    try:
        f = core.STATE_DIR / PID_NAME
        if f.read_text().strip() == str(os.getpid()):
            f.unlink()
    except Exception:
        pass


def loop_running() -> bool:
    """Is a dictation loop alive, by the pid it wrote."""
    try:
        pid = int((core.STATE_DIR / PID_NAME).read_text().strip())
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except Exception:
        return False


def _on_sigterm():
    import signal

    def _stop(signum, frame):
        raise KeyboardInterrupt
    try:
        return signal.signal(signal.SIGTERM, _stop)
    except Exception:
        # Not the main thread, as in a test: nothing to install.
        return None


def _restore_sigterm(old) -> None:
    if old is None:
        return
    import signal
    try:
        signal.signal(signal.SIGTERM, old)
    except Exception:
        pass
