"""Words the recogniser keeps getting wrong, and how to stop it.

The naive version of this is a lookup table: heard "whisper floor", write
"Whisper Flow". It fixes exactly the mistake you already saw and nothing else.
Say it slightly differently tomorrow and you are back to correcting it by hand.

So the index is built on the phonetics of the CORRECT word, and the query is
built on the phonetics of whatever came out. Teaching it "Whisper Flow" once,
from a single correction, then matches:

    whisper floor   the one that was taught
    whisper flows   never seen
    whispa flo      never seen
    whisper flew    never seen

Three things make that work, and all three are load-bearing:
  * key on the correct term, never on the mistake
  * strip whitespace before keying, so "a man dra" collapses onto "Amandra"
  * match over 1-4 word windows, so it works anywhere in a sentence

And one thing stops it being a menace. Phonetic neighbourhoods are crowded:
"Parakeet" sounds like "perfect", "nethermind" sounds like "never mind". A
term whose neighbourhood contains a common English word is admitted in
exact-match-only mode, because one ruined "perfect" in a message costs more
trust than ten rescued proper nouns earn.
"""
import json
import re
import threading
import time
from pathlib import Path

from . import core

try:
    import jellyfish
except Exception:
    jellyfish = None

STORE = core.STATE_DIR / "vocab.json"
_lock = threading.Lock()

# How far apart two phonetic keys may be and still count as the same word.
# 0.20 was chosen from measurement: it catches "floor"/"flow"/"flows" and it is
# where "Parakeet"/"perfect" sits, which is exactly why the admission test
# below exists rather than a looser threshold.
NEAR = 0.20

# Below this many phonetic symbols, a key is too short to be distinctive:
# "Krish" is KRX, "rebase" is RBS, and each sits in a neighbourhood of a
# thousand ordinary words. Short terms get exact matches only.
MIN_KEY = 5

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _key(text: str) -> str:
    """The phonetic shape of a phrase, with the spaces taken out.

    Removing whitespace is what makes word-splitting free: the recogniser
    hearing "a man dra" produces the same key as "Amandra"."""
    if not jellyfish:
        return ""
    letters = "".join(_WORD.findall(text or "")).lower()
    return jellyfish.metaphone(letters) if letters else ""


def _apart(a: str, b: str) -> float:
    if not a or not b:
        return 1.0
    return jellyfish.levenshtein_distance(a, b) / max(len(a), len(b))


class Vocab:
    def __init__(self):
        self.terms = {}          # canonical -> record
        self.load()

    # ---- storage ------------------------------------------------------

    def load(self):
        try:
            self.terms = json.loads(STORE.read_text())
        except Exception:
            self.terms = {}

    def save(self):
        try:
            core.STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = str(STORE) + ".tmp"
            Path(tmp).write_text(json.dumps(self.terms, indent=1))
            Path(tmp).replace(STORE)
        except Exception as e:
            core.log(f"vocab: {e}")

    # ---- admission ----------------------------------------------------

    def admit(self, term: str, common=None) -> dict:
        """Decide how safely a term can be matched, once, when it is learned.

        Returns the record. `mode` is "fuzzy" when the term's phonetic
        neighbourhood is empty enough to guess in, and "exact" when it is not.
        `why` is written for the user to read, because a tool that silently
        declines to do what you asked is worse than one that says why."""
        key = _key(term)
        rec = {"term": term, "key": key, "mode": "exact", "why": "",
               "heard": [], "count": 0, "at": time.time()}
        if not key:
            rec["why"] = "no pronounceable letters"
            return rec
        if len(key) < MIN_KEY:
            rec["why"] = (f"too short to guess from ({key}), so I will only "
                          f"fix it when I hear it exactly")
            return rec
        clash = [w for w in (common or COMMON)
                 if _apart(key, _key(w)) <= NEAR and w.lower() != term.lower()]
        if clash:
            rec["why"] = (f"sounds like {', '.join(sorted(clash)[:3])}, so I "
                          f"will only fix it when I hear it exactly")
            return rec
        rec["mode"] = "fuzzy"
        return rec

    def add(self, term: str, heard: str = "") -> dict:
        term = (term or "").strip()
        if not term:
            return {}
        with _lock:
            rec = self.terms.get(term) or self.admit(term)
            if heard and heard not in rec["heard"]:
                rec["heard"] = (rec["heard"] + [heard])[-8:]
            rec["count"] = rec.get("count", 0) + 1
            rec["at"] = time.time()
            self.terms[term] = rec
            self.save()
            return rec

    def remove(self, term: str) -> bool:
        with _lock:
            if term in self.terms:
                del self.terms[term]
                self.save()
                return True
        return False

    # ---- matching -----------------------------------------------------

    def fix(self, text: str) -> str:
        """Rewrite the spans that sound like something we know.

        Longest span wins, so a two-word term beats either of its halves."""
        if not text or not self.terms or not jellyfish:
            return text
        words = text.split()
        if not words:
            return text
        out, i = [], 0
        while i < len(words):
            hit = None
            for n in (4, 3, 2, 1):           # longest window first
                if i + n > len(words):
                    continue
                span = " ".join(words[i:i + n])
                got = self._match(span)
                if got:
                    hit = (got, n)
                    break
            if hit:
                term, n = hit
                # Keep whatever punctuation was hanging off the end.
                tail = re.sub(r"^[\w\s'\-]*", "", words[i + n - 1])
                out.append(term + tail)
                i += n
            else:
                out.append(words[i])
                i += 1
        return " ".join(out)

    def _match(self, span: str):
        key = _key(span)
        if not key:
            return None
        best, best_d = None, 1.0
        for term, rec in self.terms.items():
            if span.lower() == term.lower():
                return None                   # already right, leave it alone
            tk = rec.get("key") or ""
            if not tk:
                continue
            d = _apart(key, tk)
            if rec.get("mode") == "exact":
                if d > 0.0:
                    continue
            elif d > NEAR:
                continue
            if d < best_d:
                best, best_d = term, d
        return best


# A small, deliberately boring list of words that must never be overwritten.
# This is the whole guard: a term that sounds like one of these is admitted in
# exact-match mode. Kept short and common on purpose; a longer list would
# reject useful terms for the sake of words nobody says.
COMMON = [
    "perfect", "never mind", "rebates", "amend", "amends", "flow", "floor",
    "the", "this", "that", "there", "their", "here", "hear", "where", "were",
    "what", "when", "which", "with", "will", "would", "could", "should",
    "make", "made", "take", "check", "code", "file", "line", "test", "tests",
    "run", "build", "branch", "commit", "merge", "push", "pull", "change",
    "first", "second", "third", "next", "last", "now", "then", "back",
    "please", "thanks", "yes", "no", "okay", "sure", "right", "left",
]

_shared = None


def shared() -> "Vocab":
    global _shared
    if _shared is None:
        _shared = Vocab()
    return _shared
