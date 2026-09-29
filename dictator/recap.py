"""What you dictated, read back to you at the end of the day.

This summarises what was DICTATED, not what was said in a room. The distinction
is the whole design. Every competitor's notes feature records a meeting: system
audio plus the microphone, a diarization model to work out who spoke, and then a
summarisation pass in somebody's cloud. That is three new things, one of which
is a macOS permission the user has to be talked into, and the last of which
breaks the only promise this product makes.

The history already holds every utterance with its time and the application it
went into. So a recap needs no new capture, no diarization, no new permission,
and no network. It is also the half of the feature a dictation tool is uniquely
placed to do: nothing else on the machine knows what you said into Slack at
eleven and into a terminal at noon.

Prose comes from a local model when one is on the machine, and from grouping
alone when one is not. Both are honest and the report says which it is. What it
will never do is call a server that is not on this machine, because a summary
is a nice-to-have and the privacy claim is the product.

    from dictator import Dictator
    print(Dictator().recap("today"))
"""
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import core, history

# A pause this long means you got up, switched task, or joined a call. Twenty
# minutes was picked to be longer than thinking between sentences and shorter
# than a break, so a session is one piece of work rather than one morning.
SESSION_GAP = 20 * 60

# Below this, a period is not a day's work and a report about it would be
# padding. Four utterances get printed as four utterances.
QUIET = 5

# A session smaller than this is quoted in full rather than summarised. There is
# nothing to compress in two lines, and asking a model to compress them is how
# you get a summary that says more than the source did.
PROSE_MIN = 3

# A ceiling on model calls per recap, so a week of heavy dictation cannot turn
# one command into two minutes of waiting. The sessions are taken longest first,
# because those are the ones worth prose.
MAX_CALLS = 8

# How many of your own lines to show under a session that did not get prose.
QUOTE = 4


# ---- the period ------------------------------------------------------------

def window(when: "str | int" = "today") -> tuple:
    """Turn today, week, or a number of days into (since, until, label).

    Days start at local midnight rather than 24 hours ago, because "today" has
    to mean what the calendar says or the recap disagrees with the person
    reading it."""
    now = time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                            0, 0, 0, 0, 0, -1))
    spec = str(when or "today").strip().lower()
    if spec in ("", "today"):
        return midnight, now, "today"
    if spec in ("week", "7"):
        return midnight - 6 * 86400, now, "the last 7 days"
    if spec == "yesterday":
        return midnight - 86400, midnight, "yesterday"
    try:
        days = max(1, int(float(spec)))
    except Exception:
        return midnight, now, "today"
    if days == 1:
        return midnight, now, "today"
    return midnight - (days - 1) * 86400, now, f"the last {days} days"


def utterances(since: float, until: float = 0.0) -> list:
    """Everything dictated in the period, oldest first.

    `kept` wins over `shown` where we have it: it is what the sentence had
    become once the user was done with it, which is closer to what they meant
    than what the recogniser produced."""
    until = until or time.time()
    rows = [r for r in history.recent(limit=20000, since=since)
            if r["at"] <= until]
    out = []
    for r in sorted(rows, key=lambda r: r["at"]):
        text = (r.get("kept") or r.get("shown") or r.get("heard") or "").strip()
        if text:
            out.append({"at": r["at"], "app": r.get("app") or "",
                        "secs": r.get("secs") or 0.0, "text": text})
    return out


def sessions(rows: list) -> list:
    """Split a day into stretches of work, on silence rather than on clock.

    A new session starts after a long gap OR when the words started landing in
    a different application, because moving from the terminal to Slack is a
    change of task even when it happens in the same minute."""
    out = []
    for r in rows:
        if (out and r["at"] - out[-1]["end"] < SESSION_GAP
                and r["app"] == out[-1]["app"]):
            out[-1]["lines"].append(r)
            out[-1]["end"] = r["at"]
            out[-1]["secs"] += r["secs"]
        else:
            out.append({"app": r["app"], "start": r["at"], "end": r["at"],
                        "secs": r["secs"], "lines": [r], "prose": ""})
    return out


# ---- what kept coming up ---------------------------------------------------

