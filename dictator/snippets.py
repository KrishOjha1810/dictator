"""Phrases you say often, and the exact text you meant by them.

"my work email" is three words. The address is thirty characters of dots and
an at sign that no speech model will ever produce from speech, and spelling it
out loud is slower than typing it. Same for a repository path, a wallet
address, a support reply you send four times a week. That gap is what this
file is for: a phrase you choose, and the literal text it stands for.

This is NOT the vocabulary, although the two look alike from outside.

    vocab.py    fixes a word the recogniser got WRONG. It works by sound, it
                generalises, and it is allowed to guess, because the user
                never asked for the mistake in the first place.

    this file   replaces a phrase the recogniser got RIGHT. It is literal, it
                generalises to nothing, and it never guesses, because the user
                chose both halves and expects exactly what they typed.

Guessing here would be a disaster of a different shape. A vocabulary that
fires wrongly writes one odd word. A snippet that fires wrongly drops an email
address into the middle of a sentence, and the user finds out after they have
sent it.

THE RULES, AND WHY EACH ONE EXISTS
----------------------------------
1. A trigger is at least two words. One spoken word is something a person says
   by accident a hundred times a day; two words in a row is a phrase they
   chose. Every text-expander horror story is a one-word trigger.

2. A trigger you have already said is refused, with the count, rather than
   accepted and regretted. Your own dictation history is the only honest test
   of whether a phrase is one you use, and the same test is what stops the
   vocabulary from eating a word you actually say. `force=True` overrides it,
   because it is your machine and you may be about to stop saying it.

3. Matching is whole-phrase and case-insensitive, on word boundaries. "my
   email" does not fire inside "my emails".

4. The replacement is inserted verbatim and is never scanned again, so a
   snippet whose text contains another trigger cannot cascade.

5. Longest trigger first, so a two word trigger never beats the four word one
   it sits inside.

Nothing here talks to a model, touches the network, or looks at the screen.
It is a dictionary and a regular expression.
"""
import json
import re
import threading
import time
from pathlib import Path

from . import core

__all__ = ["expand", "shared", "Snippets"]

STORE = core.STATE_DIR / "snippets.json"
_lock = threading.Lock()

# Two words, for the reason in the docstring. Deliberately a constant rather
# than a judgement call per trigger: a rule the user can predict is worth more
# than a rule that is right slightly more often.
MIN_WORDS = 2

# How many times a phrase may appear in your own history before it is refused
# as a trigger. One is a coincidence; twice is a phrase you use.
TOO_FAMILIAR = 2

# How far back to look for it. The same window the vocabulary uses to decide
# which words are yours.
HISTORY_DEPTH = 800

_WORDISH = re.compile(r"[\w']+")


def _norm(phrase: str) -> str:
    """The comparable form of a phrase: lowercase words, single spaces.

    Punctuation goes because the shaping pass runs before this one, so a
    trigger said at the end of a sentence arrives with a full stop attached
    and would otherwise never match what the user typed in."""
    return " ".join(_WORDISH.findall((phrase or "").lower()))


def _pattern(trigger: str) -> "re.Pattern":
    """A trigger as a regular expression that respects word boundaries.

    The words are joined with a flexible separator rather than a literal
    space, because the recogniser decides on its own whether to write "set up"
    or "set-up", and a trigger that only matches one of them is a trigger that
    fails half the time for a reason the user cannot see."""
    words = _WORDISH.findall(trigger.lower())
    if not words:
        return re.compile(r"(?!)")          # matches nothing
    body = r"[\s\-]+".join(re.escape(w) for w in words)
    return re.compile(r"(?<![\w'])" + body + r"(?![\w'])", re.IGNORECASE)


