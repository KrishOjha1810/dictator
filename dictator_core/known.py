"""Is this a word in either language, and which words in a line are not.

Split out of tools/nonwords.py, which was a benchmarking script, because the
product needs the same answer: the words a transcript contains that are in
neither dictionary are exactly the words worth asking the user about. See
`dictator review`.

Read the warning in tools/nonwords.py before changing anything here. This
first reported 2.35% gibberish on the real corpus, of which 2.0 points were
words it did not know rather than words the model got wrong, and the opposite
failure is quieter: a dictionary loose enough to accept anything finds nothing
to ask about. Both directions are asserted in tests/test_nonwords.py.
"""
import re
from pathlib import Path

from . import hindi, roman

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

# Everyday software vocabulary that a 1934 dictionary has never heard of.
# Without these the measurement is dominated by the tool not knowing what a
# repo is, which says nothing about the speech model.
#
# Read this list as part of the instrument and not as a fact about any model.
# It was grown by looking at what the tool objected to on one person's corpus
# and adding back the words that were correct, so the 0.37% below is a figure
# for THIS vocabulary on THAT corpus. Anyone measuring a different speaker
# should expect a worse number until they have done the same pass, and any
# comparison between two models is only fair if both are scored against the
# same list. See "The measuring instrument was wrong by a factor of six" in
# docs/findings.md.
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
    # Blockchain terms. "pda" and "usdc" alone were a third of everything this
    # tool was calling gibberish on the corpus it was tuned against, and both
    # were correct transcriptions. Which is the point of the note above: a
    # word list has a subject, and this one has this corpus's.
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
ALLOW |= {"has", "held", "paid", "became", "repaid", "hang", "goodbye",
          "email", "emails", "internet", "download", "downloads", "upload",
          "uploads", "username", "logout", "signup", "standup", "fuck",
          "fucking", "shit", "damn"}

# Romanised Hindi the list is missing. Added one at a time, from words that
# appeared in real recordings and were transcribed correctly.
# Romanised Hindi the shipped lexicon is missing. This block matters more than
# it looks: a model that writes Hindi in Latin script is penalised for every
# one of these, so the instrument was marking a Hinglish model down for doing
# exactly the thing it was built to do. The comparison in docs/findings.md
# found it the hard way, on a hold where the model that got the sentence RIGHT
# scored 10% and the model that turned it into fluent English nonsense scored
# zero, because every wrong word it chose was a real English word.
#
# Their phonetic keys go in as well, and that is the part that stops this
# being whack-a-mole. Hand-adding spellings one at a time builds a list of the
# spellings ONE model happens to use: "seedha" was added and passed, "sidha"
# was not and failed, and they are the same word with the same key. Registering
# the key means any spelling of the sound passes, whichever model wrote it.
HINDI_EXTRA = {
    "aao", "apno", "apna", "apni", "apne", "aap",
    "aapko", "aapka", "aapki", "seedha", "seedhe", "sirf",
    "matlab", "thoda", "zyada", "jyada", "bilkul", "wapas",
    "abhi", "parso", "mera", "meri", "mere", "tera",
    "teri", "tere", "uska", "uski", "unka", "unki",
    "iska", "iski", "inka", "hamara", "humara", "hamari",
    "mujhe", "tujhe", "usse", "isse", "jisse", "kisse",
    "pao", "paao", "karna", "karo", "kardo", "kardena",
    "karke", "hona", "hoga", "hogi", "rahe", "raha",
    "rahi", "lekar", "lena", "dena", "banao", "banvao",
    "banvaana", "likhna", "likho", "padhna", "padho", "samjhao",
    "samjha", "gayi", "gaye", "gaya", "sakta", "sakte",
    "sakti", "chahiye", "chahie", "bolna", "bolo", "suno",
    "sunna", "dekho", "dekhna", "kab", "kya", "kyun",
    "kaise", "kahan", "kaun", "lekin", "agar",
    # Ordinary nouns and verbs the lexicon does not have, found by checking a
    # list of common Hindi against it rather than by waiting for each to turn
    # up in a transcript, which is how the English gaps were found too.
    "sawaal", "jawab", "baatein", "cheezein", "jagah", "hafta", "aadmi",
    "ladki", "ladka", "darwaza", "khidki", "pehle", "baad",
    "kehna", "poochna", "rakhna", "milna", "baithna", "daudna", "peena",
    "padha", "banvana", "banvaya", "banvaaya",
}
ALLOW |= HINDI_EXTRA
HINDI_KEYS |= {hindi.key(w) for w in HINDI_EXTRA}


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
