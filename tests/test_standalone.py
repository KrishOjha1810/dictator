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
    from dictator import core
    assert core.STATE_DIR.name == ".dictator", core.STATE_DIR


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
