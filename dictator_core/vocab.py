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

# Hindi keys are denser than metaphone keys, so the same length carries more
# of the word, but a two or three letter key still matches far too much.
MIN_HINDI_KEY = 4

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _key(text: str) -> str:
    """The phonetic shape of a phrase, with the spaces taken out.

    Removing whitespace is what makes word-splitting free: the recogniser
    hearing "a man dra" produces the same key as "Amandra"."""
    if not jellyfish:
        return ""
    letters = "".join(_WORD.findall(text or "")).lower()
    return jellyfish.metaphone(letters) if letters else ""


def _hkey(text: str) -> str:
    """The Hindi key, for words metaphone has nothing useful to say about.

    Metaphone models English spelling. On romanized Hindi it returns keys like
    XHY for chahiye and W for woh, which are too short to guess from, so every
    Hindi word was admitted in exact match mode and the generalisation that
    makes this feature worth having never applied to half of what this user
    says. See hindi.py."""
    from . import hindi
    letters = "".join(_WORD.findall(text or ""))
    return hindi.key(letters)


def _apart(a: str, b: str) -> float:
    if not a or not b:
        return 1.0
    return jellyfish.levenshtein_distance(a, b) / max(len(a), len(b))



# Ordinary words that sit in front of a term without being part of it. Kept
# deliberately short: this only has to stop a span from eating the word before
# the one it is actually matching.
GLUE = {"the", "a", "an", "this", "that", "my", "your", "our", "is", "was",
        "to", "of", "in", "on", "and", "or", "for", "with"}


