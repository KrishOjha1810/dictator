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
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictator import hindi, roman          # noqa: E402

_WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def _english() -> set:
    try:
        return {w.strip().lower()
                for w in Path("/usr/share/dict/words").read_text().splitlines()
                if w.strip()}
    except Exception:
        return set()


def _hindi_roman() -> set:
    """Every romanisation the shipped lexicon knows, plus their phonetic keys,
    so a spelling variant of a known Hindi word is not counted as gibberish."""
    words, keys = set(), set()
    try:
        for line in roman._LEX.read_text().splitlines():
            if line.startswith("#") or "\t" not in line:
                continue
            w = line.split("\t")[1].strip().lower()
            if w:
                words.add(w)
                keys.add(hindi.key(w))
    except Exception:
        pass
    return words, keys


ENGLISH = _english()
HINDI, HINDI_KEYS = _hindi_roman()

# Sounds a person makes, and things a transcriber writes that are not words.
ALLOW = {"uh", "um", "uhm", "hmm", "mm", "erm", "ok", "okay", "yeah", "yep",
         "nope", "hi", "hey", "bro", "ya", "na", "haan", "nahi", "arre"}

# Words this person says constantly that a 1934 dictionary has never heard of.
# Without these the measurement is dominated by the tool not knowing what a
# repo is, which says nothing about the speech model.
ALLOW |= {
    "repo", "repos", "github", "git", "commit", "commits", "rebase", "merge",
    "config", "json", "api", "apis", "cli", "url", "urls", "app", "apps",
    "auth", "async", "backend", "frontend", "runtime", "regex", "linter",
    "npm", "python", "swift", "macos", "ios", "xcode", "homebrew", "brew",
    "whisper", "parakeet", "hinglish", "dictator", "voicebridge", "claude",
    "slack", "notion", "figma", "vercel", "docker", "kubernetes", "aws",
    "dm", "dms", "ui", "ux", "pr", "prs", "qa", "ci", "sdk", "mvp", "llm",
    "gpt", "chatgpt", "openai", "anthropic", "tokenizer", "embeddings",
    "latency", "throughput", "changelog", "readme", "workflow", "workflows",
    "plugin", "plugins", "dashboard", "endpoint", "endpoints", "webhook",
    "timestamp", "uuid", "env", "dev", "prod", "staging", "localhost",
    # What this person actually talks about. "pda" and "usdc" alone were a
    # third of everything this tool was calling gibberish, and both are
    # correct transcriptions of words he says several times a day.
    "pda", "pdas", "usdc", "ltv", "struct", "structs", "lib", "libs",
    "solana", "anchor", "blockchain", "devnet", "mainnet", "testnet",
    "onchain", "defi", "wallet", "wallets", "escrow", "tokenomics",
    "hyperlink", "hyperlinks", "playlist", "playlists", "checkpoint",
    "checkpoints", "info", "pdf", "pdfs", "etc", "etcetera", "wanna",
    "gonna", "gotta", "updation",
}

# Common English words the system word list does not contain. These are gaps in
# the instrument, not errors by the speech model, and leaving them out means
# measuring the dictionary instead of the transcript. "has" is in this list,
# which is enough on its own to show the word list cannot be trusted as a
# complete record of English.
ALLOW |= {"has", "held", "paid", "became", "repaid", "hang", "fuck",
          "fucking", "shit", "damn"}

# Romanised Hindi the list is missing. Added one at a time, from words that
# appeared in real recordings and were transcribed correctly.
ALLOW |= {"aao", "apno", "apna", "apne", "seedha", "seedhe", "sirf",
          "matlab", "thoda", "zyada", "bilkul", "wapas", "abhi"}


# A dictionary from 1934 has the singular and not the plural, the verb and not
# the contraction. Without this the measurement is mostly the tool failing to
# recognise "agents" and "shouldn't", which says nothing about speech.
_SUFFIXES = ("'s", "s'", "s", "es", "ed", "ing", "'re", "'ve", "'ll", "'d",
             "n't", "'m", "er", "est", "ly", "ers", "ings")


def _known(w: str) -> bool:
    if w in ALLOW or w in ENGLISH or w in HINDI:
        return True
    if hindi.key(w) in HINDI_KEYS:           # a spelling variant of Hindi
        return True
    for suf in _SUFFIXES:
        # The floor used to be expressed against the whole word, which
        # rejected any short stem: "using" is five letters and "ing" wanted
        # six, so an ordinary word counted as one the model invented. What has
        # to be long enough is the stem. A contraction needs no stem length at
        # all, because "we're" leaves two letters behind.
        floor = 0 if suf.startswith("'") or suf == "n't" else 2
        if w.endswith(suf) and len(w) - len(suf) >= floor:
            stem = w[: -len(suf)]
            if stem in ENGLISH or stem in ALLOW or stem in HINDI:
                return True
            # tries to try, running to run
            if stem.endswith("i") and (stem[:-1] + "y") in ENGLISH:
                return True
            if len(stem) > 3 and stem[-1] == stem[-2] and stem[:-1] in ENGLISH:
                return True
            # delegated to delegate, preparing to prepare. English drops a
            # silent e before a vowel suffix, and without putting it back this
            # counted ordinary past tenses as gibberish: on the real corpus,
            # "delegated", "approved", "preparing", "liquidated", "completed",
            # "including", "managed", "deriving", "updating" and "arriving"
            # were all being reported as words the speech model invented.
            if (suf and suf[0] in "aeiou" and suf not in ("er", "ers")
                    and (stem + "e") in ENGLISH):
                return True
            # Irregular spellings the -ise ending gives a British speaker, which
            # a dictionary holding only "finalize" refuses.
            if stem.endswith("is") and (stem[:-2] + "ize") in ENGLISH:
                return True
    return False


def unknown(text: str) -> list:
    """The tokens that are in neither dictionary."""
    out = []
    for w in _WORD.findall(text or ""):
        lw = w.lower().strip("'")
        if len(lw) < 3 or _known(lw):
            continue
        out.append(w)
    return out


def score(text: str) -> dict:
    words = _WORD.findall(text or "")
    bad = unknown(text)
    return {
        "words": len(words),
        "unknown": len(bad),
        "share": (len(bad) / len(words)) if words else 0.0,
        "examples": bad[:8],
    }


if __name__ == "__main__":
    for line in sys.stdin:
        s = score(line)
        print(f"{s['share']:.2f}  {s['unknown']:3d}/{s['words']:3d}  "
              f"{', '.join(s['examples'])}")