# Function words, plus the words that survive every dictation regardless of
# what the work was ("okay", "please", "just"). A term list that reports "just"
# as a theme is worse than no term list.
_STOP = set("""
a an the and or but so then than that this these those it its it's is are was
were be been being am do does did doing done have has had having will would
can could should shall may might must need needs to of in on at by for with
from into onto about as if not no yes ok okay right just now also very really
i me my we us our you your he she they them their there here what which who
whom when where why how all any both each few more most other some such only
own same too let lets go going goes get gets got make makes made put puts one
two three like want wants wanted say says said thing things stuff bro yaar ye
hai kya nahi haan bhi kar karo raha rahi rahe tha the ka ki ke ko se me mein
""".split())


def _words(text: str) -> list:
    return [w for w in re.findall(r"[a-zA-Z][a-zA-Z'\-]{2,}", text.lower())
            if w not in _STOP]


def terms(rows: list, top: int = 6) -> list:
    """The words this period was actually about.

    A word only counts if it turns up in more than one utterance. Said once, a
    long word is a detail of a single sentence, and promoting it to a theme
    invents a pattern that was not there."""
    seen: dict = {}
    spread: dict = {}
    for i, r in enumerate(rows):
        for w in set(_words(r["text"])):
            spread[w] = spread.get(w, 0) + 1
        for w in _words(r["text"]):
            seen[w] = seen.get(w, 0) + 1
    out = [(w, n) for w, n in seen.items() if spread.get(w, 0) >= 2 and n >= 3]
    out.sort(key=lambda wn: (-wn[1], wn[0]))
    return out[:top]


# ---- the local model, or nothing -------------------------------------------

# Loopback only, and checked rather than assumed. This is the one place in the
# product where a URL exists at all, so it is the one place where a mistake
# could send somebody's dictation history off the machine.
_LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")
PORT = int(os.environ.get("DICTATOR_LLM_PORT") or (6300 + os.getuid() % 1000))
BASE = os.environ.get("DICTATOR_LLM_URL") or f"http://127.0.0.1:{PORT}"

TIMEOUT = 30.0          # one session summary, on a warm 4B: about 3 seconds
START_WAIT = 45.0       # a 2.5GB model off a cold disk is slower than off cache


def local_only(url: str) -> bool:
    """Whether a URL points at this machine. Anything else is refused."""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    return host.lower() in _LOOPBACK


def model_path() -> Path:
    """Where the summarising model lives, if it is here at all.

    Same order as the speech models, and for the same reason: these files are
    gigabytes and are not specific to this product, so a machine that already
    has one should not fetch it again."""
    env = os.environ.get("DICTATOR_LLM_MODEL")
    if env:
        return Path(env).expanduser()
    name = "qwen3-4b-instruct-2507-q4_k_m.gguf"
    own = core.STATE_DIR / "models" / name
    if own.exists():
        return own
    return Path.home() / ".voicebridge" / "models" / name


def server_bin() -> str:
    from shutil import which
    p = which("llama-server")
    if p:
        return p
    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        if os.path.exists(os.path.join(d, "llama-server")):
            return os.path.join(d, "llama-server")
    return ""


def up(timeout: float = 1.0) -> bool:
    if not local_only(BASE):
        return False
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=timeout).read()
        return True
    except Exception:
        return False


def available() -> bool:
    """Can this machine write the prose itself, right now."""
    if not local_only(BASE):
        return False
    if up():
        return True
    try:
        # A truncated download is worse than no model: the server fails to load
        # it and the failure reads like a bug in this code.
        return bool(server_bin()) and model_path().stat().st_size > 1_000_000_000
    except Exception:
        return False


_proc = None


