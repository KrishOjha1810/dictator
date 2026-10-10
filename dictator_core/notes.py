"""The Scratchpad: plain notes, kept on this Mac.

A note is one Markdown file in STATE_DIR/notes, named by when it was made:
20261009-142301.md. The text is the whole file; the title is its first line
that is not blank; when it was last changed is the file's own time. Nothing
else is stored, so a note can be opened, edited, grepped or backed up with any
tool, and deleting the file deletes the note.

The app's Scratchpad window and Hub page go through `dictator notes`, so this
is the one place the format is decided. Nothing here leaves the machine.
"""
import os
import re
import time

from . import core

ID = re.compile(r"\d{8}-\d{6}(-\d+)?")


def folder():
    """Computed at call time from STATE_DIR, so a test never reaches the
    real one."""
    return core.STATE_DIR / "notes"


def _path(nid: str):
    if not isinstance(nid, str) or not ID.fullmatch(nid):
        raise ValueError(f"not a note id: {nid!r}")
    return folder() / f"{nid}.md"


def new_id(now: "float|None" = None) -> str:
    """A fresh id for the current second; -2, -3 when that one is taken."""
    base = time.strftime("%Y%m%d-%H%M%S", time.localtime(now or time.time()))
    nid, n = base, 1
    while (folder() / f"{nid}.md").exists():
        n += 1
        nid = f"{base}-{n}"
    return nid


def title_of(text: str) -> str:
    for line in text.splitlines():
        t = line.strip().lstrip("#").strip()
        if t:
            return t[:80]
    return ""


def _record(nid: str, text: str, mtime: float) -> dict:
    return {"id": nid, "title": title_of(text) or "Empty note", "text": text,
            "updated": round(mtime, 3), "words": len(text.split())}


def all_notes() -> list:
    """Every note, the most recently changed first."""
    d = folder()
    if not d.exists():
        return []
    out = []
    for f in d.glob("*.md"):
        if not ID.fullmatch(f.stem):
            continue
        try:
            out.append(_record(f.stem, f.read_text(encoding="utf-8"),
                               f.stat().st_mtime))
        except OSError:
            continue
    out.sort(key=lambda r: (r["updated"], r["id"]), reverse=True)
    return out


def get(nid: str) -> "dict|None":
    p = _path(nid)
    try:
        return _record(nid, p.read_text(encoding="utf-8"), p.stat().st_mtime)
    except OSError:
        return None


def save(nid: str, text: str) -> "dict|None":
    """Write the note, atomically. Text that is only whitespace deletes it,
    so an opened-and-abandoned note does not linger as "Empty note"."""
    p = _path(nid)
    if not text.strip():
        delete(nid)
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)
    return get(nid)


def delete(nid: str) -> bool:
    try:
        _path(nid).unlink()
        return True
    except FileNotFoundError:
        return False


def find(words: str) -> list:
    """Notes containing every word, case-insensitively."""
    want = [w.lower() for w in words.split() if w]
    return [r for r in all_notes()
            if all(w in r["text"].lower() for w in want)]
