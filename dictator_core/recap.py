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

    from dictator_core import Dictator
    print(Dictator().recap("today"))
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
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
know knows knew well good great sure fine still even ever never always again
uhh umm yeah yep nope please thanks thank sorry actually basically literally
don't doesn't didn't can't won't isn't it's i'm we're you're that's there's
let's they're wasn't aren't haven't hasn't shouldn't wouldn't couldn't
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


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect rather than follow it.

    Checking the URL before the call is not enough on its own. `urlopen`
    follows redirects by default, and a 307 re-issues the POST **with the
    body**, so a process on the loopback port could have the whole transcript
    forwarded anywhere it liked. The promise this feature makes is absolute, so
    it cannot rest on the server being well behaved: there is no legitimate
    reason for a local llama-server to redirect a completion, and refusing
    costs nothing.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            f"refusing a redirect to {newurl}: this never leaves the machine",
            headers, fp)


_opener = urllib.request.build_opener(_NoRedirects)


def _fetch(req, timeout: float):
    """Every HTTP call this module makes goes through here, so the redirect
    refusal cannot be forgotten at one call site."""
    return _opener.open(req, timeout=timeout)


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
        _fetch(f"{BASE}/health", timeout).read()
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


def _ask(block: str, system: str = _SYSTEM, max_tokens: int = 200,
         limit: int = 6000, timeout: float = 0.0) -> str:
    """One summary, or '' meaning the caller shows the lines instead.

    `system` is a parameter rather than a constant because meeting notes ask
    this same model three different questions of the same transcript. Two
    summarisers would mean two places for the loopback check, the server
    lifecycle and the grounding guard to drift apart, and the guard is the part
    that must never drift."""
    if not local_only(BASE):
        return ""
    body = {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": block[:limit]}],
            "max_tokens": max_tokens, "temperature": 0.2, "stream": False}
    try:
        req = urllib.request.Request(
            f"{BASE}/v1/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        d = json.loads(_fetch(
            req, timeout or TIMEOUT).read())
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


# Numbers get spoken as words and summarised as digits, so "hundred USDC" in
# the source has to count as 100 in the summary or the guard below fires on a
# correct sentence. That was the only false positive in the ten sessions this
# was first measured on, and reading a number word as its own value was enough
# to fix it. It is not enough in general: ten sessions happened not to contain
# an amount that takes two words. "twenty five" is one number and not two, so
# comparing sets of values called a correct summary an invention every time
# somebody dictated an amount above twenty. Runs of number words are therefore
# read as the number they spell, which is what the sections below do.
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    "lakh": 100000, "million": 1000000, "crore": 10000000,
}


_TOKEN = re.compile(r"\d[\d,]*\d|\d|[A-Za-z]+")


def _runs(text: str) -> list:
    """Every number in the text, as the list of values it was written with.

    A run is the number words and digits that sit next to each other, so
    "twenty five USDC" is one run of [20, 5] and "5 tests and 3 failures" is
    two runs. "and" continues a run rather than breaking it, because "two
    hundred and fifty" is one amount."""
    out, run = [], []
    for tok in _TOKEN.findall(text):
        low = tok.lower()
        if low[0].isdigit():
            try:
                run.append(int(low.replace(",", "")))
            except ValueError:
                pass
        elif low in _NUM_WORDS:
            run.append(_NUM_WORDS[low])
        elif low == "and" and run:
            continue
        elif run:
            out.append(run)
            run = []
    if run:
        out.append(run)
    return out


def _compose(parts: list) -> int:
    """A run of number words read as the one number somebody said.

    The ordinary school algorithm: values add up until a scale word multiplies
    what has been collected so far. "twenty five" is 25, "two hundred fifty"
    is 250, "one lakh fifty thousand" is 150000, and a bare "hundred" is 100,
    which is the case this guard was first fixed for."""
    total = current = 0
    for value in parts:
        if value >= 1000:
            current = (current or 1) * value
            total += current
            current = 0
        elif value == 100:
            current = (current or 1) * 100
        else:
            current += value
    return total + current