def _start() -> bool:
    """Bring the model up for the length of one recap. Returns whether we
    started it, which is also whether we are the one allowed to stop it: a
    server somebody else is using must survive this command."""
    global _proc
    if up():
        return False
    binp = server_bin()
    if not binp:
        return False
    try:
        _proc = subprocess.Popen(
            [binp, "-m", str(model_path()), "--port", str(PORT),
             "--ctx-size", "8192",          # a long session plus its summary
             "--n-gpu-layers", "99",
             "--parallel", "1", "--no-webui"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    except Exception as e:
        core.log(f"recap: could not start the local model: {e}")
        return False
    t0 = time.time()
    while time.time() - t0 < START_WAIT:
        if up():
            return True
        time.sleep(0.4)
    core.log("recap: the local model did not come up in time")
    _stop()
    return False


def _stop() -> None:
    """Put it away again, by handle rather than by name, so this can never kill
    a server this command did not start.

    Deliberately not left resident. We measured that a warm speech server makes
    dictation SLOWER because it contends for the same GPU (3.2s against 5.8s on
    this machine), and dictation is the product. A 2.5GB process left running
    after a once-a-day command would be paid for by every hold after it."""
    global _proc
    p, _proc = _proc, None
    if p is None:
        return
    try:
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


_SYSTEM = (
    "You summarise one person's own dictated notes for them. Every fact must "
    "come from the lines you are given. Do not invent names, numbers, "
    "decisions, outcomes or reasons. If the lines do not say why something was "
    "done, do not say why. Write one to three short sentences in plain past "
    "tense, starting with a verb. No preamble, no lists, no markdown, no "
    "headings, no quotes.")


def _ask(block: str) -> str:
    """One summary, or '' meaning the caller shows the lines instead."""
    if not local_only(BASE):
        return ""
    body = {"messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": block[:6000]}],
            "max_tokens": 200, "temperature": 0.2, "stream": False}
    try:
        req = urllib.request.Request(
            f"{BASE}/v1/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
        choice = (d.get("choices") or [{}])[0]
        return ((choice.get("message") or {}).get("content") or "").strip()
    except Exception as e:
        core.log(f"recap: local model call failed: {e}")
        return ""


def _stem(word: str) -> str:
    """Enough of a word to recognise it again. Crude on purpose: this exists to
    tell "committed" from "Priya", not to do morphology."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def grounded(prose: str, source: str, floor: float = 0.7) -> bool:
    """Is every idea in this summary traceable to the lines it summarised.

    A small model's failure mode is not gibberish, it is fluent invention: a
    name nobody said, a decision nobody made, a reason for a thing that had no
    stated reason. That reads as a fact in a report about your own day, which
    is exactly the kind of wrong that gets believed.

    So the summary is checked back against its source and thrown away if too
    much of it is new. The threshold is loose (linking verbs and ordinary
    connective words are expected to be new) and it is the invented NOUN this
    is hunting: a sentence about a person or a number that was never dictated
    fails it comfortably. Throwing away a good summary costs a paragraph;
    keeping a bad one costs the user's trust in every other line."""
    have = {_stem(w) for w in _words(source)}
    want = [_stem(w) for w in _words(prose)]
    if not want:
        return False
    known = sum(1 for w in want if w in have)
    return known / len(want) >= floor


def _clean(text: str) -> str:
    """House style, and TTS style: a dash mid-sentence reads as a stumble when
    voicebridge speaks one of these out loud."""
    text = text.replace("—", ", ").replace("–", ", ")
    return re.sub(r"\s+", " ", text).replace(" ,", ",").strip()


def prose_for(block: str) -> str:
    """A summary of one session, or '' if we could not get an honest one."""
    out = _clean(_ask(block))
    if not out:
        return ""
    # Longer than what it summarised is not a summary. Small models pad when
    # they have little to work with, and padding is the failure this whole
    # feature is supposed to avoid.
    if len(out) > max(160, len(block) * 0.9):
        core.log("recap: the local model padded rather than compressed")
        return ""
    if not grounded(out, block):
        core.log("recap: dropped a summary that said more than was dictated")
        return ""
    return out


# ---- the report ------------------------------------------------------------

@dataclass
class Recap:
    """A period of dictation, and what can honestly be said about it."""
    text: str = ""              # the printable report
    label: str = "today"        # which period this is
    since: float = 0.0
    until: float = 0.0
    utterances: int = 0
    seconds: float = 0.0        # how long the person was actually talking
    sessions: list = field(default_factory=list)
    terms: list = field(default_factory=list)
    source: str = "grouping"    # "model" when prose came from the local model

    def __bool__(self) -> bool:
        return self.utterances > 0

    def __str__(self) -> str:
        return self.text


def _clock(at: float) -> str:
    return time.strftime("%H:%M", time.localtime(at))


def _day(at: float) -> str:
    return time.strftime("%A %d %B", time.localtime(at))


def _block(session: dict) -> str:
    """What the model is shown: the person's own lines, nothing else."""
    head = (f"{session['app'] or 'unknown application'}, "
            f"{_clock(session['start'])} to {_clock(session['end'])}:\n")
    return head + "".join(f"- {ln['text']}\n" for ln in session["lines"])


def report(when: "str | int" = "today", prose: bool = True) -> Recap:
    """The recap. Never raises, and never pads.

    Three honest answers before any summarising happens: nothing was dictated,
    a handful of things were dictated (so here they are, verbatim), or there is
    enough here to group and summarise."""
    since, until, label = window(when)
    rows = utterances(since, until)
    r = Recap(label=label, since=since, until=until, utterances=len(rows),
              seconds=sum(x["secs"] for x in rows))

    if not rows:
        r.text = (f"Nothing dictated {label}.\n"
                  "  Hold the key and talk, and this will have something to "
                  "tell you.\n")
        return r

    r.sessions = sessions(rows)
    r.terms = terms(rows)

    # A handful of utterances is not a day's work. Printing them as they were
    # said is more useful than a heading and a theme and a conclusion drawn
    # from four sentences.
    if len(rows) < QUIET:
        lines = [f"{len(rows)} thing{'s' if len(rows) != 1 else ''} dictated "
                 f"{label}, which is not enough to summarise. Here they are:\n"]
        for x in rows:
            lines.append(f"  {_clock(x['at'])}  {x['app'] or '':<14} "
                         f"{x['text']}\n")
        r.text = "".join(lines)
        return r

    if prose and available():
        started = False
        try:
            started = _start()
            if up():
                # Longest first: if the ceiling bites, it should bite on the
                # sessions with least in them.
                for s in sorted(r.sessions, key=lambda s: -len(s["lines"])
                                )[:MAX_CALLS]:
                    if len(s["lines"]) >= PROSE_MIN:
                        s["prose"] = prose_for(_block(s))
                        if s["prose"]:
                            r.source = "model"
        finally:
            if started:
                _stop()

    r.text = render(r)
    return r


def render(r: Recap) -> str:
    """The report as it is read. Times and applications are evidence: every
    claim above them can be checked against the line that produced it."""
    multiday = time.strftime("%j", time.localtime(r.since)) != \
        time.strftime("%j", time.localtime(r.until))
    apps = []
    for s in r.sessions:
        if s["app"] and s["app"] not in apps:
            apps.append(s["app"])

    mins = r.seconds / 60.0
    head = f"{_day(r.until) if not multiday else r.label.capitalize()}: " \
           f"{r.utterances} things dictated"
    if mins >= 1:
        head += f", {mins:.0f} minutes of talking"
    if apps:
        head += ", in " + ", ".join(apps[:4])
    out = [head + ".\n"]

    day = ""
    for s in r.sessions:
        if multiday and _day(s["start"]) != day:
            day = _day(s["start"])
            out.append(f"\n{day}\n")
        out.append(f"\n  {_clock(s['start'])} to {_clock(s['end'])}   "
                   f"{s['app'] or 'unknown'}   {len(s['lines'])} said\n")
        if s["prose"]:
            out.append(_wrap(s["prose"], "    "))
            # Even with prose, one real line is shown. It is the receipt: the
            # summary is ours, this is theirs.
            out.append(f'    said: "{_short(s["lines"][0]["text"])}"\n')
        else:
            for ln in s["lines"][:QUOTE]:
                out.append(f'    {_clock(ln["at"])}  {_short(ln["text"])}\n')
            if len(s["lines"]) > QUOTE:
                out.append(f"    and {len(s['lines']) - QUOTE} more\n")

    if r.terms:
        out.append("\n  Kept coming up: "
                   + ", ".join(f"{w} ({n})" for w, n in r.terms) + "\n")

    if r.source == "model":
        out.append("\n  The prose was written by a model on this machine. "
                   "Nothing left it.\n")
    else:
        out.append("\n  No local model here, so this is grouping only: your "
                   "own lines by\n  time and application, and the words that "
                   "repeated. It cannot tell you\n  what you decided, only "
                   "what you said.\n")
    return "".join(out)


def _short(text: str, width: int = 88) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1] + "…"


def _wrap(text: str, indent: str, width: int = 74) -> str:
    words, line, out = text.split(), "", []
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            out.append(indent + line + "\n")
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(indent + line + "\n")
    return "".join(out)
