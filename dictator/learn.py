"""Notice what you changed by hand, and learn the word behind it.

The useful signal is not that you edited the text. It is that you edited it in
a way that sounds like what was heard. If dictation wrote "whisper floor" and
you made it "Whisper Flow", those two sound the same and the model simply did
not know the word. If you wrote "check the loop" and changed it to "actually
never mind", that is you changing your mind, and learning from it would teach
it nonsense.

So the rule that makes this safe to run automatically is: only learn a
replacement whose sound is close to what was heard. Everything else is an
edit, not a correction, and is left alone.

Nothing here is promoted on first sight either. A word has to be corrected the
same way twice before it is learned, because one edit is as likely to be a
typo or a half-finished thought as a lesson.
"""
import difflib
import json
import time
from pathlib import Path

from . import core, vocab

PENDING = core.STATE_DIR / "pending-words.json"

# How alike the pasted text and the field's text must be before we believe
# they are the same sentence rather than two different ones.
MIN_LIKENESS = 0.6

# How alike a correction must SOUND before we believe it is a correction of a
# mishearing rather than a rewrite. Deliberately looser than the threshold
# vocabulary matching uses, because here we already know the user made the
# change on purpose.
MAX_APART = 0.45

# A correction of more than this many words is a rewrite, whatever it sounds
# like. Real mishearings are one word or a short phrase.
MAX_WORDS = 4

# Seen this many times before it is learned.
NEEDED = 2


def locate(shown: str, field: str) -> str:
    """The pasted text as it reads now, or "" if unchanged or not found.

    Terminals hand back the whole scrollback rather than the line you are
    editing, so this has to find the sentence inside a much larger haystack
    instead of comparing two strings of similar length."""
    shown = (shown or "").strip()
    if not shown or not field:
        return ""
    if shown in field:
        return ""                      # untouched
    sm = difflib.SequenceMatcher(None, field, shown, autojunk=False)
    m = sm.find_longest_match(0, len(field), 0, len(shown))
    # Too little in common to be the same text at all. Without this, an
    # unrelated field would be mined for "corrections" that never happened.
    if m.size < max(8, len(shown) // 4):
        return ""
    best, score = "", 0.0
    start = max(0, m.a - m.b)
    for slack in (0, 10, 25, 50):
        span = field[start:min(len(field), start + len(shown) + slack)]
        r = difflib.SequenceMatcher(None, span, shown).ratio()
        if r > score:
            best, score = span, r
    return best if score >= MIN_LIKENESS else ""


def changes(shown: str, kept: str) -> list:
    """The word spans that differ, as (was, now) pairs."""
    a, b = (shown or "").split(), (kept or "").split()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "replace":
            out.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return out


def is_correction(was: str, now: str) -> bool:
    """True when `now` is what `was` should have been heard as.

    This is the whole safety of the feature. A replacement that sounds nothing
    like the original is the user saying something else, and treating it as a
    lesson would fill the vocabulary with words that were never mistaken."""
    was, now = (was or "").strip(), (now or "").strip()
    if not was or not now or was.lower() == now.lower():
        return False
    if len(was.split()) > MAX_WORDS or len(now.split()) > MAX_WORDS:
        return False
    ka, kb = vocab._key(was), vocab._key(now)
    if not ka or not kb:
        return False
    return vocab._apart(ka, kb) <= MAX_APART


def _load() -> dict:
    try:
        return json.loads(PENDING.read_text())
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        PENDING.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(PENDING) + ".tmp"
        Path(tmp).write_text(json.dumps(d, indent=1))
        Path(tmp).replace(PENDING)
    except Exception as e:
        core.log(f"learn: could not save pending words: {e}")


def observe(shown: str, kept: str) -> list:
    """Record what changed, and learn anything seen often enough.

    Returns the terms actually learned on this call, which is usually nothing:
    most edits are not corrections and most corrections are first sightings."""
    learned = []
    pairs = [(w, n) for w, n in changes(shown, kept) if is_correction(w, n)]
    if not pairs:
        return learned
    pending = _load()
    for was, now in pairs:
        rec = pending.setdefault(now, {"heard": [], "count": 0, "at": 0})
        if was not in rec["heard"]:
            rec["heard"].append(was)
        rec["count"] += 1
        rec["at"] = time.time()
        if rec["count"] >= NEEDED:
            vocab.shared().add(now, heard=was)
            learned.append(now)
            pending.pop(now, None)
            core.log(f"learn: learned {now!r} (heard as {rec['heard']})")
        else:
            core.log(f"learn: noticed {was!r} corrected to {now!r} "
                     f"({rec['count']} of {NEEDED})")
    _save(pending)
    return learned


def waiting() -> dict:
    """Corrections seen once, not yet learned."""
    return _load()
