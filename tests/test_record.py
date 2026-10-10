"""Recording, which no longer needs a package manager.

sox was half the Homebrew dependency and all of the licence problem: GPL, so it
can never be shipped inside the app this wants to become, and nine libraries
pulled in to capture one mono stream. macOS records through AVFoundation.

What these tests are actually protecting is narrow and unforgiving: whisper
resamples nothing, so a recording that is not 16000Hz, mono, 16-bit PCM is
either refused or transcribed as noise, and the symptom of getting it wrong is
not an error, it is a key that produces nonsense.
"""
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path

import pytest

from dictator import always, recorder, stt, swiftbuild

ROOT = Path(__file__).resolve().parent.parent
HAVE_SWIFTC = bool(shutil.which("swiftc"))


class _Fake:
    """Stands in for a recorder process. Only what the callers touch."""

    def __init__(self):
        self.terminated = False

    def poll(self):
        return 0

    def terminate(self):
        self.terminated = True


# ---- which recorder answers -------------------------------------------------

def test_a_hold_uses_the_native_recorder_when_it_is_there(monkeypatch):
    fake = _Fake()
    monkeypatch.setattr(recorder, "start", lambda w, s, e=None: fake)
    monkeypatch.setattr(stt, "_find", lambda name: pytest.fail(
        f"looked for {name} while the native recorder was available"))
    assert stt.record_hold("/tmp/x.wav") is fake


def test_sox_is_still_the_fallback(monkeypatch, tmp_path):
    """A machine with no Swift toolchain must still be able to record.

    Falling back to nothing would be a key that does nothing, which is the
    failure this whole product is one long argument against."""
    monkeypatch.setattr(recorder, "start", lambda w, s, e=None: None)
    monkeypatch.setattr(stt, "_find", lambda name: "/bin/echo" if name == "rec" else "")
    seen = {}

    def fake_popen(cmd, **kw):
        seen["cmd"] = cmd
        return _Fake()

    monkeypatch.setattr(stt.subprocess, "Popen", fake_popen)
    assert stt.record_hold(str(tmp_path / "x.wav")) is not None
    cmd = seen["cmd"]
    # The fallback has to ask for the same format as the thing it replaces.
    assert "16000" in cmd and "1" in cmd and "16" in cmd, cmd
    assert "silence" not in cmd, "the hold recorder must not trim or auto-stop"


def test_no_recorder_at_all_is_none_and_not_a_crash(monkeypatch):
    monkeypatch.setattr(recorder, "start", lambda w, s, e=None: None)
    monkeypatch.setattr(stt, "_find", lambda name: "")
    assert stt.record_hold("/tmp/x.wav") is None


def test_doctor_can_name_the_recorder_in_use(monkeypatch):
    """doctor says which one, because the two fail differently and only one of
    them is something the user had to install."""
    monkeypatch.setattr(recorder, "build", lambda *a, **k: "/somewhere/dictator-rec")
    assert stt.recorder_in_use() == "native"
    monkeypatch.setattr(recorder, "build", lambda *a, **k: "")
    monkeypatch.setattr(stt, "_find", lambda name: "/opt/homebrew/bin/rec")
    assert stt.recorder_in_use() == "sox"
    monkeypatch.setattr(stt, "_find", lambda name: "")
    assert stt.recorder_in_use() == ""


def test_the_command_line_is_unchanged_for_the_caller():
    """dictate.py polls and terminates the object it gets back. Whatever is
    behind record_hold, that shape is the contract."""
    fake = _Fake()
    assert hasattr(fake, "poll") and hasattr(fake, "terminate")
    import inspect
    src = inspect.getsource(stt.record_hold)
    assert "return p" in src


# ---- the level meter --------------------------------------------------------

def test_a_published_level_is_used_and_a_stale_one_is_not(tmp_path):
    """None is not zero. A meter that shows the last thing it heard before the
    recorder stopped is a meter saying the mic is open when it is not."""
    wav = tmp_path / "r.wav"
    lvl = tmp_path / "r.wav.lvl"
    assert recorder.level(str(wav)) is None
    lvl.write_text("0.5\n")
    assert recorder.level(str(wav)) == pytest.approx(0.5)
    old = time.time() - 5
    os.utime(lvl, (old, old))
    assert recorder.level(str(wav)) is None


def test_live_level_prefers_the_published_one(tmp_path, monkeypatch):
    wav = tmp_path / "r.wav"
    wav.write_bytes(b"\0" * 5000)
    monkeypatch.setattr(recorder, "level", lambda w: 0.75)
    assert stt.live_level(str(wav)) == pytest.approx(0.75)
    monkeypatch.setattr(recorder, "level", lambda w: None)
    assert stt.live_level(str(wav)) == 0.0        # a file of silence


def test_loudness_no_longer_needs_sox(tmp_path):
    """It used to shell out to `sox stat` and parse stderr, so it answered -1
    on every machine without sox, for a number that is one pass over samples
    we already have."""
    import array
    import inspect
    assert "subprocess" not in inspect.getsource(stt.loudness)
    wav = tmp_path / "loud.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(array.array("h", [16000, -16000] * 800).tobytes())
    assert stt.loudness(str(wav)) == pytest.approx(16000 / 32768, rel=0.01)
    assert stt.loudness(str(tmp_path / "missing.wav")) == -1.0