def _lead(span: str) -> str:
    return (span.split() or [""])[0].strip(".,;:!?").lower()


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
            return
        # Bring records written before per-key admission up to date, once.
        # Without this a word learned yesterday keeps yesterday's verdict for
        # ever, and the user has no way to see that a later improvement never
        # reached it.
        stale = [t for t, r in self.terms.items()
                 if isinstance(r, dict) and "guess" not in r]
        if not stale:
            return
        for t in stale:
            old = self.terms[t]
            fresh = self.admit(t)
            fresh["heard"] = old.get("heard", [])
            fresh["count"] = old.get("count", 0)
            fresh["at"] = old.get("at", fresh["at"])
            self.terms[t] = fresh
        core.log(f"vocab: re-admitted {len(stale)} term(s) after a rule change")
        self.save()

    def save(self):
        try:
            core.STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = str(STORE) + ".tmp"
            Path(tmp).write_text(json.dumps(self.terms, indent=1))
            Path(tmp).replace(STORE)
        except Exception as e:
            core.log(f"vocab: {e}")

    # ---- admission ----------------------------------------------------

    def spoken(self, least: int = 2, most: int = 3000) -> list:
        """The words this user actually says.

        A learned term is dangerous exactly when it can overwrite a word the
        user uses, and a generic dictionary is the wrong guard for that. It
        would leave "Hinglish" free to eat "English", which this user says
        often, while blocking "dictator" because the dictionary happens to
        contain "dictate", which they have never said once. The words in their
        own history are the ones worth protecting."""
        try:
            from . import history
            rows = history.recent(limit=800)
        except Exception:
            return []
        seen = {}
        for r in rows:
            text = r.get("kept") or r.get("shown") or r.get("heard") or ""
            for w in _WORD.findall(text):
                if len(w) > 2:
                    lw = w.lower()
                    seen[lw] = seen.get(lw, 0) + 1
        return [w for w, n in sorted(seen.items(), key=lambda kv: -kv[1])
                if n >= least][:most]

    def admit(self, term: str, common=None) -> dict:
        """Decide how safely a term can be matched, once, when it is learned.

        Returns the record. `mode` is "fuzzy" when the term's phonetic
        neighbourhood is empty enough to guess in, and "exact" when it is not.
        `why` is written for the user to read, because a tool that silently
        declines to do what you asked is worse than one that says why."""
        key = _key(term)
        hkey = _hkey(term)
        # `guess` is always present, even on the early returns below, or the
        # migration in load() would decide the record is stale every single
        # time and rewrite the file on every start.
        rec = {"term": term, "key": key, "hkey": hkey, "mode": "exact",
               "guess": [], "why": "", "heard": [], "count": 0,
               "at": time.time()}
        if not key:
            rec["why"] = "no pronounceable letters"
            return rec
        if len(key) < MIN_KEY and len(hkey) < MIN_HINDI_KEY:
            rec["why"] = (f"too short to guess from ({key or hkey}), so I "
                          f"will only fix it when I hear it exactly")
            return rec
        against = common if common is not None else (COMMON + self.spoken())
        # Judge each key on its own. A term can be unsafe to guess at by its
        # English sound and perfectly safe by its Hindi one: "Amandra" keys to
        # AMNTP, which collides with "amend" and "amount", while its Hindi key
        # amandra collides with nothing. Refusing both because one collided
        # meant "Amandhra" was never corrected, which is the exact thing the
        # user asked for.
        clash, hclash = [], []
        for w in against:
            if w.lower() == term.lower():
                continue
            if key and _apart(key, _key(w)) <= NEAR:
                clash.append(w)
            if hkey and len(hkey) >= MIN_HINDI_KEY and hkey == _hkey(w):
                hclash.append(w)
        rec["guess"] = ([] if clash or len(key) < MIN_KEY else ["key"]) + \
                       ([] if hclash or len(hkey) < MIN_HINDI_KEY else ["hkey"])
        if rec["guess"]:
            rec["mode"] = "fuzzy"
            if clash or hclash:
                rec["why"] = (f"sounds like {', '.join(sorted(set(clash + hclash))[:3])}, "
                              f"so I will be stricter about it")
            return rec
        clash = clash + hclash
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
            rec = self.terms.get(term)
            # Re-admit anything written before per-key admission existed.
            # Otherwise a term learned yesterday keeps yesterday's verdict
            # forever, and the user has no way to know why teaching it again
            # changed nothing.
            if rec is None or "guess" not in rec:
                fresh = self.admit(term)
                if rec:
                    fresh["heard"] = rec.get("heard", [])
                    fresh["count"] = rec.get("count", 0)
                rec = fresh
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
                # Do not let a span swallow the ordinary word in front of the
                # term. "the voice bridge" matched "voicebridge" closely enough
                # to win as a three word span, and replacing it deleted a word
                # the user actually said. A term that really does begin with
                # "the" is still matched, because then the leading word is part
                # of the term rather than in front of it.
                if n > 1 and _lead(span) in GLUE:
                    if not any(_lead(t) in GLUE for t in self.terms):
                        continue
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
        hkey = _hkey(span)
        if not key and not hkey:
            return None
        best, best_d = None, 1.0
        for term, rec in self.terms.items():
            if span.lower() == term.lower():
                return None                   # already right, leave it alone
            tk, th = rec.get("key") or "", rec.get("hkey") or ""
            if not tk and not th:
                continue
            guess = rec.get("guess")
            if guess is None:          # written before per-key admission
                guess = ["key", "hkey"] if rec.get("mode") == "fuzzy" else []
            d = _apart(key, tk) if (key and tk and "key" in guess) else 1.0
            # The Hindi key has to match EXACTLY, never approximately. It has
            # already absorbed the spelling variation it exists for (chaahie
            # and chahiye are both cahie), so there is nothing left for a
            # distance to buy, and the keys are short enough that allowing one
            # character of slack turned "sahi hai" into "chahiye".
            if th and hkey and "hkey" in guess and len(th) >= MIN_HINDI_KEY \
                    and hkey == th:
                d = 0.0
            if rec.get("mode") == "exact":
                # Exact means the WORD, not the key. Keys collide: metaphone
                # gives "we" and "woh" both W, so a term admitted as exact
                # because it was too short to guess from still rewrote an
                # ordinary English word in ordinary English speech. "I will
                # only fix it when I hear it exactly" has to mean exactly.
                if span.lower() != term.lower():
                    continue
                d = 0.0
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
