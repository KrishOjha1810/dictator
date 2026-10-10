"""The decoder repeating itself, which is our setting rather than the model.

Two real recordings in the corpus produced this. One came back as
"ndernderndernder" and the other as "It's a little bit." three times over.
Neither is speech, and docs/findings.md records that the cause is a shrunk
encoder: the same audio at full size transcribes into words.

The reason this is not a loudness check was measured rather than assumed. The
two recordings that looped sit at 0.032 and 0.018 RMS, LOUDER than a dozen
recordings of real speech, the quietest of which ("I don't know") is 0.0079. A
loudness gate would have kept both loops and thrown away real short answers.
"""
import pytest

from dictator_core import loops


@pytest.mark.parametrize("text", [
    "Oof, ndernderndernder",
    "iririririr plplplplar",
    "It's a little bit. It's a little bit. It's a little bit.",
    "and then, I think, I think, I think, I think",
    "It is, bobs, vaulted, or, a, vaulted, a, vaulted, a, vaulted",
])
def test_a_loop_is_recognised(text):
    assert loops.looped(text), text
    assert loops.why(text), "the log line has to say which shape it was"


@pytest.mark.parametrize("text", [
    # Real transcripts from the corpus. Saying True about any of these costs
    # the user a working dictation, so this half matters more than the other.
    "sari links ek bar aur verify karlo jitni bhi hai",
    "I understood the borrower struct, but the accuracy interest",
    "No, I was wrong before. I think the vault is fine. Let me check again.",
    "mujhe yeh chahiye, aur kya",
    "Like repay logic and all whatever I can go through",
    # Repetition people genuinely produce.
    "okay, okay, okay",
    "right, right, right",
    "very very good",
    "uh, uh, uh, I mean",
    "one, two, three, four, five",
    # Words that contain a repeated unit and are not loops.
    "murmur banana hahaha couscous",
    "bookkeeper possesses",
    "Yeah.",
    "",
])
def test_ordinary_speech_is_left_alone(text):
    assert not loops.looped(text), text


def test_twice_is_not_a_loop():
    """A stutter and a real repetition both say the same thing twice. Three
    times in a row is the decoder stuck."""
    assert not loops.looped("nder nder")
    assert not loops.looped("It's a little bit. It's a little bit.")


def test_it_flags_the_two_real_failures_and_nothing_else_in_the_corpus():
    """Guard on the false positive rate, against the recordings it will
    actually meet. Skipped where the corpus is not present."""
    import pathlib
    corpus = pathlib.Path.home() / ".dictator" / "corpus"
    texts = sorted(corpus.glob("*.txt")) if corpus.exists() else []
    if len(texts) < 50:
        pytest.skip("no corpus on this machine")
    flagged = [t.name for t in texts
               if loops.looped(t.read_text(errors="ignore"))]
    assert len(flagged) <= 3, flagged


def test_the_retry_replaces_a_loop_and_keeps_a_good_answer(monkeypatch,
                                                           tmp_path):
    """The behaviour that matters: a loop is thrown away for the second
    answer, and a second answer that also loops is not preferred."""
    from dictator_core import stt

    calls = []

    class Done:
        def __init__(self, text):
            self.stdout, self.stderr, self.returncode = text, "", 0

    answers = iter(["ndernderndernder", "check once again"])

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return Done(next(answers))

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"")
    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    monkeypatch.setattr(stt, "_transcribe_server", lambda w: None)
    # English holds try Parakeet first and would never reach the whisper
    # branch. All three loops in the real history came from
    # "cli:ggml-large-v3-turbo.bin", which is this branch.
    monkeypatch.setattr(stt, "parakeet_ready", lambda: False)
    monkeypatch.setattr(stt, "whisper_bin", lambda: "/bin/true")
    # Longer than WORTH_TRIMMING, or there is no trim to retry without: a
    # short hold is no longer trimmed at all, which is the better fix for the
    # same failure and is tested above.
    monkeypatch.setattr(stt, "audio_seconds", lambda w: 12.0)
    monkeypatch.setattr(stt, "pinned_language", lambda w, l: "en")
    monkeypatch.setattr(stt, "stt_lang_mode", lambda: (wav, "en"))
    monkeypatch.setattr(stt, "_romanise", lambda t: t)

    text, _ = stt._transcribe_ex(str(wav))
    assert text == "check once again"
    assert len(calls) == 2, "it has to actually run a second time"
    assert "-ac" in calls[0] and "-ac" not in calls[1], \
        "the second pass is the one without the shrunk encoder"


