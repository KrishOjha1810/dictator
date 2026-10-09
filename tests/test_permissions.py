"""The permission state that looks exactly like a working one.

macOS draws the Accessibility list from a TCC row and decides trust from a
code requirement stored beside it. Change the app's signature and the row
survives with the old requirement: the checkbox stays ticked, the app stays
untrusted, and because a row already exists the system never prompts again.
The user sees a switch that is already on and has nothing left to click.

This was live on the machine these tests were written on. The row said

    certificate leaf = H"cbd3aabec79d29dcfc329c1bbba154709b13462a"

and the bundle said

    certificate leaf = H"8501b12ce31fe51f7ee209340e355c18398a0d23"

while `dictator doctor` reported "app identity survives a rebuild: ok" and
"running now: ok" and said nothing about it at all.

So every test here is written for the BROKEN state first. The precedent is
in this repo: doctor once had an off-by-one that passed the exact condition it
existed to report, which sent the user away from the only place the answer
was. A check that passes the broken case is worse than no check.
"""
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from unittest import mock

import pytest

from dictator import always, tcc

OURS = 'identifier "com.dictator.dictation" and certificate leaf = ' \
       'H"1111111111111111111111111111111111111111"'
SOMEONE_ELSES = 'identifier "com.dictator.dictation" and certificate leaf = ' \
                'H"2222222222222222222222222222222222222222"'


