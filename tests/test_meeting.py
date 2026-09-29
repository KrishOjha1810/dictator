"""Recording a meeting, and mostly the things it must never do.

A meeting recording is other people's voices, which makes the failures here
different in kind from every other part of this product. Getting a word wrong
is a nuisance; recording without anybody knowing, or inventing an action item
somebody then acts on, or "deleting" a recording that is still on the disk, are
not.

So most of what is tested here is refusal:

  nothing starts itself   recording begins only when the command is typed
  nothing is invented     a note that does not trace back to the transcript is
                          thrown away, not shown with a caveat
  nothing is sent         there is no call off this machine, at all, ever
  nothing is kept         forget overwrites before it unlinks

The rest is the seams, because chunking an hour of audio is where words get
lost or said twice, and neither is visible from reading the code.
"""
import json
import math
import struct
import time
import wave
from pathlib import Path

import pytest

from dictator import meeting, recap

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_network_and_no_model(monkeypatch):
    """No test may reach the network or start a 2.5GB server.

    urlopen RECORDS rather than raising quietly, because the module fails soft
    by design and a swallowed failure would let a test pass while the call had
    actually gone out."""
    calls = []

    def spy(req, *a, **kw):
        calls.append(req if isinstance(req, str) else getattr(req, "full_url", ""))
        raise OSError("no network in tests")

    monkeypatch.setattr(recap.urllib.request, "urlopen", spy)
    monkeypatch.setattr(recap, "server_bin", lambda: "")
    monkeypatch.setattr(recap, "model_path", lambda: Path("/nonexistent.gguf"))
    monkeypatch.setattr(recap, "_start", lambda: pytest.fail(
        "a test tried to start the local model"))
    meeting.calls = calls


# ---- audio the tests can make for themselves -------------------------------

