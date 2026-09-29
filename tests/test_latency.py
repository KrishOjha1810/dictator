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


# ---- the model read, and when it happens ------------------------------------
# whisper-cli reads the whole model before it can encode anything, and it is a
# new process every hold. Off the disk that read is 1.68s on the 1.62GB
# multilingual model; out of the page cache it is 0.30s. The read is not
# avoidable, so it is moved to where it is free: while the key is still held.


def test_the_model_is_read_while_the_key_is_still_down(monkeypatch, tmp_path):
    """The bug family this repo keeps hitting is a function that knows how to
    do the work and nothing calling it from where the work happens. A warm-up
    nobody calls on key down is exactly that bug, and it costs a second on
    every hold that an install has not already paid for."""
    from dictator import dictate, mac, warmup

    called = []
    monkeypatch.setattr(warmup, "models", lambda *a, **k: called.append(1))
    monkeypatch.setattr(mac, "frontmost_app", lambda: "Terminal")
    monkeypatch.setattr(dictate.stt, "record_hold", lambda *a, **k: None)
    d = dictate.Dictation()
    d.down()
    assert called, "the key went down and nothing started reading the model"


def test_the_recorder_starts_before_the_model_is_read(monkeypatch, tmp_path):
    """The microphone is the one thing that must not wait. Reading 1.6GB
    before opening it would eat the first word, which is the failure the
    recorder was rewritten to avoid in the first place."""
    from dictator import dictate, mac, warmup

    order = []
    monkeypatch.setattr(mac, "frontmost_app", lambda: "Terminal")
    monkeypatch.setattr(dictate.stt, "record_hold",
                        lambda *a, **k: order.append("mic"))
    monkeypatch.setattr(warmup, "models",
                        lambda *a, **k: order.append("model"))
    dictate.Dictation().down()
    assert order == ["mic", "model"], order


def test_the_warm_up_reads_the_model_the_next_hold_will_open(monkeypatch):
    """Warming the wrong file is worse than warming nothing: it reads a
    gigabyte, reports success, and leaves the hold paying the disk anyway."""
    from dictator import stt, warmup

    monkeypatch.setattr(stt, "language", lambda: "hinglish")
    monkeypatch.setattr(stt, "parakeet_ready", lambda: True)
    want = stt.stt_lang_mode()[0]
    if want.exists():
        assert want in warmup.models_for_next_hold()

    monkeypatch.setattr(stt, "language", lambda: "english")
    if stt._PARAKEET.exists():
        assert warmup.models_for_next_hold() == [stt._PARAKEET]


def test_a_missing_model_is_not_an_error(tmp_path):
    """A warm-up that raises would take the hold down with it, and the hold
    works perfectly well without one."""
    from dictator import warmup
    assert warmup.read_through(tmp_path / "not-here.bin") == 0.0


def test_the_warm_up_does_not_stack(monkeypatch, tmp_path):
    """Two holds in a row must not send two threads through the same 1.6GB."""
    from dictator import warmup

    p = tmp_path / "model.bin"
    p.write_bytes(b"x" * 1024)
    reads = []
    monkeypatch.setattr(warmup, "models_for_next_hold", lambda: [p])
    monkeypatch.setattr(warmup, "read_through",
                        lambda path: reads.append(path) or 0.0)
    warmup._lock.acquire()
    try:
        warmup.models(background=False)
        assert not reads, "started a second read while one was running"
    finally:
        warmup._lock.release()
    warmup.models(background=False)
    assert reads == [p]


def test_the_helpers_are_run_once_before_any_hold(monkeypatch):
    """Compiling a helper is not running it. The installer builds all five, so
    no hold pays swiftc any more, but the FIRST EXECUTION of a fresh binary
    still cost 695ms for the recorder and 547ms for the paste helper against
    5ms for every run after. The recorder's share of that is not a wait, it is
    the start of the sentence never reaching the file."""
    from dictator import core, warmup

    ran = []
    monkeypatch.setattr(warmup.subprocess, "run",
                        lambda cmd, **k: ran.append(cmd[0]))
    for name in warmup._HELPERS:
        p = core.STATE_DIR / "bin" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    warmup.helpers()
    assert [p.rsplit("/", 1)[-1] for p in ran] == list(warmup._HELPERS)


def test_the_helpers_are_run_with_no_arguments(monkeypatch):
    """With no arguments both print their usage and exit, which is the whole
    reason this is safe to do at startup: the recorder never reaches the
    microphone and the paste helper never touches the clipboard."""
    from dictator import core, warmup

    seen = []
    monkeypatch.setattr(warmup.subprocess, "run",
                        lambda cmd, **k: seen.append(cmd))
    p = core.STATE_DIR / "bin" / warmup._HELPERS[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    warmup.helpers()
    assert seen and all(len(cmd) == 1 for cmd in seen), seen


def test_the_listener_warms_everything_before_it_says_it_is_listening(monkeypatch):
    """Same bug family as every other entry in docs/findings.md: something
    that knows how to do the work, and nothing calling it."""
    import inspect
    from dictator import dictate
    src = inspect.getsource(dictate.run)
    assert "warmup.at_startup()" in src
