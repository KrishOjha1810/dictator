"""The two gestures, and the line protocol that carries them.

The listener is a separate process, so the protocol is the only thing holding
dictation together: a verb this side silently fails to understand is a
microphone that stays open, or a take that never gets transcribed, and neither
of those announces itself. So the parser is tested against every line the
Swift can emit, and the Swift is asked to prove its own state machine.
"""
import shutil
import subprocess

import pytest

from dictator import hotkey

ROOT = hotkey.SRC.parent.parent


# ---------------------------------------------------------------- the hold

def test_down_has_no_payload():
    ev = hotkey.parse("DOWN")
    assert ev.verb == "DOWN"
    assert ev.ms is None and ev.why == ""
    assert not hotkey.stops(ev)


def test_up_carries_the_hold_in_milliseconds():
    ev = hotkey.parse("UP 251")
    assert (ev.verb, ev.ms, ev.why) == ("UP", 251.0, "")
    assert hotkey.stops(ev) and hotkey.transcribes(ev)
    assert not hotkey.is_session(ev), "a bare UP is a hold, not a session"


@pytest.mark.parametrize("line", ["CANCEL 272", "LOCKED 400"])
def test_a_cancelled_hold_is_never_transcribed(line):
    ev = hotkey.parse(line)
    assert hotkey.stops(ev)
    assert not hotkey.transcribes(ev)
    assert not hotkey.is_session(ev)


def test_ready_says_how_the_listener_is_configured():
    """The cap is on the wire so the recorder can be sized from it rather than
    from a constant that drifts out of step with the listener."""
    ev = hotkey.parse("READY fn toggle=shift cap=300000")
    assert ev.verb == "READY"
    assert ev.fields == {"toggle": "shift", "cap": "300000"}
    assert ev.why == "fn", "the key name is still readable"
    assert int(ev.fields["cap"]) == hotkey.DEFAULT_MAX_SESSION_MS


def test_ready_with_the_gesture_turned_off():
    assert hotkey.parse("READY fn toggle=off cap=300000").fields["toggle"] == "off"


# ---------------------------------------------------------------- the latch

def test_latch_opens_a_session():
    ev = hotkey.parse("LATCH 212")
    assert (ev.verb, ev.ms) == ("LATCH", 212.0)
    assert hotkey.is_session(ev)
    assert not hotkey.stops(ev), "the mic stays open across a latch"


def test_heartbeat_is_a_session_line_that_stops_nothing():
    ev = hotkey.parse("LISTENING 5761")
    assert (ev.verb, ev.ms) == ("LISTENING", 5761.0)
    assert hotkey.is_session(ev) and not hotkey.stops(ev)


def test_the_user_ending_a_session_transcribes_it():
    ev = hotkey.parse("UP 6557 toggle")
    assert (ev.verb, ev.ms, ev.why) == ("UP", 6557.0, "toggle")
    assert hotkey.is_session(ev), "the reason word is what tells the two apart"
    assert hotkey.stops(ev) and hotkey.transcribes(ev)


@pytest.mark.parametrize("line,why", [
    ("CANCEL 300000 cap", "cap"),
    ("CANCEL 4120 tap", "tap"),
    ("CANCEL 2312 exit", "exit"),
    ("LOCKED 9000 lock", "lock"),
])
def test_a_session_nobody_ended_on_purpose_is_discarded(line, why):
    """Everything except the user's own second tap throws the audio away.

    Pasting minutes of whatever the room was saying into the frontmost app is
    not a mistake the user can take back, so an ending we chose is never an
    ending that types."""
    ev = hotkey.parse(line)
    assert ev.why == why
    assert hotkey.is_session(ev)
    assert hotkey.stops(ev)
    assert not hotkey.transcribes(ev)


# ------------------------------------------------------- refusing to fall over

@pytest.mark.parametrize("line", ["", "   ", "\n", None, 7, b"UP 1"])
def test_nothing_in_the_line_means_nothing_comes_back(line):
    assert hotkey.parse(line) is None


def test_an_unknown_verb_survives_instead_of_raising():
    """A listener from the future must not take the dictation loop down."""
    ev = hotkey.parse("WHISTLED 12 sideways")
    assert (ev.verb, ev.ms, ev.why) == ("WHISTLED", 12.0, "sideways")
    assert not hotkey.stops(ev) and not hotkey.transcribes(ev)


def test_a_duration_that_is_not_a_number_is_not_invented():
    ev = hotkey.parse("UP later")
    assert ev.ms is None, "better no duration than a made up one"
    assert ev.verb == "UP"


def test_stray_whitespace_and_a_trailing_newline_parse():
    ev = hotkey.parse("  UP   6557   toggle \n")
    assert (ev.verb, ev.ms, ev.why) == ("UP", 6557.0, "toggle")
    assert ev.raw == "UP   6557   toggle"


