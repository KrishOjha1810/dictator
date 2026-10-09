"""Dictator must work on a machine that has never heard of voicebridge.

This is the whole point of the product being separate, and it is the kind of
thing that is true on the day it is split and quietly false a month later, so
it is asserted rather than assumed.
"""
import ast
import plistlib
from pathlib import Path

import pytest

from dictator import always, stt

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dictator"


def test_no_module_imports_voicebridge():
    """Nothing here may reach back into the repo it came from."""
    offenders = []
    for f in sorted(PKG.glob("*.py")):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for n in names:
                if n.split(".")[0] in ("vb", "voicebridge"):
                    offenders.append(f"{f.name}:{node.lineno} {n}")
    assert not offenders, offenders


def test_the_app_runs_our_own_command():
    """The bundle must launch this install, not whichever one it finds.

    main.swift used to hardcode ~/voicebridge/bin/vb, so a freshly built
    Dictator.app looked correct in every way and ran a different product's
    dictation. Nothing about that is visible from the outside: the key works,
    the words appear, and the code being executed is not the code you changed.
    """
    swift = (ROOT / "native" / "app" / "main.swift").read_text()
    assert "voicebridge" not in swift, "the app still refers to voicebridge"
    assert "DictatorCLI" in swift, "the app no longer reads its own CLI path"


@pytest.mark.skipif(not always.APP.exists(), reason="app not built here")
def test_built_bundle_points_at_a_real_checkout():
    """The bundle must run the code it was built from.

    Checked as "a real checkout" rather than "this one" because there is only
    one Dictator.app per machine and a second clone does not own it. Insisting
    on this one made a fresh clone fail its own test suite for no reason the
    person running it could act on."""
    info = plistlib.loads(
        (always.APP / "Contents" / "Info.plist").read_bytes())
    cli = Path(info["DictatorCLI"])
    assert cli.exists(), f"the app runs {cli}, which is not there"
    assert cli.name == "dictator", cli
    assert (cli.parent.parent / "dictator" / "stt.py").exists(), \
        f"{cli} is not inside a dictator checkout"
    assert ".dictator" in info["DictatorLog"], info["DictatorLog"]


def test_state_is_our_own_directory():
    """dictator keeps its files in ~/.dictator and not in a sibling project's
    directory. Asked of the resolver rather than grepped out of the source,
    which is why this broke the first time the line was refactored: a test that
    reads source text fails on a rewording and passes on a rewrite."""
    import os

    from dictator import core
    assert core.state_dir("") == Path(os.path.expanduser("~/.dictator"))
    assert core.state_dir(None) == Path(os.path.expanduser("~/.dictator")) \
        or os.environ.get("DICTATOR_STATE")


def test_models_are_found_not_redownloaded(tmp_path, monkeypatch):
    """A machine that already has the models must not fetch six gigabytes.

    They are shared with any other whisper install rather than copied, because
    the turbo model alone is 1.6GB and duplicating it to look tidy would be a
    worse experience than sharing it."""
    monkeypatch.setenv("DICTATOR_MODELS", str(tmp_path / "forced"))
    assert stt._resolve_model_dir() == tmp_path / "forced"

    monkeypatch.delenv("DICTATOR_MODELS")
    monkeypatch.setattr(stt.core, "STATE_DIR", tmp_path)
    own = tmp_path / "models"
    own.mkdir()
    (own / "ggml-small.bin").write_bytes(b"x")
    assert stt._resolve_model_dir() == own, "our own models were ignored"


def test_no_second_key_listener_is_flagged():
    """Two hold-to-talk listeners paste everything twice, and the symptom
    reads as a stutter rather than as two programs running."""
    cli = (ROOT / "dictator" / "cli.py").read_text()
    assert "com.voicebridge.dictate.plist" in cli, \
        "doctor no longer warns about another dictation key"


def test_the_mac_helpers_can_actually_log():
    """These call core.log in their error paths, and the module was extracted
    without the import, so any failing osascript raised NameError instead of
    recording why. An error handler that itself crashes is worse than none."""
    import ast
    src = (PKG / "mac.py").read_text()
    tree = ast.parse(src)
    uses_core = any(
        isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
        and n.value.id == "core" for n in ast.walk(tree))
    if not uses_core:
        return
    imported = any(
        (isinstance(n, ast.ImportFrom) and any(a.name == "core" for a in n.names))
        or (isinstance(n, ast.Import) and any("core" in a.name for a in n.names))
        for n in ast.walk(tree))
    assert imported, "mac.py calls core.log without importing core"