def _offered(text: str) -> set:
    """Every number the source can honestly be read as offering.

    Both the composed number and the pieces it was spelled with, because the
    summary is free to quote either: the source says "twenty five" and the
    model may write 25, or the source says 25 and the model may write it out.
    Being generous here is the safe direction. This set only ever excuses a
    number, and the check that matters is whether the summary invented one."""
    out = set()
    for run in _runs(text):
        out.add(_compose(run))
        out.update(run)
    return out


def _claimed(text: str) -> list:
    """Every number the summary asserts, as (the number, the pieces).

    Two chances to be explained, because one is not enough in either
    direction. The composed value covers a summary that wrote 25 for a source
    that said "twenty five". The pieces cover the opposite, a summary that
    wrote "one and two" for a source that said "1 and 2", where composing
    would have invented a 3 that nobody claimed."""
    return [(_compose(r), set(r)) for r in _runs(text)]


def _numbers(text: str) -> set:
    """Kept for callers that only want the values. See `_offered`."""
    return _offered(text)


def _propers(text: str) -> set:
    """Capitalised words that are not simply the start of a sentence, which is
    where an invented person, product or place shows up."""
    out = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", sentence)[1:]:
            if w[0].isupper():
                out.add(re.sub(r"'s$", "", w.lower()).strip("'-"))
    return out


# Measured on ten real sessions of this user's own dictation, summarised by the
# local model. A summary scored against the lines it was actually given: 0.47
# to 0.82. The same summaries scored against a DIFFERENT session: median 0.07.
# Three invented summaries (a meeting, an offer, an incident) against every one
# of those sources: maximum 0.17. So the honest ones and the invented ones are
# two clearly separated populations, and 0.45 sits in the gap. A floor of 0.7,
# which was the first guess, threw away six of the ten good ones.
GROUND_FLOOR = 0.45


def unsupported(prose: str, source: str, floor: float = GROUND_FLOOR) -> str:
    """Why this summary cannot be shown, or '' if it can.

    A small model's failure mode is not gibberish, it is fluent invention: a
    name nobody said, a number nobody gave, a decision nobody made. In a report
    about your own day that reads as a fact, which is the kind of wrong that
    gets believed, so a summary is checked back against the lines it was given
    and thrown away rather than shown with a caveat.

    Three checks, because one is not enough. The ratio catches a summary that
    is about something else entirely but cannot see a single invented name in
    an otherwise faithful paragraph, and that is precisely the dangerous one,
    so numbers and proper nouns are checked exactly. Throwing away a good
    summary costs a paragraph, and the lines are printed instead. Keeping a bad
    one costs the reader's trust in every other line of the report."""
    if not prose.strip():
        return "empty"
    offered = _offered(source)
    for value, pieces in _claimed(prose):
        if value in offered or pieces <= offered:
            continue
        return f"a number nobody dictated ({value})"
    known_words = {re.sub(r"'s$", "", w) for w in
                   re.findall(r"[a-z][a-z'\-]+", source.lower())}
    invented = sorted(p for p in _propers(prose) if p not in known_words)
    if invented:
        return f"a name nobody dictated ({invented[0]})"
    have = {_stem(w) for w in _words(source)}
    want = [_stem(w) for w in _words(prose)]
    if not want:
        return "no content"
    share = sum(1 for w in want if w in have) / len(want)
    if share < floor:
        return f"only {share:.0%} of it traces back to what was said"
    return ""


def grounded(prose: str, source: str, floor: float = GROUND_FLOOR) -> bool:
    return not unsupported(prose, source, floor)


def _clean(text: str) -> str:
    """House style, and TTS style: a dash mid-sentence reads as a stumble when
    voicebridge speaks one of these out loud."""
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    return re.sub(r"\s+", " ", text).replace(" ,", ",").strip()


