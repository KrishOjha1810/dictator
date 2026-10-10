"""Dictator as a library.

The point of this layer is the ORDER. Turning a recording into text is six
steps that only work in one sequence, and that sequence used to live inside
the key listener, so anything else wanting the same result had to reproduce
it. A reproduction drifts, quietly, and the drift shows up as one caller
getting corrections applied and another not.
"""
import ast
from pathlib import Path
from unittest import mock

import pytest

import dictator
from dictator import Dictator, Transcript, api

ROOT = Path(__file__).resolve().parent.parent


def test_the_public_surface_is_small_and_named():
    assert dictator.__all__ == ["Dictator", "Transcript", "transcribe", "VERSION"]
    assert dictator.VERSION


def test_a_transcript_knows_what_was_heard_and_what_was_written():
    """These differ whenever a correction fired, and a caller that cannot see
    both has no way to show the user what changed."""
    said = Transcript(text="Whisper Flow is good", heard="whisper floor is good")
    assert said.text != said.heard
    assert str(said) == "Whisper Flow is good"
    assert said
    assert not Transcript(text="   ")


def test_the_pipeline_runs_in_order(monkeypatch, tmp_path):
    order = []
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")

    d = Dictator(remember=False, learn=False, keep_audio=False)
    monkeypatch.setattr(api.stt, "transcribe_ex",
                        lambda w: (order.append("hear") or ("raw", 0.9)))
    monkeypatch.setattr(api.stt, "audio_seconds", lambda w: 5.0)
    monkeypatch.setattr(d, "romanise", lambda t: order.append("romanise") or t)
    monkeypatch.setattr(api.vocab, "shared",
                        lambda: mock.Mock(fix=lambda t: order.append("vocab") or t))
    monkeypatch.setattr(api._shape, "shape",
                        lambda t, **kw: order.append("shape") or t)

    said = d.transcribe(str(wav))
    assert order == ["hear", "romanise", "vocab", "shape"], order
    assert said.text == "raw"


def test_recording_can_be_turned_off(monkeypatch, tmp_path):
    """A caller transcribing a hundred archived files must not write a hundred
    rows into somebody's personal history."""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    added = []
    monkeypatch.setattr(api.stt, "transcribe_ex", lambda w: ("hello", 0.9))
    monkeypatch.setattr(api.stt, "audio_seconds", lambda w: 5.0)
    monkeypatch.setattr(api.history, "add", lambda **kw: added.append(kw) or 1)

    said = Dictator(remember=False, keep_audio=False).transcribe(str(wav))
    assert said.row == 0 and added == []

    said = Dictator(remember=True, learn=False, keep_audio=False).transcribe(str(wav))
    assert said.row == 1 and len(added) == 1


def test_learning_can_be_turned_off(monkeypatch):
    d = Dictator(learn=False)
    d._last = (1, "something", "Terminal")
    assert d.check_corrections("Terminal") == []


def test_a_failed_transcription_returns_an_empty_transcript(monkeypatch, tmp_path):
    """Never raises at the caller. A key that throws a traceback into whatever
    had focus is worse than one that says nothing."""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")

    def boom(w):
        raise RuntimeError("whisper died")

    monkeypatch.setattr(api.stt, "transcribe_ex", boom)
    monkeypatch.setattr(api.stt, "audio_seconds", lambda w: 5.0)
    said = Dictator(remember=False, learn=False, keep_audio=False).transcribe(str(wav))
    assert said.text == "" and not said


def test_the_parts_are_usable_on_their_own(monkeypatch):
    d = Dictator()
    monkeypatch.setattr(api.vocab, "shared",
                        lambda: mock.Mock(fix=lambda t: t.replace("floor", "Flow")))
    assert "Flow" in d.polish("whisper floor")
    assert d.romanise("plain english") == "plain english"


def test_there_is_only_one_pipeline():
    """The key listener must CALL the library, not reproduce it.

    If dictate.py starts transcribing and correcting on its own again, the two
    drift and the drift is invisible: one caller gets your learned words and
    the other does not."""
    src = (ROOT / "dictator" / "dictate.py").read_text()
    assert "self.sdk.transcribe(" in src, "the listener no longer calls the library"
    tree = ast.parse(src)
    calls = {ast.unparse(n.func) for n in ast.walk(tree)
             if isinstance(n, ast.Call) and hasattr(ast, "unparse")}
    for reproduced in ("stt.transcribe_ex", "vocab.shared", "shape.shape",
                       "history.add", "learn.observe"):
        assert reproduced not in calls, \
            f"dictate.py calls {reproduced} again instead of using the library"


def test_the_shaping_flags_live_in_one_place():
    """They were defined in the listener and in the library at once, which is
    the exact duplication this layer exists to remove."""
    assert "_format_flags" not in (ROOT / "dictator" / "dictate.py").read_text()
    assert "shaping_flags" in (ROOT / "dictator" / "cli.py").read_text()


def test_a_quiet_room_is_not_transcribed_at_all(tmp_path, monkeypatch):
    """Below SILENT nothing is worth a model load.

    Measured over the 198 corpus recordings with a stored transcript: the
    quietest real speech is 0.0070, and the only two files under 0.0020 both
    came back as "Thank you", which is whisper hallucinating on an empty
    room. So this saves a wrong paste and a 1.6GB model load together."""
    import dictator
    from dictator import stt

    wav = tmp_path / "quiet.wav"
    wav.write_bytes(b"RIFF")                       # never read: loudness is faked
    monkeypatch.setattr(stt, "loudness", lambda p: 0.0005)
    monkeypatch.setattr(stt, "audio_seconds", lambda p: 1.3)

    def boom(p):
        raise AssertionError("transcribed a room")

    monkeypatch.setattr(stt, "transcribe_ex", boom)
    said = dictator.Dictator(remember=False, learn=False,
                             expand=False).transcribe(str(wav))
    assert said.text == ""
    assert said.heard == ""


def test_quiet_filler_is_dropped_and_loud_filler_is_kept(tmp_path, monkeypatch):
    """"Thank you." from an empty room is the model shrugging; said out loud
    it is a thing somebody meant to type. The phrase alone cannot tell them
    apart and neither can the level, because the quietest real speech in the
    corpus sits at exactly the level of the loudest filler. Both together
    caught 7 of 7 and cost none of 198."""
    import dictator
    from dictator import stt

    wav = tmp_path / "hold.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(stt, "audio_seconds", lambda p: 1.1)
    monkeypatch.setattr(stt, "transcribe_ex", lambda p: ("Thank you.", 0.9))

    d = dictator.Dictator(remember=False, learn=False, expand=False)

    monkeypatch.setattr(stt, "loudness", lambda p: 0.004)
    assert d.transcribe(str(wav)).text == "", "quiet filler reached the screen"

    monkeypatch.setattr(stt, "loudness", lambda p: 0.05)
    assert d.transcribe(str(wav)).text, "a spoken thank you was swallowed"


def test_an_unreadable_recording_never_silences_anything(tmp_path, monkeypatch):
    """`loudness` answers -1 when it cannot read the file. That is not a claim
    about the room, and treating it as one would silence every hold on a
    machine whose recorder writes a format this cannot parse."""
    import dictator
    from dictator import stt

    wav = tmp_path / "odd.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(stt, "loudness", lambda p: -1.0)
    monkeypatch.setattr(stt, "audio_seconds", lambda p: 2.0)
    monkeypatch.setattr(stt, "transcribe_ex", lambda p: ("Thank you.", 0.9))
    said = dictator.Dictator(remember=False, learn=False,
                             expand=False).transcribe(str(wav))
    assert said.text, "an unreadable file silenced a transcript"
