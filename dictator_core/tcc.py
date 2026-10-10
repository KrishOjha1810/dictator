"""What macOS actually remembers about Dictator, and for which signature.

There is one failure in this product that costs days rather than minutes, and
it is not a crash. macOS shows a ticked checkbox next to "Dictator" in
System Settings, Privacy & Security, Accessibility, and `AXIsProcessTrusted()`
inside the running app returns false anyway. The user has already done the
right thing, the switch they can see is already on, and there is nothing left
for them to click.

The reason is that TCC stores a row keyed by (service, bundle identifier) and
a **code requirement** alongside it. The list in System Settings is drawn from
the row. Trust is decided by the requirement. When the app's signature changes,
the row survives with the old requirement in it, so the tick stays and the
trust does not, and because a row already exists macOS never prompts again.

Measured on this machine while it was in exactly that state:

    row   kTCCServiceAccessibility  com.dictator.dictation  auth_value=2
          certificate leaf = H"cbd3aabec79d29dcfc329c1bbba154709b13462a"
    app   certificate leaf = H"8501b12ce31fe51f7ee209340e355c18398a0d23"

The tick was on. The app was not trusted. Toggling that switch cannot fix it,
because it rewrites auth_value and leaves the requirement alone. The entry has
to be REMOVED, with the minus button, so the next ask writes a fresh one.

So this module answers two different questions that look the same from the
outside:

    "never granted"  no row at all, so the prompt still works, just say yes
    "granted to a signature that is no longer ours"  a row with the wrong
                     requirement, so the prompt will never appear again and
                     the entry has to be removed by hand

Reading the databases needs Full Disk Access for whatever is doing the
reading, which a user's terminal usually does not have. That is not fatal:
`unreadable` is a real answer and is reported as one, with the behavioural
test the user can do in ten seconds instead.
"""
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from . import core

# Per account, because Accessibility rows are system-wide and keyed by this.
# See core.bundle_id.
BUNDLE_ID = core.bundle_id()

# What every install used before the identifier became per account. Any row
# still under it belongs to no app that exists now, and it shows in System
# Settings as a second entry called "Dictator" next to the real one, which is
# a good way to switch on the wrong thing and conclude the fix did not work.
LEGACY_IDS = ("com.dictator.dictation", "com.dictator.meeting")


def orphans() -> list:
    """Rows left behind by the shared identifier, or [] if there are none and
    None if the databases cannot be read."""
    found, looked = [], False
    for old in LEGACY_IDS:
        for service in ("accessibility", "input monitoring", "microphone"):
            rows = _rows(service, old)
            if rows is None:
                continue
            looked = True
            if rows:
                found.append((service, old))
    return found if looked else None

# Accessibility and Input Monitoring live in the machine-wide database.
# Microphone lives in the per-user one. Getting this the wrong way round
# reports "never granted" for a permission that has been granted for months.
SYSTEM_DB = Path("/Library/Application Support/com.apple.TCC/TCC.db")
USER_DB = (Path.home() / "Library" / "Application Support"
           / "com.apple.TCC" / "TCC.db")

SERVICES = {
    "accessibility": (SYSTEM_DB, "kTCCServiceAccessibility"),
    "input monitoring": (SYSTEM_DB, "kTCCServiceListenEvent"),
    "microphone": (USER_DB, "kTCCServiceMicrophone"),
}

# The states, in the order they are worth telling apart.
GRANTED = "granted"          # ticked, and the requirement matches this build
STALE = "stale"              # ticked, and the requirement is another build's
DENIED = "denied"            # the user said no, or switched it off
MISSING = "missing"          # no row at all: the prompt still works
UNREADABLE = "unreadable"    # no Full Disk Access, so we cannot look
NO_APP = "no app"            # the bundle is not built yet

# Read off this machine rather than remembered: on macOS 26.5.1 the shipped
# System Settings privacy extension heads this list with exactly this sentence,
# and labels the two buttons under it "Add" (the plus) and "Remove" (the minus).
PANE = ("System Settings, Privacy & Security, Accessibility\n     "
        "(headed \"Allow the applications below to control your computer.\")")

# The other two panes. Sending somebody to Accessibility to switch on the
# microphone is a wrong instruction that reads like a right one: they go to
# the named pane, do not find the switch, and conclude the tool is confused.
_PANES = {
    "accessibility": PANE,
    "input monitoring": "System Settings, Privacy & Security, Input Monitoring",
    "microphone": "System Settings, Privacy & Security, Microphone",
}

