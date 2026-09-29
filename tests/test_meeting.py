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
import sys
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


def test_a_dropped_section_says_so_rather_than_reading_as_empty(monkeypatch,
                                                                tmp_path):
    """A blank "Decided" otherwise reads as "nothing was decided", when what
    happened is that something was said and could not be believed. Those are
    opposite facts and must not print the same."""
    lines = [{"at": 0.0, "who": "them", "text": "the recorder is ready"},
             {"at": 5.0, "who": "me", "text": "I will test it tomorrow"}]
    mid = _recorded(tmp_path, lines)
    monkeypatch.setattr(recap, "available", lambda: True)
    monkeypatch.setattr(recap, "_start", lambda: False)
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_ask", lambda block, *a, **k:
                        "Priya agreed to ship the billing migration.")
    rec = meeting.notes(mid)
    assert "decided" in rec["notes"]["dropped"]
    # And a section the model honestly reported as empty is NOT called dropped.
    monkeypatch.setattr(recap, "_ask", lambda block, *a, **k: "nothing was decided")
    rec = meeting.notes(mid)
    assert "decided" not in rec["notes"]["dropped"]


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

def test_forget_overwrites_the_audio_before_it_unlinks_it(tmp_path,
                                                          monkeypatch):
    """"Delete" has to mean more than dropping a directory entry when the file
    is other people's voices.

    The file is deliberately larger than 2MiB. An earlier version of `forget`
    overwrote the first and last megabyte only, and an earlier version of this
    test used a one second WAV of about 32KB, which sits entirely inside the
    first window: it passed on a function that left 82% of an eleven megabyte
    recording intact. It also asserted only that something had changed, which
    a single altered byte satisfies."""
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time()})
    wav = meeting._dir(mid) / "them.wav"
    payload = b"SECRET-VOICE-DATA"
    wav.write_bytes(payload * 200_000)          # about 3.4MB
    assert wav.stat().st_size > 2 << 20, "smaller than this cannot see the bug"
    seen = {}

    real = meeting.shutil.rmtree

    def watch(path, **kw):
        seen["before_removal"] = wav.read_bytes()
        return real(path, **kw)

    monkeypatch.setattr(meeting.shutil, "rmtree", watch)
    assert meeting.forget(mid) is True
    assert not meeting._dir(mid).exists()
    # Not "something changed". None of it is left.
    assert payload not in seen["before_removal"]


def test_forget_says_so_when_it_could_not_keep_the_promise(tmp_path,
                                                           monkeypatch):
    """A caller is about to repeat the sentence "nothing on the filesystem
    reads it back" to the user. It must not say that after a failed
    overwrite."""
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time()})
    wav = meeting._dir(mid) / "them.wav"
    wav.write_bytes(b"x" * 4096)

    def refuse(*a, **kw):
        raise PermissionError("read only")

    monkeypatch.setattr(meeting, "open", refuse, raising=False)
    assert meeting.forget(mid) is False


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


# ---- starting, which had no test at all and is where the bugs were ---------

class _Launched:
    """What `open` returns when it accepted the launch. The code reads
    returncode now, because `open` refusing is instant and says why, and
    throwing that away turned every refusal into a thirty second wait."""
    returncode = 0
    stdout = ""
    stderr = ""


