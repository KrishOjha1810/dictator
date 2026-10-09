"""Running from the downloadable app, and what the app reads back.

The app sets DICTATOR_BUNDLE before it starts Python, and from then on every
compiled helper has to come from inside the bundle: nothing on the user's Mac
may compile one, sign one, or fall back to a copy built under ~/.dictator by
an older install. Each of those would either fail on a Mac with no swiftc or
change a signature the user's permissions are pinned to.

Nothing here builds, signs or launches anything. A fake bundle is a temporary
directory with empty executable files in it, and the real swiftc, codesign and
launchctl are replaced by functions that fail the test if they are reached.
"""
import json
import os
import plistlib
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dictator import core, views  # noqa: E402


def _fake_bundle(tmp_path, helpers=("dictator-hotkey", "dictator-rec",
                                    "dictator-paste", "dictator-orb",
                                    "dictator-readback", "whisper-server",
                                    "whisper-cli", "parakeet-cli"),
                 ident="com.dictator.dictation"):
    app = tmp_path / "Dictator.app"
    h = app / "Contents" / "Helpers"
    h.mkdir(parents=True)
    for name in helpers:
        (h / name).write_text("#!/bin/sh\n")
        (h / name).chmod(0o755)
    meeting = h / "Dictator Meeting.app" / "Contents" / "MacOS"
    meeting.mkdir(parents=True)
    (meeting / "DictatorMeeting").write_text("")
    (meeting / "DictatorMeeting").chmod(0o755)
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "Dictator").write_text("")
    (macos / "Dictator").chmod(0o755)
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": ident}))
    return app


def _no_tools(monkeypatch, *modules):
    """Fail the test if swiftc, codesign or launchctl would run."""
    def refuse(cmd, *a, **k):
        pytest.fail(f"bundle mode ran {cmd[0]}")
    for m in modules:
        monkeypatch.setattr(m.subprocess, "run", refuse)


# ---- deciding the mode --------------------------------------------------------

def test_no_bundle_means_a_checkout():
    for empty in ("", "   "):
        assert core.bundle_root(empty) is None


def test_the_bundle_is_the_path_the_app_gave():
    assert core.bundle_root("/Applications/Dictator.app") == \
        Path("/Applications/Dictator.app")


def test_the_suite_runs_as_a_checkout():
    """conftest pins it, so a suite started from inside the app does not go
    looking for helpers in the real bundle."""
    assert core.BUNDLE is None
    assert views.mode() == "repo install"


# ---- where the helpers are -----------------------------------------------------

def test_a_checkout_keeps_its_helpers_in_the_state_directory():
    assert core.helper_path("dictator-rec") == core.STATE_DIR / "bin" / "dictator-rec"


def test_the_app_keeps_its_helpers_inside_itself(tmp_path, monkeypatch):
    app = _fake_bundle(tmp_path)
    monkeypatch.setattr(core, "BUNDLE", app)
    assert core.helper_path("dictator-rec") == \
        app / "Contents" / "Helpers" / "dictator-rec"


