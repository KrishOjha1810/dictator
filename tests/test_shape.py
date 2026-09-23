"""What shaping a transcript is allowed to do, and mostly what it is not.

Most of this file is the second kind. The failure that matters here is not a
list somebody wanted and did not get, it is a sentence that was restructured
because it happened to start with "first of all". So the ordinary sentences,
the Hinglish, and the speech about code are the tests that count.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictator.shape import shape, drop_fillers


def on(text):
    """Everything on, including the list rule that normally has to be asked for."""
    return shape(text, lists=True)


# --- things that must come out exactly as they went in ----------------------

UNCHANGED = [
    # The one in the brief: a connective, not a list.
    "First of all, thanks for coming.",
    "First of all, thanks. Second of all, sorry I am late.",
    "First and foremost, the loop is slow.",
    "First off, I did not break it.",
    # An ordinal that is part of the sentence rather than in front of it.
    "He came first, she came second, I came third.",
    "The first thing is the build, the second thing is the tests.",
    "At first it looked fine.",
    "In the first place, nobody asked.",
    # Time, not counting.
    "Give me one second, two minutes at the most.",
    "Wait a second, that is not what I said.",
    # Counting is not a list.
    "One, two, three, testing.",
    # Punctuation words being used as words.
    "There is a comma missing in that line.",
    "The colon is inflamed, says the doctor.",
    "Put a question mark at the end of that.",
    "I said the word comma out loud.",
    # Numbers are never touched, in any direction.
    "It went up by one point something percent.",
    "Version two point five is the one that works.",
    "Chapter one covers the basics.",
    # Speech about code.
    "Check package.json and then run the build.",
    "useState is not defined in that file.",
    "The value of x is 3.5 and it should be 4.0.",
    "iPhone and gRPC both keep their own spelling.",
    # Ordinary sentences with nothing to do.
    "The loop is slow and I do not know why.",
    "Ship it.",
]


def test_ordinary_speech_is_left_alone():
    for text in UNCHANGED:
        assert on(text) == text, text


HINGLISH_UNCHANGED = [
    # The sentence from the brief. One marker is never a list, in any language.
    "Pehla point yeh hai ki the loop is slow.",
    "Dusra point yeh hai ki the tests are flaky.",
    "Yaar ye function thoda slow lag raha hai, can you check the loop.",
    "Mujhe ek second do, main dekh raha hoon.",
    "Iska pehla version hi theek tha.",
    "Teesra option bhi hai but woh mehnga hai.",
]


def test_hinglish_is_left_alone():
    for text in HINGLISH_UNCHANGED:
        assert on(text) == text, text


def test_the_switch_really_switches_it_off():
    spoken = "hello comma world question mark first, do x. second, do y. third, do z"
    assert shape(spoken, enabled=False) == spoken


def test_each_rule_can_be_turned_off_on_its_own():
    text = "first, fix the loop. second, add a test. third, ship it."
    assert shape(text, lists=False) == "First, fix the loop. Second, add a test. Third, ship it."
    assert shape("hello comma world", punctuation=False) == "Hello comma world"
    assert shape("hello comma world", sentences=False) == "hello, world"


def test_lists_are_off_unless_asked_for():
    """The default has to be the safe one: this is the only rule that moves
    the user's words around."""
    text = "first, fix the loop. second, add a test. third, ship it."
    assert "\n" not in shape(text)


def test_empty_and_blank_survive():
    assert shape("") == ""
    assert shape("   ") == "   "


# --- spoken punctuation -----------------------------------------------------


def test_spoken_punctuation_becomes_characters():
    assert shape("hello comma world") == "Hello, world"
    assert shape("is it done question mark") == "Is it done?"
    assert shape("ship it exclamation mark") == "Ship it!"
    assert shape("that is done full stop") == "That is done."


def test_the_recogniser_s_own_comma_is_absorbed():
    """It hears the pause before the spoken word and writes a comma there, so
    without this every substitution arrives doubled."""
    assert shape("Hello, comma, world.") == "Hello, world."
    assert shape("It works, question mark") == "It works?"


def test_new_line_keeps_the_sentence_s_own_full_stop():
    assert shape("that is done. new line next thing") == "That is done.\nNext thing"
    assert shape("one thing. new paragraph another thing") == "One thing.\n\nAnother thing"


def test_quotes():
    assert shape("he said open quote hello close quote to me") == 'He said "hello" to me'
    # Paired, so it wraps.
    assert shape("he said inverted commas slow inverted commas and moved on") == \
        'He said "slow" and moved on'


def test_a_single_inverted_commas_is_not_believed():
    """One of a pair is somebody talking about quoting. Converting it leaves a
    stray quote mark, which is worse than doing nothing."""
    text = "Put that bit in inverted commas."
    assert on(text) == text


def test_joining_punctuation_has_no_spaces_round_it():
    assert shape("a well hyphen known problem") == "A well-known problem"
    assert shape("read write forward slash execute") == "Read write/execute"


def test_at_the_rate_is_only_an_address_when_it_is_one():
    # An address keeps its own case: a token with an @ in it is not prose.
    assert shape("krish at the rate example dot com") == "krish@example dot com"
    assert on("It grew at the rate of five percent.") == "It grew at the rate of five percent."


def test_period_is_not_a_full_stop():
    """A noun this user says often, and "full stop" already covers the intent."""
    assert on("The grace period is over.") == "The grace period is over."
    assert on("What is the period of the loop?") == "What is the period of the loop?"


# --- lists ------------------------------------------------------------------


def test_three_ordinals_make_a_list():
    assert on("first, fix the loop. second, add a test. third, ship it.") == (
        "1. Fix the loop.\n2. Add a test.\n3. Ship it."
    )


