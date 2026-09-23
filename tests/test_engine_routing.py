"""Catching the fast engine when it drops speech instead of transcribing it.

Parakeet has no Hindi. On Hinglish it sometimes fuses syllables into blobs,
which is easy to spot, and sometimes does something worse: it invents fluent
English with no relation to what was said. A real hold of

    "jiske liye mujhe tumhari ek Hinglish line chahiye..."

came back as

    "This is the English line. Bobi Bhikkhullah or Mare is English accuracy."

Every word of that is ordinary English, so nothing about its shape is
suspicious. What gives it away is that twelve seconds of speech produced
twelve words.
"""
import wave
import struct

import pytest

from dictator import stt


def _wav(path, secs, rate=16000):
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(secs * rate))
    return str(path)


def test_the_real_failure_is_caught(tmp_path):
    wav = _wav(tmp_path / "a.wav", 12.4)
    bad = "This is the English line. Bobi Bhikkhullah or Mare is English accuracy."
    assert stt._too_little(bad, wav)


def test_a_good_english_pass_is_left_alone(tmp_path):
    wav = _wav(tmp_path / "b.wav", 12.8)
    good = ("Is everything done? Uh like have you made it a repo in itself and "
            "is it separate from voicebridge now? And all of the things that I "
            "asked for, are they all done?")
    assert not stt._too_little(good, wav)


def test_a_good_hinglish_pass_is_left_alone(tmp_path):
    wav = _wav(tmp_path / "c.wav", 12.4)
    good = ("jiske liye mujhe tumhari ek English line chaahie vo abhee bhi "
            "khula hai aur mere hisab se English accuracy ke liye sabse bada "
            "lead mein hai")
    assert not stt._too_little(good, wav)


def test_a_short_hold_is_never_judged(tmp_path):
    """One word in two seconds is a normal thing to say, not a failure, and
    there is not enough audio to tell a pause from dropped speech."""
    wav = _wav(tmp_path / "d.wav", 2.0)
    assert not stt._too_little("yes", wav)


def test_the_fallback_goes_multilingual_not_english(monkeypatch):
    """Falling back to the English model would swap one wrong answer for
    "[NON-ENGLISH SPEECH]", since the reason Parakeet dropped the speech is
    that the audio was not English."""
    monkeypatch.setattr(stt, "_force_multilingual", True)
    monkeypatch.setattr(stt, "language", lambda: "english")
    model, lang = stt.stt_lang_mode()
    assert lang == "auto", lang
    assert ".en." not in model.name, model.name


def test_the_fallback_also_romanises(monkeypatch):
    """The multilingual model writes Devanagari. Correct words in a script the
    user cannot paste into a terminal is a worse failure than the one this
    just fixed."""
    monkeypatch.setattr(stt, "language", lambda: "english")
    monkeypatch.setattr(stt, "_force_multilingual", True)
    out = stt._romanise("मुझे तुम्हारी")
    assert not any("ऀ" <= ch <= "ॿ" for ch in out), out


def test_the_engine_label_names_the_model_that_ran(monkeypatch):
    """LAST_ENGINE read the module level MODEL, which is resolved once at
    import from the English list, so it reported small.en for work turbo had
    done and every recorded row was wrong about it."""
    import inspect
    src = inspect.getsource(stt._transcribe_ex)
    assert "MODEL.name" not in src, "engine label is back on the import time default"
