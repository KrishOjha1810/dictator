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


@pytest.mark.parametrize("said", [
    # Real holds, from the history. Parakeet reached for a language it could
    # spell the sounds in when the speaker switched mid sentence.
    "Mujal okta heangtoe plazma, iż jídti bazej kutka ku banana ċajk.",
    "Менен Телеранде.",
    "منن تھیلرر آنڈے",
])
def test_an_answer_in_another_script_is_caught(said):
    """Neither of the other two checks sees these. They are not long fused
    blobs and they are not short on words for the audio, and the second is too
    short to judge by rate at all. What gives them away is the characters."""
    assert stt._not_english(said)


@pytest.mark.parametrize("said", [
    "This is the English line. Bobi Bhikkhullah or Mare is English accuracy.",
    "User token account would be the one like his public key, something like that.",
    "Is everything done? Uh like have you made it a repo in itself",
    "He said “hello” and left…",
])
def test_ordinary_english_is_left_alone(said):
    """Curly quotes and an ellipsis are the only things above ASCII a
    transcriber of English has any business producing."""
    assert not stt._not_english(said)


def test_all_three_checks_guard_the_fast_path():
    """Each one catches a failure the others miss, so dropping any of them
    quietly reopens a hole: fused blobs, speech that went missing, and an
    answer in a script nobody spoke."""
    import inspect
    src = inspect.getsource(stt._transcribe_ex)
    for check in ("_parakeet_lost(got)", "_too_little(got, wav)", "_not_english(got)"):
        assert check in src, f"{check} no longer guards the Parakeet path"



@pytest.mark.parametrize("marker", [
    "[MUSIC PLAYING]", "[INAUDIBLE]", "[BLANK_AUDIO]",
    "[No speech detected] [no speech detected]", "(silence)",
])
def test_the_model_saying_nothing_is_not_a_transcript(marker):
    """These reached the screen. Pasting "[MUSIC PLAYING]" into an editor is
    worse than pasting nothing: it reads as a wrong transcription, so the user
    goes looking for what they said wrong."""
    assert stt.is_silence(marker)


@pytest.mark.parametrize("said", [
    "Thank you.", "hello world", "[laughs] but I said yes",
])
def test_real_speech_is_not_mistaken_for_silence(said):
    assert not stt.is_silence(said)


def test_an_empty_answer_from_the_fast_engine_also_falls_back():
    """It was treated as "no opinion" and fell through to the English model,
    which produced [NON-ENGLISH SPEECH] and [INAUDIBLE] on real Hinglish
    holds. An English-only model returning nothing on audio that was not
    English is the same signal as it returning nonsense."""
    import inspect
    src = inspect.getsource(stt._transcribe_ex)
    body = src[src.index("parakeet_ready()"):]
    force = body.index("_force_multilingual = True")
    guard = body.index("if got:")
    assert force < guard, \
        "the fallback is inside `if got:` again, so an empty answer is ignored"