def _blob(requirement: str) -> bytes:
    """The stored requirement, in the form TCC actually keeps it."""
    out = Path(subprocess.run(["mktemp"], capture_output=True,
                              text=True).stdout.strip())
    r = subprocess.run(["/usr/bin/csreq", f"-r={requirement}", "-b", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = out.read_bytes()
    out.unlink(missing_ok=True)
    return data


def _db(path: Path, rows) -> Path:
    """A TCC database with the columns this code reads, and the real names."""
    path.unlink(missing_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("create table access (service text not null, "
                "client text not null, client_type integer not null, "
                "auth_value integer not null, auth_reason integer not null, "
                "auth_version integer not null, csreq blob)")
    for service, client, auth, req in rows:
        con.execute("insert into access values (?,?,0,?,2,1,?)",
                    (service, client, auth, _blob(req) if req else None))
    con.commit()
    con.close()
    return path


@pytest.fixture
def pretend(tmp_path, monkeypatch):
    """Point the module at a database we made, not the machine's."""
    def use(rows, readable=True):
        db = _db(tmp_path / "TCC.db", rows) if readable else tmp_path / "gone.db"
        monkeypatch.setattr(tcc, "SERVICES", dict(
            tcc.SERVICES, **{"accessibility": (db, "kTCCServiceAccessibility")}))
        return db
    return use


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A stand-in bundle whose designated requirement we control."""
    bundle = tmp_path / "Dictator.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "MacOS" / "Dictator").write_bytes(b"\x00")
    monkeypatch.setattr(tcc, "satisfies",
                        lambda a, req: req in ("", OURS))
    return bundle


# ---------------------------------------------------------------------------
# The broken state, first.

def test_a_ticked_box_for_another_signature_is_not_granted(pretend, app):
    """THE bug. auth_value 2 means the switch in System Settings is on."""
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, SOMEONE_ELSES)])
    info = tcc.state("accessibility", app)
    assert info["state"] == tcc.STALE, info
    assert info["ticked"] is True, "the user really can see a tick"
    assert tcc.verdict(info)[0] == "bad", \
        "doctor would pass the exact state it exists to report"


def test_the_stale_case_names_the_signature_on_both_sides(pretend, app):
    """The difference the user cannot see is the only evidence there is."""
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, SOMEONE_ELSES)])
    info = tcc.state("accessibility", app)
    assert "2222222222" in info["held_by"], info["held_by"]


def test_the_stale_advice_names_the_minus_button(pretend, app):
    """Toggling cannot fix it, so the instructions must not say to toggle."""
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, SOMEONE_ELSES)])
    text = tcc.advice(tcc.state("accessibility", app)).lower()
    assert "minus" in text, text
    assert "remove" in text, text
    assert "privacy & security" in text, text
    assert "will not fix it" in text, \
        "nothing warns that switching it off and on is a dead end"


def test_never_granted_is_a_different_answer_with_different_steps(pretend, app):
    """Two states that look identical from inside the app and need opposite
    instructions: one is a switch to flip, the other is a row to delete."""
    pretend([])
    missing = tcc.state("accessibility", app)
    assert missing["state"] == tcc.MISSING
    assert missing["ticked"] is False

    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, SOMEONE_ELSES)])
    stale = tcc.state("accessibility", app)

    assert tcc.advice(missing) != tcc.advice(stale)
    assert "minus" not in tcc.advice(missing).lower(), \
        "telling a first-time user to delete an entry that is not there"
    assert "plus" in tcc.advice(missing).lower(), \
        "nothing says how to add it when it is not in the list at all"


def test_a_switched_off_row_is_not_confused_with_a_stale_one(pretend, app):
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 0, OURS)])
    info = tcc.state("accessibility", app)
    assert info["state"] == tcc.DENIED, info
    assert info["ticked"] is False
    assert "minus" not in tcc.advice(info).lower()


def test_an_unreadable_database_is_never_reported_as_fine(pretend, app):
    """Reading TCC needs Full Disk Access, which most terminals do not have.

    "I could not look" is a third answer. Folding it into "ok" would rebuild
    the off-by-one in a new shape, and folding it into "broken" would fail
    every healthy machine."""
    pretend([], readable=False)
    info = tcc.state("accessibility", app)
    assert info["state"] == tcc.UNREADABLE
    assert info["readable"] is False
    assert tcc.verdict(info)[0] == "unknown", "passed a state it cannot see"

    # Unless the app itself has said it is not trusted, which is not a guess.
    assert tcc.verdict(info, {"trusted": False})[0] == "bad"
    assert tcc.verdict(info, {"trusted": True})[0] == "unknown"


def test_the_unreadable_advice_still_tells_them_how_to_tell(pretend, app):
    pretend([], readable=False)
    text = tcc.advice(tcc.state("accessibility", app)).lower()
    assert "already on" in text, \
        "no way for the user to spot the stale case by eye"
    assert "minus" in text


def test_a_matching_grant_is_granted(pretend, app):
    """The healthy state, so the check cannot pass by always failing."""
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, OURS)])
    info = tcc.state("accessibility", app)
    assert info["state"] == tcc.GRANTED, info
    assert tcc.verdict(info) == ("ok", tcc.verdict(info)[1])
    assert tcc.advice(info) == ""


def test_an_old_row_next_to_a_good_one_is_still_granted(pretend, app):
    """macOS can keep both. Any row this build satisfies is a working grant,
    so finding the stale one first must not condemn the app."""
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, SOMEONE_ELSES),
             ("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, OURS)])
    assert tcc.state("accessibility", app)["state"] == tcc.GRANTED


def test_a_missing_app_is_not_a_permission_problem(pretend, tmp_path):
    pretend([])
    info = tcc.state("accessibility", tmp_path / "nothing.app")
    assert info["state"] == tcc.NO_APP
    assert tcc.verdict(info)[0] == "unknown"


# ---------------------------------------------------------------------------
# Comparing signatures, rather than comparing strings.

def test_the_requirement_is_tested_with_codesign_not_string_equality():
    """TCC asks codesign whether the code satisfies the stored requirement.
    Asking the same question the same way is the only way to stay right about
    requirements written in a form we do not emit ourselves."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(tcc.satisfies).lstrip())
    body = " ".join(n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str))
    assert "codesign" in body, "back to comparing two hashes as text"


def test_an_unanswerable_requirement_check_leaves_the_grant_alone():
    """Calling a working grant broken sends the user to delete it, which costs
    them a permission that was fine. Errors must fall the safe way."""
    with mock.patch("subprocess.run", side_effect=OSError("boom")):
        assert tcc.satisfies("/nowhere", OURS) is True


@pytest.mark.skipif(not always.APP.exists(), reason="app not built here")
def test_the_real_bundle_satisfies_its_own_requirement():
    """End to end against the real thing, so a change in how codesign is
    invoked cannot pass the mocked tests and fail on a machine."""
    from dictator import signing
    req = signing.requirement(always.APP)
    assert tcc.satisfies(always.APP, req), req
    wrong = req.replace('H"', 'H"00')[:-1] + '"' if 'H"' in req else ""
    if wrong:
        assert not tcc.satisfies(always.APP, wrong), \
            "any requirement at all is being accepted"


# ---------------------------------------------------------------------------
# Saying it where the person is looking.

def _swift() -> str:
    return (Path(__file__).resolve().parent.parent
            / "native" / "app" / "main.swift").read_text()


def test_the_waiting_listener_does_more_than_log_one_line():
    """It waited forever and wrote "waiting for Accessibility" to a file
    nobody had been told to open. From outside, dictation had simply died."""
    src = _swift()
    assert "permission.json" in src, \
        "nothing records that the app is stuck where another process can read it"
    assert "permissions\", \"--explain\"" in src, \
        "the app no longer asks WHY it is not trusted, so it cannot say"
    assert "display notification" in src, "nothing reaches the user's screen"


def test_the_listener_recovers_without_being_restarted():
    """A permission granted while it waits has to be picked up on its own.
    The child is spawned fresh, which is the only kind of process macOS
    honours a new grant for, so there is nothing a restart would add."""
    src = _swift()
    after = src.split("if AXIsProcessTrusted()", 1)[1][:600]
    assert "runDictation()" in after, \
        "it notices the grant and then does not start dictation"


def test_the_app_never_rebuilds_itself_to_explain_itself():
    """Rebuilding changes the signature, which is what causes this state.
    The path the waiting app calls must not be able to trigger one."""
    src = (Path(__file__).resolve().parent.parent / "dictator" / "cli.py").read_text()
    body = src.split("def permissions(", 1)[1].split("\n\ndef ", 1)[0]
    explain = body.split("if explain:", 1)[1].split("\n    if not app.exists()", 1)[0]
    assert "build_app" not in explain, \
        "the waiting app would rebuild the bundle and revoke its own grant"


def test_dictator_on_says_it_in_the_terminal():
    """A log file is not where somebody who just typed a command is looking."""
    import inspect
    src = inspect.getsource(always.on)
    assert "_permission_warning" in src, \
        "`dictator on` prints a cheerful paragraph over a dead listener again"


def test_the_warning_is_silent_when_everything_is_fine(monkeypatch):
    monkeypatch.setattr(tcc, "state", lambda *a, **k: {"state": tcc.GRANTED})
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert always._permission_warning() == ""


def test_the_warning_speaks_up_when_the_tick_is_stale(monkeypatch, app, pretend):
    pretend([("kTCCServiceAccessibility", tcc.BUNDLE_ID, 2, SOMEONE_ELSES)])
    real = tcc.state
    monkeypatch.setattr(tcc, "state", lambda *a, **k: real("accessibility", app))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    out = always._permission_warning()
    assert "minus" in out.lower(), out


# ---------------------------------------------------------------------------
# Clearing a permission is the most expensive thing this program can do.

def _cli():
    import importlib.util
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).resolve().parent.parent / "bin" / "dictator"
    # By full loader, because the command has no .py on the end and
    # spec_from_file_location decides what to do from the extension.
    loader = SourceFileLoader("dictator_cli", str(path))
    spec = importlib.util.spec_from_loader("dictator_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_a_working_microphone_grant_is_not_cleared_with_a_stale_one():
    """An earlier version reset Accessibility, Microphone and ListenEvent
    together on a guess, so recovering from a stale Accessibility entry threw
    away a microphone permission that was working."""
    cli = _cli()
    calls = []

    def fake(args, **kw):
        calls.append(args)
        return mock.Mock(returncode=0, stdout="", stderr="")

    states = {"accessibility": tcc.STALE, "microphone": tcc.GRANTED,
              "input monitoring": tcc.GRANTED}
    with mock.patch.object(cli.subprocess, "run", side_effect=fake), \
         mock.patch.object(tcc, "state",
                           side_effect=lambda s="accessibility", app=None:
                           {"state": states[s], "service": s}):
        done = cli._forget({"service": "accessibility", "state": tcc.STALE})

    assert done == ["Accessibility"], done
    flat = " ".join(" ".join(c) for c in calls)
    assert "Microphone" not in flat, \
        "it cleared a microphone grant that was working"


def test_nothing_is_cleared_behind_somebody_back():
    """The app bundle calls into this with no terminal attached. It must never
    be able to delete a permission the user granted without being asked."""
    cli = _cli()
    with mock.patch.object(cli.sys.stdin, "isatty", return_value=False):
        assert cli._asked_to_clear() is False


# ---- what the listener saw, and for how long it stays true -------------------
#
# The app writes what it can see of its own trust into permission.json, and
# that file is the only signal left on a machine whose TCC databases cannot be
# read. Neither `waiting()` nor `stuck()` had a test, which is uncomfortable
# for the pair of functions whose entire job is answering "is somebody stuck
# right now".


def _wrote(**payload):
    import json
    tcc.WAITING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tcc.WAITING_FILE.write_text(json.dumps(payload))


def test_no_record_at_all_is_not_a_problem():
    assert tcc.waiting() == {}
    assert tcc.stuck() is False


def test_a_live_listener_waiting_for_a_permission_is_reported():
    _wrote(trusted=False, at=time.time(), pid=os.getpid())
    assert tcc.stuck() is True


def test_a_listener_that_was_stopped_while_waiting_is_not_still_waiting():
    """The claim is about right now. Stopping the listener mid wait used to
    leave doctor reporting a permission problem forever, and `dictator on`
    printing the whole TCC diagnosis at somebody with nothing wrong."""
    _wrote(trusted=False, at=time.time(), pid=_a_dead_pid())
    assert tcc.waiting() == {}
    assert tcc.stuck() is False


def test_trusted_never_expires():
    """It is written once, on the way past the permission, and never again. An
    age check would throw away the only good news in the file."""
    _wrote(trusted=True, at=time.time() - 30 * 86400, pid=_a_dead_pid())
    assert tcc.waiting().get("trusted") is True
    assert tcc.stuck() is False


def test_an_older_record_without_a_pid_falls_back_to_its_age():
    _wrote(trusted=False, at=time.time())
    assert tcc.stuck() is True
    _wrote(trusted=False, at=time.time() - tcc.STALE_AFTER - 60)
    assert tcc.stuck() is False


def test_a_damaged_record_is_not_read_as_either_answer():
    tcc.WAITING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tcc.WAITING_FILE.write_text("{not json")
    assert tcc.waiting() == {}
    tcc.WAITING_FILE.write_text('["not a dict"]')
    assert tcc.waiting() == {}
    assert tcc.stuck() is False


def _a_dead_pid() -> int:
    """A pid that has certainly exited: one we started and reaped ourselves."""
    p = subprocess.Popen(["/usr/bin/true"])
    p.wait()
    return p.pid


# ---- which answer wins when two of them disagree ------------------------------
#
# `verdict` has two sources: what macOS remembers about an app bundle on disk,
# and what the running listener says about itself. They can disagree, and the
# rule is not symmetric.


def _state(s):
    return {"service": "accessibility", "app": "/x", "state": s,
            "ticked": None, "held_by": "", "wanted": "", "readable": True}


def test_a_running_listener_saying_no_beats_a_database_saying_yes():
    """The bug this function's own docstring is about, in a new shape. A grant
    can match the build on disk while the process actually holding the key is
    an older copy that macOS does not trust, and reporting that as fine sends
    the user away from the only place the answer was."""
    how, detail = tcc.verdict(_state(tcc.GRANTED), {"trusted": False})
    assert how == "bad", "the one direct measurement was ignored"
    assert "not this build" in detail


def test_a_listener_saying_yes_never_excuses_a_stale_tick():
    """Not symmetric, and this is the half that must not be 'fixed'. A process
    launched from a terminal that has the grant reports itself trusted even
    when its own entry is stale, which is why the broken state could never be
    reproduced from a shell."""
    assert tcc.verdict(_state(tcc.STALE), {"trusted": True})[0] == "bad"
    assert tcc.verdict(_state(tcc.DENIED), {"trusted": True})[0] == "bad"
    assert tcc.verdict(_state(tcc.UNREADABLE), {"trusted": True})[0] == "unknown"


def test_a_dead_listener_cannot_make_a_working_grant_look_broken():
    """The two halves together. A listener stopped while it was waiting leaves
    a record saying NOT trusted, and without `waiting()` dropping it, every
    `doctor` after that would report a permission problem on a machine whose
    permission is fine."""
    _wrote(trusted=False, at=time.time(), pid=_a_dead_pid())
    assert tcc.verdict(_state(tcc.GRANTED), tcc.waiting())[0] == "ok"
    _wrote(trusted=False, at=time.time(), pid=os.getpid())
    assert tcc.verdict(_state(tcc.GRANTED), tcc.waiting())[0] == "bad"


def test_no_listener_record_at_all_changes_nothing():
    for state, expected in ((tcc.GRANTED, "ok"), (tcc.NO_APP, "unknown"),
                            (tcc.UNREADABLE, "unknown"), (tcc.STALE, "bad"),
                            (tcc.DENIED, "bad"), (tcc.MISSING, "bad")):
        assert tcc.verdict(_state(state))[0] == expected, state
        assert tcc.verdict(_state(state), {})[0] == expected, state


def _cli():
    # The CLI body lives in dictator.cli now; bin/dictator is just a launcher.
    import importlib
    return importlib.import_module("dictator.cli")


def test_a_refused_tccutil_is_reported_rather_than_swallowed(monkeypatch):
    """`tccutil` refusing used to leave `cleared` empty and print nothing, and
    the caller went on to say "Restarted, so it can ask again". That is untrue:
    a row that is still there is exactly the reason macOS will not ask again,
    so the one sentence somebody reads sends them away believing it is fixed.
    """
    cli = _cli()

    class Refused:
        returncode = 1
        stdout = ""
        stderr = "tccutil: Failed to reset Accessibility"

    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: Refused())
    from dictator import tcc
    got = cli._forget({"service": "accessibility", "state": tcc.STALE})
    assert got == [], got
    assert cli._forget.refused, "the refusal was swallowed"
    assert "Failed to reset" in cli._forget.refused[0][1]


def test_a_successful_reset_records_no_refusal(monkeypatch):
    cli = _cli()

    class Done:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: Done())
    from dictator import tcc
    got = cli._forget({"service": "accessibility", "state": tcc.STALE})
    assert got, got
    assert cli._forget.refused == []