def _fake_recorder(monkeypatch, phases, seconds=6.0):
    """A recorder that is really running, publishing the phases you give it.

    A live pid matters: the whole class of bug here is Python deciding what a
    running recorder is doing, so a stubbed `_alive` would test nothing."""
    import subprocess
    proc = subprocess.Popen(["sleep", str(seconds)])
    written = {}

    def launch(*a, **kw):
        d = meeting._dir(written["mid"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "status.json").write_text(json.dumps(
            {"state": phases[0], "pid": proc.pid, "started": time.time(),
             "elapsed": 0.1, "them_seconds": 0, "me_seconds": 0}))

    monkeypatch.setattr(meeting, "build_app", lambda: "/tmp/nowhere.app")
    monkeypatch.setattr(meeting.subprocess, "run",
                        lambda *a, **k: launch() or _Launched())
    return proc, written


def test_starting_is_not_reported_as_recording(monkeypatch):
    """The heartbeat used to publish the word "recording" from half a second
    after launch, before the capture had been asked for and before the
    microphone dialog had been shown. Python saw that, told the user the
    meeting was being recorded, and if they then refused the microphone the
    recorder exited with no audio and `stop` answered "No meeting is being
    recorded"."""
    proc, written = _fake_recorder(monkeypatch, ["starting"])
    written["mid"] = time.strftime("%Y%m%d-%H%M%S")
    try:
        got = meeting.start(wait=1.0)
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert "id" not in got, got
    assert got["problem"] == "timeout", got


def test_a_refusal_is_read_from_the_state_and_not_from_the_prose(monkeypatch):
    """`_reason` matched the recorder's own line announcing that it was ASKING
    for Screen Recording, which is what an ordinary first run prints. So the
    directory of a live recorder was deleted while it was starting up."""
    proc, written = _fake_recorder(monkeypatch, ["starting"])
    mid = written["mid"] = time.strftime("%Y%m%d-%H%M%S")
    d = meeting._dir(mid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "recorder.err").write_text(
        "asking for Screen Recording, which is the permission that carries "
        "system audio\n")
    try:
        got = meeting.start(wait=1.0)
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert got.get("problem") != "screen", \
        "an ordinary first run was read as a refusal"


def test_a_real_refusal_is_still_reported(monkeypatch):
    proc, written = _fake_recorder(monkeypatch, ["no-screen"])
    written["mid"] = time.strftime("%Y%m%d-%H%M%S")
    try:
        got = meeting.start(wait=1.0)
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert got["problem"] == "screen", got


def test_a_recorder_that_died_does_not_burn_the_whole_wait(monkeypatch):
    import subprocess
    proc = subprocess.Popen(["true"])
    proc.wait()
    mid = time.strftime("%Y%m%d-%H%M%S")

    def launch(*a, **kw):
        d = meeting._dir(mid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "status.json").write_text(json.dumps(
            {"state": "starting", "pid": proc.pid, "started": time.time()}))

    monkeypatch.setattr(meeting, "build_app", lambda: "/tmp/nowhere.app")
    monkeypatch.setattr(meeting.subprocess, "run",
                        lambda *a, **k: launch() or _Launched())
    t0 = time.time()
    got = meeting.start(wait=30.0)
    assert got["problem"] == "died", got
    assert time.time() - t0 < 5, "it sat out the whole wait for a dead process"


def test_a_recorder_that_ignores_sigterm_is_killed_rather_than_abandoned(
        monkeypatch, tmp_path):
    """SIGTERM is preferred because the WAV headers are written when the files
    close. That justifies waiting for it, not giving up on it. This used to
    unlink CURRENT whichever way the wait ended, leaving a recorder running
    with no record of it: `running()` said nothing, `stop` said no meeting was
    being recorded, `start` would launch a second one beside it, and macOS kept
    the screen recording indicator lit for the remaining four hours."""
    import subprocess
    # Ignores SIGTERM, dies on SIGKILL. Exactly the case.
    #
    # It has to say when its handler is installed. Signalling a Python that is
    # still starting up kills it in the ordinary way, so without this the test
    # passed against a `stop` with no escalation in it at all: the process it
    # was meant to find still running had already died.
    ready = tmp_path / "ready"
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import signal,sys,time\n"
         "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
         "open(sys.argv[1], 'w').write('y')\n"
         "time.sleep(30)", str(ready)])
    for _ in range(100):
        if ready.exists():
            break
        time.sleep(0.05)
    assert ready.exists(), "the stubborn process never started"
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time()})
    (meeting._dir(mid) / "status.json").write_text(json.dumps(
        {"state": "recording", "pid": proc.pid, "started": time.time()}))
    meeting.CURRENT.parent.mkdir(parents=True, exist_ok=True)
    meeting.CURRENT.write_text(mid)
    try:
        got = meeting.stop(wait=1.0)
        assert "problem" not in got, got
        assert not meeting._alive(proc.pid), "it was left running"
        assert not meeting.CURRENT.exists()
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        proc.wait(timeout=5)


def test_forgetting_the_meeting_being_recorded_stops_it_first(monkeypatch):
    """Removing the directory does not stop the recorder. Its files stay open
    on unlinked inodes and CURRENT goes with them, so nothing can find it
    again."""
    import subprocess
    proc = subprocess.Popen(["sleep", "30"])
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time()})
    (meeting._dir(mid) / "status.json").write_text(json.dumps(
        {"state": "recording", "pid": proc.pid, "started": time.time()}))
    meeting.CURRENT.parent.mkdir(parents=True, exist_ok=True)
    meeting.CURRENT.write_text(mid)
    try:
        assert meeting.forget(mid) is True
        assert not meeting._alive(proc.pid), "forget left an orphan recorder"
        assert not meeting._dir(mid).exists()
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        proc.wait(timeout=5)


def test_a_meeting_can_be_transcribed_after_the_fact(monkeypatch, capsys):
    """Anything that interrupts the transcribing half, a Ctrl-C, a missing
    whisper, a full disk, used to strand the recording as "audio only" with no
    command anywhere that would ever process it. By that point the audio exists
    and the people in the room have already agreed to it."""
    import importlib.machinery
    import importlib.util
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time(), "seconds": 60})
    tone(meeting._dir(mid) / "them.wav", [(1, 0.5)])

    done = []
    monkeypatch.setattr(meeting, "chunks_expected", lambda m: 1)
    monkeypatch.setattr(meeting, "transcribe",
                        lambda m, p=None: done.append(m))
    monkeypatch.setattr(meeting, "notes", lambda m: meeting.load(m))
    monkeypatch.setattr(meeting, "render", lambda r, **k: "notes here\n")

    loader = importlib.machinery.SourceFileLoader("dcli", "bin/dictator")
    spec = importlib.util.spec_from_loader("dcli", loader)
    cli = importlib.util.module_from_spec(spec)
    loader.exec_module(cli)
    assert cli.meeting(["transcribe"]) == 0
    assert done == [mid]