_TITLES = {
    "accessibility": "Accessibility",
    "input monitoring": "Input Monitoring",
    "microphone": "Microphone",
}


def pane(service: str) -> str:
    return _PANES.get(service, PANE)


def title(service: str) -> str:
    return _TITLES.get(service, "Accessibility")


def _rows(service: str, client: str = BUNDLE_ID):
    """Every TCC row for this service and client, or None if we cannot look.

    None and [] are different answers and the difference is the whole point of
    this module: [] means there is no entry and the prompt will work, None
    means we were not allowed to find out."""
    try:
        db, name = SERVICES[service]
    except KeyError:
        return None
    if not db.exists():
        return None
    try:
        # immutable, so reading never creates a journal next to a database
        # owned by root, and never waits on a writer.
        con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
        try:
            cur = con.execute(
                "select auth_value, csreq from access "
                "where service = ? and client = ?", (name, client))
            return [(int(a or 0), bytes(b) if b else b"") for a, b in cur]
        finally:
            con.close()
    except Exception as e:
        # Almost always "unable to open database file", which is macOS
        # refusing the read rather than anything being wrong.
        core.log(f"tcc: cannot read {db.name}: {e}")
        return None


def requirement_text(csreq: bytes) -> str:
    """The stored requirement in the form codesign prints it.

    The blob is a serialised code requirement. /usr/bin/csreq turns it back
    into text, which is the same text `codesign -d -r-` prints for the bundle,
    so the two can be put side by side in front of a user."""
    if not csreq:
        return ""
    try:
        with tempfile.TemporaryDirectory() as d:
            blob = Path(d) / "req"
            blob.write_bytes(csreq)
            r = subprocess.run(["/usr/bin/csreq", "-r", str(blob), "-t"],
                               capture_output=True, text=True, timeout=20)
            return (r.stdout or "").strip()
    except Exception as e:
        core.log(f"tcc: could not read a stored requirement: {e}")
        return ""


def satisfies(app, requirement: str) -> bool:
    """Does this bundle satisfy that requirement?

    This is not a string comparison of two hashes, on purpose. It asks
    codesign the same question TCC asks, so a requirement written in any form
    macOS accepts is answered correctly rather than only the one form we
    happen to emit today."""
    if not requirement:
        # An empty requirement means the row constrains nothing beyond the
        # bundle identifier, so anything with that identifier satisfies it.
        return True
    try:
        r = subprocess.run(["codesign", "--verify", f"-R={requirement}",
                            str(app)], capture_output=True, text=True,
                           timeout=60)
        return r.returncode == 0
    except Exception as e:
        core.log(f"tcc: could not test the requirement: {e}")
        return True          # never call a working grant broken on a failure


def state(service: str = "accessibility", app=None) -> dict:
    """The true state of one permission, and who currently holds it.

    Returns a dict rather than a string because every caller needs the reason
    as well as the verdict: `doctor` prints one line, `permissions` prints the
    recovery steps, and the app in native/app writes it where the user will
    see it."""
    if app is None:
        from . import always
        app = always.APP
    app = Path(app)
    out = {
        "service": service,
        "app": str(app),
        "state": NO_APP,
        "ticked": None,       # what System Settings is showing, if we can see
        "held_by": "",        # the requirement the grant was written for
        "wanted": "",         # what this build actually is
        "readable": False,
    }
    if not app.exists():
        return out
    from . import signing
    out["wanted"] = signing.requirement(app)

    rows = _rows(service)
    if rows is None:
        out["state"] = UNREADABLE
        return out
    out["readable"] = True
    if not rows:
        out["state"] = MISSING
        out["ticked"] = False
        return out

    # More than one row for the same client is possible when macOS has kept an
    # old identity around. Any row this build satisfies is a working grant, so
    # look for one before concluding anything.
    allowed = [(a, b) for a, b in rows if a == 2]
    out["ticked"] = bool(allowed)
    if not allowed:
        out["state"] = DENIED
        out["held_by"] = requirement_text(rows[0][1])
        return out
    for _, blob in allowed:
        req = requirement_text(blob)
        if satisfies(app, req):
            out["state"] = GRANTED
            out["held_by"] = req
            return out
    out["state"] = STALE
    out["held_by"] = requirement_text(allowed[0][1])
    return out