def test_the_helpers_tolerate_nothing_at_all():
    for f in (hotkey.stops, hotkey.transcribes, hotkey.is_session):
        assert f(None) is False


# ---------------------------------------------------------------- launching

def test_listen_passes_the_gesture_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(hotkey, "build", lambda: "/tmp/fake-hotkey")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda argv, **kw: seen.setdefault("argv", argv))
    hotkey.listen("fn", min_hold_ms=0, toggle_key="shift", max_session_ms=300000)
    argv = seen["argv"]
    assert argv[:3] == ["/tmp/fake-hotkey", "--key", "fn"]
    assert argv[argv.index("--toggle-key") + 1] == "shift"
    assert argv[argv.index("--max-session") + 1] == "300000"


def test_an_unknown_toggle_key_falls_back_rather_than_launching_it(monkeypatch):
    """swiftc's argument parser exits 2 on a key it does not know, which would
    turn a typo into a listener that never arms and never says why."""
    seen = {}
    monkeypatch.setattr(hotkey, "build", lambda: "/tmp/fake-hotkey")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda argv, **kw: seen.setdefault("argv", argv))
    hotkey.listen("fn", toggle_key="banana")
    argv = seen["argv"]
    assert argv[argv.index("--toggle-key") + 1] == hotkey.DEFAULT_TOGGLE


def test_off_is_spellable_so_the_hold_only_listener_is_still_reachable():
    assert "off" in hotkey.TOGGLE_KEYS


# ------------------------------------------------- the two sides agreeing

def test_every_reason_the_listener_can_send_is_documented_here():
    """A reason word added in Swift and not here is a take that gets handled
    by whatever the default branch happens to do."""
    src = hotkey.SRC.read_text()
    import re
    reasons = set(re.findall(r'why: "([a-z]+)"', src))
    assert reasons, "the reasons moved; this test is now blind"
    for r in reasons:
        assert r in hotkey.__doc__, f"the listener can send {r!r} and nothing documents it"


def test_every_verb_the_listener_ends_a_take_with_is_a_stop_verb():
    src = hotkey.SRC.read_text()
    import re
    verbs = set(re.findall(r'reason: "([A-Z]+)"', src))
    assert verbs, "the endings moved; this test is now blind"
    assert verbs <= set(hotkey.STOP_VERBS), verbs


def test_space_is_not_the_default_gesture():
    """fn is not a translation modifier, so fn+space still types a space into
    whatever is in front, and a listen-only tap cannot take it back."""
    assert hotkey.DEFAULT_TOGGLE != "space"


def test_the_hands_free_gesture_is_off_by_default():
    """With it on, holds that were meant to be ordinary dictation latched into
    a hands free session, ended immediately, and the sentence was thrown away.
    The log filled with "Thank you." and "[MUSIC PLAYING]", which is what
    whisper returns for the silence that follows. It ate several dictations
    before anyone worked out what it was. A feature that breaks the thing
    people came for does not get to be the default."""
    assert hotkey.DEFAULT_TOGGLE == "off"
    assert "space" in hotkey.TOGGLE_KEYS, "still offered, just not chosen for you"


@pytest.mark.skipif(not shutil.which("swiftc"), reason="no swiftc here")
def test_the_listener_proves_its_own_state_machine(tmp_path):
    """Runs the Swift self test, which drives the gesture state machine with
    scripted events: no tap, no permissions, no hot microphone. This is the
    part that cannot be checked by hand without opening one."""
    exe = tmp_path / "hk"
    subprocess.run(["swiftc", "-O", str(hotkey.SRC), "-o", str(exe)],
                   check=True, capture_output=True, timeout=300)
    out = subprocess.run([str(exe), "--self-test"], capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "passed" in out.stdout
    assert "FAIL" not in out.stdout, out.stdout


def test_the_two_caps_are_the_same_number():
    """The listener's session cap and the recorder's cap must agree.

    A hold ends when a finger lifts, which the hardware can be asked about. A
    hands free session has no such witness: the user's hands are off the
    keyboard, that is the point. If the listener ran longer than the recorder,
    it would go on reporting that it is listening after the recording had
    stopped, and the indicator is the only thing telling the user whether the
    microphone is open."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "dictator" / "dictate.py").read_text()
    assert "max_session_ms=int(MAX_SECS * 1000)" in src, \
        "the listener's session cap no longer follows the recorder's"
    tree = ast.parse(src)
    caps = [n.value.value for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
            and any(getattr(t, "id", "") == "MAX_SECS" for t in n.targets)]
    assert caps and caps[0] > 0, caps


def test_a_discarded_session_says_why():
    """Every way a session ends except the user's own second tap throws the
    audio away. Silently dropping a long dictation is the kind of thing people
    assume is a crash."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "dictator" / "dictate.py").read_text()
    for why in ("cap", "tap", "exit", "lock"):
        assert f'"{why}":' in src, f"no explanation for a session ending on {why}"