def test_the_one_outside_dependency_is_installed_and_checked():
    """jellyfish does the phonetic matching, and it is not stdlib.

    Without it vocab.py sets it to None and the whole vocabulary and learning
    feature does nothing at all, with no error anywhere. The installer never
    installed it and doctor never looked for it, so on anyone else's machine
    the feature would simply have been absent while everything reported fine.
    """
    assert "jellyfish" in (ROOT / "install.sh").read_text(), \
        "the installer does not install it"
    assert "jellyfish" in (ROOT / "dictator" / "cli.py").read_text(), \
        "doctor does not check for it"


def test_nothing_else_came_in_from_outside():
    """One outside dependency is a packaging problem. Five is a different
    product, and this is where that starts."""
    import ast, sys
    std = getattr(sys, "stdlib_module_names", set())
    if not std:
        return
    outside = set()
    for f in sorted(PKG.glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            outside |= {n for n in names if n and n not in std and n != "dictator"}
    assert outside <= {"jellyfish"}, f"new outside dependencies: {outside}"


def test_the_installer_and_the_code_agree_on_the_models():
    """They named different files once: doctor reported ggml-base.bin missing
    while the installer only ever downloaded ggml-large-v3-turbo.bin, so the
    user was sent looking for something that was never going to arrive."""
    from dictator import stt
    script = (ROOT / "install.sh").read_text()
    for name, mb, why, essential in stt.SHIPPED:
        assert name in script, f"the installer never downloads {name}"


def test_english_does_not_wait_for_the_multilingual_model():
    """1.5GB before the first word is ten minutes of progress bar before the
    product has proved it does anything. English needs 712MB of it."""
    from dictator import stt
    essential = [m[0] for m in stt.SHIPPED if m[3]]
    assert "ggml-large-v3-turbo.bin" not in essential
    assert sum(m[1] for m in stt.SHIPPED if m[3]) < 800
    assert "nohup" in (ROOT / "install.sh").read_text(), \
        "the big model is no longer fetched in the background"


def test_the_installer_counts_its_own_steps():
    """It said "1/4" at the top and "6/6" at the bottom, because steps were
    added in the middle and the numbers were not. Small, but it is the first
    thing a new user reads and it makes the whole thing look unmaintained."""
    import re
    steps = re.findall(r'step "(\d+)/(\d+)', (ROOT / "install.sh").read_text())
    assert steps, "no numbered steps found"
    total = len(steps)
    assert [(str(i), str(total)) for i in range(1, total + 1)] == steps, steps


def test_the_suite_does_not_write_into_the_benchmark_corpus():
    """It did. The capture flag and the corpus path are module constants
    computed from STATE_DIR at import, so redirecting STATE_DIR in the fixture
    missed them, and a test run filled the user's corpus with one-byte files
    that look like recordings. Third time this exact shape has bitten."""
    conftest = (ROOT / "tests" / "conftest.py").read_text()
    for attr in ("CORPUS", "CAPTURE_FLAG"):
        assert attr in conftest, f"{attr} is not redirected for tests"


def test_starting_stops_whatever_was_already_running():
    """It did not, and it looked like it did. Running the installer twice left
    two listeners watching the same key, so every hold was handled twice and
    every sentence pasted twice. The symptom reads as a bug in the paste path,
    which is where the time goes looking for it."""
    import ast, inspect
    from dictator import always
    src = inspect.getsource(always.on)
    assert "_stop_everything()" in src, "on() is not idempotent again"
    # And the cleanup must be scoped to this user: another account on the same
    # Mac runs its own copy and killing theirs is not ours to do.
    assert '"-u", me' in inspect.getsource(always._stop_everything)


def test_no_listener_is_reported_as_a_problem():
    """The check was n <= 1, so zero listeners passed. Zero is the state where
    the key does nothing at all, which is the exact complaint this check was
    added to answer."""
    src = (ROOT / "dictator" / "cli.py").read_text()
    assert "n == 1" in src, "the listener count check accepts zero again"


def test_permissions_clears_a_grant_made_to_an_older_identity():
    """The first time an ad-hoc app gets a real certificate its identity
    changes, so the permission the user already granted stops applying. The
    old entry stays in the list, still ticked, next to an app macOS no longer
    recognises, and nothing the user can do in that pane fixes it because the
    tick they can see is not the tick that counts.

    Noticing it used to be a guess: no listener, service up, therefore stale.
    It is now read off the TCC row's stored code requirement, so the check is
    on the answer rather than on the shape of the guess. The full set of cases
    lives in test_permissions.py."""
    from dictator import tcc
    src = (ROOT / "dictator" / "cli.py").read_text()
    assert "tccutil" in src, "it no longer clears what macOS remembers"
    assert "tcc.state(" in src, "permissions no longer asks what macOS remembers"
    assert tcc.verdict({"state": tcc.STALE})[0] == "bad", \
        "a stale grant is reported as fine"


def test_a_bundle_pointing_at_another_checkout_is_rebuilt(tmp_path,
                                                          monkeypatch):
    """The mtime check asks whether the app is older than its source. It never
    asked whether the app still points at us, and a bundle does not have to be
    stale to be wrong: built once with the wrong DictatorCLI it stays wrong
    forever, because every later `dictator on` sees a fresh enough binary and
    returns early without looking inside.

    Found live: the installed bundle carried a path into a different user
    account's checkout, eleven hours behind, so every fix landed in one place
    and none of them ever ran. Dictation kept working, which is what made it
    invisible."""
    import plistlib

    from dictator import always

    app = tmp_path / "Dictator.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Dictator").write_bytes(b"binary")
    monkeypatch.setattr(always, "APP", app)

    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "DictatorCLI": "/Users/somebody-else/dictator/bin/dictator",
        "DictatorLog": str(always.core.STATE_DIR / "dictate.log"),
    }))
    assert always._bundle_points_here() is False

    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "DictatorCLI": always._cli(),
        "DictatorLog": str(always.core.STATE_DIR / "dictate.log"),
        "CFBundleIdentifier": always.core.bundle_id(),
    }))
    assert always._bundle_points_here() is True


