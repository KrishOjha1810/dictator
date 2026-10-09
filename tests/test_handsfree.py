"""Hands free dictation: double-tap the key, talk, press it once to finish.

Two halves. The key listener (native/hotkey.swift) decides what the taps were
and prints a line; the loop (dictate.handle) acts on the line. The listener's
half is driven here through its --script mode, the real state machine with no
event tap and no permission; the loop's half with the lines a listener prints.
"""
import shutil
import subprocess

import pytest

from dictator import dictate, hotkey


# ---- the listener --------------------------------------------------------

@pytest.fixture(scope="module")
def listener(tmp_path_factory):
    if not shutil.which("swiftc"):
        pytest.skip("no swiftc here")
    exe = tmp_path_factory.mktemp("hk") / "hk"
    subprocess.run(["swiftc", "-O", str(hotkey.SRC), "-o", str(exe)],
                   check=True, capture_output=True, timeout=300)

    def run(script, *args):
        # --min-hold 0, as the loop starts it.
        out = subprocess.run([str(exe), "--script", "--min-hold", "0", *args], input=script,
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        return [ln.split()[0] + (" " + ln.split()[-1] if len(ln.split()) > 2 else "")
                for ln in out.stdout.splitlines() if ln.strip()]
    return run


def test_a_double_tap_latches(listener):
    assert listener("down\nup\ndown\nup\n") == ["DOWN", "UP", "DOWN", "LATCH"]


def test_one_tap_is_nothing_but_a_short_press(listener):
    assert listener("down\nup\n") == ["DOWN", "UP"]


def test_taps_too_slow_are_two_taps(listener):
    assert listener("down\nup\nsleep 450\ndown\nup\n") == ["DOWN", "UP", "DOWN", "UP"]


def test_holding_is_still_push_to_talk(listener):
    assert listener("down\nsleep 400\nup\n") == ["DOWN", "UP"]
    # ...even straight after a tap: a held second press is not a tap.
    assert listener("down\nup\ndown\nsleep 350\nup\n") == ["DOWN", "UP", "DOWN", "UP"]


def test_one_press_in_a_session_finishes_it(listener):
    out = listener("down\nup\ndown\nup\nsleep 350\ndown\nup\n")
    assert out == ["DOWN", "UP", "DOWN", "LATCH", "UP toggle"]


def test_escape_throws_the_session_away(listener):
    out = listener("down\nup\ndown\nup\nesc\n")
    assert out == ["DOWN", "UP", "DOWN", "LATCH", "CANCEL esc"]


def test_the_pill_opens_finishes_and_cancels_through_the_listener(listener):
    assert listener("TOGGLE\nsleep 50\nFINISH\n") == ["DOWN", "LATCH", "UP toggle"]
    assert listener("TOGGLE\nCANCEL\n") == ["DOWN", "LATCH", "CANCEL button"]
    assert listener("FINISH\nCANCEL\n") == []


def test_double_tap_can_be_turned_off(listener):
    assert listener("down\nup\ndown\nup\n", "--double-tap", "off") == \
        ["DOWN", "UP", "DOWN", "UP"]


def test_the_listener_is_given_a_pipe_to_hear_the_pill_on(monkeypatch):
    seen = {}
    monkeypatch.setattr(hotkey, "build", lambda: "/tmp/fake-hotkey")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda argv, **kw: seen.update(argv=argv, kw=kw))
    hotkey.listen("fn")
    assert seen["kw"]["stdin"] == subprocess.PIPE
    assert seen["argv"][seen["argv"].index("--double-tap") + 1] == "on"


# ---- the loop ------------------------------------------------------------

class _Rec:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


@pytest.fixture
def loop(monkeypatch):
    hud, finished = [], []
    monkeypatch.setattr(dictate.core, "set_hud", lambda ph, lv=0.0, *a: hud.append(ph))
    monkeypatch.setattr(dictate.core, "log", lambda *a, **k: None)
    monkeypatch.setattr(dictate.stt, "record_hold", lambda w, **k: _Rec())
    monkeypatch.setattr(dictate.mac, "frontmost_app", lambda: "Notes")
    monkeypatch.setattr(dictate.warmup, "models", lambda: None)
    monkeypatch.setattr(dictate, "publish", lambda *a, **k: None)
    d = dictate.Dictation()
    monkeypatch.setattr(d, "_levels", lambda: None)
    monkeypatch.setattr(d, "_finish", lambda *a, **k: finished.append(a))

    class NoThread:
        def __init__(self, target=None, args=(), **k):
            self.t, self.a = target, args

        def start(self):
            if self.t is not None and self.t is not d._levels:
                self.t(*self.a)
    monkeypatch.setattr(dictate.threading, "Thread", NoThread)
    d.hud, d.finished = hud, finished
    return d


def test_a_double_tap_leaves_the_microphone_open(loop):
    for line in ("DOWN", "UP 80", "DOWN", "LATCH 90"):
        dictate.handle(loop, line)
    assert loop.proc is not None and loop.hands_free
    assert loop.hud[-1] == "handsfree"
    assert loop.finished == []          # the first tap was a mis-press


def test_one_press_finishes_transcribes_and_pastes_where_you_were(loop):
    for line in ("DOWN", "UP 80", "DOWN", "LATCH 90", "UP 4200 toggle"):
        dictate.handle(loop, line)
    assert loop.proc is None and not loop.hands_free
    assert len(loop.finished) == 1
    wav, app = loop.finished[0][0], loop.finished[0][1]
    assert app == "Notes"


@pytest.mark.parametrize("why", ["esc", "button", "cap", "lock", "tap", "exit"])
def test_every_other_ending_throws_it_away(loop, why):
    for line in ("DOWN", "LATCH 0", f"CANCEL 9000 {why}"):
        dictate.handle(loop, line)
    assert loop.proc is None and not loop.hands_free
    assert loop.finished == []


def test_a_hold_is_still_push_to_talk(loop):
    dictate.handle(loop, "DOWN")
    assert not loop.hands_free
    dictate.handle(loop, "UP 1500")
    assert len(loop.finished) == 1 and loop.proc is None


def test_two_slow_taps_do_nothing(loop):
    for line in ("DOWN", "UP 90", "DOWN", "UP 85"):
        dictate.handle(loop, line)
    assert loop.finished == [] and loop.proc is None and not loop.hands_free


def test_the_heartbeat_keeps_saying_hands_free(loop):
    for line in ("DOWN", "LATCH 0", "LISTENING 5000"):
        dictate.handle(loop, line)
    assert loop.hud[-1] == "handsfree"


def test_ready_and_bye_are_reported_to_the_loop(loop):
    assert dictate.handle(loop, "READY fn toggle=off cap=120000 doubletap=on") == "ready"
    assert dictate.handle(loop, "BYE") == "bye"
    assert dictate.handle(loop, "   ") == ""
    assert dictate.handle(loop, "WHATEVER 1") == ""


def test_the_session_cap_is_the_recorders_cap():
    """A hands free session must end on its own, and no later than the
    recorder does: the existing cap, passed to the listener."""
    assert dictate.MAX_SECS > 0
    assert dictate.MAX_SECS * 1000 <= hotkey.DEFAULT_MAX_SESSION_MS
