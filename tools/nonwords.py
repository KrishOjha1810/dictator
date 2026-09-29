#!/usr/bin/env python3
"""How much of a transcript is not a word in either language.

Two speech models can be compared on real audio with no reference text at all,
which matters because writing references is the one part of a benchmark that
cannot be delegated and the audio is sitting there now.

The signal is narrow and it is the one that decides this product: when a model
mangles an English technical word it does not produce a different English
word, it produces something that is not a word at all. "pull request" comes
back as "pool rekvest", "accuracy" as "ekyoorisee". Those are detectable
without knowing what was said, because they are in neither dictionary.

It is a lower bound on the damage, not a word error rate. A genuine mishearing
of one real word for another (Hinglish heard as English) is invisible here,
and a rare proper noun counts as a miss when it is not one. Read it as "how
much of this output is gibberish", compared between models on the same audio,
never as an accuracy score on its own.

Read `unknown()` before you believe `score()`. This tool first reported 2.35%
on the real corpus, of which 2.0 points were words it did not know rather than
words the model got wrong: ordinary past tenses, superlatives, "has", and the
terms this person says every day. The true figure was 0.37%. The list of
offending words took a minute to read and moved the answer by a factor of six;
the number alone had been believed for a day. A summary statistic over a
dictionary you did not write will measure the dictionary.

The opposite failure is worse and quieter: a dictionary loose enough to accept
anything scores every model as perfect. Both directions are asserted in
tests/test_nonwords.py, and any change belongs in that file first.

The dictionaries themselves now live in dictator/known.py, because the product
needs the same answer to decide which words to ask the user about.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictator.known import (ALLOW, ENGLISH, HINDI, HINDI_KEYS,  # noqa: E402,F401
                            _known, score, unknown)

if __name__ == "__main__":
    for line in sys.stdin:
        s = score(line)
        print(f"{s['share']:.2f}  {s['unknown']:3d}/{s['words']:3d}  "
              f"{', '.join(s['examples'])}")
