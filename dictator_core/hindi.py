"""A phonetic key for Hindi written in English letters.

The vocabulary matches words by sound so that one correction covers its
variants: teach it "Whisper Flow" and "whisper flows" and "whispa flo" are
fixed too. That works because metaphone is a good model of how English is
spelled. It is a bad model of how Hindi is spelled in Latin letters, and the
keys it produces are short and uninformative:

    chahiye -> XHY      woh -> W      abhi -> ABH      hisaab -> HSB

Short keys are refused as too risky to guess from, so every Hindi word ended
up in exact match mode and the generalisation never applied to the half of
this user's speech that is Hindi.

The variation in romanized Hindi is not arbitrary. It is almost entirely in
which vowel spelling someone picked and which of a few interchangeable
consonants, because there is no standard and people write what looks right:

    chaahie / chahiye / chahie      vo / woh / wo
    hisab / hisaab                  abhee / abhi
    tumaree / tumhari

So the key normalises exactly that variation and leaves the skeleton alone.
It is not a transliteration and it is not reversible. It only has to give the
same answer for two spellings of the same word, and different answers for
different words.
"""
import re

_VOWELS = "aeiou"

# Spellings that differ only by which letter somebody reached for. These are
# the ones that actually vary in the wild, not every theoretical equivalence.
_PAIRS = (
    ("ph", "f"),      # phone / fone
    ("kh", "k"), ("gh", "g"), ("ch", "c"), ("jh", "j"),
    ("th", "t"), ("dh", "d"), ("bh", "b"), ("sh", "s"),
    ("w", "v"),       # woh / voh
    ("z", "j"),       # zaroori / jaroori
    ("y", "i"),       # chahiye / chahie
    ("q", "k"), ("x", "ks"),
)


def key(word: str) -> str:
    """The sound of a romanized Hindi word, as a comparable string."""
    w = re.sub(r"[^A-Za-z]", "", (word or "")).lower()
    if not w:
        return ""
    # Aspiration and letter choice first, longest pairs before single letters
    # so "ph" is not eaten by the "h" handling below.
    for a, b in _PAIRS:
        w = w.replace(a, b)
    # A trailing h is decoration on an open syllable: woh, yeh, kah. A bare h
    # after a consonant is the same thing spelled inside the word: tumhari and
    # tumaree are one word. Aspirated pairs were already folded above, so what
    # is left here is decoration rather than a sound.
    w = re.sub(r"h+$", "", w)
    w = re.sub(r"(?<=[bcdfgjklmnprstvi])h", "", w)
    # Long vowels first, because these are specific spellings and collapsing
    # every double letter ahead of them would turn "abhee" into "abe" and lose
    # the i that makes it "abhi".
    w = w.replace("ee", "i").replace("oo", "u").replace("ai", "e")
    # What is left is length that nobody spells consistently (chaahie, hisaab)
    # and doubled consonants (khulla, achha).
    w = re.sub(r"(.)\1+", r"\1", w)
    return w


def looks_hindi(word: str) -> bool:
    """A rough test for whether this word is Hindi rather than English.

    Deliberately weak. It only has to decide whether the Hindi key is worth
    trying as well, never whether to rewrite anything, so a wrong answer costs
    one extra comparison."""
    w = re.sub(r"[^A-Za-z]", "", (word or "")).lower()
    if len(w) < 3:
        return False
    # Vowel spellings that English does not use this way.
    if re.search(r"aa|ee(?!r)|oo(?!r)|ij|kh|gh|jh|bh|dh(?!e)|th(?=[aiou])", w):
        return True
    # Hindi in Latin letters is overwhelmingly alternating consonant vowel.
    vowels = sum(1 for c in w if c in _VOWELS)
    return 0.3 <= vowels / len(w) <= 0.6
