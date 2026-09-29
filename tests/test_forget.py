"""Erasing what you said, which used to have exactly one setting.

`dictator forget` deleted the entire history, with no argument and no
question. Both halves were wrong. The usual reason to reach for this command
is one thing somebody wishes they had not said out loud, and an irreversible
delete of every word they have ever dictated should take more than four
letters and a Return.
"""
from dictator import history


def _said(text, heard=None):
    return history.add(heard=heard or text, shown=text, app="Terminal")


def test_it_finds_the_line_by_what_is_in_it():
    _said("the deploy key is in the vault")
    _said("something else entirely")
    rows = history.matching("deploy key")
    assert len(rows) == 1
    assert "deploy key" in rows[0]["shown"]


def test_it_searches_what_was_heard_as_well_as_what_landed():
    """The reason to delete a line is often that it holds something that
    should not have been written down, and the copy holding it may be the one
    the recogniser produced rather than the one that was pasted."""
    _said("the password is hunter two", heard="the password is Hunter Too")
    assert history.matching("Hunter Too")
    assert history.matching("hunter two")


def test_it_searches_what_you_kept_too():
    rid = _said("nothing here")
    history.kept(rid, "the account number is 4001")
    assert history.matching("4001")


def test_matching_is_not_case_sensitive():
    _said("The Vault Address")
    assert history.matching("vault address")


def test_an_empty_search_matches_nothing_rather_than_everything():
    """Otherwise a mistyped argument erases the lot, which is the accident
    this command is most able to cause."""
    _said("something")
    assert history.matching("") == []
    assert history.matching("   ") == []
    assert history.forget(containing="") != 1


def test_forgetting_by_text_leaves_everything_else_alone():
    _said("the deploy key is in the vault")
    _said("the deploy key again")
    _said("an unrelated thought")
    assert history.forget(containing="deploy key") == 2
    assert [r["shown"] for r in history.recent()] == ["an unrelated thought"]


def test_forgetting_text_that_is_not_there_deletes_nothing():
    _said("an unrelated thought")
    assert history.forget(containing="deploy key") == 0
    assert len(history.recent()) == 1


def test_forgetting_everything_still_works():
    _said("one")
    _said("two")
    assert history.forget(before=9e18) == 2
    assert history.recent() == []


def test_forgetting_one_row_by_id_still_works():
    rid = _said("one")
    _said("two")
    assert history.forget(row_id=rid) == 1
    assert [r["shown"] for r in history.recent()] == ["two"]


def test_the_lock_is_not_taken_twice():
    """`forget(containing=...)` reads through `matching`, which takes the same
    lock, and it is not reentrant. Doing this the obvious way deadlocks the
    caller, and on the dictation path the caller is holding the user's words.
    Caught by this file hanging rather than failing, which is why it has a
    timeout on it."""
    import threading
    _said("the deploy key is in the vault")
    done = []
    t = threading.Thread(target=lambda: done.append(
        history.forget(containing="deploy key")))
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "forget deadlocked"
    assert done == [1]
