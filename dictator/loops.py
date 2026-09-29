"""Catch the decoder talking to itself.

When whisper is given too small an encoder for the audio it is holding, it
stops transcribing and starts repeating. It comes out in two shapes, and both
are in the real corpus:

    ndernderndernder            one short unit inside a single token
    It's a little bit. It's a little bit. It's a little bit.

Neither is speech and neither is detectable by loudness. That was checked
rather than assumed: the two recordings in the corpus that produced a loop
measure 0.032 and 0.018 RMS, which is LOUDER than a dozen recordings of real
speech, the quietest of which ("I don't know") sits at 0.0079. A loudness gate
would have thrown away real short utterances and kept both loops.

What does separate them is the shape of the output, which is what this module
reads. The point of catching it is that the cause is ours: docs/findings.md
records that undershooting `audio_ctx` produces exactly this, and that running
the same audio through the full encoder produces real words instead. So a loop
is a reason to try again, not a reason to paste it.
"""
import re

# Below this a repeated unit is ordinary English. "murmur" is "mur" twice,
# "banana" has "ana" in it, and "hahaha" is a real thing people say. Loops in
# the corpus run to sixteen characters and beyond.
MIN_TOKEN = 8

# Twice is a stutter or a real repetition ("very very good"). Three times in a
# row is the decoder stuck.
MIN_REPEATS = 3

_WORD = re.compile(r"[^\W\d_]{%d,}" % MIN_TOKEN, re.UNICODE)
# Commas count as breaks, not only full stops. The loop turbo produced on a
# real hold was "I think, I think, I think, I think", which a full-stop split
# reads as one long sentence and lets through.
_SENTENCE = re.compile(r"[^.!?,;]+")


def _repeats_within(token: str) -> bool:
    """Is this token one short unit written over and over."""
    t = token.lower()
    n = len(t)
    for size in range(1, n // MIN_REPEATS + 1):
        unit = t[:size]
        reps = 1
        while t.startswith(unit * (reps + 1)):
            reps += 1
        # The tail does not have to be a whole unit: "plplplplar" is "pl" four
        # times and then something else, and it is still a loop.
        if reps >= MIN_REPEATS and reps * size >= MIN_TOKEN:
            return True
    return False


# Short clauses are dropped before the run is counted, which deliberately
# treats "a, vaulted, a, vaulted, a, vaulted" as three of the same thing with
# filler between. Six rather than four, so that "okay, okay, okay" and "right,
# right, right", which people genuinely say, are left alone.
MIN_CLAUSE = 6


def _repeats_across(text: str) -> bool:
    """Is the same clause being said over and over."""
    parts = [p.strip().lower() for p in _SENTENCE.findall(text) if p.strip()]
    parts = [p for p in parts if len(p) >= MIN_CLAUSE]
    if len(parts) < MIN_REPEATS:
        return False
    run = 1
    for a, b in zip(parts, parts[1:]):
        run = run + 1 if a == b else 1
        if run >= MIN_REPEATS:
            return True
    return False


def looped(text: str) -> bool:
    """Is this the decoder repeating itself rather than transcribing.

    Answering True is a claim that the audio was NOT transcribed, so it has to
    be wrong rarely: the caller's response is to spend another few seconds
    running the model again."""
    t = (text or "").strip()
    if not t:
        return False
    if any(_repeats_within(w) for w in _WORD.findall(t)):
        return True
    return _repeats_across(t)


def why(text: str) -> str:
    """A line for the log saying which shape was seen, or ""."""
    t = (text or "").strip()
    for w in _WORD.findall(t):
        if _repeats_within(w):
            return f"a token repeating itself: {w[:40]!r}"
    if _repeats_across(t):
        return "the same sentence three times over"
    return ""
