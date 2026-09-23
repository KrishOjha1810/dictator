"""What the learned vocabulary is allowed to rewrite, and what it must not.

A vocabulary that fires too eagerly is worse than one that never fires. It
changes words the user got right, in every application, without being asked,
and the user has no way to see why.
"""
import pytest

from dictator import vocab


@pytest.fixture
def v(tmp_path, monkeypatch):
    monkeypatch.setattr(vocab, "FILE", tmp_path / "words.json", raising=False)
    box = vocab.Vocab()
    box.terms = {}
    for term in ("Whisper Flow", "voicebridge"):
        box.terms[term] = box.admit(term)
    box.save = lambda: None
    return box


def test_it_fixes_what_it_was_taught(v):
    assert v.fix("I use whisper floor daily") == "I use Whisper Flow daily"
    assert v.fix("open voice bridge and check") == "open voicebridge and check"


def test_it_generalises_beyond_the_exact_mishearing(v):
    """The point of matching by sound is that one lesson covers the variants,
    so this is not a lookup table with a row per mistake."""
    for said in ("whisper flows", "whispa flo", "whisper floor"):
        assert "Whisper Flow" in v.fix(f"try {said} today"), said


def test_it_leaves_ordinary_sentences_alone(v):
    for line in ("this sentence is perfect and should not change",
                 "never mind that, run the tests",
                 "check the code and make a commit",
                 "the flowers are nice"):
        assert v.fix(line) == line, line


def test_it_does_not_eat_the_word_in_front_of_the_term(v):
    """"the voice bridge" matched "voicebridge" closely enough to win as a
    three word span, and replacing the whole span deleted a word the user
    actually said."""
    assert v.fix("lets do the voice bridge shift") == \
        "lets do the voicebridge shift"


def test_it_does_not_reach_inside_a_longer_word(v):
    """A substring matcher corrupted unrelated words in a comparable tool, so
    matching here is on whole words only."""
    assert v.fix("whisper flooring company") == "whisper flooring company"
    assert v.fix("vergrossern lernen") == "vergrossern lernen"


def test_a_crowded_sounding_term_is_not_guessed_by_that_sound(v):
    """A term that collides with words the user says cannot be guessed at by
    the sound it collides on, and the reason is written for them to read
    rather than silently applied. It may still be guessed at by a key that
    does not collide, which is what makes "Amandhra" correctable at all."""
    rec = v.admit("Amandra")
    assert "key" not in rec["guess"], rec
    assert rec["why"], "declined to guess without saying why"


def test_a_term_that_sounds_like_a_word_you_use_is_exact_only(monkeypatch):
    """The guard has to be the words this user says, not a dictionary.

    "Hinglish" and "English" are 0.20 apart, which is exactly the fuzzy
    threshold, so learning the first would have rewritten every correct
    "English" this user ever dictates. A dictionary would also have blocked
    "dictator", because it contains "dictate", which they have never once
    said. Their own history separates the two."""
    box = vocab.Vocab()
    box.terms = {}
    monkeypatch.setattr(box, "spoken", lambda **kw: ["english", "line", "accuracy"])

    hinglish = box.admit("Hinglish")
    assert "key" not in hinglish["guess"], hinglish
    assert "english" in hinglish["why"]

    assert "key" in box.admit("dictator")["guess"]


def test_learning_it_anyway_does_not_break_the_word_it_sounds_like(monkeypatch):
    box = vocab.Vocab()
    box.terms = {}
    box.save = lambda: None
    monkeypatch.setattr(box, "spoken", lambda **kw: ["english"])
    box.terms["Hinglish"] = box.admit("Hinglish")
    assert box.fix("this is the English line") == "this is the English line"
    assert box.fix("mujhe Hinglish line chahiye") == "mujhe Hinglish line chahiye"


def test_the_spoken_list_comes_from_what_was_actually_said(monkeypatch):
    box = vocab.Vocab()
    rows = [{"kept": "", "shown": "the loop is slow", "heard": ""}] * 3
    monkeypatch.setattr(vocab, "history", __import__("types").SimpleNamespace(
        recent=lambda limit=0: rows), raising=False)
    import sys
    sys.modules["dictator.history"].recent = lambda limit=0: rows
    got = box.spoken(least=2)
    assert "loop" in got and "slow" in got
    assert "is" not in got, "two letter words are noise, not vocabulary"


def test_exact_mode_means_the_word_not_the_key(monkeypatch):
    """Learning "woh" rewrote "we" in ordinary English speech.

    "woh" was admitted in exact match mode because its metaphone key, W, is
    too short to guess from. But exact mode compared KEYS, and metaphone gives
    "we" the key W as well, so the safest possible admission still corrupted
    one of the most common words in the language. Told a user it would "only
    fix it when I hear it exactly", then did not."""
    box = vocab.Vocab()
    box.terms = {}
    box.save = lambda: None
    monkeypatch.setattr(box, "spoken", lambda **kw: ["we", "english"])
    box.terms["woh"] = box.admit("woh")
    assert box.terms["woh"]["mode"] == "exact"
    for line in ("we can do this", "where is the file", "who wrote this"):
        assert box.fix(line) == line, line


def test_one_bad_key_does_not_disable_the_good_one(monkeypatch):
    """"Amandra" keys to AMNTP, which collides with "amend" and "amount", and
    to amandra in Hindi, which collides with nothing. Refusing to guess at all
    because one of the two collided meant a misheard "Amandhra" was never
    corrected, which is the case the user actually reported."""
    box = vocab.Vocab()
    box.terms = {}
    box.save = lambda: None
    monkeypatch.setattr(box, "spoken",
                        lambda **kw: ["amend", "amends", "amount", "we"])
    box.terms["Amandra"] = box.admit("Amandra")
    assert box.terms["Amandra"]["guess"] == ["hkey"], box.terms["Amandra"]
    assert box.fix("tell Amandhra to review") == "tell Amandra to review"
    # The words it collided with must still be safe.
    for line in ("we need to amend the file", "the amount is wrong"):
        assert box.fix(line) == line, line


def test_old_records_are_re_admitted_once_and_only_once(tmp_path, monkeypatch):
    """A word learned before a rule changed kept the old verdict for ever, and
    the user had no way to see that a later improvement never reached it. The
    migration has to be idempotent, or it decides every record is stale on
    every start and rewrites the file each time."""
    import json
    store = tmp_path / "vocab.json"
    monkeypatch.setattr(vocab, "STORE", store)
    store.write_text(json.dumps({
        "Amandra": {"term": "Amandra", "key": "AMNTP", "mode": "exact",
                     "why": "", "heard": ["Amandhra"], "count": 3, "at": 1.0},
    }))
    first = vocab.Vocab()
    rec = first.terms["Amandra"]
    assert rec["guess"] == ["hkey"], rec
    assert rec["heard"] == ["Amandhra"], "lost what it had already been taught"
    assert rec["count"] == 3

    second = vocab.Vocab()
    assert not [t for t, r in second.terms.items() if "guess" not in r]