def prose_for(block: str, system: str = _SYSTEM, max_tokens: int = 200,
              limit: int = 6000, against: str = "", what: str = "recap",
              timeout: float = 0.0, exempt: tuple = ()) -> str:
    """A summary of one session, or '' if we could not get an honest one.

    `against` is the text the answer is checked back against, when that is not
    the same as the text the model was shown. Meeting notes need it: the model
    is handed one stretch of a long transcript at a time, and the answer still
    has to trace back to the whole transcript."""
    out = _clean(_ask(block, system, max_tokens, limit, timeout))
    if not out:
        return ""
    # An answer that says there is nothing to report is not a claim about the
    # source and cannot be checked against it. Meeting notes need this: asked
    # what was decided in a meeting where nothing was, the honest answer is
    # "nothing was decided", and the grounding check threw exactly that away
    # for not tracing back to words anybody said. The section then looked
    # rejected when it had been answered correctly, which is the opposite fact.
    if out.strip().lower().rstrip(".") in exempt:
        return out
    # Longer than what it summarised is not a summary. Small models pad when
    # they have little to work with, and padding is the failure this whole
    # feature is supposed to avoid.
    if len(out) > max(160, len(block) * 0.9):
        core.log(f"{what}: the local model padded rather than compressed")
        return ""
    why = unsupported(out, against or block)
    if why:
        core.log(f"{what}: dropped a summary, {why}")
        return ""
    return out


@contextmanager
def model_up():
    """Hold the local model up for the length of one command, and put it away.

    Yields whether it is answering. The server is started and stopped per
    invocation on purpose: a resident speech server was measured to make
    dictation slower by contending for the same GPU (3.2s against 5.8s), and
    2.5GB left resident after a once-a-day command is paid for by every hold
    after it. A server somebody else started survives this, because we only
    stop the one we started."""
    started = False
    try:
        started = _start()
        yield up()
    finally:
        if started:
            _stop()


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
    # Where the prose came from, and when there is none, why there is none:
    #   model      a model on this machine wrote it
    #   not-asked  the caller asked for no prose
    #   no-model   there is no local model, so nothing could write it
    #   no-server  there is a model and it would not start
    #   rejected   the model answered and the answer was not supported
    #   too-short  nothing here was long enough to be worth compressing
    #
    # These used to be two labels doing the work of five. The default was
    # "no-model", and `--plain` short-circuits before anything corrects it, so
    # somebody with the 2.5GB model sitting in their models directory was told
    # it was not there. A server that failed to come up inside START_WAIT left
    # "rejected", which blames the model's honesty for a failure to launch.
    source: str = "not-asked"

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
            # Whole, not shortened. This is the path that promises the lines
            # themselves, so the only thing done to them is wrapping.
            lines.append(f"\n  {_clock(x['at'])}  {x['app'] or 'unknown'}\n")
            lines.append(_wrap(x["text"], "    "))
        r.text = "".join(lines)
        return r

    worth_prose = [s for s in r.sessions if len(s["lines"]) >= PROSE_MIN]
    if not worth_prose:
        r.source = "too-short"
    elif not prose:
        r.source = "not-asked"
    elif not available():
        r.source = "no-model"
    if prose and worth_prose and available():
        r.source = "rejected"       # until something usable comes back
        with model_up() as answering:
            if not answering:
                r.source = "no-server"
            if answering:
                # Longest first: if the ceiling bites, it should bite on the
                # sessions with least in them.
                for s in sorted(worth_prose,
                                key=lambda s: -len(s["lines"]))[:MAX_CALLS]:
                    s["prose"] = prose_for(_block(s))
                    if s["prose"]:
                        r.source = "model"

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
        # One sentence into one application is not a session, and giving it a
        # heading, a time range and a count makes a week of dictation read as
        # forty pieces of work instead of six.
        if len(s["lines"]) == 1:
            out.append(f"\n  {_clock(s['start'])}   {s['app'] or 'unknown'}   "
                       f"{_short(s['lines'][0]['text'], 60)}\n")
            continue
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
        out.append("\n  The prose above was written by a model on this "
                   "machine. Nothing left it.\n")
    else:
        why = {"not-asked": "you asked for it without the model",
               "no-model": "there is no local model on this machine",
               "no-server": "the local model is here but would not start; "
                            "see ~/.dictator/log",
               "rejected": "the local model did not return anything that "
                           "matched what you said",
               "too-short": "nothing here was long enough to be worth "
                            "compressing"}.get(r.source, "")
        out.append("\n")
        out.append(_wrap("Grouping only: your own lines by time and "
                         "application, and the words that repeated. Nothing "
                         "was summarised, because " + why + ".", "  "))
    return "".join(out)


def _short(text: str, width: int = 88) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3] + "..."


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
