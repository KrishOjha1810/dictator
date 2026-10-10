"""Finding something you said weeks ago, by three words of it.

The history is only worth keeping if it can be interrogated, and the test that
matters most is the one about `heard`: a search that cannot find a sentence by
the words the recogniser got WRONG fails exactly when the user needs it.
"""
import time

import pytest

from dictator_core import history, search


def _said(text, app="", at=None, heard=None, kept=""):
    row_id = history.add(heard=heard if heard is not None else text,
                         shown=text, app=app)
    if kept:
        history.kept(row_id, kept)
    if at is not None:
        con = history._db()
        con.execute("UPDATE said SET at=? WHERE id=?", (at, row_id))
        con.commit()
        con.close()
    return row_id


@pytest.fixture
def said():
    now = time.time()
    _said("the loop is slow and we should profile it", app="Ghostty", at=now - 60)
    _said("ping the team about the deploy", app="Slack", at=now - 3600)
    _said("yaar ye loop thoda slow lag raha hai", app="Slack",
          at=now - 40 * 86400)
    _said("git rebase on origin main", app="Ghostty", at=now - 120)
    return now


def test_it_finds_a_phrase(said):
    hits = search.find("the loop is slow")
    assert len(hits) == 1
    assert hits[0].phrase is True
    assert "profile it" in hits[0].text


def test_the_words_do_not_have_to_be_next_to_each_other(said):
    hits = search.find("loop slow")
    assert len(hits) == 2
    # And the contiguous match, if there were one, would come first.
    assert all(h.phrase is False for h in hits)


def test_every_word_has_to_be_there(said):
    assert search.find("loop parakeet") == []


def test_a_word_is_matched_inside_a_longer_one(said):
    """Somebody searching for "deploy" wants the line that says "deployed",
    and a search that makes you guess the suffix is one people stop using."""
    assert len(search.find("deplo")) == 1


def test_contiguous_matches_come_before_scattered_ones():
    now = time.time()
    _said("scattered: the loop, and separately, slow", at=now - 10)
    _said("the loop is slow", at=now - 100000)
    hits = search.find("loop is slow")
    assert hits[0].phrase is True
    assert hits[0].text == "the loop is slow"


def test_it_searches_what_the_recogniser_heard_not_only_what_landed():
    """The one that makes this worth building. You remember saying the word;
    the recogniser wrote something else; the history is the only record of
    what it wrote."""
    _said("Whisper Flow is the competitor", heard="whisper floor is the competitor")
    assert search.find("whisper floor")
    assert search.find("Whisper Flow")


def test_it_shows_what_you_kept_rather_than_what_was_pasted():
    _said("run the tests", kept="run the tests twice")
    hit = search.find("run the tests")[0]
    assert hit.text == "run the tests twice"


def test_it_can_be_limited_to_one_application(said):
    assert len(search.find("loop")) == 2
    assert len(search.find("loop", app="Slack")) == 1
    assert len(search.find("loop", app="slack")) == 1     # case does not matter
    assert len(search.find("rebase", app="Ghost")) == 1   # nor does the full name
    assert search.find("loop", app="Notes") == []


def test_it_can_be_limited_to_recent_days(said):
    assert len(search.find("loop")) == 2
    assert len(search.find("loop", days=7)) == 1


def test_newest_first_within_a_group(said):
    hits = search.find("the")
    assert hits == sorted(hits, key=lambda h: -h.at)


def test_an_empty_query_finds_nothing_rather_than_everything(said):
    assert search.find("") == []
    assert search.find("   ") == []


def test_nothing_recorded_is_not_an_error():
    assert search.find("anything") == []


def test_a_long_line_is_cut_around_the_match():
    filler = "padding words here and there " * 12
    _said(filler + "the parakeet engine dropped it " + filler)
    hit = search.find("parakeet")[0]
    around = hit.around(width=60)
    assert "parakeet" in around
    assert len(around) <= 70
    assert around.startswith("...")


def test_a_short_line_is_shown_whole():
    _said("the loop is slow")
    assert search.find("loop")[0].around() == "the loop is slow"


def test_the_stamp_leaves_out_this_year():
    now = time.time()
    assert str(time.localtime(now).tm_year) not in search.stamp(now)
    old = now - 800 * 86400
    assert str(time.localtime(old).tm_year) in search.stamp(old)
