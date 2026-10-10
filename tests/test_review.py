"""Asking about the words it got wrong, which is the other half of learning.

The correction loop reads the text field back after a paste. That works where
the field can be read and does not work in a terminal, and a terminal is where
most dictation here goes, so the words it gets wrong most often are the ones
it never hears about. This goes the other way: find the words in neither
dictionary and ask.

Worth building because of a count rather than a hunch. Of the 21 genuine
errors in 130 real recordings, 8 were names and acronyms, the largest single
category, and no speech model will ever know them.
"""
import pytest

from dictator_core import history, review, vocab


def _said(text, app="Terminal"):
    return history.add(heard=text, shown=text, app=app)


def test_it_asks_about_a_name_and_not_about_the_sentence_around_it():
    _said("Er hello Zhrkvander. I think please give me some time.")
    rows = review.suspects()
    assert len(rows) == 1
    assert rows[0]["words"] == ["Zhrkvander"]


def test_a_line_it_got_right_is_never_raised():
    _said("I understood the borrower struct, but the accuracy interest")
    _said("mujhe yeh chahiye, aur kya")
    assert review.suspects() == []


def test_the_same_word_twice_in_a_line_is_one_question():
    _said("Zhrkvander and then Zhrkvander again")
    assert review.suspects()[0]["words"] == ["Zhrkvander"]


def test_a_word_already_dismissed_does_not_come_back():
    _said("hello Zhrkvander")
    assert review.suspects(ignore={"zhrkvander"}) == []


def test_the_word_is_shown_inside_enough_of_its_sentence_to_answer():
    """Nobody can say what "Zhrkvander" was meant to be. Everybody can say it
    when they can see it was a greeting."""
    text = ("Er hello Zhrkvander. I think uh please give me some time and I "
            "would like we can discuss it afterwards uh after 8:30 pm.")
    shown = review.show(text, "Zhrkvander")
    assert "Zhrkvander" in shown
    assert "hello" in shown, "the answer is in the words before it"
    assert len(shown) < len(text)


def test_a_word_at_the_very_start_still_gets_its_context():
    shown = review.show("Checkmone again full PDF full HTML", "Checkmone")
    assert shown.startswith("Checkmone")
    assert "again" in shown


def test_teaching_records_what_was_heard_so_the_sound_is_matched():
    rec = review.teach("Rohan Verma", heard="Zhrkvander")
    assert rec.get("mode") == "fuzzy", rec
    assert "Zhrkvander" in vocab.shared().terms["Rohan Verma"]["heard"]


def test_nothing_is_learned_from_an_empty_answer():
    """Silence is a skip. A guess accepted quietly would rewrite correct words
    in every later dictation, which is what vocab.admit exists to prevent."""
    before = dict(vocab.shared().terms)
    assert review.teach("", heard="Zhrkvander").get("ok") is False
    assert vocab.shared().terms == before


def test_it_prefers_what_you_kept_over_what_it_heard():
    """If the correction loop did see an edit, that edit is the better text to
    look at, and asking about a word the user already fixed is noise."""
    rid = _said("Zhrkvander is here")
    history.kept(rid, "everybody is here")
    assert review.suspects() == []


def test_a_word_already_taught_is_never_asked_about_again():
    """Otherwise a helpful prompt turns into a nag, and the name you fixed
    last week is the one it keeps raising."""
    _said("hello Zhrkvander")
    assert review.suspects(), "it should ask before being taught"
    review.teach("Zhrkvander", heard="Zhrkvander")
    assert review.suspects() == []


@pytest.mark.parametrize("app", ["Terminal", "Slack", ""])
def test_it_says_where_the_word_was_said(app):
    _said("hello Zhrkvander", app=app)
    assert review.suspects()[0]["app"] == app


def test_it_asks_once_per_word_rather_than_once_per_sentence():
    """Walking utterances asks about the same name forty times. Walking words
    asks once and fixes forty."""
    for _ in range(4):
        _said("hello Zhrkvander")
    _said("goodbye Zhrkvander")
    ws = review.words()
    assert [w["word"] for w in ws] == ["Zhrkvander"]
    assert ws[0]["count"] == 5


def test_the_words_you_say_most_come_first():
    """So that stopping halfway still got the value out of it."""
    _said("Zhrkvander again")
    for _ in range(3):
        _said("about Glentworthy")
    assert [w["word"] for w in review.words()] == ["Glentworthy", "Zhrkvander"]


def test_it_shows_the_longest_example_because_the_shortest_is_unanswerable():
    _said("Zhrkvander")
    _said("Er hello Zhrkvander, please give me some time")
    assert "hello" in review.words()[0]["text"]


def test_nothing_to_ask_about_is_an_empty_list_not_an_error():
    _said("I understood the borrower struct")
    assert review.words() == []


# ---- the library surface -----------------------------------------------

def test_a_caller_can_ask_what_it_got_wrong_without_the_command():
    """The loop that catches corrections cannot read a terminal's text field,
    so an embedder with its own way of asking the user is better placed than
    we are. That only helps if the list is reachable."""
    import dictator_core
    _said("hello Zhrkvander")
    got = dictator_core.Dictator().review()
    assert [w["word"] for w in got] == ["Zhrkvander"]


def test_a_caller_can_erase_one_thing_without_erasing_everything():
    import dictator_core
    _said("the deploy key is in the vault")
    _said("an unrelated thought")
    assert dictator_core.Dictator().forget(containing="deploy key") == 1
    assert [r["shown"] for r in history.recent()] == ["an unrelated thought"]


def test_an_empty_search_through_the_library_erases_nothing():
    """The same accident as on the command line, one layer up: a caller
    passing a variable that happened to be empty must not lose the history."""
    import dictator_core
    _said("something")
    assert dictator_core.Dictator().forget(containing="") == 0
    assert dictator_core.Dictator().forget() == 0
    assert len(history.recent()) == 1


def test_erasing_everything_has_to_be_asked_for_by_name():
    import dictator_core
    _said("one")
    _said("two")
    assert dictator_core.Dictator().forget(everything=True) == 2
    assert history.recent() == []
