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
    """Checked in the source, because the suite redirects STATE_DIR to a
    temporary directory so tests cannot write into the user's real data."""
    src = (PKG / "core.py").read_text()
    assert 'expanduser("~/.dictator")' in src, "state directory is not ~/.dictator"


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
    cli = (ROOT / "bin" / "dictator").read_text()
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
    assert "jellyfish" in (ROOT / "bin" / "dictator").read_text(), \
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
    src = (ROOT / "bin" / "dictator").read_text()
    assert "n == 1" in src, "the listener count check accepts zero again"