def test_a_bundle_sharing_the_identifier_with_another_account_is_rebuilt(
        tmp_path, monkeypatch):
    """Accessibility rows are system-wide and keyed by the bundle identifier,
    so two accounts sharing one share a row that can pin only one certificate.
    Whichever granted last wins and the other is silently untrusted with a tick
    showing the whole time. A bundle still carrying the shared identifier has
    to be rebuilt, and nothing else here would notice."""
    import plistlib

    from dictator import always

    app = tmp_path / "Dictator.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    monkeypatch.setattr(always, "APP", app)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "DictatorCLI": always._cli(),
        "DictatorLog": str(always.core.STATE_DIR / "dictate.log"),
        "CFBundleIdentifier": "com.dictator.dictation",   # the shared one
    }))
    assert always._bundle_points_here() is False


def test_a_bundle_logging_somewhere_else_counts_as_wrong_too(tmp_path,
                                                             monkeypatch):
    """The log path comes from the same place as the CLI path. A bundle
    writing its log into another account's state directory is the same bug,
    and it is how the mismatch shows up first: the log you are reading is not
    the log it is writing."""
    import plistlib

    from dictator import always

    app = tmp_path / "Dictator.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    monkeypatch.setattr(always, "APP", app)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "DictatorCLI": always._cli(),
        "DictatorLog": "/Users/somebody-else/.dictator/dictate.log",
    }))
    assert always._bundle_points_here() is False


def test_a_bundle_with_no_plist_is_not_assumed_to_be_ours(tmp_path,
                                                          monkeypatch):
    from dictator import always
    app = tmp_path / "Dictator.app"
    (app / "Contents").mkdir(parents=True)
    monkeypatch.setattr(always, "APP", app)
    assert always._bundle_points_here() is False


def test_the_installer_does_not_take_a_name_another_install_owns():
    """/opt/homebrew/bin and /usr/local/bin are shared by every account on the
    Mac. `ln -sf` there does not add a command, it takes one: whichever
    account installed last owns the name and every other account's `dictator`
    silently runs that account's checkout.

    Measured on a real machine: a second account spent a day running the
    first's code from four days earlier. `git pull` said "Already up to date",
    `dictator build` reported success on every helper, and none of it was the
    checkout the user was standing in."""
    src = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
    link = src[src.index("Make the command reachable"):]
    link = link[:link.index('step "6/6')]
    assert "readlink" in link, \
        "it does not look at who owns the name before taking it"
    assert "belongs to another install" in link, \
        "it does not say so when it declines"
    assert "continue" in link, "it does not decline, it just warns"


def test_doctor_checks_the_command_on_path_is_this_checkout():
    """The failure is completely silent: every command reports success and
    none of them is running your code."""
    src = (Path(__file__).resolve().parent.parent / "dictator" / "cli.py").read_text()
    assert '"and it is this checkout"' in src
    assert "realpath" in src, "comparing unresolved paths misses a symlink"


