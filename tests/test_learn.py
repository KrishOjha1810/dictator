"""What gets learned from an edit, and more importantly what does not.

The danger in learning automatically is not that it misses something. It is
that it learns the wrong thing from an ordinary edit and then starts rewriting
words the user never got wrong, in every application, silently.
"""
import pytest

from dictator import learn


def _learned(shown, kept):
    return [(w, n) for w, n in learn.changes(shown, kept)
            if learn.is_correction(w, n)]


@pytest.mark.parametrize("shown,kept,expected", [
    ("I was using whisper floor today", "I was using Whisper Flow today",
     [("whisper floor", "Whisper Flow")]),
    ("open Vice Bridge and check", "open voicebridge and check",
     [("Vice Bridge", "voicebridge")]),
    ("tell a man dra to review it", "tell Amandra to review it",
     [("a man dra", "Amandra")]),
])
def test_a_mishearing_is_learned(shown, kept, expected):
    assert _learned(shown, kept) == expected


@pytest.mark.parametrize("shown,kept", [
    # Changing your mind is not a correction, however small the edit.
    ("the loop is slow", "the loop is fast"),
    ("ship it on Monday", "ship it on Friday"),
    # A rewrite is not a correction either.
    ("check the code and make a commit", "actually never mind, forget it"),
    # Nothing changed.
    ("run the tests", "run the tests"),
])
def test_an_edit_is_not_learned(shown, kept):
    assert _learned(shown, kept) == [], f"learned something from {shown!r}"


def test_a_long_replacement_is_never_a_correction():
    """Real mishearings are a word or a short phrase. Anything longer is the
    user writing something else, and the sound test is not enough on its own
    to tell the difference."""
    was = "one two three four five six"
    now = "won too three for five sicks"
    assert not learn.is_correction(was, now)


def test_unchanged_text_is_not_reported_as_moved():
    field = "some earlier output\nI was using Whisper Flow today\nmore output"
    assert learn.locate("I was using Whisper Flow today", field) == ""


def test_an_edit_is_found_inside_a_terminal_scrollback():
    """Terminals hand back the whole scrollback, not the line being edited,
    so the sentence has to be found inside a much larger haystack."""
    field = ("Last login: Wed Sep 16\n% claude\n"
             "I was using Whisper Flow today\n% \n") * 3
    got = learn.locate("I was using whisper floor today", field)
    assert "Whisper Flow" in got, got


def test_an_unrelated_field_yields_nothing():
    """Without this the reader would mine any text it happened to see for
    corrections that never happened."""
    assert learn.locate("deploy the service now",
                        "a completely different sentence about lunch") == ""


def test_nothing_is_learned_on_first_sighting(tmp_path, monkeypatch):
    """One edit is as likely to be a typo as a lesson."""
    monkeypatch.setattr(learn, "PENDING", tmp_path / "pending.json")
    added = []
    monkeypatch.setattr(learn.vocab, "shared",
                        lambda: type("V", (), {"add": lambda s, t, heard="": added.append(t)})())
    first = learn.observe("using whisper floor", "using Whisper Flow")
    assert first == [] and added == []
    second = learn.observe("using whisper floor", "using Whisper Flow")
    assert second == ["Whisper Flow"] and added == ["Whisper Flow"]