def test_two_accounts_do_not_share_one_permission_row(monkeypatch, tmp_path):
    """The bug this fixes, stated as a test.

    Accessibility lives in the SYSTEM TCC database, which holds one row per
    bundle identifier. Each account builds and signs its own app with its own
    self-signed certificate, so two accounts sharing an identifier share a row
    that can pin only one of them. Whichever granted last wins, the other is
    silently untrusted with a tick showing in System Settings, and granting it
    again in the broken one simply flips the breakage back.

    Measured on a real two-account Mac: the same row read
    `certificate leaf = H"8501b12c"` from one account and `H"cbd3aabe"` from
    the other.
    """
    from dictator import core

    mine = core.bundle_id()
    monkeypatch.setattr(core.Path, "home",
                        classmethod(lambda cls: tmp_path / "somebody-else"))
    (tmp_path / "somebody-else").mkdir(parents=True, exist_ok=True)
    theirs = core.bundle_id()
    assert mine != theirs, "two accounts would fight over one TCC row"
    assert mine.startswith("com.dictator.dictation.")
    assert theirs.startswith("com.dictator.dictation.")


def test_the_identifier_carries_no_account_name():
    """It is a hash of the home directory rather than the user's name, so no
    account name is written into a file or shown in a requirement string."""
    import getpass

    from dictator import core

    got = core.bundle_id()
    assert getpass.getuser().lower() not in got.lower()
    assert core.Path.home().name.lower() not in got.lower()