def test_the_bundle_is_registered_after_its_identifier_changes(tmp_path,
                                                               monkeypatch):
    """Changing CFBundleIdentifier in place is invisible to LaunchServices: it
    has the path cached under the OLD identifier and nothing asks it to look
    again. The bundle then exists, is correctly signed, and cannot be
    addressed by the name written inside it.

    Measured on a real machine after the identifier went per account:
    `tccutil reset Accessibility com.dictator.dictation.<id>` answered
    `No such bundle identifier` with OSStatus -10814, so the permission could
    not be cleared, and macOS had no registered app to attach a grant to."""
    from dictator import always

    ran = []
    monkeypatch.setattr(always.subprocess, "run",
                        lambda cmd, **k: ran.append(cmd))
    always._register(tmp_path / "Dictator.app")
    # Skipped silently where the tool is absent, which is fine; where it is
    # present it must be asked to look again.
    tool = ("/System/Library/Frameworks/CoreServices.framework/Frameworks"
            "/LaunchServices.framework/Support/lsregister")
    if Path(tool).exists():
        assert ran, "LaunchServices was never told"
        assert "-f" in ran[0], "a registration that is not forced is a no-op"


def test_registering_is_attempted_as_part_of_building_the_app():
    src = (Path(__file__).resolve().parent.parent
           / "dictator" / "always.py").read_text()
    build = src[src.index("def build_app"):]
    assert "_register(APP)" in build, \
        "the bundle is signed and then never registered"
    assert build.index("_sign(APP)") < build.index("_register(APP)"), \
        "register after signing, or it registers a bundle about to change"


def test_the_orb_goes_to_the_screen_with_the_keyboard_focus():
    """It used to prefer the notched screen, because the orb tucks into the
    notch and that looks good on a laptop. On a desk with an external display
    it is simply the wrong screen: the person types into a window on the
    monitor in front of them and the one indicator saying the microphone is
    live appears on the laptop, often closed or off to one side.

    `NSScreen.main` is AppKit's name for the screen with the KEYBOARD FOCUS,
    not the built-in one, so it was already the right answer and was being
    asked second.

    Asserted on the source: the decision is NSScreen behaviour and cannot be
    faked in a test without a second display attached."""
    src = (Path(__file__).resolve().parent.parent
           / "native" / "orb.swift").read_text()
    pick = src[src.index("func pickScreen()"):]
    pick = pick[:pick.index("\n}") + 2]
    assert pick.index("NSScreen.main") < pick.index("notchRect"), \
        "the notch is still preferred over the screen being typed into"


def test_the_orb_chooses_its_screen_on_every_hold():
    """An indicator that picked its screen when the listener started is on the
    wrong one for the rest of the session, and somebody with a laptop on a
    desk moves between displays all day.

    The screen is picked again where a hold begins, the move from any other
    look to listening, and a window that is rebuilt is still placed."""
    src = (Path(__file__).resolve().parent.parent
           / "native" / "orb.swift").read_text()
    show = src[src.index("private func show(_ f: NSRect"):]
    show = show[:show.index("private func hide(")]
    assert "makeWindow()" in show and "win.setFrame(f" in show, \
        "the window is rebuilt but never re-placed"
    ev = src[src.index("private func evaluate()"):]
    ev = ev[:ev.index("private func apply(")]
    assert "newLook == .listening" in ev and "pickScreen()" in ev, \
        "a hold no longer brings the pill to the screen being worked on"


def test_no_module_keeps_a_path_into_the_real_state_directory():
    """Four separate features have now written into the user's own data
    because a module computed its paths from STATE_DIR at import and the test
    isolation redirected STATE_DIR alone: the history, the vocabulary, the
    benchmark corpus, and the reference transcripts.

    This asserts the pattern rather than the four names, so the fifth one
    fails here instead of in somebody's data."""
    import importlib
    import pkgutil

    import dictator
    from dictator import core

    real = str(Path.home() / ".dictator")
    leaked = []
    for mod in pkgutil.iter_modules(dictator.__path__):
        try:
            m = importlib.import_module(f"dictator.{mod.name}")
        except Exception:
            continue
        for name in dir(m):
            if name.startswith("__"):
                continue
            v = getattr(m, name, None)
            if not isinstance(v, Path) or not str(v).startswith(real):
                continue
            # `~/.dictator/bin` holds compiled helpers, which tests READ and
            # are supposed to: pointing those at a temporary directory would
            # test a binary that is not the one shipped. Everything else under
            # the state directory is the user's own data.
            if str(v).startswith(real + "/bin/"):
                continue
            leaked.append(f"{mod.name}.{name} = {v}")
    assert not leaked, (
        "these point at the real state directory and the suite redirects "
        "STATE_DIR, so they must be in tests/conftest.py: " + ", ".join(leaked))
