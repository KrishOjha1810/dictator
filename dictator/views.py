"""What the app's windows show, as plain data.

The app never imports Python and Python never draws anything. Each page in
the app runs one command with --json and draws what comes back, so every page
is a thin view over something the CLI already does and the tests already
cover. This file is where those answers are put together, kept out of
bin/dictator so they can be tested without running the CLI.

Every function returns something json.dumps can write as it is, and none of
them raises: a page that gets an empty list draws "nothing yet", and a page
that gets a traceback draws nothing at all.
"""
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import core


# ---- where this install's parts came from -----------------------------------

# The helpers the app ships in Contents/Helpers, in the order doctor lists
# them. The first five are built from native/*.swift, the meeting recorder is
# its own app bundle, and the last three are whisper.cpp's.
SWIFT_HELPERS = ("dictator-hotkey", "dictator-rec", "dictator-paste",
                 "dictator-orb", "dictator-readback")
MEETING_APP = "Dictator Meeting.app"
ENGINES = ("whisper-server", "whisper-cli", "parakeet-cli")


def mode() -> str:
    """"app bundle" or "repo install", the two words doctor prints."""
    return "app bundle" if core.BUNDLE is not None else "repo install"


def _origin(path: str) -> str:
    """Where a found helper came from, in words a person can act on."""
    if not path:
        return "missing"
    p = str(path)
    if core.BUNDLE is not None and p.startswith(str(core.BUNDLE) + "/"):
        return "app bundle"
    if p.startswith(str(core.STATE_DIR / "bin") + "/"):
        return "built on this Mac"
    if p.startswith(("/opt/homebrew/", "/usr/local/")):
        return "Homebrew"
    return "PATH"


def helpers() -> dict:
    """{name: {"path": str, "from": str}} for every helper, without building
    or running any of them. Doctor reads this to say which copy of each it
    would use, which is the question when an app and a checkout share a Mac."""
    out = {}
    for name in SWIFT_HELPERS:
        p = core.helper_path(name)
        found = str(p) if p.exists() else ""
        out[name] = {"path": found or str(p), "from": _origin(found)}
    try:
        from . import meeting
        app = meeting.APP
    except Exception:
        app = core.helper_path(MEETING_APP)
    found = str(app) if Path(app).exists() else ""
    # In a checkout it is built into ~/Applications rather than STATE_DIR/bin,
    # so the path alone would not say it was built here.
    where = (_origin(found) if core.BUNDLE is not None or not found
             else "built on this Mac")
    out[MEETING_APP] = {"path": found or str(app), "from": where}
    try:
        from . import stt
        find = stt._find
    except Exception:
        find = lambda name: ""          # noqa: E731
    for name in ENGINES:
        found = find(name)
        out[name] = {"path": found, "from": _origin(found)}
    return out


# ---- status ------------------------------------------------------------------

def status() -> dict:
    """What `dictator status --json` says: the install, and the loop's own
    last word from status.json. `running` and `login_item` are asked of
    launchd by the caller, because asking here would make this untestable
    without touching the real login item."""
    from . import stt
    return {
        "mode": mode(),
        "bundle": str(core.BUNDLE) if core.BUNDLE is not None else None,
        "state_dir": str(core.STATE_DIR),
        "language": stt.language(),
        "status": core.read_status() or None,
    }


# ---- words and snippets --------------------------------------------------------

def words() -> dict:
    """Learned terms, and the ones seen once and waiting for a second."""
    out = {"words": [], "pending": []}
    try:
        from . import vocab
        for term, rec in sorted(vocab.shared().terms.items()):
            out["words"].append({
                "term": term,
                "mode": rec.get("mode") or "",
                "heard": list(rec.get("heard", []))[:8],
                "count": int(rec.get("count", 0) or 0),
            })
    except Exception as e:
        core.log(f"views: words: {e}")
    try:
        from . import learn
        for term, rec in sorted(learn.waiting().items()):
            out["pending"].append({"term": term,
                                   "heard": list(rec.get("heard", []))[:8]})
    except Exception as e:
        core.log(f"views: pending words: {e}")
    return out


def snippets() -> dict:
    out = {"snippets": []}
    try:
        from . import snippets as _sn
        for trigger, rec in sorted(_sn.shared().items.items()):
            out["snippets"].append({
                "trigger": trigger,
                "text": rec.get("text", ""),
                "count": int(rec.get("count", 0) or 0),
            })
    except Exception as e:
        core.log(f"views: snippets: {e}")
    return out


# ---- history and stats --------------------------------------------------------

def _row(r: dict) -> dict:
    """One utterance as the Home page lists it. `text` is what landed, which
    is what anybody scrolling their own history means by "what I said"."""
    return {
        "id": r.get("id"),
        "at": r.get("at"),
        "text": r.get("shown") or r.get("heard") or "",
        "heard": r.get("heard") or "",
        "kept": r.get("kept") or "",
        "app": r.get("app") or "",
        "lang": r.get("lang") or "",
        "engine": r.get("engine") or "",
        "secs": r.get("secs") or 0,
    }


def _day_bounds(day: str) -> "tuple[float, float]":
    """Local midnight to local midnight. Local, because "today" in the app
    is the user's today and not UTC's."""
    d = datetime.strptime(day, "%Y-%m-%d")
    start = d.timestamp()
    return start, (d + timedelta(days=1)).timestamp()


def history(limit: int = 20, day: "str|None" = None) -> dict:
    """Newest first. With `day` (YYYY-MM-DD) every row from that local day,
    because a page that shows one day must not stop at twenty."""
    from . import history as _h
    if day:
        try:
            start, end = _day_bounds(day)
        except ValueError:
            return {"day": day, "items": [], "error": "day must be YYYY-MM-DD"}
        rows = [r for r in _h.recent(limit=100000, since=start)
                if r["at"] < end]
        return {"day": day, "items": [_row(r) for r in rows]}
    return {"day": None, "items": [_row(r) for r in _h.recent(limit=limit)]}


def _streak(days: set, today: date) -> int:
    """Consecutive days with something said, ending today or yesterday.

    Yesterday counts as an end, so a streak does not read zero all morning
    until the first sentence of the day: it is still alive until today is
    over without one."""
    if today in days:
        d = today
    elif today - timedelta(days=1) in days:
        d = today - timedelta(days=1)
    else:
        return 0
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


def stats(now: "float|None" = None) -> dict:
    """{"words": int, "wpm": number|None, "streak_days": int}, from local
    history only.

    Words per minute is counted over the rows that know how long they took.
    Rows with no duration are left out of it rather than counted as instant,
    which would push the average to infinity, and with none at all it is None
    rather than zero: zero words a minute is a claim, and there is no
    evidence for it."""
    from . import history as _h
    rows = _h.recent(limit=10_000_000)
    words = 0
    timed_words, secs = 0, 0.0
    days = set()
    for r in rows:
        n = len((r.get("shown") or r.get("heard") or "").split())
        words += n
        if (r.get("secs") or 0) > 0:
            timed_words += n
            secs += float(r["secs"])
        try:
            days.add(date.fromtimestamp(float(r["at"])))
        except Exception:
            pass
    wpm = round(timed_words / (secs / 60.0), 1) if secs > 0 else None
    today = date.fromtimestamp(now if now is not None else time.time())
    return {"words": words, "wpm": wpm, "streak_days": _streak(days, today)}
