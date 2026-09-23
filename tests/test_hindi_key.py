"""Matching Hindi written in English letters.

Metaphone models English spelling. On romanized Hindi it returns XHY for
chahiye and W for woh, which are too short to guess from, so every Hindi word
was admitted in exact match mode and the generalisation this whole feature
exists for never applied to half of what this user says.
"""
import pytest

from dictator import hindi, vocab


@pytest.mark.parametrize("spellings", [
    ["chaahie", "chahiye", "chahie"],
    ["vo", "woh", "wo"],
    ["hisab", "hisaab"],
    ["abhee", "abhi"],
    ["tumaree", "tumhari", "tumhaari"],
    ["khula", "khulla"],
    ["jaroori", "zaroori"],
    ["mujhe", "muje"],
])
def test_spellings_of_one_word_agree(spellings):
    keys = {hindi.key(w) for w in spellings}
    assert len(keys) == 1, f"{spellings} gave {keys}"


@pytest.mark.parametrize("a,b", [
    ("chahiye", "hisaab"), ("woh", "yeh"), ("abhi", "sabhi"),
    ("kaam", "naam"), ("bada", "bura"),
])
def test_different_words_stay_different(a, b):
    assert hindi.key(a) != hindi.key(b)


@pytest.fixture
def v(monkeypatch):
    box = vocab.Vocab()
    box.terms = {}
    box.save = lambda: None
    monkeypatch.setattr(box, "spoken",
                        lambda **kw: ["english", "line", "sahi", "hai"])
    for t in ("chahiye", "hisaab", "abhi", "tumhari", "Whisper Flow"):
        box.terms[t] = box.admit(t)
    return box


@pytest.mark.parametrize("said,want", [
    ("mujhe chaahie tha", "mujhe chahiye tha"),
    ("vo abhee bhi khula hai", "vo abhi bhi khula hai"),
    ("mere hisab se", "mere hisaab se"),
    ("tumaree baat", "tumhari baat"),
])
def test_a_hindi_spelling_is_corrected(v, said, want):
    assert v.fix(said) == want


@pytest.mark.parametrize("line", [
    # "sahi hai" keys to sahie, one character from chahiye's cahie, and a
    # single character of slack on a five character key was enough to rewrite
    # it. The Hindi key has to match exactly, never approximately.
    "tumaree baat sahi hai",
    "sahi hai bhai",
    "yeh sahi hai na",
    "this is the English line",
])
def test_a_near_miss_is_not_rewritten(v, line):
    out = v.fix(line)
    assert "chahiye" not in out or "chahiye" in line, out


def test_english_matching_still_generalises(v):
    assert v.fix("I use whisper floor") == "I use Whisper Flow"


def test_a_hindi_word_is_no_longer_exact_only(v):
    """This is the whole point: before the Hindi key, chahiye keyed to XHY,
    was refused as too short to guess from, and only ever matched itself."""
    assert v.terms["chahiye"]["mode"] == "fuzzy"
