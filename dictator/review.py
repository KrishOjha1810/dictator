"""Ask the user about the words it is least sure it got right.

The learning loop reads corrections out of the text field after a paste, which
works where the field can be read back and does not work in a terminal, and a
terminal is where most dictation here goes. So the words it gets wrong most
often are exactly the words it never gets told about.

This is the other direction. Rather than waiting to catch an edit, go through
what was said, find the words that are in neither dictionary, and ask. The
measurement that made this worth building: of the 21 genuine errors in 130
real recordings, 8 were names and acronyms (`Zhrkvander`, `Glentworthy`,
`LRDR`), which no speech model will ever know and `dictator learn` fixes in
one line. They were the single largest category, and nothing was asking.

It only ever suggests. The user types the real spelling or skips, and nothing
is learned from silence: a wrong guess accepted quietly would then rewrite
correct words in later dictations, which is the failure `vocab.admit` exists
to prevent.
"""
from . import history, known, vocab


def suspects(limit: int = 200, ignore: "set|None" = None) -> list:
    """Utterances containing a word in neither dictionary, most recent first.

    Each is {"id", "at", "text", "words", "app"}. `words` is what to ask
    about. Rows whose every suspect word is in `ignore` are left out, so a
    word already dismissed does not come back every time."""
    skip = {w.lower() for w in (ignore or set())}
    # A word already taught is not a word it got wrong, and asking about it
    # again is how a helpful prompt turns into a nag. Terms are phrases, so
    # each word of one counts.
    try:
        for term in vocab.shared().terms:
            skip.update(w.lower() for w in term.split())
    except Exception:
        pass
    out = []
    for r in history.recent(limit):
        text = (r.get("kept") or r.get("shown") or r.get("heard") or "").strip()
        if not text:
            continue
        words = [w for w in known.unknown(text) if w.lower() not in skip]
        if not words:
            continue
        # The same word twice in one line is one question, not two.
        seen, uniq = set(), []
        for w in words:
            if w.lower() not in seen:
                seen.add(w.lower())
                uniq.append(w)
        out.append({"id": r.get("id"), "at": r.get("at"), "text": text,
                    "words": uniq, "app": r.get("app") or ""})
    return out


def show(text: str, word: str, width: int = 72) -> str:
    """The word in enough of its sentence to remember saying it.

    Without the surrounding words the question is unanswerable: nobody can say
    what "Zhrkvander" was meant to be, and everybody can say it when they can
    see it was a greeting."""
    i = text.lower().find(word.lower())
    if i < 0:
        return text[:width]
    room = max(width - len(word), 10) // 2
    start = max(0, i - room)
    end = min(len(text), i + len(word) + room)
    return (("..." if start else "") + text[start:end]
            + ("..." if end < len(text) else ""))


def words(limit: int = 200, ignore: "set|None" = None) -> list:
    """One entry per distinct word, most often said first.

    Walking utterances asks about the same word forty times. Walking words
    asks once and fixes forty, and taking the most frequent first means the
    person can stop whenever they have had enough and still have got the value
    out of it. Each is {"word", "count", "text", "app"}, where `text` is the
    utterance to show it in: the longest one, because the shortest is often
    the word on its own and unanswerable."""
    seen = {}
    for r in suspects(limit, ignore):
        for w in r["words"]:
            k = w.lower()
            got = seen.get(k)
            if got is None:
                seen[k] = {"word": w, "count": 1, "text": r["text"],
                           "app": r["app"]}
            else:
                got["count"] += 1
                if len(r["text"]) > len(got["text"]):
                    got["text"], got["app"] = r["text"], r["app"]
    return sorted(seen.values(), key=lambda d: (-d["count"], d["word"]))


def teach(said: str, heard: str) -> dict:
    """Learn the real spelling, so the same sound comes out right next time.

    Returns vocab's own record, which says whether it can be matched by sound
    or only exactly, and why when it cannot."""
    said = (said or "").strip()
    if not said:
        return {"ok": False, "why": "nothing to learn"}
    return vocab.shared().add(said, heard=(heard or "").strip())
