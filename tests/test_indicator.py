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


DEFAULT = {"position": "top", "idle": "hover",
           "controls": ["dictate", "notetaker", "scratchpad"],
           "shortcuts": {"notetaker": True, "scratchpad": True}, "hide_idle": False}


def test_no_file_means_top_shown_on_hover_with_every_button():
    assert orbnative.settings() == DEFAULT


def test_a_broken_file_reads_as_the_defaults():
    """A file someone broke by hand must not stop the pill from starting."""
    for junk in ("{not json", "[1, 2]",
                 '{"position": "middle", "hide_idle": "yes", "idle": "sometimes",'
                 ' "controls": "all", "shortcuts": {"notetaker": "yes"}}'):
        orbnative.SETTINGS.write_text(junk)
        assert orbnative.settings() == DEFAULT


def test_a_file_from_before_the_three_choices_keeps_its_meaning():
    """hide_idle on meant hidden while idle, and still does. Off was the
    faint pill; it now reads as the new default, shown on hover."""
    orbnative.SETTINGS.write_text(json.dumps({"position": "left", "hide_idle": True}))
    assert orbnative.settings()["idle"] == "hide"
    orbnative.SETTINGS.write_text(json.dumps({"position": "left", "hide_idle": False}))
    assert orbnative.settings()["idle"] == "hover"


def test_save_keeps_the_other_settings_and_unknown_keys():
    orbnative.SETTINGS.write_text(json.dumps({"hide_idle": True, "later": 1}))
    got = orbnative.save(position="bottom-right")
    assert got["position"] == "bottom-right" and got["idle"] == "hide"
    raw = json.loads(orbnative.SETTINGS.read_text())
    assert raw["later"] == 1 and raw["hide_idle"] is True
    assert not orbnative.SETTINGS.with_name("indicator.json.tmp").exists()


def test_controls_and_shortcuts():
    got = orbnative.save(controls=["scratchpad", "dictate"])
    assert got["controls"] == ["dictate", "scratchpad"]       # canonical order
    got = orbnative.save(shortcuts={"notetaker": False})
    assert got["shortcuts"] == {"notetaker": False, "scratchpad": True}
    assert orbnative.save(controls=[])["controls"] == []
    for bad in ({"controls": ["dance"]}, {"shortcuts": {"dictate": True}},
                {"shortcuts": {"notetaker": "off"}}, {"idle": "sometimes"}):
        with pytest.raises(ValueError):
            orbnative.save(**bad)


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
    argv, env = orbnative.command("/x/dictator-orb", "rightcmd")
    assert argv == ["/x/dictator-orb"]
    assert env["DICTATOR_STATE"] == str(core.STATE_DIR) == str(tmp_path)
    assert env["DICTATOR_KEY"] == "rightcmd"


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
    got = json.loads(capsys.readouterr().out)
    assert got["position"] == "left" and got["idle"] == "hide" and got["hide_idle"]
    assert cli.main(["dictator", "indicator", "idle", "always"]) == 0
    assert cli.main(["dictator", "indicator", "controls", "dictate,scratchpad"]) == 0
    assert cli.main(["dictator", "indicator", "shortcut", "scratchpad", "off"]) == 0
    capsys.readouterr()
    assert cli.main(["dictator", "indicator", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["idle"] == "always" and not got["hide_idle"]
    assert got["controls"] == ["dictate", "scratchpad"]
    assert got["shortcuts"] == {"notetaker": True, "scratchpad": False}
    assert cli.main(["dictator", "indicator", "controls", "none"]) == 0
    assert orbnative.settings()["controls"] == []


def test_cli_refuses_nonsense_without_writing(capsys):
    cli = _cli()
    assert cli.main(["dictator", "indicator", "position", "middle"]) == 2
    assert cli.main(["dictator", "indicator", "hide-idle", "maybe"]) == 2
    assert cli.main(["dictator", "indicator", "idle", "maybe"]) == 2
    assert cli.main(["dictator", "indicator", "controls", "jazz"]) == 2
    assert cli.main(["dictator", "indicator", "shortcut", "dictate", "on"]) == 2
    assert not orbnative.SETTINGS.exists()