def test_a_byte_the_model_emitted_does_not_throw_the_hold_away(monkeypatch,
                                                                tmp_path):
    """Live failure, taken from the log: `'utf-8' codec can't decode bytes in
    position 37-38: invalid continuation byte`, which raised inside
    `subprocess.run(text=True)`, was caught by the broad handler and logged as
    "nothing was said". The person had spoken. It was thrown away because one
    byte was ugly."""
    from dictator_core import stt

    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        # What a strict decoder would have raised on.
        broken = b"the vault is fine \xe0\xa4 and that is all".decode(
            "utf-8", errors=kw.get("errors", "strict"))

        class Done:
            stdout, stderr, returncode = broken, "", 0
        return Done()

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"")
    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    monkeypatch.setattr(stt, "_transcribe_server", lambda w: None)
    monkeypatch.setattr(stt, "parakeet_ready", lambda: False)
    monkeypatch.setattr(stt, "whisper_bin", lambda: "/bin/true")
    monkeypatch.setattr(stt, "audio_seconds", lambda w: 6.0)
    monkeypatch.setattr(stt, "pinned_language", lambda w, l: "en")
    monkeypatch.setattr(stt, "stt_lang_mode", lambda: (wav, "en"))
    monkeypatch.setattr(stt, "_romanise", lambda t: t)

    text, _ = stt._transcribe_ex(str(wav))
    assert seen.get("errors") == "replace", \
        "the engine's stdout is still decoded strictly"
    assert "the vault is fine" in text
    assert "that is all" in text, "everything after the bad byte was lost"


# ---- the encoder sizing, which was costing the short holds twice -----------

def test_a_short_hold_is_not_trimmed_at_all():
    """Measured over 146 real holds: under six seconds, trimming the encoder
    is worse AND slower than leaving it alone (7.59% against 3.95% gibberish
    for the shortest, and 0.83s against 0.58s). A decoder given too little
    context loops, and looping takes longer than the encoding it saved."""
    from dictator_core import stt
    for secs in (0.5, 1.0, 2.7, 4.0, 5.9):
        assert stt.audio_ctx_for(secs) == 0, secs


def test_a_long_hold_is_still_trimmed():
    """Above six seconds it buys real time for nothing, which is what it was
    written for. Removing it there would make every long dictation slower."""
    from dictator_core import stt
    assert 0 < stt.audio_ctx_for(8.0) < 1500
    assert 0 < stt.audio_ctx_for(12.0) < 1500
    assert stt.audio_ctx_for(40.0) == 1500


def test_the_boundary_is_where_the_measurement_put_it():
    from dictator_core import stt
    assert stt.audio_ctx_for(stt.WORTH_TRIMMING - 0.1) == 0
    assert stt.audio_ctx_for(stt.WORTH_TRIMMING) > 0


def test_unknown_duration_still_means_do_not_trim():
    """A wav that could not be read must not be guessed at."""
    from dictator_core import stt
    assert stt.audio_ctx_for(0) == 0
    assert stt.audio_ctx_for(-1) == 0


def test_a_sentence_looped_three_times_is_kept_once():
    from dictator_core import loops
    got = loops.collapse("yar ye test karke dekho. yar ye test karke dekho. "
                         "yar ye test karke dekho. yar ye tes")
    assert got == "yar ye test karke dekho."


def test_a_sentence_said_twice_is_left_alone():
    from dictator_core import loops
    t = "Do it now. Do it now. Then stop."
    assert loops.collapse(t) == t