def test_the_meeting_app_gets_its_own_identifier_too():
    """Screen Recording is system-wide as well, so the same collision."""
    from dictator import core
    assert core.bundle_id("com.dictator.meeting") != core.bundle_id()


def test_rows_from_the_shared_identifier_are_found(monkeypatch):
    """After the identifier became per account, a row under the old shared one
    belongs to no app that exists, and it still shows in System Settings under
    the SAME NAME as the real entry. Switching on the Dictator you can see then
    switches on nothing, which reads exactly like the fix having failed."""
    from dictator import tcc

    def rows(service, client=tcc.BUNDLE_ID):
        return [("row",)] if client == "com.dictator.dictation" else []

    monkeypatch.setattr(tcc, "_rows", rows)
    got = tcc.orphans()
    assert got, "the leftover row was not found"
    assert all(old == "com.dictator.dictation" for _, old in got)
    assert all(old != tcc.BUNDLE_ID for _, old in got)


def test_nothing_left_over_is_an_empty_list_not_a_failure(monkeypatch):
    from dictator import tcc
    monkeypatch.setattr(tcc, "_rows", lambda service, client=None: [])
    assert tcc.orphans() == []


def test_databases_it_cannot_read_answer_none_rather_than_nothing(monkeypatch):
    """"I looked and there is nothing" and "I could not look" are different
    answers, and reporting the second as the first is how this module's own
    docstring says a doctor comes to pass the state it exists to report."""
    from dictator import tcc
    monkeypatch.setattr(tcc, "_rows", lambda service, client=None: None)
    assert tcc.orphans() is None


def test_a_running_listener_is_not_proof_that_macos_trusts_it():
    """An untrusted listener starts, finds it cannot tap the key, and sits
    there. So a process existing is not the permission working, and the
    watcher used to declare "Granted. Hold fn anywhere and talk." on exactly
    that.

    Told that, a user with a DENIED row spent an hour switching on the two
    OTHER Dictator entries in the list, because the tool had said the
    permission was fine and the problem must be elsewhere."""
    src = (Path(__file__).resolve().parent.parent / "dictator" / "cli.py").read_text()
    watch = src[src.index("Watching. This updates itself"):]
    watch = watch[:watch.index("def ") if "def " in watch else len(watch)]
    assert "if live and trusted:" in watch, \
        "success is still declared on the listener alone"
    assert "macOS trusts it" in watch, \
        "the progress line does not separate running from trusted"
