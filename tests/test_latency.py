"""Sizing the work to the utterance instead of to whisper's fixed window.

Two things were being paid for on every hold and neither bought anything.
whisper's own `-l auto` runs the ENCODER TWICE, once to decide the language
and once to transcribe: measured on a 12.4 second hold with turbo, 2447ms over
2 runs against 1230ms over 1 run for a pinned language, with an identical
transcript. And whisper.cpp encodes a full 30 second window however long you
actually spoke, while the encoder is around 85 percent of the bill.
"""
import pytest

from dictator import stt


@pytest.mark.parametrize("secs,window", [
    (2, 200), (5, 330), (12.4, 700), (25, 1330), (40, 1500),
])
def test_the_window_is_sized_to_the_utterance(secs, window):
    assert stt.audio_ctx_for(secs) == window


@pytest.mark.parametrize("secs", [0.5, 1, 3, 7, 12.4, 20, 29])
def test_the_window_never_undershoots_the_audio(secs):
    """Undershooting is not merely lossy. At 600 frames on a 12.4 second clip
    (12 seconds, just under the audio) a word was lost, and smaller still
    sends the decoder into a repetition loop that takes LONGER than full
    context. Every window must cover its own audio with room to spare."""
    ctx = stt.audio_ctx_for(secs)
    assert ctx * 0.02 >= secs, f"{secs}s got a {ctx * 0.02}s window"


def test_an_unknown_duration_asks_for_the_default():
    assert stt.audio_ctx_for(0) == 0


def test_a_confident_detection_replaces_auto(monkeypatch):
    monkeypatch.setattr(stt, "detect_language", lambda w: ("hi", 0.86))
    assert stt.pinned_language("x.wav", "auto") == "hi"


def test_an_unsure_detection_leaves_it_to_whisper(monkeypatch):
    """A wrong pin is worse than no pin. Forcing Hindi onto English audio
    triggered a temperature fallback storm that took 8.9 seconds against 3.4
    for the same audio left on auto."""
    monkeypatch.setattr(stt, "detect_language", lambda w: ("hi", 0.31))
    assert stt.pinned_language("x.wav", "auto") == "auto"


def test_a_pinned_language_is_never_second_guessed(monkeypatch):
    called = []
    monkeypatch.setattr(stt, "detect_language",
                        lambda w: called.append(w) or ("hi", 0.9))
    assert stt.pinned_language("x.wav", "en") == "en"
    assert not called, "paid for detection on a language that was already known"


def test_the_server_is_declined_when_the_window_can_be_sized(monkeypatch, tmp_path):
    """A server cannot be told an audio context per request, so it always
    encodes 30 seconds. Measured on a 12.4 second hold: 2.90s through the CLI
    with the window sized, 4.25s through the server."""
    import inspect
    src = inspect.getsource(stt._transcribe_server)
    assert "audio_seconds(wav)" in src, "server no longer checks the duration"
    assert "< 25" in src