def test_every_module_looks_inside_the_bundle(tmp_path):
    """Read at import, so checked in a fresh interpreter the way the app
    starts one, rather than by reloading modules under the rest of the suite."""
    app = _fake_bundle(tmp_path)
    probe = (
        "import json\n"
        "from dictator import hotkey, recorder, paste, orbnative, readback, "
        "always, meeting\n"
        "print(json.dumps({'hotkey': str(hotkey.BIN), 'rec': str(recorder.BIN),"
        " 'paste': str(paste._HELPER), 'orb': str(orbnative.BIN),"
        " 'readback': str(readback.BIN), 'app': str(always.APP),"
        " 'meeting': str(meeting.APP)}))\n")
    env = dict(os.environ, DICTATOR_BUNDLE=str(app),
               DICTATOR_STATE=str(tmp_path / "state"),
               PYTHONPATH=str(REPO))
    out = subprocess.run([sys.executable, "-c", probe], cwd=str(tmp_path),
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    helpers = str(app / "Contents" / "Helpers")
    for name in ("hotkey", "rec", "paste", "orb", "readback", "meeting"):
        assert got[name].startswith(helpers + "/"), (name, got[name])
    assert got["meeting"].endswith("Dictator Meeting.app")
    assert got["app"] == str(app)


def test_the_app_never_compiles(tmp_path, monkeypatch):
    from dictator import swiftbuild
    app = _fake_bundle(tmp_path)
    monkeypatch.setattr(core, "BUNDLE", app)
    _no_tools(monkeypatch, swiftbuild)
    src = tmp_path / "newer.swift"
    src.write_text("// newer than the helper, which would rebuild a checkout")
    out = core.helper_path("dictator-rec")
    assert swiftbuild.compile_if_needed(src, out, "recorder", force=True) == str(out)


def test_a_missing_helper_in_the_app_is_reported_not_built(tmp_path, monkeypatch):
    from dictator import swiftbuild
    app = _fake_bundle(tmp_path, helpers=())
    monkeypatch.setattr(core, "BUNDLE", app)
    _no_tools(monkeypatch, swiftbuild)
    out = core.helper_path("dictator-orb")
    assert swiftbuild.compile_if_needed(tmp_path / "orb.swift", out, "orb") == ""
    said = core.errors()
    assert said and "orb" in said[-1]["msg"]
    assert "Download" in said[-1]["hint"]


def test_whisper_comes_from_the_app_before_homebrew(tmp_path, monkeypatch):
    from dictator import stt
    app = _fake_bundle(tmp_path)
    monkeypatch.setattr(core, "BUNDLE", app)
    monkeypatch.setattr(stt.shutil, "which", lambda n: f"/opt/homebrew/bin/{n}")
    assert stt._find("whisper-server") == \
        str(app / "Contents" / "Helpers" / "whisper-server")
    # And the old search still answers for what the app does not ship.
    assert stt._find("rec") == "/opt/homebrew/bin/rec"


def test_a_checkout_still_finds_whisper_where_it_did(monkeypatch):
    from dictator import stt
    monkeypatch.setattr(stt.shutil, "which", lambda n: f"/opt/homebrew/bin/{n}")
    assert stt._find("whisper-cli") == "/opt/homebrew/bin/whisper-cli"


def test_the_login_item_is_the_app_itself(tmp_path, monkeypatch):
    from dictator import always
    app = _fake_bundle(tmp_path)
    monkeypatch.setattr(core, "BUNDLE", app)
    _no_tools(monkeypatch, always)
    assert always.build_app() == str(app)


def test_the_app_is_never_signed_here(tmp_path, monkeypatch):
    from dictator import always, meeting, signing
    app = _fake_bundle(tmp_path)
    monkeypatch.setattr(core, "BUNDLE", app)
    _no_tools(monkeypatch, always, meeting, signing)
    assert not signing.local()
    assert signing.identity() == ""
    assert not (core.STATE_DIR / "signing.keychain-db").exists()
    always._sign(app)
    meeting._sign()


def test_the_meeting_recorder_is_used_as_shipped(tmp_path, monkeypatch):
    from dictator import meeting
    app = _fake_bundle(tmp_path)
    monkeypatch.setattr(core, "BUNDLE", app)
    shipped = app / "Contents" / "Helpers" / "Dictator Meeting.app"
    monkeypatch.setattr(meeting, "APP", shipped)
    monkeypatch.setattr(meeting, "EXE",
                        shipped / "Contents" / "MacOS" / "DictatorMeeting")
    _no_tools(monkeypatch, meeting)
    assert meeting.build_app(force=True) == str(shipped)


def test_the_permission_identifier_is_the_one_the_release_carries(tmp_path,
                                                                  monkeypatch):
    app = _fake_bundle(tmp_path, ident="com.dictator.app")
    monkeypatch.setattr(core, "BUNDLE", app)
    assert core.bundle_id() == "com.dictator.app"
    # The meeting recorder's identifier is not read from the dictation app.
    assert core.bundle_id("com.dictator.meeting").startswith("com.dictator.meeting.")


def test_doctor_can_say_where_each_helper_came_from(tmp_path, monkeypatch):
    from dictator import meeting
    app = _fake_bundle(tmp_path, helpers=("dictator-hotkey", "whisper-cli"))
    monkeypatch.setattr(core, "BUNDLE", app)
    monkeypatch.setattr(meeting, "APP",
                        app / "Contents" / "Helpers" / "Dictator Meeting.app")
    from dictator import stt
    monkeypatch.setattr(stt.shutil, "which", lambda n: None)
    monkeypatch.setattr(stt, "_BREW_BINS", ())
    got = views.helpers()
    assert views.mode() == "app bundle"
    assert got["dictator-hotkey"]["from"] == "app bundle"
    assert got["dictator-rec"]["from"] == "missing"
    assert got["whisper-cli"]["from"] == "app bundle"
    assert got["whisper-server"]["from"] == "missing"
    assert got["Dictator Meeting.app"]["from"] == "app bundle"


# ---- status.json ---------------------------------------------------------------

def test_status_has_the_shape_the_app_reads():
    assert core.write_status("ready", models={"ggml-tiny.bin":
                                              {"have": True, "progress": 1.0}})
    got = json.loads(core.STATUS_FILE.read_text())
    assert set(got) == {"state", "models", "error", "updated"}
    assert got["state"] == "ready"
    assert got["error"] is None
    assert got["models"]["ggml-tiny.bin"] == {"have": True, "progress": 1.0}
    assert abs(got["updated"] - time.time()) < 5


def test_an_unknown_state_is_not_written():
    assert not core.write_status("thinking")
    assert not core.STATUS_FILE.exists()


def test_an_error_is_one_line():
    core.write_status("error", error="the listener\nexited\n  badly")
    assert core.read_status()["error"] == "the listener exited badly"


def test_status_is_replaced_whole_and_leaves_no_temporary_file():
    core.write_status("listening")
    core.write_status("transcribing")
    assert core.read_status()["state"] == "transcribing"
    assert [p.name for p in core.STATUS_FILE.parent.glob("status.json*")] == \
        ["status.json"]


def test_model_progress_never_reads_full_before_the_file_lands(tmp_path,
                                                               monkeypatch):
    from dictator import stt
    monkeypatch.setattr(stt, "MODEL_DIR", tmp_path)
    (tmp_path / "ggml-tiny.bin").write_bytes(b"x")
    name, mb = stt.SHIPPED[2][0], stt.SHIPPED[2][1]
    with open(tmp_path / (name + ".part"), "wb") as f:
        f.truncate(mb * 1024 * 1024 * 2)          # sparse, and oversized
    got = stt.model_status()
    assert got["ggml-tiny.bin"] == {"have": True, "progress": 1.0,
                                    "essential": True}
    assert got[name]["have"] is False and got[name]["progress"] == 0.99
    assert got[name]["essential"] is False
    assert got[stt.SHIPPED[1][0]] == {"have": False, "progress": 0.0,
                                      "essential": True}


def test_a_hold_is_published_as_it_happens(monkeypatch):
    """listening on DOWN, transcribing on UP, ready when it is done."""
    from dictator import dictate
    seen = []
    monkeypatch.setattr(dictate, "publish", lambda s, e=None: seen.append(s))
    monkeypatch.setattr(dictate.core, "set_hud", lambda *a, **k: None)
    monkeypatch.setattr(dictate.mac, "frontmost_app", lambda: "Terminal")
    monkeypatch.setattr(dictate.warmup, "models", lambda: None)

    class Rec:
        def poll(self):
            return 0

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(dictate.stt, "record_hold", lambda *a, **k: Rec())
    monkeypatch.setattr(dictate.threading, "Thread",
                        lambda target, args=(), daemon=None: type(
                            "T", (), {"start": lambda self: None})())
    d = dictate.Dictation()
    d.down()
    d.up(900.0)
    monkeypatch.setattr(d, "_deliver", lambda *a, **k: None)
    d._finish("/tmp/x.wav", "Terminal")
    assert seen == ["listening", "transcribing", "ready"]


def test_a_mis_press_goes_straight_back_to_ready(monkeypatch):
    from dictator import dictate
    seen = []
    monkeypatch.setattr(dictate, "publish", lambda s, e=None: seen.append(s))
    monkeypatch.setattr(dictate.core, "set_hud", lambda *a, **k: None)
    d = dictate.Dictation()
    d.proc = type("P", (), {"terminate": lambda s: None,
                            "wait": lambda s, timeout=None: 0,
                            "poll": lambda s: 0})()
    d.up(50.0)
    assert seen == ["ready"]


def test_ready_does_not_cover_a_missing_permission(monkeypatch):
    from dictator import dictate
    seen = []
    monkeypatch.setattr(dictate, "publish",
                        lambda s, e=None: seen.append((s, e)))
    d = dictate.Dictation()
    d.blocked = "Dictator needs Accessibility."
    d._publish("ready")
    d._publish("listening")
    assert seen == [("needs_permission", "Dictator needs Accessibility."),
                    ("listening", None)]


def test_ready_while_english_is_still_arriving_says_downloading(tmp_path,
                                                                monkeypatch):
    from dictator import dictate, stt
    monkeypatch.setattr(stt, "MODEL_DIR", tmp_path)
    (tmp_path / (stt.SHIPPED[1][0] + ".part")).write_bytes(b"x" * 1000)
    dictate.publish("ready")
    assert core.read_status()["state"] == "downloading"
    for name, *_ in stt.SHIPPED[:2]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / (stt.SHIPPED[1][0] + ".part")).unlink()
    # Hinglish still arriving: English works, so it is ready.
    (tmp_path / (stt.SHIPPED[2][0] + ".part")).write_bytes(b"x")
    dictate.publish("ready")
    assert core.read_status()["state"] == "ready"


