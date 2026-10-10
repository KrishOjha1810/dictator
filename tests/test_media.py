"""Other audio is quieted while the microphone is open, and put back after.

The helper is replaced by a recorder: nothing here pauses or mutes the
machine running the tests."""
import time

import pytest

from dictator import core, media


@pytest.fixture
def helper(monkeypatch):
    calls = []
    answer = {"quiet": "paused"}

    def run(*args, timeout=4.0):
        calls.append(args)
        return answer.get(args[0], "")
    monkeypatch.setattr(media, "_run", run)
    monkeypatch.setattr(media, "DELAY_S", 0.02)
    media.set_enabled(True)
    return calls, answer


def test_what_was_paused_is_resumed(helper):
    calls, _ = helper
    q = media.Quieting().start()
    q.wait()              # the quiet has happened, however slow the machine
    q.stop()
    q.wait()
    assert calls == [("quiet",), ("restore", "paused")]
    assert not (core.STATE_DIR / "media-quieted").exists()


def test_what_was_muted_is_unmuted(helper):
    calls, answer = helper
    answer["quiet"] = "muted"
    q = media.Quieting().start()
    q.wait()              # the quiet has happened, however slow the machine
    assert (core.STATE_DIR / "media-quieted").read_text() == "muted"
    q.stop()
    q.wait()
    assert calls[-1] == ("restore", "muted")


def test_a_tap_shorter_than_the_delay_touches_nothing(helper, monkeypatch):
    calls, _ = helper
    monkeypatch.setattr(media, "DELAY_S", 0.5)
    q = media.Quieting().start()
    q.stop()
    time.sleep(0.7)
    assert calls == []


def test_nothing_playing_means_nothing_to_restore(helper):
    calls, answer = helper
    answer["quiet"] = "none"
    q = media.Quieting().start()
    q.wait()              # the quiet has happened, however slow the machine
    q.stop()
    q.wait()
    assert calls == [("quiet",)]
    assert not (core.STATE_DIR / "media-quieted").exists()


def test_turned_off_it_never_runs(helper):
    calls, _ = helper
    media.set_enabled(False)
    q = media.Quieting().start()
    q.wait()              # the quiet has happened, however slow the machine
    q.stop()
    q.wait()
    assert calls == []
    assert media.enabled() is False


def test_a_mute_left_by_a_crash_is_undone_at_the_next_start(helper):
    calls, _ = helper
    (core.STATE_DIR / "media-quieted").write_text("muted")
    media.recover()
    assert calls == [("restore", "muted")]
    assert not (core.STATE_DIR / "media-quieted").exists()


def test_a_pause_left_by_a_crash_is_not_resumed_later(helper):
    calls, _ = helper
    for left in ("paused", "pending"):
        (core.STATE_DIR / "media-quieted").write_text(left)
        media.recover()
    assert calls == []


def _hold(monkeypatch):
    """A Dictation whose recorder and side effects are all stand-ins, and a
    list of what it asked the quieting to do."""
    from dictator import dictate
    did = []

    class Q:
        def start(self):
            did.append("quiet")
            return self

        def stop(self):
            did.append("restore")

    class Rec:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(dictate.media, "Quieting", Q)
    monkeypatch.setattr(dictate, "publish", lambda *a, **k: None)
    monkeypatch.setattr(dictate.core, "set_hud", lambda *a, **k: None)
    monkeypatch.setattr(dictate.mac, "frontmost_app", lambda: "Terminal")
    monkeypatch.setattr(dictate.warmup, "models", lambda: None)
    monkeypatch.setattr(dictate.stt, "record_hold", lambda *a, **k: Rec())
    monkeypatch.setattr(dictate.threading, "Thread",
                        lambda target, args=(), daemon=None: type(
                            "T", (), {"start": lambda self: None})())
    return dictate.Dictation(), did


def test_a_hold_quiets_on_press_and_restores_on_release(monkeypatch):
    d, did = _hold(monkeypatch)
    d.down()
    assert did == ["quiet"]
    d.up(900.0)
    assert did == ["quiet", "restore"]


def test_a_cancelled_chord_restores_too(monkeypatch):
    d, did = _hold(monkeypatch)
    d.down()
    d.cancel()
    assert did == ["quiet", "restore"]
