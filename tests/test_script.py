"""Output in an alphabet the speaker has never used.

Every string here is a real one, taken from a user's history or produced by
running the benchmark corpus through the shipped pipeline. The product
transcribes English and Hindi; Cyrillic, Greek, Arabic, Han and Hiragana have
all reached a cursor.

The strings are written as escapes rather than as characters so that nothing
between here and the test runner can quietly normalise them into something
that passes.
"""
import pytest

from dictator import script


REAL_FAILURES = [
    # 0.67s of audio from the corpus, through the current pipeline:
    # Hiragana, Han, a CJK bracket, Polish, and two broken bytes.
    "\u306e" "rdrdrd" "\u300a\u00e9\u8a55" "' pens du\u017cetetet "
    "c\ufffd c\ufffd du\u017cuwuwuwof",
    # Parakeet, which has no language but English, answering in Cyrillic.
    "\u041a\u043e\u043d\u043e\u0440.",
    "\u042d\u0441\u043a\u0440\u043e\u0443.",
    "\u0421\u043b\u044d\u0433 \u0441\u043e\u043c\u0440\u0438.",
    # turbo, answering a Hindi sentence in Arabic script.
    "\u0645\u0646\u0646 \u062a\u06be\u06cc\u0644\u0631\u0631",
]

REAL_TRANSCRIPTS = [
    "the pull request is ready for review",
    "mujhe yeh chahiye, aur kya",
    "Signer here would be Alice.",
    "I understood the borrower struct, but the accuracy interest",
    # Devanagari is a CORRECT intermediate answer: roman.py converts it on
    # the way out, so refusing it here throws away a good hold one step
    # early.
    "\u0938\u093e\u0930\u0940 \u0932\u093f\u0902\u0915\u094d\u0938 verify kar lo",
    # Ordinary accented Latin is Latin.
    "naive caf\u00e9 r\u00e9sum\u00e9 jalape\u00f1o",
    # Punctuation, digits and symbols are not letters and are never foreign.
    "25 USDC into the vault, 100% done!",
]


@pytest.mark.parametrize("text", REAL_FAILURES)
def test_an_answer_in_another_alphabet_is_refused(text):
    assert not script.usable(text), text


@pytest.mark.parametrize("text", REAL_TRANSCRIPTS)
def test_a_real_transcript_is_kept(text):
    """The half that matters more. Refusing a good hold costs the user their
    words, which is the failure this whole product is built around
    avoiding."""
    assert script.usable(text), text


def test_devanagari_is_not_foreign():
    assert script.foreign("\u0938\u093e\u0930\u0940 \u0932\u093f\u0902\u0915\u094d\u0938") == []


def test_the_offending_characters_are_named_and_the_others_left_alone():
    got = script.foreign("hello \u041a\u043e\u043d\u043e\u0440 world")
    assert got and all(ord(c) > 127 for c in got)
    assert "h" not in got and " " not in got


def test_a_broken_byte_is_removed_and_the_words_around_it_kept():
    """errors="replace" keeps the words around a byte that was not valid
    UTF-8, which is the right trade against losing the hold. What it leaves
    in their place is not a character anybody said."""
    assert script.repair("I don't kno\ufffdw") == "I don't know"
    assert script.repair("a \ufffd\ufffd b \ufffd c") == "a b c"
    assert "\ufffd" not in script.repair("\ufffd" * 3 + "hello")


def test_text_with_nothing_broken_in_it_is_returned_unchanged():
    same = "nothing to do here"
    assert script.repair(same) is same


def test_a_few_broken_bytes_are_a_truncation_and_many_are_not_an_answer():
    """A hold that ends mid-character leaves one replacement per bad byte, so
    a truncation is a few whatever the sentence length. One real 1.05s hold
    came back as thirty of them around four letters."""
    assert script.usable("I don't kno\ufffdw")
    assert script.usable("an ordinary sentence with one \ufffd somewhere in it")
    assert not script.usable(",\ufffd\ufffd\ufffd gy i i" + "\ufffd" * 28)


def test_an_empty_answer_is_not_this_module_to_judge():
    """Nothing transcribed is a different failure with a different cure, and
    answering False here would send the caller looking for a script"""
    assert script.usable("")
    assert script.usable("   ")


def test_one_stray_character_in_a_long_sentence_is_tolerated():
    """Measured: the real failures are 30% to 100% foreign and a correct
    transcript is 0%, so the threshold sits in a gap nothing has been seen
    in. Being strict here would cost a good hold over one character."""
    long = "this is a perfectly ordinary and quite long English sentence " * 2
    assert script.usable(long + "\u0438")


# ---- the guard where it actually runs --------------------------------------

def _whisper_answering(monkeypatch, tmp_path, text):
    """The multilingual path, with the engine made to answer `text`."""
    from dictator import stt

    class Done:
        stdout, stderr, returncode = text, "", 0

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"")
    monkeypatch.setattr(stt.subprocess, "run", lambda *a, **k: Done())
    monkeypatch.setattr(stt, "_transcribe_server", lambda w: None)
    monkeypatch.setattr(stt, "parakeet_ready", lambda: False)
    monkeypatch.setattr(stt, "whisper_bin", lambda: "/bin/true")
    monkeypatch.setattr(stt, "audio_seconds", lambda w: 6.0)
    monkeypatch.setattr(stt, "pinned_language", lambda w, l: "en")
    monkeypatch.setattr(stt, "stt_lang_mode", lambda: (wav, "en"))
    monkeypatch.setattr(stt, "_romanise", lambda t: t)
    return stt._transcribe_ex(str(wav))[0]


def test_the_multilingual_model_is_guarded_too(monkeypatch, tmp_path):
    """`_not_english` is applied to Parakeet's answer and to nothing else, so
    the model every Hinglish hold falls through to could return any alphabet
    and have it pasted. Three real ones were."""
    got = _whisper_answering(
        monkeypatch, tmp_path,
        "منن تھیلرر")
    assert got == "", got


def test_devanagari_from_the_multilingual_model_is_kept(monkeypatch, tmp_path):
    """It is a correct intermediate answer. Refusing it would throw away a good
    hold one step before roman.py makes it readable."""
    hindi = "सारी लिंक्स verify kar lo"
    assert _whisper_answering(monkeypatch, tmp_path, hindi) == hindi


def test_a_broken_byte_is_cleaned_out_of_the_answer(monkeypatch, tmp_path):
    got = _whisper_answering(monkeypatch, tmp_path, "the vault is kno�wn")
    assert "�" not in got
    assert "the vault is known" == got


def test_an_ordinary_answer_passes_through_untouched(monkeypatch, tmp_path):
    text = "I understood the borrower struct, but the accuracy interest"
    assert _whisper_answering(monkeypatch, tmp_path, text) == text
