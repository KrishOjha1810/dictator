"""The measuring instrument, which was wrong by a factor of six.

`tools/nonwords.py` scores a transcript by the share of its words that are in
neither dictionary. It is the only judge of a speech model this project has,
because nobody has written reference transcripts by hand. So a gap in its
dictionaries is not a rounding error, it is the tool reporting the model as
wrong about words the model got right.

On the real corpus it said 2.35%. Of that, 2.0 points were its own gaps:
ordinary past tenses, superlatives, "has", and the terms this person says
every day. The genuine figure is 0.37%. These tests exist so that never
silently comes back, in either direction: the second half is as important as
the first, because a tool that accepts everything scores zero on gibberish.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import nonwords                                              # noqa: E402


@pytest.mark.parametrize("word", [
    # A silent e is dropped before a vowel suffix, and putting it back is the
    # single rule that accounted for most of the false alarms.
    "delegated", "approved", "preparing", "liquidated", "completed",
    "including", "managed", "deriving", "updating", "arriving", "introduced",
    # Comparatives and superlatives, which had no rule at all.
    "simplest", "smallest", "earlier", "quickly",
    # Short stems. "using" is five letters and the old floor wanted six.
    "using", "taking", "coming", "making",
    # Words the system word list simply does not contain. "has" is one of
    # them, which is the clearest evidence it cannot be read as a record of
    # English.
    "has", "held", "paid", "became", "hang",
    # British spelling, against a dictionary holding only the z form.
    "finalised", "organised",
])
def test_ordinary_english_is_not_reported_as_invented(word):
    assert nonwords._known(word), f"{word} is a real word"


@pytest.mark.parametrize("word", [
    # Real failures taken from real recordings in the corpus. Every one of
    # these is the model mangling something, and the tool exists to count them.
    # The corpus also contains mangled attempts at real people's names, which
    # are the same shape and are deliberately not copied into a public test
    # file; "zhrkvan" stands in for one of them.
    "rekvest", "progrem", "darived", "deploi", "collater", "accura", "acur",
    "ndernderndernder", "semesnirkkorpray", "lrdr", "bnvay", "checkmone",
    "zhrkvan",
])
def test_mangled_speech_is_still_caught(word):
    assert not nonwords._known(word), f"{word} is not a word and must count"


def test_a_suffix_rule_cannot_launder_a_truncation():
    """Restoring a silent e after -er turns "collater", a real truncation of
    "collateral", into "collate". Comparatives are rarer in speech than
    truncations, so -er does not get the rule."""
    assert not nonwords._known("collater")
    assert nonwords._known("collate")


def test_correct_and_mangled_versions_of_the_same_phrase_score_apart():
    assert nonwords.score("pull request")["unknown"] == 0
    assert nonwords.unknown("pool rekvest") == ["rekvest"]


def test_romanised_hindi_counts_as_words_however_it_is_spelled():
    for t in ("mujhe yeh chahiye", "mujhe yeh chahiyeee", "woh kar do"):
        assert nonwords.score(t)["unknown"] == 0, t


def test_letter_salad_scores_as_badly_as_it_can():
    """The guard against the opposite failure: a dictionary loose enough to
    accept anything reports every model as perfect."""
    import random
    import string
    random.seed(7)
    junk = " ".join("".join(random.choice(string.ascii_lowercase)
                            for _ in range(random.randint(5, 9)))
                    for _ in range(60))
    s = nonwords.score(junk)
    assert s["unknown"] >= s["words"] * 0.9, s


def test_a_repetition_loop_is_counted_rather_than_shrugged_off():
    """The failure that made a model look bad in the first benchmark. It has
    to be visible, because the audio_ctx setting that causes it is ours."""
    assert nonwords.score("iririririr plplplplar")["unknown"] == 2