def test_a_failure_while_transcribing_says_how_to_pick_it_up(monkeypatch,
                                                             capsys):
    import importlib.machinery
    import importlib.util
    mid = "20260101-090000"
    meeting.save(mid, {"id": mid, "started": time.time(), "seconds": 60})
    tone(meeting._dir(mid) / "them.wav", [(1, 0.5)])

    def boom(*a, **k):
        raise RuntimeError("no room on the disk")

    monkeypatch.setattr(meeting, "chunks_expected", lambda m: 1)
    monkeypatch.setattr(meeting, "transcribe", boom)

    loader = importlib.machinery.SourceFileLoader("dcli", "bin/dictator")
    spec = importlib.util.spec_from_loader("dcli", loader)
    cli = importlib.util.module_from_spec(spec)
    loader.exec_module(cli)
    assert cli.meeting(["transcribe"]) == 1
    out = capsys.readouterr().out
    assert "recording is safe" in out
    assert f"dictator meeting transcribe {mid}" in out


def test_permission_is_not_granted_when_only_the_screen_is(monkeypatch):
    """"Granted. Start a meeting" on a machine whose microphone is denied
    starts a recording that captures the room and not the person in it, and
    the walkthrough that exists to prevent exactly that said it was fine."""
    monkeypatch.setattr(meeting, "check",
                        lambda *a, **k: {"screen": True, "mic": False,
                                         "mic_asked": True})
    assert meeting.granted() is False
    monkeypatch.setattr(meeting, "check",
                        lambda *a, **k: {"screen": False, "mic": True})
    assert meeting.granted() is False
    monkeypatch.setattr(meeting, "check",
                        lambda *a, **k: {"screen": True, "mic": True})
    assert meeting.granted() is True
    monkeypatch.setattr(meeting, "check", lambda *a, **k: {})
    assert meeting.granted() is False, "cannot tell is not the same as yes"


def test_a_bundle_macos_refuses_to_open_says_so_at_once(monkeypatch):
    """`open` refusing is instant and says why: a damaged or quarantined
    bundle, or one whose LSMinimumSystemVersion is newer than this macOS.
    Throwing that away turned every one of those into thirty seconds of a
    progress line followed by "it said nothing"."""
    class Refused:
        returncode = 1
        stdout = ""
        stderr = ("The application cannot be opened because it is not "
                  "supported on this version of macOS.")

    monkeypatch.setattr(meeting, "build_app", lambda: "/tmp/nowhere.app")
    monkeypatch.setattr(meeting.subprocess, "run", lambda *a, **k: Refused())
    t0 = time.time()
    got = meeting.start(wait=30.0)
    assert got["problem"] == "launch", got
    assert "not supported on this version" in got["say"]
    assert time.time() - t0 < 5, "it waited out the whole timeout anyway"


def test_one_bad_chunk_does_not_take_the_rest_of_the_batch_with_it(monkeypatch,
                                                                   tmp_path):
    """`whisper-cli` stops processing the remaining files when one fails, and
    an empty result is indistinguishable from "this stretch was silent". So a
    single bad chunk silently lost up to BATCH * CHUNK minutes of a meeting,
    with one line in a log nobody reads."""
    paths = [tmp_path / f"c{i}.wav" for i in range(3)]
    for q in paths:
        q.write_bytes(b"")
    runs = []

    def fake_run(cmd, **kw):
        files = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-f"]
        runs.append(files)
        # The first file is poison. In a batch it kills everything after it.
        poisoned = str(paths[0]) in files
        for f in files:
            if poisoned and f != str(paths[0]):
                continue            # whisper stopped, no json for these
            if f == str(paths[0]) and len(files) > 1:
                continue            # nor for the one that failed
            Path(f + ".json").write_text(json.dumps(
                {"transcription": [{"text": f"said in {Path(f).name}",
                                    "offsets": {"from": 0, "to": 1000}}]}))

        class Done:
            stdout, stderr, returncode = None, iter([]), 0

            def wait(self, timeout=None):
                return 0
        return Done()

    monkeypatch.setattr(meeting.stt, "whisper_bin", lambda: "/bin/true")
    monkeypatch.setattr(meeting.stt, "stt_lang_mode",
                        lambda: (tmp_path, "en"))
    monkeypatch.setattr(meeting.subprocess, "Popen", fake_run)
    monkeypatch.setattr(meeting, "_watchdog", lambda *a, **k: None)
    (tmp_path / "model").write_bytes(b"")
    monkeypatch.setattr(meeting.stt, "stt_lang_mode",
                        lambda: (tmp_path / "model", "en"))

    got = meeting._whisper(paths, "en")
    # The two good chunks must survive the one bad one.
    assert got[str(paths[1])], "the chunk after the bad one was lost"
    assert got[str(paths[2])], "the chunk after the bad one was lost"
    assert len(runs) > 1, "it never retried them on their own"