def _run_with_listener(monkeypatch, script):
    """dictate.run against a fake listener: a python that prints `script`'s
    lines and does whatever it does next. Nothing real is started."""
    from dictator import dictate
    monkeypatch.setattr(dictate.orbnative, "show", lambda: True)
    monkeypatch.setattr(dictate.orbnative, "hide", lambda: None)
    monkeypatch.setattr(dictate.warmup, "at_startup", lambda: None)
    monkeypatch.setattr(dictate.core, "set_hud", lambda *a, **k: None)
    monkeypatch.setattr(dictate.stt, "missing", lambda *a, **k: [])
    monkeypatch.setattr(
        dictate.hotkey, "listen",
        lambda *a, **k: subprocess.Popen(
            [sys.executable, "-c", script], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True))
    return dictate.run("fn", debug=False)


def test_a_listener_without_permission_leaves_needs_permission(monkeypatch):
    """It prints why on stderr and exits. That used to end as "paused", which
    the menu offers no fix for."""
    code = _run_with_listener(monkeypatch, (
        "import sys; print('READY', flush=True); "
        "sys.stderr.write('could not create an event tap.\\n'); sys.exit(1)"))
    st = core.read_status()
    assert st["state"] == "needs_permission" and "Accessibility" in st["error"]
    assert code == 1