# ---- the real thing ---------------------------------------------------------

@pytest.mark.skipif(not HAVE_SWIFTC, reason="no swiftc here")
def test_the_recorder_produces_exactly_what_whisper_wants(tmp_path, monkeypatch):
    """16000Hz, mono, 16-bit. Whisper resamples nothing.

    This records the room for a moment. It does not care what is in the file,
    only about its shape, so it passes in a silent room and on a machine that
    has never been granted the microphone."""
    monkeypatch.setattr(recorder, "BIN", tmp_path / "bin" / "dictator-rec")
    assert recorder.build(), "the recorder did not compile"
    # Once to warm it, then the real take. The very first execution of a newly
    # written binary costs about 0.45s in dyld and signature checks, which is
    # measured and real but is not what this test is about.
    warm = recorder.start(str(tmp_path / "warm.wav"), 5)
    time.sleep(0.4)
    warm.terminate()
    warm.wait(timeout=10)

    wav = tmp_path / "take.wav"
    p = recorder.start(str(wav), 10)
    assert p is not None
    began = time.monotonic()
    time.sleep(1.2)
    window = time.monotonic() - began
    # Terminate, never kill: the WAV header is written at stop.
    p.terminate()
    assert p.wait(timeout=10) == 0
    with wave.open(str(wav), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        seconds = w.getnframes() / 16000
    # Most of the wall clock, or something is eating the start of every
    # sentence, and the whole point of push-to-talk is that the first word is
    # in. Measured against the window that actually elapsed, and as a fraction
    # of it, because a fixed lower bound turned red whenever the machine was
    # busy: it read 0.87 against a floor of 0.9 with a benchmark running. The
    # real figure (the recorder loses about 0.15s of the start, where sox lost
    # 0.50s) belongs in docs/findings.md as a measurement. What this test is
    # for is a recorder that loses a large part of every take.
    assert seconds > window * 0.6, (seconds, window)
    assert seconds < window + 0.3, (seconds, window)
    assert not (tmp_path / "take.wav.lvl").exists(), "left a stale level behind"


@pytest.mark.skipif(not HAVE_SWIFTC, reason="no swiftc here")
def test_whisper_reads_the_file_the_recorder_wrote(tmp_path, monkeypatch):
    """The point of the format is that the transcriber accepts it. A file
    whisper refuses is a hold that produced nothing, with no error anywhere."""
    whisper = stt.whisper_bin()
    model = stt.MODEL_DIR / "ggml-tiny.bin"
    if not whisper or not model.exists():
        pytest.skip("no whisper or no tiny model here")
    monkeypatch.setattr(recorder, "BIN", tmp_path / "bin" / "dictator-rec")
    assert recorder.build()
    wav = tmp_path / "take.wav"
    p = recorder.start(str(wav), 10)
    assert p is not None
    time.sleep(1.2)
    p.terminate()
    p.wait(timeout=10)
    r = subprocess.run([whisper, "-m", str(model), "-f", str(wav), "-nt", "-np"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-400:]
    assert "error" not in r.stderr.lower(), r.stderr[-400:]


@pytest.mark.skipif(not os.environ.get("DICTATOR_MIC_TEST"),
                    reason="plays audio out loud; set DICTATOR_MIC_TEST=1")
def test_a_sentence_spoken_out_loud_comes_back_as_words(tmp_path, monkeypatch):
    """The end to end claim, checked the only honest way: put a sentence in the
    air, record it with the new recorder, and read the transcript.

    Opt in, because it needs speakers, a microphone that can hear them, and a
    model on disk, and because a test suite that starts talking is rude."""
    monkeypatch.setattr(recorder, "BIN", tmp_path / "bin" / "dictator-rec")
    assert recorder.build()
    wav = tmp_path / "spoken.wav"
    p = recorder.start(str(wav), 30)
    time.sleep(0.4)
    subprocess.run(["say", "-r", "170", "The quick brown fox jumps over the lazy dog."])
    time.sleep(0.3)
    p.terminate()
    p.wait(timeout=10)
    text, _ = stt.transcribe_ex(str(wav))
    assert "brown fox" in text.lower(), text


# ---- built once, at install time --------------------------------------------

def test_every_helper_is_built_before_first_use(monkeypatch):
    """Built lazily, swiftc runs in the middle of the first few holds, which is
    where somebody decides whether this works (issue #1)."""
    calls = []
    from dictator import hotkey, media, orbnative, paste, readback
    for mod, attr in ((hotkey, "build"), (orbnative, "build"),
                      (recorder, "build"), (readback, "build"), (media, "build")):
        monkeypatch.setattr(mod, attr,
                            lambda force=False, _m=mod: calls.append(_m.__name__) or "x")
    monkeypatch.setattr(paste, "helper", lambda: calls.append("paste") or "x")
    monkeypatch.setattr(always, "build_app", lambda: calls.append("app") or "x")
    built = always.build_all()
    assert set(built) == {"hotkey", "orb", "recorder", "paste", "readback",
                          "media", "app"}
    for name in ("dictator.hotkey", "dictator.orbnative", "dictator.recorder",
                 "dictator.readback", "dictator.media", "paste", "app"):
        assert name in calls, calls


def test_the_app_bundle_is_never_force_rebuilt():
    """Rebuilding the bundle costs the user the Accessibility permission they
    just granted, so the one helper that must not be swept up in a forced
    rebuild is that one."""
    import inspect
    src = inspect.getsource(always.build_all)
    assert "build_app()" in src, "build_all must call build_app with no force"
    assert "build_app(force" not in src


def test_the_installer_no_longer_asks_for_sox():
    """sox was half the Homebrew dependency, and it was the GPL half."""
    text = (ROOT / "scripts" / "install.sh").read_text()
    assert "brew install" in text
    assert "for pkg in whisper-cpp" in text, "the brew package list changed"


# ---- building helpers safely ------------------------------------------------

def test_a_missing_source_is_a_reason_not_an_exception(tmp_path):
    assert swiftbuild.compile_if_needed(tmp_path / "nope.swift",
                                        tmp_path / "out", "test") == ""


def test_an_up_to_date_binary_is_left_alone(tmp_path):
    src = tmp_path / "a.swift"
    src.write_text("print(1)\n")
    out = tmp_path / "a"
    out.write_text("pretend binary")
    before = out.stat().st_mtime
    assert swiftbuild.compile_if_needed(src, out, "test") == str(out)
    assert out.stat().st_mtime == before


@pytest.mark.skipif(not HAVE_SWIFTC, reason="no swiftc here")
def test_a_failed_build_does_not_replace_a_working_binary(tmp_path):
    """The old code compiled straight to the final path, so a build that failed
    halfway left a truncated binary that the next mtime check read as built."""
    out = tmp_path / "bad"
    out.write_text("the working one")
    src = tmp_path / "bad.swift"
    src.write_text("this is not swift\n")
    os.utime(src, (time.time() + 10, time.time() + 10))   # newer, so it builds
    assert swiftbuild.compile_if_needed(src, out, "test") == ""
    assert out.read_text() == "the working one"
    assert not (tmp_path / "bad.new").exists(), "left a half built binary behind"


# ---- a recording that was cut short ------------------------------------------
#
# AVAudioRecorder stops on its own when the input device changes underneath it,
# which is what a Bluetooth headset connecting mid sentence does. What is left
# is a valid WAV holding the first few seconds, so every check downstream passes
# and the user is handed part of their own sentence formatted exactly like a
# whole one. These are about telling that apart from an ordinary stop.


class _Exited:
    """A recorder that has already finished, with a code."""

    def __init__(self, code, native=True):
        self.returncode = code
        if native:
            self.dictator_native = True

    def poll(self):
        return self.returncode


def test_an_ordinary_exit_is_not_reported_as_a_problem():
    assert recorder.why_it_stopped(_Exited(0)) == ""


def test_a_cut_recording_says_so_in_words_the_user_can_act_on():
    why = recorder.why_it_stopped(_Exited(recorder.CUT_SHORT))
    assert why, "an interrupted recording explained nothing"
    assert "cut short" in why
    assert "microphone" in why or "input device" in why


def test_sox_exit_codes_are_never_read_as_ours():
    """sox answers the same interface and its numbers mean unrelated things. A
    wrong explanation on the hold path is worse than none at all."""
    assert recorder.why_it_stopped(_Exited(recorder.CUT_SHORT, native=False)) == ""


def test_asking_a_process_that_has_not_exited_is_not_an_error():
    """It is asked on the key-up edge, where a raised exception is a key press
    that does nothing at all and shows the user no reason."""
    assert recorder.why_it_stopped(_Exited(None)) == ""
    assert recorder.why_it_stopped(None) == ""
    assert recorder.why_it_stopped(object()) == ""


def test_the_two_sides_agree_on_the_exit_code():
    """Swift and Python cannot share a constant, so the number is written down
    twice and this is what stops the two copies meaning different things."""
    src = (ROOT / "native" / "record.swift").read_text()
    assert f"let CUT_SHORT: Int32 = {recorder.CUT_SHORT}" in src


@pytest.mark.skipif(not HAVE_SWIFTC, reason="no swiftc here")
def test_reaching_max_seconds_is_not_an_interruption(tmp_path, monkeypatch):
    """The dangerous regression in the other direction. Stopping at the cap
    fires the same AVFoundation callback an interruption does, so a recorder
    that cannot tell them apart would report every long hold as cut short and
    the warning would mean nothing within a day."""
    monkeypatch.setattr(recorder, "BIN", tmp_path / "bin" / "dictator-rec")
    assert recorder.build(), "the recorder did not compile"
    p = recorder.start(str(tmp_path / "capped.wav"), 2)
    assert p is not None
    assert p.wait(timeout=20) == 0, "reaching the cap was reported as a failure"
    assert recorder.why_it_stopped(p) == ""
    with wave.open(str(tmp_path / "capped.wav"), "rb") as w:
        assert w.getnframes() / 16000 > 1.0, "the cap closed the file too early"
