"""Output in an alphabet the speaker has never used.

This product transcribes English and Hindi. English arrives in Latin, Hindi
arrives either romanised or in Devanagari, and `roman.py` converts the second
into the first on the way out. Nothing in that path can legitimately produce
Cyrillic, Greek, Arabic, Han or Hiragana, and yet all five have been delivered
to a user's cursor.

Measured on real holds rather than imagined. Of 270 utterances in one install's
history, 12 contained characters from none of the scripts above, and every one
was pasted. Running the 25 shortest recordings in the benchmark corpus through
the current pipeline, 2 came back like this, from 0.67 and 1.05 seconds of
audio:

    のrdrdrd《é評' pens dużetetet c? c? dużuwuwuwuwuwuwof
    ,??? gy i i????????????????????????????????

Most of it comes from Parakeet, which has no language but English, so an answer
in Cyrillic is not a mistranscription at all, it is the model telling us it had
nothing. The router already rejects that 82 times in one log, by other means,
and these are the ones its heuristics miss. A script check catches all of them
and is a dozen lines.

Two different faults, so two different answers:

  **A replacement character** (U+FFFD) is not speech and never was. It is what
  `errors="replace"` leaves where the engine emitted a byte that was not valid
  UTF-8, which happens when a hold ends mid-character. The words around it are
  real and worth keeping, so these are simply removed.

  **A foreign script** means the engine was not transcribing. Dropping the
  characters would leave a sentence with holes in it that reads as if the user
  said something they did not, so the whole answer is refused and the caller
  decides what to do instead.
"""
import re
import unicodedata

# U+FFFD, left by a decoder where the engine wrote a byte that was not UTF-8.
# Carries no information by construction: it is the absence of a character.
BROKEN = "�"

# Scripts this product can legitimately produce. Latin for English and
# romanised Hindi, Devanagari because the multilingual model answers in it and
# roman.py converts it afterwards, so refusing it here would throw away a
# correct answer one step before it is made readable.
ALLOWED = {"LATIN", "DEVANAGARI", "COMMON", "INHERITED"}

_WORDISH = re.compile(r"\w", re.UNICODE)


def _script(ch: str) -> str:
    """Which alphabet a character belongs to, as a word.

    Python has no script property, so this reads the first word of the Unicode
    name, which is the script for every letter and "GREEK"/"CYRILLIC"/"CJK"
    exactly where it needs to be. Punctuation, digits and spaces have names
    that start elsewhere, so they are answered as COMMON by the caller rather
    than looked up here."""
    try:
        return unicodedata.name(ch).split()[0]
    except ValueError:
        return "COMMON"


def foreign(text: str) -> list:
    """The characters in an alphabet this product cannot have meant to write.

    Digits, punctuation and whitespace are not letters and are never foreign.
    An accented Latin letter is Latin."""
    out = []
    for ch in text or "":
        if ch == BROKEN:
            continue                     # handled separately, see `repair`
        if not _WORDISH.match(ch):
            continue                     # punctuation, spaces, symbols
        if ch.isascii():
            continue                     # the overwhelmingly common case
        if _script(ch) not in ALLOWED:
            out.append(ch)
    return out


def repair(text: str) -> str:
    """Remove the characters a broken decode left behind, and nothing else.

    `errors="replace"` keeps the words around a bad byte, which is the right
    trade against losing the hold. What it leaves in their place is not a
    character the user said and must not reach their cursor."""
    if not text or BROKEN not in text:
        return text
    # Collapse the whitespace a removal leaves doubled, because "a ? b" would
    # otherwise become "a  b" and the join is invisible in a diff.
    return re.sub(r"\s{2,}", " ", text.replace(BROKEN, "")).strip()


# A hold that ends mid-character leaves one replacement per bad byte, so a
# truncation is a handful of them whatever the sentence length. Thirty of them
# is not a truncation, it is an engine that was not transcribing: one real
# 1.05s hold came back as ",??? gy i i????????????????????????????????", which
# after repair reads ", gy i i" and is not worth pasting either.
MAX_BROKEN = 5


def usable(text: str, limit: float = 0.02) -> bool:
    """Is this an answer at all, or an engine saying it had nothing.

    `limit` is a share of the letters rather than a count, so one stray
    character in a long sentence is tolerated and a short answer made entirely
    of them is not. Two percent: the real failures measured here are 30% to
    100% foreign, and a correct transcript is 0%, so anything in between is a
    gap nothing has been seen in."""
    raw = text or ""
    if raw.count(BROKEN) > MAX_BROKEN:
        return False
    t = repair(raw)
    if not t.strip():
        return True                      # empty is not this module's problem
    letters = [c for c in t if _WORDISH.match(c)]
    if not letters:
        return True
    return (len(foreign(t)) / len(letters)) <= limit
