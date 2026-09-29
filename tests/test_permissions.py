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
import sqlite3
import subprocess
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
    src = (Path(__file__).resolve().parent.parent / "bin" / "dictator").read_text()
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
