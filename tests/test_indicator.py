"""The indicator pill's settings: where it sits, and whether it hides.

The helper (native/orb.swift) reads STATE_DIR/indicator.json and watches it;
the app writes it through `dictator indicator`; dragging the pill writes it
from the helper. These tests pin the Python half of that contract: the names
of the eight places, what a broken file reads as, and that the helper is told
which state directory to use.
"""
import json
import re
from pathlib import Path

import pytest

from dictator import core, orbnative


def _cli():
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("dcli", "bin/dictator")
    spec = importlib.util.spec_from_loader("dcli", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def test_no_file_means_top_and_always_shown():
    assert orbnative.settings() == {"position": "top", "hide_idle": False}


def test_a_broken_file_reads_as_the_defaults():
    """A file someone broke by hand must not stop the pill from starting."""
    for junk in ("{not json", "[1, 2]", '{"position": "middle", "hide_idle": "yes"}'):
        orbnative.SETTINGS.write_text(junk)
        assert orbnative.settings() == {"position": "top", "hide_idle": False}


def test_save_keeps_the_other_setting_and_unknown_keys():
    orbnative.SETTINGS.write_text(json.dumps({"hide_idle": True, "later": 1}))
    assert orbnative.save(position="bottom-right") == {
        "position": "bottom-right", "hide_idle": True}
    raw = json.loads(orbnative.SETTINGS.read_text())
    assert raw["later"] == 1
    assert not orbnative.SETTINGS.with_name("indicator.json.tmp").exists()


def test_save_refuses_a_place_that_does_not_exist():
    with pytest.raises(ValueError):
        orbnative.save(position="middle")
    with pytest.raises(ValueError):
        orbnative.save(hide_idle="on")
    assert not orbnative.SETTINGS.exists()


def test_the_eight_names_match_the_swift_helper():
    """The helper decodes the same strings; a renamed case on either side
    would silently put the pill back at the top."""
    src = Path(orbnative.SRC).read_text()
    m = re.search(r"enum Spot: String, CaseIterable \{(.*?)\n\}", src, re.S)
    assert m, "Spot enum not found in orb.swift"
    body = m.group(1)
    names = []
    for case in re.findall(r"case ([^\n]+)", body):
        for part in case.split(","):
            part = part.strip()
            if not part:
                continue
            raw = re.search(r'"([^"]+)"', part)
            names.append(raw.group(1) if raw else part.split()[0])
    assert tuple(names) == orbnative.POSITIONS


def test_the_helper_is_told_which_state_directory_to_use(tmp_path):
    """It used to read a hardcoded ~/.dictator, so a loop started with
    DICTATOR_STATE elsewhere had a pill watching some other mic.lock."""
    argv, env = orbnative.command("/x/dictator-orb")
    assert argv == ["/x/dictator-orb"]
    assert env["DICTATOR_STATE"] == str(core.STATE_DIR) == str(tmp_path)


def test_show_starts_the_helper_with_that_environment(monkeypatch, tmp_path):
    seen = {}

    class P:
        pid = 4321

    def fake_popen(argv, **kw):
        seen["argv"], seen["env"] = argv, kw.get("env")
        return P()

    monkeypatch.delenv("VB_NO_ORB", raising=False)
    monkeypatch.setattr(orbnative, "running", lambda: False)
    monkeypatch.setattr(orbnative, "build", lambda force=False: "/x/dictator-orb")
    monkeypatch.setattr(orbnative.subprocess, "Popen", fake_popen)
    assert orbnative.show() is True
    assert seen["argv"] == ["/x/dictator-orb"]
    assert seen["env"]["DICTATOR_STATE"] == str(tmp_path)
    assert orbnative.PID.read_text() == "4321"


def test_cli_sets_and_reports(capsys):
    cli = _cli()
    assert cli.main(["dictator", "indicator", "position", "left"]) == 0
    assert cli.main(["dictator", "indicator", "hide-idle", "on"]) == 0
    capsys.readouterr()
    assert cli.main(["dictator", "indicator", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"position": "left", "hide_idle": True}


def test_cli_refuses_nonsense_without_writing(capsys):
    cli = _cli()
    assert cli.main(["dictator", "indicator", "position", "middle"]) == 2
    assert cli.main(["dictator", "indicator", "hide-idle", "maybe"]) == 2
    assert not orbnative.SETTINGS.exists()