def test_a_listener_that_dies_leaves_an_error(monkeypatch):
    code = _run_with_listener(monkeypatch,
                              "print('READY', flush=True); import sys; sys.exit(3)")
    st = core.read_status()
    assert st["state"] == "error" and st["error"] == "The key listener exited."
    assert code == 1


def test_a_listener_that_says_goodbye_leaves_paused(monkeypatch):
    from dictator import dictate
    code = _run_with_listener(monkeypatch,
                              "print('READY', flush=True); print('BYE', flush=True)")
    assert core.read_status()["state"] == "paused" and code == 0
    assert not dictate.loop_running()


def test_status_writers_on_several_threads_never_leave_half_a_file():
    """Three threads of the loop write status.json. With one temporary name
    per process they wrote into the same file and left invalid JSON."""
    import threading
    stop = threading.Event()
    bad = []

    def writer(state, error):
        while not stop.is_set():
            core.write_status(state, error=error)

    def reader():
        while not stop.is_set():
            try:
                json.loads(core.STATUS_FILE.read_text())
            except FileNotFoundError:
                pass
            except ValueError:
                bad.append(1)
    ts = [threading.Thread(target=writer, args=("ready", None)),
          threading.Thread(target=writer, args=("error", "x" * 150)),
          threading.Thread(target=reader)]
    for t in ts:
        t.start()
    time.sleep(0.5)
    stop.set()
    for t in ts:
        t.join()
    assert not bad
    json.loads(core.STATUS_FILE.read_text())
    assert [p.name for p in core.STATUS_FILE.parent.glob("status.json*")] == \
        ["status.json"]


def test_a_model_that_lands_is_published_without_a_key_press(tmp_path,
                                                              monkeypatch):
    """status.json is written on state changes, and a finished download is
    not one. The watcher writes the same state again with the new models."""
    import threading
    from dictator import dictate, stt
    monkeypatch.setattr(stt, "MODEL_DIR", tmp_path)
    for name, *_ in stt.SHIPPED[:2]:
        (tmp_path / name).write_bytes(b"x")
    dictate.publish("ready")
    turbo = stt.SHIPPED[2][0]
    assert core.read_status()["models"][turbo]["have"] is False
    stop = threading.Event()
    t = threading.Thread(target=dictate._watch_models, args=(stop, 0.05))
    t.start()
    (tmp_path / turbo).write_bytes(b"x")
    t.join(timeout=3)
    stop.set()
    assert not t.is_alive(), "it stops once every model is there"
    st = core.read_status()
    assert st["state"] == "ready" and st["models"][turbo]["have"] is True