class Snippets:
    """The store, and the one pass over a transcript."""

    def __init__(self):
        self.items = {}          # normalised trigger -> record
        self.load()

    # ---- storage ------------------------------------------------------

    def load(self) -> None:
        try:
            raw = json.loads(STORE.read_text())
        except Exception:
            self.items = {}
            return
        self.items = {k: v for k, v in raw.items()
                      if isinstance(v, dict) and isinstance(v.get("text"), str)}

    def save(self) -> None:
        try:
            core.STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = str(STORE) + ".tmp"
            Path(tmp).write_text(json.dumps(self.items, indent=1))
            Path(tmp).replace(STORE)
        except Exception as e:
            core.log(f"snippets: {e}")

    # ---- admission ----------------------------------------------------

    def said_before(self, trigger: str) -> int:
        """How many of your own utterances contain this phrase.

        The check that stops a snippet from eating ordinary speech, and it is
        done once, when the snippet is created, rather than on every hold. A
        guard the user meets at the moment they make the mistake can explain
        itself; a guard that fires silently three weeks later cannot."""
        want = _pattern(trigger)
        try:
            from . import history
            rows = history.recent(limit=HISTORY_DEPTH)
        except Exception:
            return 0
        n = 0
        for r in rows:
            text = r.get("kept") or r.get("shown") or r.get("heard") or ""
            if want.search(text):
                n += 1
        return n

    def add(self, trigger: str, text: str, force: bool = False) -> dict:
        """Create a snippet, or explain in the user's words why not.

        Returns {"ok": bool, "trigger": str, "text": str, "why": str}. The
        refusals are the interesting half: a tool that declines silently is
        worse than one that does the wrong thing loudly."""
        key = _norm(trigger)
        text = text or ""
        if not key:
            return {"ok": False, "trigger": trigger, "text": text,
                    "why": "there are no words in that trigger"}
        if not text.strip():
            return {"ok": False, "trigger": key, "text": text,
                    "why": "there is nothing to put in its place"}
        if len(key.split()) < MIN_WORDS:
            return {"ok": False, "trigger": key, "text": text,
                    "why": (f"a trigger needs at least {MIN_WORDS} words. One "
                            f"word is something you say by accident, and it "
                            f"would fire in the middle of a sentence")}
        if not force:
            seen = self.said_before(key)
            if seen >= TOO_FAMILIAR:
                return {"ok": False, "trigger": key, "text": text,
                        "why": (f"you have already dictated that phrase "
                                f"{seen} times, so it would start replacing "
                                f"things you meant to say. Pick a phrase you "
                                f"would not otherwise use, or add it anyway")}
        with _lock:
            rec = self.items.get(key) or {"count": 0}
            rec.update({"trigger": key, "text": text, "at": time.time(),
                        "count": rec.get("count", 0)})
            self.items[key] = rec
            self.save()
        return {"ok": True, "trigger": key, "text": text, "why": ""}

    def remove(self, trigger: str) -> bool:
        key = _norm(trigger)
        with _lock:
            if key in self.items:
                del self.items[key]
                self.save()
                return True
        return False

    # ---- the one pass -------------------------------------------------

    def expand(self, text: str) -> "tuple[str, list]":
        """Replace every trigger in `text`. Returns (text, triggers fired).

        One left to right pass, longest trigger first, and what a replacement
        put in is never looked at again: a snippet whose text happens to
        contain another trigger expands once, not forever."""
        if not text or not self.items:
            return text, []
        order = sorted(self.items, key=lambda k: (-len(k.split()), -len(k)))
        # Each piece is (text, frozen). Frozen pieces came out of a
        # replacement and are never scanned again.
        pieces = [(text, False)]
        fired = []
        for key in order:
            want = _pattern(key)
            replacement = self.items[key]["text"]
            out = []
            hit = False
            for piece, frozen in pieces:
                if frozen:
                    out.append((piece, True))
                    continue
                last = 0
                for m in want.finditer(piece):
                    hit = True
                    if m.start() > last:
                        out.append((piece[last:m.start()], False))
                    out.append((replacement, True))
                    last = m.end()
                out.append((piece[last:], False))
            pieces = [p for p in out if p[0] or p[1]]
            if hit:
                fired.append(key)
        if not fired:
            return text, []
        self._used(fired)
        return "".join(p for p, _ in pieces), fired

    def _used(self, keys: list) -> None:
        try:
            with _lock:
                for k in keys:
                    if k in self.items:
                        self.items[k]["count"] = self.items[k].get("count", 0) + 1
                self.save()
        except Exception as e:
            core.log(f"snippets: could not record use: {e}")


_shared = None


def shared() -> "Snippets":
    global _shared
    if _shared is None:
        _shared = Snippets()
    return _shared


def expand(text: str) -> str:
    """The shared store, applied. The form the pipeline calls."""
    try:
        return shared().expand(text)[0]
    except Exception as e:
        core.log(f"snippets: expansion failed: {e}")
        return text
