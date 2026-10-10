"""Find something you said, weeks after you said it.

Every one of these products keeps a history and then gives you a list to
scroll. A list is fine for the last five things and useless for the thing you
dictated into Slack in the middle of last month, which is exactly when the
history is worth having at all: you said the sentence once, you know three
words of it, and the alternative is writing it again from memory.

So this is the search. It is text over a local SQLite file and it is
deliberately not clever: no index to keep in step with the rows, no embeddings,
no model. A personal dictation history is tens of thousands of short lines,
and scanning all of them takes single digit milliseconds. The moment that stops
being true is the moment to add an index, and not before.

It reads through history.recent() rather than reaching into the database,
which is the same thing recap.py does and for the same reason: one module owns
the schema, and a second one writing its own SQL is how a column gets renamed
and a feature quietly stops working.

WHAT IT SEARCHES
----------------
All three columns, because they answer three different questions:

    heard   what the recogniser produced. Search this to find out how it
            mangles a word, which is what you need before teaching it one.
    shown   what was actually inserted.
    kept    what the text had become once you were done with it.

What is DISPLAYED is the last of those that exists, because that is closest to
what the person meant. What is MATCHED is any of them, because a search that
cannot find a sentence by the wrong words is a search that fails precisely
when the recogniser did.
"""
import re
import time

from . import history

__all__ = ["find", "Hit"]

# One scan over everything. A history this size is a few megabytes of text and
# the scan is not the slow part of anything.
DEPTH = 50000

_WORDS = re.compile(r"[\w'\-]+")


class Hit:
    """One matching utterance, and where in it the words were."""

    def __init__(self, row: dict, phrase: bool, at_pos: int):
        self.row = row
        self.at = row.get("at", 0.0)
        self.app = row.get("app") or ""
        self.text = (row.get("kept") or row.get("shown")
                     or row.get("heard") or "")
        # True when the query appeared as one contiguous phrase, which is a
        # much stronger hit than the same words scattered across a sentence.
        self.phrase = phrase
        self.pos = at_pos

    def around(self, width: int = 90) -> str:
        """The line, or enough of it to show the match in context.

        A history line is usually one sentence and fits whole. When it does
        not, cutting around the match is the only useful thing to show: a
        search result truncated at the start is a result you cannot check."""
        text = " ".join(self.text.split())
        if len(text) <= width:
            return text
        start = max(0, min(self.pos - width // 3, len(text) - width))
        # Do not cut a word in half; a broken word reads as a transcription
        # error, which is the one thing this tool must never fake.
        if start > 0:
            space = text.find(" ", start)
            start = space + 1 if 0 <= space < start + 20 else start
        piece = text[start:start + width]
        return ("..." if start else "") + piece.strip() + \
               ("..." if start + width < len(text) else "")


def _wanted(query: str) -> list:
    return [w.lower() for w in _WORDS.findall(query or "")]


def _where(haystack: str, words: list, phrase: str) -> "tuple[bool, int]":
    """Does this text match, and where. Returns (phrase hit, position).

    A position of -1 means no match at all. Words are matched as substrings
    on purpose: somebody searching for "commit" wants the line that says
    "committed", and a search that makes you guess the suffix is a search
    people stop using."""
    low = haystack.lower()
    if not words:
        return False, -1
    at = low.find(phrase)
    if at >= 0:
        return True, at
    first = -1
    for w in words:
        i = low.find(w)
        if i < 0:
            return False, -1
        if first < 0 or i < first:
            first = i
    return False, first


def find(query: str, days: float = 0.0, app: str = "",
         limit: int = 20) -> list:
    """Utterances containing every word of `query`, newest first.

    Contiguous matches come before scattered ones, and within each group the
    order is by time, because "the thing I said about the loop" is almost
    always the most recent thing said about the loop.

    days   only the last N days. 0 means everything.
    app    only what was dictated into this application. Matched loosely,
           because macOS reports "Google Chrome" and nobody types that.
    """
    words = _wanted(query)
    if not words:
        return []
    phrase = " ".join(words)
    since = time.time() - days * 86400 if days else 0.0
    want_app = (app or "").strip().lower()

    hits = []
    for r in history.recent(limit=DEPTH, since=since):
        if want_app and want_app not in (r.get("app") or "").lower():
            continue
        best = None
        for column in ("kept", "shown", "heard"):
            text = r.get(column) or ""
            if not text:
                continue
            is_phrase, at = _where(text, words, phrase)
            if at < 0:
                continue
            # The displayed text is `kept` or `shown`, so a position found in
            # `heard` would point into a string nobody is going to see. Only
            # a match in a column that is actually shown carries its offset.
            shown_here = column != "heard" or not (r.get("kept") or r.get("shown"))
            here = (is_phrase, at if shown_here else 0)
            if best is None or here[0] > best[0]:
                best = here
        if best is not None:
            hits.append(Hit(r, best[0], best[1]))

    hits.sort(key=lambda h: (0 if h.phrase else 1, -h.at))
    return hits[:limit]


def stamp(at: float) -> str:
    """Date and time, with the year only when it is not this one. A history
    search is mostly about the last few weeks and a four digit year on every
    line is noise until the day it is not."""
    now = time.localtime()
    then = time.localtime(at)
    fmt = "%d %b %H:%M" if then.tm_year == now.tm_year else "%d %b %Y %H:%M"
    return time.strftime(fmt, then)
