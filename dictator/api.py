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
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import core, history, learn as _learn, roman, shape as _shape, stt, vocab

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
                   "sentences": True}
FORMAT_FILE = core.STATE_DIR / "format.json"


def shaping_flags() -> dict:
    """Which shaping rules are on. The conservative ones are the defaults.

    Kept in a file rather than in code because the user has to be able to turn
    this off without editing anything, which is the single most common
    complaint about every tool that reshapes dictated text."""
    flags = dict(DEFAULT_SHAPING)
    try:
        import json
        flags.update(json.loads(FORMAT_FILE.read_text()))
    except Exception:
        pass
    return {k: bool(v) for k, v in flags.items() if k in DEFAULT_SHAPING}


class Dictator:
    """The speech pipeline, as one object.

    learn=False stops it watching for corrections, remember=False stops it
    recording anything at all. Both are on by default because the product is
    built around getting better at your words, but a caller transcribing a
    hundred archived files wants neither."""

    def __init__(self, learn: bool = True, remember: bool = True,
                 shaping: "dict | None" = None, keep_audio: bool = True):
        self.learning = learn
        self.remember = remember
        self.shaping = shaping
        self.keep_audio = keep_audio
        self._last = None       # (row id, text, app) for correction watching
        # What the most recent transcribe() learned from a correction. Worth
        # surfacing: a tool that silently changes how it hears you is alarming,
        # and this is the one moment it can say so.
        self.last_learned: list = []

    # ---- the whole thing ---------------------------------------------

    def transcribe(self, wav: "str | Path", app: str = "") -> Transcript:
        """Audio file in, finished text out. This is the pipeline."""
        wav = str(wav)
        started = time.time()
        said = Transcript(seconds=stt.audio_seconds(wav))
        self.last_learned = self.check_corrections(app)
        try:
            said.heard, said.confidence = stt.transcribe_ex(wav)
            said.heard = (said.heard or "").strip()
        except Exception as e:
            core.log(f"dictator: transcription failed: {e}")
            said.took = time.time() - started
            return said
        finally:
            self._retire(wav)
        said.language = stt.language()
        said.engine = stt.LAST_ENGINE
        said.heard = self.romanise(said.heard)
        said.text = self.polish(said.heard) if said.heard else ""
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

    def polish(self, text: str) -> str:
        """The words this user has taught it, then punctuation and casing."""
        if not text:
            return text
        try:
            text = vocab.shared().fix(text)
        except Exception as e:
            core.log(f"dictator: vocabulary failed: {e}")
        try:
            text = _shape.shape(text, **(self.shaping or shaping_flags()))
        except Exception as e:
            core.log(f"dictator: shaping failed: {e}")
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
        if not row_id or (app and last_app and app != last_app):
            return []
        try:
            from . import readback
            seen = readback.field()
            if not seen.get("ok") or not isinstance(seen.get("value"), str):
                return []
            kept = _learn.locate(shown, seen["value"])
            if not kept:
                return []
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

    @property
    def words(self) -> dict:
        return dict(vocab.shared().terms)

    def said(self, limit: int = 50) -> list:
        return history.recent(limit=limit)

    # ---- getting it onto the screen ------------------------------------

    def paste(self, text: str, app: str = "") -> bool:
        """Deliver into the frontmost application. Never presses Return."""
        from . import paste as _paste, mac
        return _paste.deliver(text, app or mac.frontmost_app() or "")

    # ---- internals -----------------------------------------------------

    def _retire(self, wav: str) -> None:
        """Keep the last recording, because when a transcription comes out
        wrong the audio is the only evidence that matters."""
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
