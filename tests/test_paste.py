"""Long dictation has to arrive as words, not as an attachment chip.

Claude Code collapses a paste over 800 UTF-16 units, or over two newlines,
into "[Pasted text #1 +12 lines]". These tests are about the decision, not the
delivery: nothing here opens a terminal, presses a key or touches the
pasteboard, because the part that goes wrong is choosing how to cut the text
up, and that is a pure function.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictator import paste


def _quiet(monkeypatch):
    monkeypatch.setattr(paste.core, "log", lambda *a, **k: None)


# ---- what gets cut up, and what is left alone -------------------------------

def test_short_text_is_still_one_paste():
    """The path that already works must not change shape."""
    assert paste._plan("deploy the thing", "Terminal") == ["deploy the thing"]


def test_a_paragraph_in_a_terminal_is_cut_up():
    text = "word " * 400                      # 2000 units, one long line
    pieces = paste._plan(text, "Terminal")
    assert len(pieces) > 1
    assert "".join(pieces) == text


def test_every_piece_stays_under_both_of_claude_codes_limits():
    text = ("a sentence that keeps going and going " * 60) + "\n" * 9
    for piece in paste._plan(text, "Ghostty"):
        assert paste._units(piece) <= paste.MAX_UNITS
        assert paste._newlines(piece) <= paste.MAX_NEWLINES


def test_more_than_two_newlines_is_enough_on_its_own():
    """Four short lines are 17 characters and still become a chip, so length
    is not the only trigger."""
    text = "one\ntwo\nthree\nfour"
    pieces = paste._plan(text, "iTerm2")
    assert len(pieces) > 1
    assert "".join(pieces) == text


def test_three_lines_are_left_alone():
    text = "one\ntwo\nthree"
    assert paste._plan(text, "iTerm2") == [text]


def test_only_terminals_get_cut_up():
    """Slack and a browser show a long paste as words already. Cutting it up
    there would buy nothing and add three more chances to land in the wrong
    window."""
    text = "word " * 400
    assert paste._plan(text, "Slack") == [text]
    assert paste._plan(text, "Google Chrome") == [text]
    assert paste._plan(text, "") == [text]


# ---- counting the way Claude Code counts ------------------------------------

def test_emoji_are_counted_as_javascript_counts_them():
    """It measures a JavaScript string, so an astral character is two units.
    Counting Python code points instead would let a sentence full of emoji sit
    over the limit while we believed it was under."""
    assert paste._units("hi") == 2
    assert paste._units("\U0001f600") == 2
    assert paste._units("नमस्ते") == 6


def test_a_windows_line_ending_is_one_newline_not_two():
    assert paste._newlines("a\r\nb\r\nc") == 2
    assert paste._newlines("a\rb\nc") == 2


def test_devanagari_and_emoji_survive_the_cutting():
    text = ("नमस्ते दुनिया "
            * 60) + " \U0001f642\U0001f44d\U0001f3fd done"
    pieces = paste._plan(text, "Terminal")
    assert len(pieces) > 1
    assert "".join(pieces) == text


def test_a_piece_does_not_end_mid_word_when_a_space_is_available():
    text = "alpha bravo charlie delta " * 80
    for piece in paste._plan(text, "Terminal")[:-1]:
        assert piece.endswith(" ")


def test_text_with_no_spaces_at_all_still_gets_cut():
    """A single unbroken token is rare and must not become an endless loop or
    one oversized piece."""
    text = "x" * 2000
    pieces = paste._plan(text, "Terminal")
    assert "".join(pieces) == text
    assert all(paste._units(p) <= paste.MAX_UNITS for p in pieces)


# ---- delivery reports what actually happened --------------------------------

def test_nothing_to_say_is_not_a_success(monkeypatch):
    _quiet(monkeypatch)
    assert paste.deliver("", "Terminal") is False


def test_every_piece_is_pasted_in_order(monkeypatch):
    _quiet(monkeypatch)
    sent = []
    monkeypatch.setattr(paste, "_paste_once", lambda t: sent.append(t) or True)
    monkeypatch.setattr(paste.mac, "frontmost_app", lambda: "Terminal")
    monkeypatch.setattr(paste.time, "sleep", lambda s: None)
    text = "word " * 400
    assert paste.deliver(text, "Terminal") is True
    assert "".join(sent) == text


def test_moving_away_mid_paste_stops_it(monkeypatch):
    """Half a sentence into the window you switched to is worse than none."""
    _quiet(monkeypatch)
    sent = []
    monkeypatch.setattr(paste, "_paste_once", lambda t: sent.append(t) or True)
    monkeypatch.setattr(paste.mac, "frontmost_app", lambda: "Slack")
    monkeypatch.setattr(paste.time, "sleep", lambda s: None)
    assert paste.deliver("word " * 400, "Terminal") is False
    assert len(sent) == 1


def test_a_piece_that_did_not_land_is_reported_honestly(monkeypatch):
    _quiet(monkeypatch)
    calls = []

    def flaky(t):
        calls.append(t)
        return len(calls) < 2

    monkeypatch.setattr(paste, "_paste_once", flaky)
    monkeypatch.setattr(paste.mac, "frontmost_app", lambda: "Terminal")
    monkeypatch.setattr(paste.time, "sleep", lambda s: None)
    assert paste.deliver("word " * 400, "Terminal") is False


def test_one_piece_never_asks_where_the_focus_is(monkeypatch):
    """Short text takes the same single paste it always did, and the caller has
    already checked the focus for it."""
    _quiet(monkeypatch)
    asked = []
    monkeypatch.setattr(paste, "_paste_once", lambda t: True)
    monkeypatch.setattr(paste.mac, "frontmost_app",
                        lambda: asked.append(1) or "Terminal")
    assert paste.deliver("deploy the thing", "Terminal") is True
    assert asked == []


def test_the_module_that_uses_the_helper_can_build_it():
    """It checked whether the binary existed and gave up if it did not, while
    the code that knew how to build it sat in another module that nothing here
    called. Deleting the binary once sent every delivery down a path that
    cannot work, quietly, and the only symptom was that the key did nothing."""
    import inspect
    from dictator import paste
    assert hasattr(paste, "helper"), "paste can no longer build its own helper"
    src = inspect.getsource(paste._paste_once)
    assert "helper()" in src, "the delivery path no longer builds the helper"


def test_there_is_no_silent_path_that_cannot_work():
    """osascript is a separate binary and never inherits the app's
    Accessibility grant, so falling back to it was falling back to a
    guaranteed failure that also overwrote the user's clipboard."""
    import inspect
    from dictator import paste
    src = inspect.getsource(paste._paste_once)
    assert "surface_error" in src, \
        "a missing helper no longer says so and fails silently again"
