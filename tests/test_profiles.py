"""Which formatting rules apply where, and what an override may not do.

The dangerous property here is not that an override is wrong. It is that the
result of this file is handed to shape() as keyword arguments, on the
dictation path, in a thread nobody is watching, so a stray key is not a bad
format, it is a hold that silently produces no words at all.
"""
import json

import pytest

from dictator import api, profiles, shape


@pytest.fixture
def base():
    return dict(api.DEFAULT_SHAPING)


def _write(rules):
    profiles.FILE.parent.mkdir(parents=True, exist_ok=True)
    profiles.FILE.write_text(json.dumps(rules))


def test_nothing_set_means_nothing_changes(base):
    assert profiles.overlay(base, "Slack") == base
    assert profiles.overlay(base, "") == base


def test_an_application_overrides_one_rule(base):
    profiles.set_rule("Slack", "lists", True)
    assert profiles.overlay(base, "Slack")["lists"] is True
    assert profiles.overlay(base, "Notes")["lists"] is False
    # And only that rule.
    for k in base:
        if k != "lists":
            assert profiles.overlay(base, "Slack")[k] == base[k], k


def test_the_application_name_is_matched_whatever_the_case(base):
    profiles.set_rule("SLACK", "lists", True)
    assert profiles.overlay(base, "Slack")["lists"] is True


def test_terminals_are_one_group_rather_than_a_list_to_maintain(base):
    profiles.set_rule("terminal", "sentences", False)
    for app in ("iTerm2", "Ghostty", "Terminal", "WezTerm", "Alacritty"):
        assert profiles.overlay(base, app)["sentences"] is False, app
    assert profiles.overlay(base, "Slack")["sentences"] is True


def test_naming_the_application_beats_the_group_it_is_in(base):
    profiles.set_rule("terminal", "sentences", False)
    profiles.set_rule("iTerm2", "sentences", True)
    assert profiles.overlay(base, "iTerm2")["sentences"] is True
    assert profiles.overlay(base, "Ghostty")["sentences"] is False


def test_an_unknown_key_in_the_file_never_reaches_shape(base):
    """The whole point of overlay() adding no keys. A hand-edited file, or one
    written by an older version, must not turn into a TypeError inside the
    thread that was delivering somebody's sentence."""
    _write({"slack": {"lists": True, "tone": True, "emoji": False}})
    flags = profiles.overlay(base, "Slack")
    assert set(flags) == set(base)
    shape.shape("this should not raise", **flags)


def test_a_broken_file_is_ignored_rather_than_fatal(base):
    profiles.FILE.parent.mkdir(parents=True, exist_ok=True)
    profiles.FILE.write_text("{not json at all")
    assert profiles.overlay(base, "Slack") == base


def test_clearing_puts_the_global_rules_back(base):
    profiles.set_rule("Slack", "lists", True)
    assert profiles.clear("Slack") is True
    assert profiles.overlay(base, "Slack") == base
    assert profiles.clear("Slack") is False


def test_the_pipeline_asks_for_the_right_rules(base):
    """shaping_flags() is what api.polish() actually calls, so the wiring is
    worth a test of its own: the module could be perfect and never consulted."""
    profiles.set_rule("terminal", "sentences", False)
    assert api.shaping_flags("Ghostty")["sentences"] is False
    assert api.shaping_flags("Slack")["sentences"] is True
    assert api.shaping_flags()["sentences"] is True


def test_it_changes_what_lands_in_the_terminal():
    """End to end through polish(), because that is where a user would notice.
    A shell prompt is the one place a capital letter is a syntax error."""
    profiles.set_rule("terminal", "sentences", False)
    d = api.Dictator(learn=False, remember=False)
    assert d.polish("make the tests pass", app="Ghostty") == "make the tests pass"
    assert d.polish("make the tests pass", app="Slack") == "Make the tests pass"
