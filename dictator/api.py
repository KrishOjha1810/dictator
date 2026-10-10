"""Dictator as a library: audio in, the words you would have typed out.

The reason this exists is the ORDER. Turning a recording into text is not one
call, it is six, and they only work in one sequence: transcribe, put Devanagari
into English letters, apply the words this user has taught it, shape the
punctuation, record what happened, and notice what they corrected last time.
That order used to live inside the key listener, so anything else wanting the
same result had to reproduce it, and a reproduction drifts. Now there is one
pipeline and the key listener is just its first caller.

    from dictator import Dictator

    d = Dictator()
    said = d.transcribe("recording.wav")
    print(said.text)          # after your corrections and punctuation
    print(said.heard)         # what the model actually returned

Everything is optional and off switches exist, because a caller that only
wants the model should not silently write to someone's history:

    d = Dictator(remember=False, learn=False)

Nothing here needs the key, the indicator or the launchd agent. It is the
speech half on its own.
"""
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import (core, history, learn as _learn, recap as _recap, roman,
               shape as _shape, stt, vocab)

__all__ = ["Dictator", "Transcript", "transcribe", "VERSION"]

# The shape of Transcript and the names of these methods are the promise.
# Everything under dictator/ other than this file is internal and will move.
VERSION = "1.0"


@dataclass
class Transcript:
    """What was said, and everything worth knowing about how we got there."""
    text: str = ""              # final: corrections and punctuation applied
    heard: str = ""             # what the model returned, before corrections
    confidence: float = 0.0     # 0 to 1; real directed speech scores 0.7 up
    language: str = ""          # what the router decided
    engine: str = ""            # which model actually answered
    seconds: float = 0.0        # how long the audio was
    took: float = 0.0           # how long this took, wall clock
    row: int = 0                # history id, 0 when not recorded

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    def __str__(self) -> str:
        return self.text


DEFAULT_SHAPING = {"enabled": True, "punctuation": True, "lists": False,
                   "sentences": True, "fillers": True, "stutters": True}
FORMAT_FILE = core.STATE_DIR / "format.json"

# Where held audio is kept while a capture is running, so two speech models can
# be compared on the same real speech instead of on somebody's careful reading
# of a script.
CORPUS = core.STATE_DIR / "corpus"
CAPTURE_FLAG = core.STATE_DIR / "capturing"


def capturing() -> bool:
    return CAPTURE_FLAG.exists()


def shaping_flags(app: str = "") -> dict:
    """Which shaping rules are on. The conservative ones are the defaults.

    Kept in a file rather than in code because the user has to be able to turn
    this off without editing anything, which is the single most common
    complaint about every tool that reshapes dictated text.

    `app` applies whatever the user set for that application on top. A spoken
    list belongs in Slack and is four lines with numbers in front of them at a
    shell prompt, so the same rule cannot be right in both places. See
    profiles.py. Passing nothing gives the global rules, which is what a
    caller transcribing a file rather than a hold wants."""
    flags = dict(DEFAULT_SHAPING)
    try:
        import json
        flags.update(json.loads(FORMAT_FILE.read_text()))
    except Exception:
        pass
    flags = {k: bool(v) for k, v in flags.items() if k in DEFAULT_SHAPING}
    if app:
        try:
            from . import profiles
            flags = profiles.overlay(flags, app)
        except Exception as e:
            core.log(f"dictator: per-application formatting failed: {e}")
    return flags


