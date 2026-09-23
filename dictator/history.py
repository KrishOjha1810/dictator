"""What was said, what we made of it, and what you kept.

Three columns, and the gap between them is the whole point:

    heard      what the recogniser produced, untouched
    shown      what we actually inserted, after any cleanup
    kept       what was there afterwards, once you had your way with it

Diff `kept` against `shown` and you have a record of what our formatting got
wrong. Diff `kept` against `heard` and you have a record of what the
recogniser got wrong, which is the vocabulary the user actually needs.

The product being chased stores exactly these three, and that schema IS its
learning loop. Theirs sits in a 694MB file alongside raw audio, screenshots
and accessibility dumps, and uploads hourly. Ours holds text and stays here.

Nothing else in this module matters as much as the fact that it is local.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

from . import core

DB = core.STATE_DIR / "history.db"
_lock = threading.Lock()

# Text only. No audio, no screenshots, no window contents. If this file ever
# grows something that could embarrass someone, the feature was built wrong.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS said (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     REAL NOT NULL,
    heard  TEXT NOT NULL DEFAULT '',
    shown  TEXT NOT NULL DEFAULT '',
    kept   TEXT NOT NULL DEFAULT '',
    app    TEXT NOT NULL DEFAULT '',
    lang   TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT '',
    secs   REAL NOT NULL DEFAULT 0,
    conf   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS said_at ON said(at DESC);
"""


def _db():
    con = sqlite3.connect(str(DB), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(_SCHEMA)
    try:
        DB.chmod(0o600)          # it is a record of everything you have said
    except Exception:
        pass
    return con


def add(heard, shown="", app="", lang="", engine="", secs=0.0, conf=0.0) -> int:
    """Record an utterance. Returns its id, or 0.

    Never raises: losing a transcript to a locked database is worse than not
    recording it, and this sits on the path that answers."""
    try:
        core.STATE_DIR.mkdir(parents=True, exist_ok=True)
        with _lock:
            con = _db()
            try:
                cur = con.execute(
                    "INSERT INTO said (at, heard, shown, kept, app, lang, "
                    "engine, secs, conf) VALUES (?,?,?,?,?,?,?,?,?)",
                    (time.time(), heard or "", shown or heard or "", "",
                     app or "", lang or "", engine or "", float(secs),
                     float(conf)))
                con.commit()
                return int(cur.lastrowid or 0)
            finally:
                con.close()
    except Exception as e:
        core.log(f"history: {e}")
        return 0


def kept(row_id: int, text: str) -> None:
    """What the text had become by the time you were done with it.

    Written later than the row itself, because it is only knowable after the
    user has had a chance to edit. An empty `kept` means we never found out,
    which is different from the user changing nothing."""
    if not row_id:
        return
    try:
        with _lock:
            con = _db()
            try:
                con.execute("UPDATE said SET kept=? WHERE id=?",
                            (text or "", int(row_id)))
                con.commit()
            finally:
                con.close()
    except Exception as e:
        core.log(f"history: {e}")


def recent(limit: int = 50, since: float = 0.0) -> list:
    try:
        with _lock:
            con = _db()
            try:
                rows = con.execute(
                    "SELECT id, at, heard, shown, kept, app, lang, engine, "
                    "secs, conf FROM said WHERE at >= ? ORDER BY at DESC "
                    "LIMIT ?", (float(since), int(limit))).fetchall()
            finally:
                con.close()
    except Exception:
        return []
    cols = ("id", "at", "heard", "shown", "kept", "app", "lang", "engine",
            "secs", "conf")
    return [dict(zip(cols, r)) for r in rows]


def corrections(limit: int = 200) -> list:
    """Utterances the user changed. The training data, such as it is.

    Only rows where we actually observed the aftermath AND it differs. A row
    with an empty `kept` is not a correction, it is a row where we never
    looked."""
    out = []
    for r in recent(limit * 4):
        if r["kept"] and r["kept"].strip() != (r["shown"] or "").strip():
            out.append(r)
            if len(out) >= limit:
                break
    return out


def forget(row_id: int = 0, before: float = 0.0) -> int:
    """Delete one row, or everything older than a timestamp. Returns the count.

    Deliberately easy to reach. A record of everything you have said needs a
    delete that is as simple as the record itself."""
    try:
        with _lock:
            con = _db()
            try:
                if row_id:
                    cur = con.execute("DELETE FROM said WHERE id=?", (int(row_id),))
                elif before:
                    cur = con.execute("DELETE FROM said WHERE at < ?", (float(before),))
                else:
                    cur = con.execute("DELETE FROM said")
                con.commit()
                return cur.rowcount or 0
            finally:
                con.close()
    except Exception as e:
        core.log(f"history: {e}")
        return 0


def stats(days: float = 7.0) -> dict:
    rows = recent(5000, since=time.time() - days * 86400)
    words = sum(len((r["shown"] or "").split()) for r in rows)
    secs = sum(r["secs"] for r in rows)
    apps = {}
    for r in rows:
        if r["app"]:
            apps[r["app"]] = apps.get(r["app"], 0) + 1
    return {"utterances": len(rows), "words": words, "seconds": round(secs, 1),
            "wpm": round(words / (secs / 60), 1) if secs > 30 else 0.0,
            "apps": sorted(apps.items(), key=lambda kv: -kv[1])[:8]}
