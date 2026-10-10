"""Reading another installation's files.

One Mac, two user accounts, and the dictation that matters happening in the
one you are not sitting in. Without an override there is no way to read the
other installation's log at all, so "why did it do that over there" could only
be answered by logging out and back in.

Tested through `state_dir()` rather than by reloading the module: every other
module computes its own paths from `STATE_DIR` at import, so a reload here
leaves them pointing at a directory this file invented.
"""
import os
from pathlib import Path

from dictator_core import core


def test_it_reads_the_installation_you_point_it_at(tmp_path):
    elsewhere = tmp_path / "someone-elses" / ".dictator"
    assert core.state_dir(str(elsewhere)) == elsewhere


def test_the_home_directory_is_the_default():
    assert core.state_dir("") == Path(os.path.expanduser("~/.dictator"))


def test_a_tilde_is_expanded():
    """Otherwise a perfectly ordinary value makes a directory called "~"."""
    got = core.state_dir("~/somewhere-else")
    assert "~" not in str(got)
    assert str(got).endswith("somewhere-else")


def test_an_empty_value_is_ignored_rather_than_used():
    """`DICTATOR_STATE=` in a shell profile is an empty string, and treating
    that as a path would put the state at the filesystem root."""
    for empty in ("", "   ", None):
        if empty is None:
            continue
        assert core.state_dir(empty) == Path(os.path.expanduser("~/.dictator"))


def test_the_environment_is_what_it_reads_when_nothing_is_passed(monkeypatch):
    monkeypatch.setenv("DICTATOR_STATE", "/tmp/somebody-elses-dictator")
    assert core.state_dir() == Path("/tmp/somebody-elses-dictator")
    monkeypatch.delenv("DICTATOR_STATE")
    assert core.state_dir() == Path(os.path.expanduser("~/.dictator"))