def test_ready_waits_for_every_hold_still_transcribing(monkeypatch):
    """Two holds in flight: the first one finishing must not say ready while
    the second is still being transcribed."""
    from dictator import dictate
    seen = []
    monkeypatch.setattr(dictate, "publish", lambda s, e=None: seen.append(s))
    monkeypatch.setattr(dictate.core, "set_hud", lambda *a, **k: None)
    monkeypatch.setattr(dictate.threading, "Thread",
                        lambda target, args=(), daemon=None: type(
                            "T", (), {"start": lambda self: None})())
    d = dictate.Dictation()
    monkeypatch.setattr(d, "_deliver", lambda *a, **k: None)
    for _ in range(2):
        d.proc = type("P", (), {"terminate": lambda s: None,
                                "wait": lambda s, timeout=None: 0,
                                "poll": lambda s: 0})()
        d.up(900.0)
    d._finish("/tmp/a.wav", "Terminal")
    assert seen[-1] == "transcribing"
    d._finish("/tmp/b.wav", "Terminal")
    assert seen[-1] == "ready"


# ---- what the app's pages read --------------------------------------------------

def _said(text, at, secs=0.0):
    from dictator import history
    row = history.add(heard=text, shown=text, secs=secs)
    con = history._db()
    try:
        con.execute("UPDATE said SET at=? WHERE id=?", (at, row))
        con.commit()
    finally:
        con.close()
    return row


def _noon(days_ago: int) -> float:
    d = date.today() - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, 12).timestamp()


def test_stats_with_nothing_said():
    assert views.stats() == {"words": 0, "wpm": None, "streak_days": 0,
                             "saved_secs": None, "today_words": 0,
                             "today_saved_secs": None}


def test_words_per_minute_is_unknown_without_durations():
    _said("deploy the thing now", _noon(0))
    assert views.stats() == {"words": 4, "wpm": None, "streak_days": 1,
                             "saved_secs": None, "today_words": 4,
                             "today_saved_secs": None}


def test_words_per_minute_counts_only_timed_rows():
    _said("one two three four five six", _noon(0), secs=3.0)
    _said("no duration here", _noon(0))
    got = views.stats()
    assert got["words"] == 9
    assert got["wpm"] == 120.0


def test_time_saved_is_typing_time_minus_speaking_time():
    # 40 words typed at 40 a minute is 60 s; said in 15 s, 45 s saved.
    _said(" ".join(["word"] * 40), _noon(0), secs=15.0)
    # Yesterday: 20 words is 30 s to type, said in 10 s, 20 s saved.
    _said(" ".join(["word"] * 20), _noon(1), secs=10.0)
    # No duration: not counted either way.
    _said("no duration here", _noon(0))
    got = views.stats()
    assert got["saved_secs"] == 65
    assert got["today_saved_secs"] == 45
    assert got["today_words"] == 43


def test_time_saved_never_goes_below_zero():
    # Two words said in ten seconds: slower than typing them.
    _said("um okay", _noon(0), secs=10.0)
    got = views.stats()
    assert got["saved_secs"] == 0
    assert got["today_saved_secs"] == 0


def test_today_counts_only_today():
    _said("yesterday only words", _noon(1), secs=1.0)
    got = views.stats()
    assert got["today_words"] == 0
    assert got["today_saved_secs"] is None


def test_a_streak_ending_yesterday_is_still_alive():
    for ago in (1, 2, 3, 5):
        _said("hello there", _noon(ago))
    assert views.stats()["streak_days"] == 3


def test_a_streak_with_a_gap_before_yesterday_is_over():
    _said("hello there", _noon(2))
    assert views.stats()["streak_days"] == 0


def test_history_for_one_day_is_that_day_only():
    _said("yesterday's line", _noon(1))
    _said("today's line", _noon(0))
    day = (date.today() - timedelta(days=1)).isoformat()
    got = views.history(day=day)
    assert got["day"] == day
    assert [r["text"] for r in got["items"]] == ["yesterday's line"]
    assert views.history(day="8 Oct")["items"] == []


def test_history_without_a_day_is_the_newest_first():
    _said("older", _noon(1))
    _said("newer", _noon(0))
    assert [r["text"] for r in views.history(limit=5)["items"]] == \
        ["newer", "older"]