def test_a_preamble_stays_above_the_list():
    assert on("here is the plan. first, fix the loop. second, add a test. third, ship it.") == (
        "Here is the plan.\n1. Fix the loop.\n2. Add a test.\n3. Ship it."
    )


def test_two_ordinals_are_not_enough():
    text = "First, fix the loop. Second, add a test."
    assert on(text) == text


def test_counting_words_need_the_pause_written_down():
    assert on("one, buy the milk, two, buy the eggs, three, buy the bread") == (
        "1. Buy the milk\n2. Buy the eggs\n3. Buy the bread"
    )
    # Same words, no pauses, so no evidence. Only the sentence capital moves.
    text = "One buy the milk two buy the eggs three buy the bread"
    assert on(text) == text


def test_a_broken_sequence_cancels_the_whole_thing():
    text = "First, fix the loop. Third, ship it. Second, add a test."
    assert on(text) == text


def test_a_stray_ordinal_later_cancels_it_too():
    text = ("First, fix the loop. Second, add a test. Third, ship it. "
            "First, I need coffee though.")
    assert on(text) == text


def test_markers_with_nothing_behind_them_are_not_items():
    text = "First, no. Second, no. Third, no."
    assert on(text) == text


def test_the_trailing_and_belongs_to_the_sentence():
    assert on("first, wake up, second, drink coffee, and third, write code") == (
        "1. Wake up\n2. Drink coffee\n3. Write code"
    )


def test_a_hinglish_list_works_when_it_really_is_one():
    assert on("pehla, loop theek karo. dusra, test likho. teesra, ship kar do.") == (
        "1. Loop theek karo.\n2. Test likho.\n3. Ship kar do."
    )


def test_number_one_is_a_marker_without_a_pause():
    assert on("number one fix the loop number two add a test number three ship it") == (
        "1. Fix the loop\n2. Add a test\n3. Ship it"
    )


def test_a_marker_before_a_copula_is_a_subject_not_an_item():
    """"Point one is the loop" is a statement about point one. Turned into an
    item it reads "1. is the loop", which is not what anybody said."""
    text = "Point one is the loop, point two is the query, point three is the cache."
    assert on(text) == text
    assert on("Number one is shipping.") == "Number one is shipping."


def test_an_explicit_enumeration_word_works_without_pauses():
    assert on("step one, fix the loop, step two, add a test, step three, ship it") == (
        "1. Fix the loop\n2. Add a test\n3. Ship it"
    )
    # Bare labels with nothing behind them are still not a list.
    assert on("Step one, step two, step three.") == "Step one, step two, step three."


def test_digits_the_recogniser_already_wrote_count_as_markers():
    assert on("1. fix it 2. test it 3. ship it") == "1. Fix it\n2. Test it\n3. Ship it"


def test_nothing_is_ever_removed_as_filler():
    """A leading "so" can carry the condition of the whole sentence, and this
    is where every rewriting formatter loses meaning. Words stay."""
    text = "So if the loop is slow, first check the index, then check the query."
    assert on(text) == text


def test_bullets_are_explicit_so_two_are_enough():
    assert on("bullet point buy the milk bullet point buy the eggs") == (
        "- Buy the milk\n- Buy the eggs"
    )


def test_talking_about_bullets_is_not_asking_for_them():
    text = "The bullet points I sent you were wrong, every bullet point of them."
    assert on(text) == text


# --- capitals and spacing ---------------------------------------------------


def test_sentences_get_a_capital():
    assert shape("the loop is slow. it always was.") == "The loop is slow. It always was."


def test_commands_keep_their_lowercase():
    """Dictating into a terminal is one of the things this is for, and
    "Git push" does not run."""
    assert shape("git push origin main. npm install after that.") == (
        "git push origin main. npm install after that."
    )


def test_a_word_wearing_punctuation_is_still_a_word():
    assert shape("is it done question mark. yes. ship it.") == "Is it done? Yes. Ship it."


def test_code_shaped_words_keep_their_shape():
    assert shape("useState is fine. package.json is not.") == (
        "useState is fine. package.json is not."
    )


def test_spacing_is_tidied_but_nothing_is_invented():
    assert shape("hello   world ,  again") == "Hello world, again"
    # No space is inserted after a full stop that never had one.
    assert shape("open package.json now") == "Open package.json now"


def test_shaping_twice_changes_nothing_the_second_time():
    for text in ["first, fix the loop. second, add a test. third, ship it.",
                 "hello comma world question mark",
                 "The loop is slow."]:
        once = on(text)
        assert on(once) == once, text


@pytest.mark.parametrize("said,want", [
    ("Before we didn't used to take in uh and all of these",
     "Before we didn't used to take in and all of these"),
    ("Get back to me with the plans and uh proper fix",
     "Get back to me with the plans and proper fix"),
    # Lowercase in, lowercase out: capitalising is the sentences stage's job,
    # and doing it here would fight it.
    ("um so uh what I meant was hmm the loop",
     "so what I meant was the loop"),
])
def test_thinking_sounds_are_removed(said, want):
    """Parakeet is verbatim and writes them down. Whisper drops them, which is
    why they appeared the moment English started going to Parakeet again."""
    assert drop_fillers(said) == want


@pytest.mark.parametrize("said", [
    # Every one of these means something, and a vendor that strips them has
    # documented what it costs: a leading "so" carries a condition, and
    # deliberate repetition carries emphasis.
    "So the loop is slow and I cannot tell why",
    "I mean, you know, actually it works like that",
    "Like for like, the numbers are the same",
    "Right, so, the thing is",
])
def test_words_that_carry_meaning_are_left_alone(said):
    assert drop_fillers(said) == said


def test_a_sentence_of_nothing_but_filler_survives():
    """Returning an empty string would look like a failed transcription."""
    assert drop_fillers("um uh hmm") == "um uh hmm"