def summary(info: dict) -> str:
    """One line, for a checklist."""
    s = info["state"]
    if s == GRANTED:
        return "granted to this build"
    if s == STALE:
        return ("the tick in System Settings belongs to an older build, so "
                "macOS does not trust this one")
    if s == DENIED:
        return "switched off in System Settings"
    if s == MISSING:
        return "never granted"
    if s == NO_APP:
        return "the app is not built yet"
    return ("cannot tell: reading what macOS remembers needs Full Disk "
            "Access, which whatever is asking does not have")


def advice(info: dict) -> str:
    """What to actually do about it, in the order that works.

    The wording of the pane and of the buttons was read off this machine
    rather than remembered: the labels come out of the shipped System Settings
    privacy extension, where the list is headed "Allow the applications below
    to control your computer." and the two buttons under it are "Add" (the
    plus) and "Remove" (the minus)."""
    s = info["state"]
    # Which pane, taken from the service rather than assumed. Accessibility,
    # Input Monitoring and Microphone are three different lists in System
    # Settings, and naming the wrong one reads as a right instruction: the
    # user goes where they were sent, finds no switch, and stops trusting the
    # rest of the diagnosis.
    PANE = pane(info.get("service") or "accessibility")
    WHAT = title(info.get("service") or "accessibility")
    if s == GRANTED:
        return ""
    if s == STALE:
        return f"""macOS is showing a tick next to Dictator that does not count.

The permission was granted to an earlier build with a different code
signature. The switch you can see is on, and this build is still not trusted.

  macOS remembers:  {info['held_by'] or 'a requirement it will not show us'}
  this build is:    {info['wanted'] or 'unsigned'}

Switching that toggle off and on will NOT fix it. It rewrites the tick and
leaves the signature alone, which is the one thing that is wrong. The entry
has to be removed so the app can ask again:

  1. Open {PANE}
  2. Click Dictator once, to select the row
  3. Click the minus button under the list, the one labelled Remove
  4. Confirm if it asks, and enter your password if it asks for that
  5. Run:  dictator off && dictator on
  6. Say yes to the dialog that appears

Or have all of that done for you:  dictator permissions --reset"""
    if s == DENIED:
        return f"""{WHAT} is switched off for Dictator.

  1. Open {PANE}
  2. Switch Dictator on

It starts listening on its own within a couple of seconds. Nothing to
restart."""
    if s == MISSING:
        return f"""Dictator has never been granted {WHAT}.

  1. Open {PANE}
  2. Switch Dictator on. If it is not in the list at all, click the plus
     button under the list and choose the app:
       {info.get('app') or Path.home() / 'Applications' / 'Dictator.app'}

It starts listening on its own within a couple of seconds. Nothing to
restart."""
    if s == NO_APP:
        return "The app is not built yet. Run:  dictator build"
    return f"""Cannot read what macOS remembers, so this is the ten second
version you can do by eye.

  1. Open {PANE}
  2. Is Dictator in the list?
       no   click the plus button under the list and add:
              {info.get('app') or Path.home() / 'Applications' / 'Dictator.app'}
       yes, and the switch is off   switch it on, and you are done
       yes, and the switch is ALREADY ON   this is the one that traps
              people. The tick belongs to an older build. Select the row,
              click the minus button under the list (labelled Remove), then
              run:  dictator off && dictator on

To get the precise answer instead of this one, give the terminal you run
`dictator doctor` from Full Disk Access, in System Settings, Privacy &
Security. Reading which signature a grant was written for needs it."""


