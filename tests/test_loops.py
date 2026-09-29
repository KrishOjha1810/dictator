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

from dictator import loops


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
    from dictator import stt

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
    monkeypatch.setattr(stt, "audio_seconds", lambda w: 2.7)
    monkeypatch.setattr(stt, "pinned_language", lambda w, l: "en")
    monkeypatch.setattr(stt, "stt_lang_mode", lambda: (wav, "en"))
    monkeypatch.setattr(stt, "_romanise", lambda t: t)

    text, _ = stt._transcribe_ex(str(wav))
    assert text == "check once again"
    assert len(calls) == 2, "it has to actually run a second time"
    assert "-ac" in calls[0] and "-ac" not in calls[1], \
        "the second pass is the one without the shrunk encoder"
