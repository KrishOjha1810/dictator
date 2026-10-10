"""What a snippet is allowed to replace, and what it must never touch.

A vocabulary that fires wrongly writes one odd word and the user fixes it. A
snippet that fires wrongly drops an email address into the middle of a
sentence, and they find out after they have sent it. So the interesting tests
here are the refusals.
"""
import pytest

from dictator_core import snippets


@pytest.fixture
def box(monkeypatch, tmp_path):
    monkeypatch.setattr(snippets, "STORE", tmp_path / "snippets.json")
    s = snippets.Snippets()
    # No history in these tests unless a test puts one there, so the
    # familiarity guard has nothing to complain about by default.
    monkeypatch.setattr(s, "said_before", lambda trigger: 0)
    return s


def test_it_replaces_the_phrase_you_taught_it(box):
    box.add("my work email", "krish@example.com")
    out, fired = box.expand("send it to my work email please")
    assert out == "send it to krish@example.com please"
    assert fired == ["my work email"]


def test_it_is_case_insensitive_because_shaping_runs_first(box):
    """shape() capitalises the first word of a sentence, so by the time this
    runs the trigger may not look the way it was typed in."""
    box.add("my work email", "krish@example.com")
    assert box.expand("My work email is that one")[0] == \
        "krish@example.com is that one"


def test_it_respects_word_boundaries(box):
    box.add("my email", "krish@example.com")
    for line in ("check my emails later", "dummy emails are fine"):
        assert box.expand(line)[0] == line, line


def test_a_hyphen_the_recogniser_invented_does_not_break_it(box):
    """The model decides on its own whether to write "set up" or "set-up",
    and a trigger that only matches one of them fails half the time for a
    reason the user cannot see."""
    box.add("my set up line", "zsh -l")
    assert box.expand("run my set-up line now")[0] == "run zsh -l now"


def test_the_longest_trigger_wins(box):
    box.add("my email", "krish@example.com")
    box.add("my email signature", "Krish Ojha\nDictator")
    out, _ = box.expand("paste my email signature at the end")
    assert out.startswith("paste Krish Ojha")


def test_a_replacement_is_never_scanned_again(box):
    """A snippet whose text contains another trigger expands once, not
    forever."""
    box.add("my handle", "at my handle")
    out, _ = box.expand("it is my handle")
    assert out == "it is at my handle"


def test_one_word_triggers_are_refused(box):
    rec = box.add("email", "krish@example.com")
    assert not rec["ok"]
    assert f"{snippets.MIN_WORDS} words" in rec["why"]
    assert box.expand("send an email")[0] == "send an email"


def test_an_empty_replacement_is_refused(box):
    assert not box.add("my work email", "   ")["ok"]


def test_a_phrase_you_already_say_is_refused(box, monkeypatch):
    """The guard that stops a snippet from eating ordinary speech, and it is
    checked once when the snippet is made rather than on every hold."""
    monkeypatch.setattr(box, "said_before", lambda trigger: 7)
    rec = box.add("check the loop", "https://example.com/loop")
    assert not rec["ok"]
    assert "7 times" in rec["why"]
    assert not box.items


def test_you_can_add_it_anyway(box, monkeypatch):
    monkeypatch.setattr(box, "said_before", lambda trigger: 7)
    assert box.add("check the loop", "x", force=True)["ok"]


def test_the_familiarity_check_reads_your_own_history(monkeypatch, tmp_path):
    monkeypatch.setattr(snippets, "STORE", tmp_path / "snippets.json")
    from dictator_core import history
    for _ in range(3):
        history.add(heard="raw", shown="please check the loop again")
    assert snippets.Snippets().said_before("check the loop") == 3
    assert snippets.Snippets().said_before("check the wallet") == 0


def test_removing_one_is_the_off_switch(box):
    box.add("my work email", "krish@example.com")
    assert box.remove("My Work Email") is True
    assert box.expand("my work email")[0] == "my work email"
    assert box.remove("my work email") is False


def test_nothing_happens_when_there_are_no_snippets(box):
    line = "ye function thoda slow lag raha hai"
    assert box.expand(line) == (line, [])


def test_it_survives_a_reload(monkeypatch, tmp_path):
    monkeypatch.setattr(snippets, "STORE", tmp_path / "snippets.json")
    first = snippets.Snippets()
    monkeypatch.setattr(first, "said_before", lambda t: 0)
    first.add("my work email", "krish@example.com")
    assert snippets.Snippets().expand("my work email")[0] == "krish@example.com"


def test_one_added_from_a_terminal_works_on_the_very_next_hold(box, tmp_path):
    """The listener is one process that runs for days and `dictator snippet`
    is another that writes this file. A store that only reads it once means a
    new snippet does nothing until a restart, and restarting costs the user a
    macOS permission, so "restart it" is not an answer."""
    other = snippets.Snippets()          # the terminal, same file
    other.add("my work email", "krish@example.com", force=True)
    assert box.expand("send my work email")[0] == "send krish@example.com"


def test_a_hold_never_deletes_a_snippet_added_while_it_was_running(box):
    """The quiet half of the same bug. Firing a snippet writes the use count
    back, so a store holding a stale copy of the file would save over whatever
    the terminal had just added, and the user would find it gone with no
    error anywhere."""
    box.add("the vault path", "/srv/vault")
    snippets.Snippets().add("my work email", "krish@example.com", force=True)
    box.expand("use the vault path")     # writes the use count back
    assert sorted(snippets.Snippets().items) == ["my work email",
                                                 "the vault path"]
    assert snippets.Snippets().items["the vault path"]["count"] == 1


def test_use_is_counted(box):
    box.add("my work email", "krish@example.com")
    box.expand("my work email")
    box.expand("my work email")
    assert box.items["my work email"]["count"] == 2


def test_the_module_level_call_never_raises(monkeypatch):
    """It runs inside the dictation pipeline, where an exception costs the
    user the sentence they just spoke."""
    monkeypatch.setattr(snippets, "_shared", None)

    class Broken:
        def expand(self, text):
            raise RuntimeError("no")

    monkeypatch.setattr(snippets, "shared", lambda: Broken())
    assert snippets.expand("hello there") == "hello there"
