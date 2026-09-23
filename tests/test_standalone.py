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
def test_built_bundle_points_at_this_checkout():
    info = plistlib.loads(
        (always.APP / "Contents" / "Info.plist").read_bytes())
    assert info["DictatorCLI"] == str(ROOT / "bin" / "dictator"), info["DictatorCLI"]
    assert Path(info["DictatorCLI"]).exists()
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