def verdict(info: dict, saw: dict = None) -> tuple:
    """The checklist answer: ("ok" | "bad" | "unknown", detail).

    Separate from the printing, and tested on its own, because this is exactly
    where this product has already been bitten. `doctor` once reported the
    single state it exists to catch as fine, and a check that passes the
    broken case is worse than no check, because it sends the user away from
    the one place the answer was.

    Three outcomes, not two. "I could not read the database" is not "fine",
    and collapsing it into one would rebuild that bug in a new shape.

    `saw` is `waiting()`, what the listener last said about ITSELF, and it is
    consulted before the databases rather than only when they cannot be read.
    That ordering is the point. Everything else here is us reading a record
    macOS keeps about an app bundle on disk; `AXIsProcessTrusted()` can only
    be asked by the process asking it, so a running listener saying NO is the
    one direct measurement in this file and the only one about the process
    that actually holds the key.

    It is deliberately not symmetric, and the reason is written down elsewhere
    in docs/findings.md: a process launched from a terminal that has the grant
    reports `AXIsProcessTrusted() == true` even when its own entry is stale,
    which is exactly why the broken state could not be reproduced from a shell
    and kept being reported as working. So a listener saying YES is not
    evidence of anything and never overrides the databases. Only NO counts."""
    saw = saw or {}
    s = info.get("state")
    if saw.get("trusted") is False:
        # A dead listener's last words are not a claim about now; `waiting()`
        # drops those, so reaching here means something is running and saying
        # it cannot see the permission.
        if s == GRANTED:
            # The confusing one, and the reason this branch is not simply
            # folded in with the others. macOS remembers a grant that matches
            # this BUILD and the process actually running still cannot see it,
            # which means the thing holding the key is not the build the grant
            # was written for: an older copy still resident from before a
            # rebuild. No pane will show this and nothing in it needs changing.
            return "bad", ("macOS has a grant for this build and the listener "
                           "that is running still cannot see it, so the "
                           "process holding the key is not this build. "
                           "Run: dictator permissions")
        return "bad", ("the listener says it is NOT trusted. "
                       "Run: dictator permissions")
    if s == GRANTED:
        return "ok", "the grant matches the signature it is running under"
    if s == NO_APP:
        return "unknown", "the app is not built yet"
    if s == UNREADABLE:
        return "unknown", ("cannot read what macOS remembers (needs Full Disk "
                           "Access). Run: dictator permissions")
    return "bad", summary(info) + ". Run: dictator permissions"


def report(service: str = "accessibility", app=None) -> str:
    """The whole diagnosis as one block of text, for a log or a terminal."""
    info = state(service, app)
    head = f"{title(service)}: {summary(info)}"
    rest = advice(info)
    return f"{head}\n\n{rest}" if rest else head


# ---------------------------------------------------------------------------
# What the listener saw, which is the only reliable signal when the databases
# cannot be read.

WAITING_FILE = core.STATE_DIR / "permission.json"

# Only used for a record that has no pid in it, which means an app bundle from
# before the pid was written down. The app republishes "still waiting" every
# two minutes, so five missed republishes is comfortably past any doubt.
STALE_AFTER = 600.0


def _alive(pid) -> bool:
    """Is that process still there?

    Anything we cannot answer counts as alive, because the cost of the two
    mistakes is not the same: calling a live listener dead hides the one
    problem this file exists to report."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        # PermissionError means it exists and is not ours, which is alive.
        return True


def waiting() -> dict:
    """The app's own last word on whether it is trusted, while it still holds.

    `AXIsProcessTrusted()` can only be asked by the process itself, and the
    process that matters here is the app bundle, not python. So the app writes
    its answer down and this reads it back. That makes the whole diagnosis
    work on a machine where the TCC databases are unreadable, which is most of
    them.

    The two answers do not age the same way and this is the whole reason the
    function is not one line. "Trusted" is a fact that was true when it was
    written and stays true until something changes it, and the app writes it
    once and never again, so nothing may expire it. "Not trusted" is a claim
    about RIGHT NOW: somebody is sitting in front of a dialog. Stop the
    listener while it is in that state and the claim outlives the process
    making it, so `doctor` goes on reporting a permission problem for a
    machine that is simply not running anything, and `dictator on` prints the
    whole TCC diagnosis at somebody who has nothing wrong.

    So an untrusted record is believed only while the process that wrote it is
    alive. The pid is exact where an age would be a guess, which is the same
    argument `recorder.level` makes one file over about a level published by a
    microphone that has since closed."""
    import json
    import time
    try:
        w = json.loads(WAITING_FILE.read_text())
    except Exception:
        return {}
    if not isinstance(w, dict):
        return {}
    if w.get("trusted") is not False:
        return w
    if "pid" in w:
        return w if _alive(w.get("pid")) else {}
    try:
        return w if time.time() - float(w.get("at") or 0) < STALE_AFTER else {}
    except Exception:
        return w


def stuck() -> bool:
    """Is a listener sitting there waiting for a permission right now?"""
    w = waiting()
    return bool(w) and w.get("trusted") is False
