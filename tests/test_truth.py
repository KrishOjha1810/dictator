"""Writing down what was actually said, and measuring against it.

Every accuracy number in this project until now counts words in neither
dictionary, which is blind by construction to a model swapping one real word
for another. docs/findings.md has the case that matters: a Hindi sentence came
back as fluent English, scored zero, and was wrong about every word.

These cover the two halves: collecting references cheaply enough that somebody
actually does it, and scoring honestly once they exist.
"""
import json
import sys
from pathlib import Path

import pytest

from dictator import truth

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import wer as scorer                                   # noqa: E402


def _wav(tmp_path, stem, secs=4.0):
    import struct
    import wave
    p = truth.CORPUS / f"{stem}.wav"
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * int(16000 * secs))
    return p


def test_the_sample_is_the_same_every_time(tmp_path):
    """Stopping halfway and coming back has to continue the same set, or the
    references are of forty different recordings and cover none of them."""
    for i in range(20):
        _wav(tmp_path, f"17900000000{i:02d}")
    first = [w.stem for w in truth.sample(10)]
    assert first == [w.stem for w in truth.sample(10)]


def test_the_sample_is_drawn_rather_than_chosen(tmp_path):
    """A reference set made of the holds somebody remembered as bad measures
    the bad ones, and the number that comes out of it is not an error rate."""
    for i in range(30):
        _wav(tmp_path, f"17900000000{i:02d}")
    got = [w.stem for w in truth.sample(10)]
    ordered = sorted(w.stem for w in truth.candidates())[:10]
    assert got != ordered, "it is taking the first ten, not a sample"


def test_a_recording_too_short_to_judge_is_not_offered(tmp_path):
    _wav(tmp_path, "1790000000001", secs=0.5)
    _wav(tmp_path, "1790000000002", secs=5.0)
    stems = [w.stem for w in truth.candidates()]
    assert "1790000000002" in stems
    assert "1790000000001" not in stems


def test_a_reference_records_whether_it_was_corrected(tmp_path):
    """The difference between a reference and a rubber stamp. Somebody who
    pressed Return forty times has written forty references that say the model
    was right, and a later reader needs to be able to see that."""
    w = _wav(tmp_path, "1790000000003")
    truth.save(w, "what I said", heard="what it heard")
    assert truth.load(w)["changed"] is True
    truth.save(w, "same thing", heard="same thing")
    assert truth.load(w)["changed"] is False


def test_what_the_model_said_is_offered_from_beside_the_recording(tmp_path):
    """The transcript kept when the hold was captured, because that is what
    the shipped pipeline produced. Transcribing it fresh would offer a
    different answer from the one the user saw."""
    w = _wav(tmp_path, "1790000000004")
    w.with_suffix(".txt").write_text("what the product   actually said\n")
    assert truth.guess(w) == "what the product actually said"


def test_progress_counts_only_the_sample(tmp_path):
    for i in range(10):
        _wav(tmp_path, f"17900000001{i:02d}")
    g = truth.progress(5)
    assert g["total"] == 5 and g["done"] == 0 and g["left"] == 5
    truth.save(truth.sample(5)[0], "said", "said")
    assert truth.progress(5)["done"] == 1


# ---- the scoring -----------------------------------------------------------

def test_an_identical_transcript_scores_zero():
    assert scorer.wer("hello world", "hello world") == 0.0


def test_one_word_wrong_in_three_is_a_third():
    assert round(scorer.wer("hello world there", "hello word there"), 3) == 0.333


@pytest.mark.parametrize("a,b", [
    ("mujhe yeh chahiye", "mujhe yeh chahie"),
    ("woh kar do", "wo kar do"),
])
def test_two_spellings_of_one_hindi_word_are_not_an_error(a, b):
    """Romanised Hindi has no settled spelling, so counting "chahiye" against
    "chahie" measures the speaker's keyboard rather than the model. Plain WER
    does count it, which is why both numbers are reported."""
    assert scorer.wer_sound(a, b) == 0.0
    assert scorer.wer(a, b) > 0.0


def test_english_is_scored_exactly_because_it_has_one_spelling():
    """The "pool rekvest" detector. A coding tool that mangles technical
    English is useless whatever its average looks like."""
    got, total = scorer.eng_exact("the pull request is ready",
                                  "the pool rekvest is ready")
    assert total > 0
    assert got < total, "it did not notice the mangled words"
    got, total = scorer.eng_exact("the pull request is ready",
                                  "the pull request is ready")
    assert got == total


def test_an_empty_reference_does_not_divide_by_zero():
    assert scorer.wer("", "anything") >= 0
    assert scorer.eng_exact("", "anything") == (0, 0)