def tone(path, spans, rate=16000):
    """A 16kHz mono WAV. `spans` is [(seconds, amplitude), ...]."""
    frames = bytearray()
    phase = 0.0
    for secs, amp in spans:
        for _ in range(int(secs * rate)):
            phase += 2 * math.pi * 440 / rate
            frames += struct.pack("<h", int(amp * 32000 * math.sin(phase)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


# ---- the seams -------------------------------------------------------------

def test_the_repeated_words_at_a_seam_are_said_once():
    """The overlap means the end of one chunk is the start of the next. Without
    this every seam reads as a stutter."""
    prev = "so the plan is we ship the recorder first and then the notes"
    nxt = "and then the notes come after the transcript is stable"
    assert meeting.dedup(prev, nxt) == "come after the transcript is stable"


def test_a_seam_that_did_not_actually_repeat_is_left_alone():
    """Two different sentences that happen to follow each other must survive
    intact. Trimming them would silently lose real speech, which is the same
    failure the overlap exists to prevent."""
    prev = "we agreed to postpone the migration"
    nxt = "Priya is writing the rollback plan"
    assert meeting.dedup(prev, nxt) == nxt


def test_the_repeat_is_found_even_when_the_chunk_starts_mid_word():
    """A chunk begins three seconds before the cut, which lands the recogniser
    in the middle of a word, and what it makes of half a word is not what the
    other pass made of the whole one. Measured on a real recording:
    "...rediscovering it" came back as "I'm covering it", so the repeat began
    at the fourth word and a match anchored at the first word could not see it
    at all."""
    prev = "so nobody spends another afternoon rediscovering it. Please do. " \
           "Now the long recordings."
    nxt = "I'm covering it. Please do. Now the long recordings. An hour of " \
          "audio cannot go through the model in one piece."
    assert meeting.dedup(prev, nxt).startswith("An hour of audio")


def test_a_short_coincidence_partway_in_is_not_treated_as_a_repeat():
    """Further into the chunk, two or three words in common is a coincidence,
    and acting on a coincidence deletes real speech."""
    prev = "and that is why we are doing it this way"
    nxt = "Right, so the way to think about it is as two tracks"
    assert meeting.dedup(prev, nxt) == nxt


def test_one_repeated_word_is_not_treated_as_an_overlap():
    """A single shared word is a coincidence, not a seam. Acting on it would
    delete the first word of a sentence about once a paragraph."""
    prev = "that is the whole thing"
    nxt = "thing about it is nobody checked"
    assert meeting.dedup(prev, nxt) == nxt


def test_the_cut_lands_in_the_quiet_part_not_on_the_clock(tmp_path):
    """Cutting on the clock puts the seam inside a word about as often as not.
    The point of looking for the quietest moment nearby is that the cut lands
    in a breath, which is what makes a few seconds of overlap enough."""
    step = meeting.STEP
    # Loud everywhere except a gap at 122 seconds.
    env = [0.5] * int(200 / step)
    for i in range(int(122 / step), int(122.4 / step)):
        env[i] = 0.001
    got = meeting.cuts(env, chunk=120.0, seek=10.0, step=step)
    assert got, "no cut at all"
    assert abs(got[0] - 122.0) < 0.5, got


def test_every_second_of_a_track_is_inside_some_chunk(tmp_path):
    """A chunking that loses a stretch of audio loses it silently, and the only
    symptom is a transcript that is quietly missing a minute of somebody
    talking."""
    wav = tone(tmp_path / "t.wav", [(6, 0.4)])
    got = meeting.pieces(wav, chunk=2.0, overlap=0.5, seek=0.3)
    assert got
    assert got[0]["start"] == 0.0
    assert abs(got[-1]["end"] - 6.0) < 0.2
    for a, b in zip(got, got[1:]):
        assert b["start"] < a["end"], "a gap between two chunks"


def test_silence_is_never_handed_to_the_model_at_all(tmp_path):
    """Whisper does not return nothing for silence, it fills it, and the
    filling is fluent enough to read as a transcript. On the microphone track
    of a meeting most of the audio is silence, because most of a meeting is
    somebody else talking, so leaving it out is the accuracy guard and the
    biggest speed win at the same time."""
    wav = tone(tmp_path / "t.wav", [(3, 0.4), (20, 0.0), (3, 0.4)])
    got = meeting.pieces(wav, chunk=60.0, seek=0.3)
    assert len(got) == 2, got
    assert got[0]["end"] < 5.0, "the silence after the first burst was kept"
    assert got[1]["start"] > 20.0, "the silence before the second was kept"


def test_a_track_with_nothing_on_it_produces_no_work(tmp_path):
    """A meeting where the owner never spoke leaves a silent microphone track.
    Handing it to whisper anyway is minutes of waiting for invented sentences."""
    wav = tone(tmp_path / "t.wav", [(20, 0.0)])
    assert meeting.pieces(wav) == []


def test_a_slice_is_a_playable_wav_of_the_right_length(tmp_path):
    wav = tone(tmp_path / "t.wav", [(4, 0.4)])
    out = tmp_path / "part.wav"
    assert meeting._slice(wav, 1.0, 3.0, out)
    with wave.open(str(out)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 16000
        assert abs(w.getnframes() / 16000.0 - 2.0) < 0.05


# ---- who said it -----------------------------------------------------------

def test_the_two_tracks_become_one_conversation_in_order():
    rec = {"transcript": [
        {"at": 0.0, "who": "them", "text": "can you take the migration"},
        {"at": 4.0, "who": "me", "text": "yes I will do it this week"},
        {"at": 9.0, "who": "them", "text": "good"},
    ]}
    text = meeting.as_text(rec)
    assert text.index("them") < text.index("you") < text.rindex("them")
    assert "[00:04] you" in text


def test_the_label_comes_from_the_track_and_nothing_else():
    """"me" and "them" are which file the audio came out of, which is the only
    speaker labelling that is free and honest. Nothing here guesses at which of
    "them" was talking, and nothing should start."""
    rec = {"transcript": [{"at": 0.0, "who": "them", "text": "hello"}]}
    assert "them:" in meeting.as_text(rec)
    assert "speaker 1" not in meeting.as_text(rec).lower()


# ---- the notes -------------------------------------------------------------

def _recorded(tmp_path, lines):
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "title": "", "started": time.time(),
                       "ended": time.time(), "seconds": 60.0,
                       "transcript": lines, "notes": {}})
    return mid


def test_notes_never_call_anything_off_this_machine(tmp_path):
    """Every URL this feature touches, over a whole run, must point at this
    Mac. Checked rather than asserted about, because the one place a mistake
    could send somebody else's voice off the machine is here."""
    mid = _recorded(tmp_path, [{"at": 0.0, "who": "them", "text": "hello"}])
    meeting.notes(mid)
    assert meeting.calls, "nothing was recorded, so this proved nothing"
    for url in meeting.calls:
        assert recap.local_only(url), url


def test_an_invented_action_item_is_thrown_away(monkeypatch, tmp_path):
    """The dangerous failure is not gibberish, it is a fluent sentence naming
    somebody who was never in the room. In a list of things to do that reads as
    a fact, so it is checked back against the transcript and dropped."""
    lines = [{"at": 0.0, "who": "them", "text": "the recorder is ready"},
             {"at": 5.0, "who": "me", "text": "I will test it tomorrow"}]
    mid = _recorded(tmp_path, lines)
    monkeypatch.setattr(recap, "available", lambda: True)
    monkeypatch.setattr(recap, "_start", lambda: False)
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_ask", lambda block, *a, **k:
                        "Priya agreed to ship the billing migration on Friday.")
    rec = meeting.notes(mid)
    assert rec["notes"]["source"] == "rejected"
    assert not rec["notes"].get("decided")