class Dictator:
    """The speech pipeline, as one object.

    learn=False stops it watching for corrections, remember=False stops it
    recording anything at all. Both are on by default because the product is
    built around getting better at your words, but a caller transcribing a
    hundred archived files wants neither."""

    def __init__(self, learn: bool = True, remember: bool = True,
                 shaping: "dict | None" = None, keep_audio: bool = True,
                 expand: bool = True):
        self.learning = learn
        self.remember = remember
        self.shaping = shaping
        self.keep_audio = keep_audio
        # Whether a spoken phrase may stand for a fixed piece of text. On,
        # because the user had to create every one of them by hand and a
        # store with nothing in it is already the off switch. Off is for a
        # caller transcribing somebody ELSE's audio, where this user's
        # shorthand has no business firing.
        self.expanding = expand
        self._last = None       # (row id, text, app) for correction watching
        # What the most recent transcribe() learned from a correction. Worth
        # surfacing: a tool that silently changes how it hears you is alarming,
        # and this is the one moment it can say so.
        self.last_learned: list = []

    # ---- the whole thing ---------------------------------------------

    def transcribe(self, wav: "str | Path", app: str = "",
                   ours: bool = False) -> Transcript:
        """Audio file in, finished text out. This is the pipeline.

        `ours` says the file is a recording this program made and may be
        cleaned up afterwards. The key listener passes it; nobody else should,
        and the default is False because a library that deletes the path it
        was handed is a trap, and this one was."""
        wav = str(wav)
        started = time.time()
        said = Transcript(seconds=stt.audio_seconds(wav))
        self.last_learned = self.check_corrections(app)

        # How loud it was, measured once and used twice: here to decide
        # whether transcribing is worth doing at all, and below to decide
        # whether a one-word answer is a word or an empty room.
        #
        # -1 means the file could not be read, which is not a claim about
        # the room, so it never silences anything.
        try:
            level = stt.loudness(wav)
        except Exception:
            level = -1.0

        # A room is not speech. Below this nothing in 198 corpus recordings
        # was ever a real word, and the two files that are there both came
        # back as "Thank you", so this saves a 1.6GB model load as well as a
        # wrong paste.
        if 0 <= level < stt.SILENT:
            core.log(f"dictator: nothing was said (too quiet, {level:.4f})")
            self._retire(wav, said, ours=ours)
            said.took = time.time() - started
            return said

        try:
            said.heard, said.confidence = stt.transcribe_ex(wav)
            said.heard = (said.heard or "").strip()
        except Exception as e:
            core.log(f"dictator: transcription failed: {e}")
            said.took = time.time() - started
            return said
        finally:
            self._retire(wav, said, ours=ours)
        said.language = stt.language()
        said.engine = stt.LAST_ENGINE
        # The model saying "there was nothing" is not a transcript. Pasting
        # "[MUSIC PLAYING]" into somebody's editor is worse than pasting
        # nothing, because it reads as a wrong transcription rather than as
        # silence, and they go looking for what they said wrong.
        if stt.is_silence(said.heard):
            core.log(f"dictator: nothing was said ({said.heard.strip()[:40]!r})")
            said.heard = ""
            said.took = time.time() - started
            return said

        # The other way a model says nothing: it says "Thank you".
        #
        # Whisper learned its filler from subtitle data whose silent stretches
        # were captioned with exactly these words, and it emits them on an
        # empty room with ordinary confidence, so neither the bracket test
        # above nor a probability threshold catches them. Somebody tapped the
        # key, said nothing, and "Thank you." was pasted into their editor.
        #
        # Two conditions, because either alone is wrong. The phrase alone
        # would eat a real "thank you"; the loudness alone would eat the
        # quietest real speech in the corpus, which sits at exactly the same
        # level as the loudest of these. Together they caught 7 of 7 in the
        # corpus and cost none of the 198.
        if 0 <= level < stt.QUIET_SPEECH and stt.is_filler(said.heard):
            core.log(f"dictator: nothing was said "
                     f"({said.heard.strip()[:30]!r} at {level:.4f})")
            said.heard = ""
            said.took = time.time() - started
            return said
        said.heard = self.romanise(said.heard)
        said.text = self.polish(said.heard, app=app) if said.heard else ""
        if said.text and self.remember:
            said.row = self.record(said, app)
            self._last = (said.row, said.text, app)
        said.took = time.time() - started
        return said

    # ---- the parts, for callers that want one of them -----------------

    def hear(self, wav: "str | Path") -> "tuple[str, float]":
        """Just the model. No corrections, no shaping, no recording."""
        return stt.transcribe_ex(str(wav))

    def romanise(self, text: str) -> str:
        """Devanagari into English letters, which is the only form that can be
        pasted into a terminal or an editor."""
        if text and roman.has_devanagari(text):
            return roman.to_latin(text)
        return text

    def polish(self, text: str, app: str = "") -> str:
        """The words this user has taught it, then punctuation and casing,
        then the phrases they have given a fixed text to.

        The order is not arbitrary. The vocabulary runs first because a
        snippet trigger the recogniser mangled has to be put right before
        anything can match it. Snippets run LAST, after shaping, because the
        text they insert is literal: an email address that went through the
        sentence capitaliser would come out with a capital letter the user
        never typed."""
        if not text:
            return text
        try:
            text = vocab.shared().fix(text)
        except Exception as e:
            core.log(f"dictator: vocabulary failed: {e}")
        try:
            text = _shape.shape(text,
                                **(self.shaping or shaping_flags(app)))
        except Exception as e:
            core.log(f"dictator: shaping failed: {e}")
        if self.expanding:
            from . import snippets
            text = snippets.expand(text)
        return text

    def record(self, said: Transcript, app: str = "") -> int:
        """Keep a row. Text only: no audio, no screenshots."""
        try:
            return history.add(heard=said.heard, shown=said.text, app=app,
                               lang=said.language, engine=said.engine,
                               secs=said.seconds, conf=said.confidence)
        except Exception as e:
            core.log(f"dictator: could not record: {e}")
            return 0

    def check_corrections(self, app: str = "") -> list:
        """Look at what became of the last thing pasted, and learn from it.

        Returns the terms learned, usually nothing: most edits are not
        corrections and most corrections are first sightings."""
        if not self.learning or not self._last:
            return []
        row_id, shown, last_app = self._last
        self._last = None
        if not row_id:
            return []
        if app and last_app and app != last_app:
            history.saw(row_id, "moved")
            return []
        try:
            from . import readback
            seen = readback.field()
            if not seen.get("ok") or not isinstance(seen.get("value"), str):
                history.saw(row_id, "unreadable")
                core.log("dictator: could not read the field back: "
                         + str(seen.get("why", ""))[:120])
                return []
            field = seen["value"]
            kept = _learn.locate(shown, field)
            if not kept:
                # locate() answers "" for two opposite reasons, so ask the
                # cheap question itself rather than inferring. Recording them
                # apart is the whole point: one says the loop is working and
                # you had nothing to correct, the other says it never saw a
                # thing and has been learning from nothing.
                history.saw(row_id, "same" if (shown or "").strip() in field
                            else "gone")
                return []
            history.saw(row_id, "edited")
            history.kept(row_id, kept)
            return _learn.observe(shown, kept)
        except Exception as e:
            core.log(f"dictator: learning from the last one failed: {e}")
            return []

    # ---- teaching it words --------------------------------------------

    def learn(self, term: str, heard: str = "") -> dict:
        """Teach it a word. The record says whether it can be guessed at and,
        when it cannot, why not in words the user can read."""
        return vocab.shared().add(term, heard=heard)

    def unlearn(self, term: str) -> bool:
        return vocab.shared().remove(term)

    def review(self, limit: int = 300) -> list:
        """The words it is least sure it got right, most often said first.

        Each is {"word", "count", "text", "app"}. Teaching one is `learn(said,
        heard=word)`. This exists on the library surface because the loop that
        catches corrections cannot read a terminal's text field, so a caller
        that has its own way of asking the user is better placed than we are.
        """
        from . import review as _review
        return _review.words(limit)

    # ---- forgetting ---------------------------------------------------

    def forget(self, containing: str = "", everything: bool = False) -> int:
        """Erase what was said. Returns how many rows went.

        `containing` erases only the utterances holding that text, which is
        the usual case: one thing somebody wishes they had not said out loud.
        `everything` is the whole history and has to be asked for by name,
        because a caller passing an empty search must never erase the lot.
        """
        if everything:
            return history.forget(before=9e18)
        if not (containing or "").strip():
            return 0
        return history.forget(containing=containing)

    @property
    def words(self) -> dict:
        return dict(vocab.shared().terms)

    def said(self, limit: int = 50) -> list:
        return history.recent(limit=limit)

    def recap(self, when: "str | int" = "today", prose: bool = True):
        """What you dictated in a period, summarised. `when` is "today",
        "week", "yesterday" or a number of days.

        Returns a `Recap`: `text` is the report as it would be printed,
        `sessions` and `terms` are the same thing structured, and `source`
        says who wrote the prose or why nobody did. `prose=False` skips the
        local model entirely, which is what a caller wants when it is going to
        do its own wording.

        Reads history and nothing else. It starts no recording, asks for no
        permission, and talks to no network: a summary is a convenience and
        this product's only real promise is that nothing leaves the machine."""
        return _recap.report(when, prose=prose)

    # ---- getting it onto the screen ------------------------------------

    def paste(self, text: str, app: str = "") -> bool:
        """Deliver into the frontmost application. Never presses Return."""
        from . import paste as _paste, mac
        return _paste.deliver(text, app or mac.frontmost_app() or "")

    # ---- internals -----------------------------------------------------

    def _retire(self, wav: str, said: "Transcript | None" = None,
                ours: bool = False) -> None:
        """Keep the last recording, because when a transcription comes out
        wrong the audio is the only evidence that matters.

        And keep ALL of them while a capture is running. Comparing two speech
        models needs the same audio through both, and this product otherwise
        keeps none: every hold overwrites the last one. Asking somebody to sit
        down and record forty sentences to order produces careful, unnatural
        speech, which is the wrong thing to measure. Their ordinary dictation
        is the right corpus, and this is how it gets collected."""
        # And only a recording we made gets kept, for the same reason. A
        # measurement run transcribing the benchmark corpus was adding a copy
        # of every file back into it: 166 recordings had grown 586 transcripts
        # before anybody looked, and each pass made the next pass slower and
        # the corpus less like what the user actually said.
        try:
            if ours and capturing():
                keep = CORPUS / f"{int(time.time() * 1000)}.wav"
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(wav, keep)
                if said is not None:
                    keep.with_suffix(".txt").write_text(said.heard or "")
        except Exception as e:
            core.log(f"dictator: could not keep the recording: {e}")
        # Only a recording WE made. This used to delete whatever path it was
        # handed, which is right for the listener, whose file is a temporary
        # one nobody else owns, and catastrophic for every other caller: a
        # library whose `transcribe(path)` removes the caller's file.
        #
        # It destroyed a benchmark corpus one measurement at a time, and then
        # the forty recordings somebody had just spent twenty minutes writing
        # reference transcripts for, because the scorer transcribed each one
        # and this deleted it afterwards. Nothing in the signature said so.
        if not ours:
            return
        try:
            if self.keep_audio:
                os.replace(wav, core.STATE_DIR / "last-dictation.wav")
            else:
                os.unlink(wav)
        except Exception:
            pass


_shared = None


def transcribe(wav: "str | Path", **kw) -> Transcript:
    """One call, for callers that do not want to hold an object."""
    global _shared
    if _shared is None:
        _shared = Dictator(**kw)
    return _shared.transcribe(wav)