def test_snippets_and_words_as_data():
    from dictator import snippets, vocab
    assert snippets.shared().add("my work email", "a@b.example",
                                 force=True)["ok"]
    assert views.snippets()["snippets"][0]["trigger"] == "my work email"
    assert views.snippets()["snippets"][0]["text"] == "a@b.example"
    vocab.shared().add("Amandra", heard="a man dra")
    got = views.words()
    assert [w["term"] for w in got["words"]] == ["Amandra"]
    assert "a man dra" in got["words"][0]["heard"]
    assert got["pending"] == []


def _cli(tmp_path, *args):
    env = dict(os.environ, DICTATOR_STATE=str(tmp_path / "state"))
    env.pop("DICTATOR_BUNDLE", None)
    out = subprocess.run([sys.executable, str(REPO / "bin" / "dictator"), *args],
                         cwd=str(tmp_path), env=env, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("args,keys", [
    (("stats", "--json"), {"words", "wpm", "streak_days", "saved_secs",
                            "today_words", "today_saved_secs"}),
    (("words", "--json"), {"words", "pending"}),
    (("snippet", "--json"), {"snippets"}),
    (("snippets", "--json"), {"snippets"}),
    (("history", "--json"), {"day", "items"}),
    (("history", "--json", "--day", "2026-10-08"), {"day", "items"}),
])
def test_the_cli_prints_one_json_document(tmp_path, args, keys):
    """stdout is exactly one JSON object and nothing else, against an empty
    state directory of its own."""
    assert set(_cli(tmp_path, *args)) == keys


def test_status_carries_the_loops_last_word():
    """`running` and `login_item` are added by the CLI from launchd, which a
    test must not ask, so this checks the rest."""
    assert views.status()["status"] is None
    core.write_status("listening")
    got = views.status()
    assert got["mode"] == "repo install" and got["bundle"] is None
    assert got["status"]["state"] == "listening"
    json.dumps(got)


@pytest.mark.parametrize("name,args", [
    ("stats", ("stats", "--json")),
    ("words", ("words", "--json")),
    ("snippet", ("snippet", "--json")),
    ("history", ("history", "--json")),
])
def test_the_apps_fixtures_have_the_clis_shape(tmp_path, name, args):
    """DICTATOR_FAKE=1 draws the app from native/app/Fixtures. A fixture with
    a shape the CLI never prints makes a window that looks right and is
    wrong, so each one has the same top-level keys as the real command."""
    fixture = json.loads((REPO / "native" / "app" / "Fixtures"
                          / f"{name}.json").read_text())
    assert set(fixture) == set(_cli(tmp_path, *args))
    if name == "history":
        assert set(fixture["items"][0]) == set(views._row({}))


def test_the_last_result_fixture_has_the_loops_shape():
    """The "Try it" card and Home's time-to-paste read last.json, and fake
    mode reads Fixtures/last.json instead. Same rule as the other fixtures:
    the keys the loop writes, no more and no fewer."""
    assert core.write_last("yaar ye test kar ke dekho", 640, "whisper", "Terminal", True)
    written = json.loads(core.LAST_FILE.read_text())
    fixture = json.loads((REPO / "native" / "app" / "Fixtures"
                          / "last.json").read_text())
    assert set(fixture) == set(written)


def test_the_fixtures_ship_inside_the_app():
    """Fake mode reads its fixtures from the bundle. It used to fall back to
    the source path compiled into the binary, the maintainer's Desktop, which
    made macOS ask a user for Desktop access."""
    script = (REPO / "tools" / "build_dmg.sh").read_text()
    assert 'native/app/Fixtures" "$C/Resources/Fixtures"' in script
    swift = "".join(f.read_text() for f in (REPO / "native" / "app").glob("*.swift"))
    assert "fileURLWithPath: #filePath" not in swift


def test_status_inside_the_app_does_not_ask_launchd(tmp_path):
    """The app's loop is its own child and its login item is SMAppService's,
    so launchd knows nothing about either. Running comes from the loop's pid
    file; login_item is left to the app."""
    app = _fake_bundle(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    env = dict(os.environ, DICTATOR_STATE=str(state), DICTATOR_BUNDLE=str(app))

    def status(*args):
        out = subprocess.run([sys.executable, str(REPO / "bin" / "dictator"),
                              "status", *args], cwd=str(tmp_path), env=env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return out.stdout

    got = json.loads(status("--json"))
    assert got["running"] is False and got["login_item"] is None
    (state / "dictate.pid").write_text(str(os.getpid()))
    assert json.loads(status("--json"))["running"] is True
    assert "dictator on" not in status()