def test_a_grounded_note_survives(monkeypatch, tmp_path):
    lines = [{"at": 0.0, "who": "them", "text": "the recorder is ready to test"},
             {"at": 5.0, "who": "me", "text": "I will test the recorder tomorrow"}]
    mid = _recorded(tmp_path, lines)
    monkeypatch.setattr(recap, "available", lambda: True)
    monkeypatch.setattr(recap, "_start", lambda: False)
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_ask", lambda block, *a, **k:
                        "Discussed the recorder and agreed to test it tomorrow.")
    rec = meeting.notes(mid)
    assert rec["notes"]["source"] == "model"
    assert "recorder" in rec["notes"]["discussed"]


def test_no_transcript_says_so_rather_than_summarising_nothing(tmp_path):
    mid = _recorded(tmp_path, [])
    rec = meeting.notes(mid)
    assert rec["notes"]["source"] == "no-transcript"


def test_a_long_transcript_is_shown_to_the_model_in_whole_lines():
    """A call that sees half a sentence produces a summary of half a sentence,
    and the grounding check cannot tell that apart from an invention."""
    block = "".join(f"them: line number {i} of the meeting\n" for i in range(600))
    parts = meeting._stretches(block, size=2000)
    assert len(parts) > 1
    assert "".join(parts) == block
    for p in parts:
        assert p.endswith("\n")


# ---- it never starts itself ------------------------------------------------

def test_importing_the_module_records_nothing(tmp_path):
    """There is no detector, no schedule and no login item in this feature, and
    there is not going to be one. Recording other people has to be something
    the user did, not something that happened."""
    assert meeting.running() == {}
    assert not meeting.MEETINGS.exists() or not list(meeting.MEETINGS.glob("2*"))


def test_a_dead_recorder_is_not_reported_as_recording(tmp_path):
    """A flag file left behind by a crash is how a product ends up claiming to
    be listening when it is not, which is the one thing this must never do. So
    the answer comes from the process, not from a file."""
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time()})
    (meeting._dir(mid) / "status.json").write_text(
        json.dumps({"state": "recording", "pid": 999999}))
    meeting.CURRENT.parent.mkdir(parents=True, exist_ok=True)
    meeting.CURRENT.write_text(mid)
    assert meeting.running() == {}
    assert not meeting.CURRENT.exists()


def test_stopping_when_nothing_is_recording_is_not_an_error(tmp_path):
    assert meeting.stop()["problem"] == "none"


# ---- forgetting ------------------------------------------------------------

def test_forget_overwrites_the_audio_before_it_unlinks_it(tmp_path):
    """"Delete" has to mean more than dropping a directory entry when the file
    is other people's voices."""
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time()})
    wav = meeting._dir(mid) / "them.wav"
    tone(wav, [(1, 0.5)])
    original = wav.read_bytes()
    seen = {}

    real = meeting.shutil.rmtree

    def watch(path, **kw):
        seen["before_removal"] = wav.read_bytes()
        return real(path, **kw)

    meeting.shutil.rmtree = watch
    try:
        assert meeting.forget(mid) is True
    finally:
        meeting.shutil.rmtree = real
    assert not meeting._dir(mid).exists()
    assert seen["before_removal"] != original


def test_forgetting_something_that_is_not_there_says_so(tmp_path):
    assert meeting.forget("20200101-000000") is False


def test_a_recording_is_listed_with_its_size(tmp_path):
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time(), "seconds": 120.0})
    tone(meeting._dir(mid) / "them.wav", [(1, 0.4)])
    out = meeting.listing()
    assert mid in out
    assert "MB" in out
    assert "audio only" in out
