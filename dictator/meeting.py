"""Record a meeting, transcribe it here, and say what it was about.

This is the other half of the notes feature. `recap.py` summarises what YOU
dictated; this records what was said in the room, which needs three things the
recap needed none of: a second audio source, a way through an hour of audio
that whisper can actually swallow, and a permission macOS treats as serious.

    dictator meeting start
    ...
    dictator meeting stop

Two tracks, never one. Your voice arrives at the microphone and everybody
else's arrives at the speakers, so they come from two different places and
there is no reason to mix them. Which file a sentence came out of is then the
only speaker labelling that is both free and honest: the microphone is you, the
system is them. Anything finer is diarization, which is a research problem and
is deliberately not attempted here.

Nothing about this is automatic. It does not watch your calendar, it does not
notice that a call started, and it does not begin without you typing the
command. macOS shows its own screen recording indicator in the menu bar for as
long as it runs, and that is on purpose too: recording other people has consent
implications and in some places legal ones, and a recorder nobody can see is
the wrong product whatever the law says where you are.

And, as with everything else here, no audio and no transcript leaves the
machine. The summarising model is the same local one `recap` uses, started for
the length of one command and put away afterwards, and it is held to the same
grounding checks, because an invented action item is worse than no notes.
"""
import array
import json
import os
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

from . import core, recap, stt

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "native" / "meeting.swift"
PLIST = REPO / "native" / "meetingapp" / "Info.plist"

# Its own bundle, and this is the load-bearing decision of the whole feature.
# macOS remembers a permission against a bundle identifier, so putting the
# recorder in a SEPARATE app means the Screen Recording grant it needs lands on
# com.dictator.meeting and cannot disturb the Microphone and Accessibility
# grants that com.dictator.dictation already holds. Adding this to the
# dictation bundle would have meant re-signing that bundle, and a rebuild of it
# has already cost this user his permissions once.
APP = Path.home() / "Applications" / "Dictator Meeting.app"
EXE = APP / "Contents" / "MacOS" / "DictatorMeeting"

MEETINGS = core.STATE_DIR / "meetings"
CURRENT = MEETINGS / "current"

# Four hours. Long enough that nobody hits it in a real meeting, short enough
# that a recorder forgotten overnight stops on its own rather than filling the
# disk. At 16kHz mono on two tracks that ceiling is about 920MB.
MAX_SECONDS = 4 * 3600

# Exit codes the recorder uses for the two things that are not bugs.
NO_SCREEN = 3
NO_MIC = 4


# ---- building the recorder -------------------------------------------------

def build_app(force: bool = False) -> str:
    """Build the recorder's own app bundle. Path, or "" with the reason logged.

    The staleness check is not an optimisation, it is the permission. Every
    rebuild produces a different binary, and macOS drops a grant when the
    binary changes even though the designated requirement is unchanged, so an
    unconditional rebuild here would cost the user the Screen Recording
    permission every single time they started a meeting. `always.build_app`
    learned this the expensive way and this is the same check for the same
    reason."""
    if not SRC.exists() or not PLIST.exists():
        return ""
    if not shutil.which("swiftc"):
        core.log("meeting: swiftc not found, cannot build the recorder")
        return ""
    if EXE.exists() and not force:
        newest = max(SRC.stat().st_mtime, PLIST.stat().st_mtime)
        if EXE.stat().st_mtime >= newest:
            return str(APP)
    EXE.parent.mkdir(parents=True, exist_ok=True)
    tmp = EXE.with_name(EXE.name + ".new")
    try:
        subprocess.run(["swiftc", "-O", str(SRC), "-o", str(tmp)],
                       check=True, capture_output=True, timeout=600)
        os.replace(tmp, EXE)
        shutil.copyfile(PLIST, APP / "Contents" / "Info.plist")
    except subprocess.CalledProcessError as e:
        core.log(f"meeting: build failed: {(e.stderr or b'').decode()[:400]}")
        return ""
    except Exception as e:
        core.log(f"meeting: build failed: {e}")
        return ""
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    _sign()
    return str(APP)


def _sign() -> None:
    """Same local certificate as the dictation app, so this bundle's own
    permissions also survive a rebuild. See signing.py."""
    from . import signing
    who = signing.identity()
    r = subprocess.run(["codesign", "--force", "-s", who or "-", str(APP)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        core.log(f"meeting: signing failed ({who or 'ad-hoc'}): "
                 f"{r.stderr.strip()[:200]}")
        if who:
            subprocess.run(["codesign", "--force", "-s", "-", str(APP)],
                           capture_output=True, timeout=120)
        return
    if "cdhash" in signing.requirement(APP):
        core.log("meeting: the recorder is ad-hoc signed, so macOS will forget "
                 "its Screen Recording permission on the next rebuild")


# ---- sessions on disk ------------------------------------------------------

def check(wait: float = 8.0) -> dict:
    """What macOS will actually allow right now. {} if we could not find out.

    Asked by running the recorder in a mode that records nothing, because TCC
    answers a process ONCE and caches it: a check made inside this Python
    process would keep reporting whatever was true when it started, which is
    exactly wrong for a walkthrough whose whole job is to notice a switch being
    flipped."""
    import tempfile
    if not EXE.exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        try:
            # -n: a fresh instance every time. Without it LaunchServices hands
            # the arguments to whatever copy is already running, which for a
            # cached TCC answer is the one thing that must not happen.
            r = subprocess.run(["open", "-n", "-a", str(APP), "--args",
                                "--check", str(out)],
                               capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                core.log("meeting: open refused to run the check: "
                         + ((r.stderr or "").strip() or str(r.returncode)))
                return {}
        except Exception as e:
            core.log(f"meeting: could not check permissions: {e}")
            return {}
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                return json.loads((out / "check.json").read_text())
            except Exception:
                time.sleep(0.2)
    return {}


def granted() -> bool:
    """Is everything a recording needs allowed yet.

    Both permissions, not just Screen Recording. Checking only the screen
    answered "Granted. Start a meeting" on a machine whose microphone was
    denied, which starts a recording that captures the room and not the person
    in it, and the walkthrough that exists to prevent exactly that said it was
    fine."""
    got = check()
    return bool(got.get("screen")) and bool(got.get("mic"))


def _dir(mid: str) -> Path:
    return MEETINGS / mid


def ids() -> list:
    """Every recorded meeting, newest first."""
    if not MEETINGS.exists():
        return []
    return sorted((p.name for p in MEETINGS.iterdir()
                   if p.is_dir() and re.fullmatch(r"\d{8}-\d{6}", p.name)),
                  reverse=True)


def load(mid: str) -> dict:
    try:
        return json.loads((_dir(mid) / "meeting.json").read_text())
    except Exception:
        return {}


def save(mid: str, rec: dict) -> None:
    d = _dir(mid)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "meeting.json.tmp"
    tmp.write_text(json.dumps(rec, indent=1))
    os.replace(tmp, d / "meeting.json")


def status(mid: str) -> dict:
    """What the recorder itself last published, or {}."""
    try:
        return json.loads((_dir(mid) / "status.json").read_text())
    except Exception:
        return {}


def _alive(pid: int) -> bool:
    """Is this process still doing anything.

    A signalled process that has exited but not been reaped is a zombie, and
    `os.kill(pid, 0)` succeeds for one. That is not a live recorder, it is a
    dead one whose parent has not noticed, and calling it alive is how `stop`
    would report a recorder it had just killed as refusing to die. Checking the
    state costs one `ps`, and only in the case where the cheap answer is yes."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    try:
        r = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
        st = (r.stdout or "").strip()
        if st:
            return not st.startswith("Z")
    except Exception:
        pass
    return True


def running() -> dict:
    """The meeting being recorded right now, or {}.

    Asked of the process rather than of a flag file. A recorder that died takes
    its pid with it, and a "recording" flag left behind by a crash is how a
    product ends up claiming to be listening when it is not, which is exactly
    the thing this feature must never do."""
    try:
        mid = CURRENT.read_text().strip()
    except Exception:
        return {}
    st = status(mid)
    if st.get("state") == "recording" and _alive(int(st.get("pid") or 0)):
        rec = load(mid)
        rec.update({"id": mid, "elapsed": st.get("elapsed", 0.0),
                    "them_seconds": st.get("them_seconds", 0.0),
                    "me_seconds": st.get("me_seconds", 0.0),
                    "them_level": st.get("them_level", 0.0),
                    "me_level": st.get("me_level", 0.0)})
        return rec
    try:
        CURRENT.unlink()
    except Exception:
        pass
    return {}


# ---- starting and stopping -------------------------------------------------

def _reason(mid: str) -> str:
    try:
        return (_dir(mid) / "recorder.err").read_text().strip()
    except Exception:
        return ""


def start(title: str = "", wait: float = 30.0) -> dict:
    """Start recording. {"id": ...} on success, {"problem": ...} otherwise.

    Never called by anything but the user typing the command. There is no
    detector, no schedule and no calendar in this product, and there is not
    going to be one."""
    live = running()
    if live:
        return {"problem": "already",
                "id": live["id"],
                "say": f"A meeting is already recording ({live['id']}). "
                       f"Stop it first: dictator meeting stop"}
    if not build_app():
        return {"problem": "build",
                "say": "Could not build the meeting recorder. It needs Apple's "
                       "command line tools: xcode-select --install"}

    mid = time.strftime("%Y%m%d-%H%M%S")
    d = _dir(mid)
    d.mkdir(parents=True, exist_ok=True)
    save(mid, {"id": mid, "title": title.strip(), "started": time.time(),
               "ended": 0.0, "seconds": 0.0, "transcript": [], "notes": {}})

    # Through LaunchServices, not as a child process, and this is measured
    # rather than stylistic. macOS attributes a permission to the RESPONSIBLE
    # process, and a bundle's executable spawned directly from a terminal is
    # attributed to the terminal: the first attempt here wrote its microphone
    # request against Terminal instead of against this app. Launched with
    # `open`, the row lands on com.dictator.meeting, which is the only way the
    # user can grant it to something they recognise.
    try:
        r = subprocess.run(["open", "-n", "-a", str(APP), "--args", str(d),
                            str(MAX_SECONDS)],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {"problem": "launch", "say": f"Could not start the recorder: {e}"}
    # `open` refusing is instant and says why: a damaged or quarantined bundle,
    # or one whose LSMinimumSystemVersion is newer than this macOS. Throwing
    # that away turned every one of those into the user watching a progress
    # line for thirty seconds and then being told the recorder "said nothing".
    if r.returncode != 0:
        why = (r.stderr or r.stdout or "").strip() or f"open exited {r.returncode}"
        core.log(f"meeting: open refused to launch the recorder: {why}")
        _scrap(mid)
        return {"problem": "launch",
                "say": f"macOS would not start the recorder: {why}"}

    t0 = time.time()
    while time.time() - t0 < wait:
        st = status(mid)
        if st.get("state") == "recording" and _alive(int(st.get("pid") or 0)):
            CURRENT.parent.mkdir(parents=True, exist_ok=True)
            CURRENT.write_text(mid)
            return {"id": mid, "started": time.time()}
        # The recorder says why it gave up in `state`, not in its prose. This
        # used to grep the recorder's own log, where the line announcing that
        # it was ASKING for Screen Recording matched the same test as the line
        # saying it had been refused. So an ordinary first run, where the
        # permission is being requested exactly as designed, was read as a
        # refusal, and `_scrap` deleted the working directory of a recorder
        # that was still running and about to open its tracks in it.
        state = st.get("state") or ""
        if state == "no-screen":
            _scrap(mid)
            return {"problem": "screen", "say": _SCREEN_HELP}
        if state == "no-mic":
            _scrap(mid)
            return {"problem": "mic", "say":
                    "macOS has not allowed the meeting recorder to use the "
                    "microphone, so it could not record your half.\n"
                    "  System Settings, Privacy and Security, Microphone, and "
                    "switch on Dictator Meeting."}
        # A recorder that has exited without saying why is not coming back, so
        # there is no reason to sit out the rest of the wait.
        pid = int(st.get("pid") or 0)
        if pid and not _alive(pid):
            _scrap(mid)
            return {"problem": "died",
                    "say": "The recorder stopped before it started recording. "
                           + (_reason(mid) or "See ~/.dictator/log.")}
        time.sleep(0.3)
    _scrap(mid)
    return {"problem": "timeout",
            "say": "The recorder did not start within "
                   f"{wait:.0f} seconds. " + (_reason(mid) or
                   "It said nothing; see ~/.dictator/log.")}


_SCREEN_HELP = (
    "macOS has not allowed the meeting recorder to capture system audio yet,\n"
    "which is the half of a meeting that is the other people.\n\n"
    "  dictator meeting permissions\n\n"
    "walks you to the right pane. It is called Screen Recording (or Screen and\n"
    "System Audio Recording) because macOS treats capturing what comes out of\n"
    "your speakers as the same privilege as capturing what is on your screen.\n"
    "This records no video: the capture is set to two pixels and the frames are\n"
    "never read.")


def _scrap(mid: str) -> None:
    """Throw away a session that never actually recorded anything, so a failed
    permission does not leave a list full of empty meetings."""
    shutil.rmtree(_dir(mid), ignore_errors=True)


def stop(wait: float = 15.0) -> dict:
    """Stop the recording. {"id": ...}, or {"problem": "none"}.

    Terminate, never kill: a WAV's header is written when the file is closed,
    so a killed recorder leaves two files that claim to hold no audio. The
    recorder handles SIGTERM for exactly this."""
    live = running()
    if not live:
        return {"problem": "none",
                "say": "No meeting is being recorded.  (dictator meeting start)"}
    mid = live["id"]
    pid = int(status(mid).get("pid") or 0)
    try:
        os.kill(pid, 15)
    except Exception as e:
        core.log(f"meeting: could not signal the recorder: {e}")
    t0 = time.time()
    while time.time() - t0 < wait and _alive(pid):
        time.sleep(0.2)
    # SIGTERM is the polite ask, not the whole story. The reason to prefer it
    # is that the WAV headers are written when the files close, and that reason
    # justifies WAITING for it, not giving up on it. This used to unlink
    # CURRENT whichever way the wait ended, so a recorder that survived was
    # left running with no record of it: `running()` answered nothing, `stop`
    # answered "No meeting is being recorded", `start` would happily launch a
    # second one alongside it, and macOS kept the screen recording indicator
    # lit for the remaining four hours.
    if pid and _alive(pid):
        core.log(f"meeting: the recorder ({pid}) ignored SIGTERM after "
                 f"{wait:.0f}s, killing it")
        try:
            os.kill(pid, 9)
        except Exception:
            pass
        t1 = time.time()
        while time.time() - t1 < 3 and _alive(pid):
            time.sleep(0.1)
        if _alive(pid):
            return {"problem": "stuck", "id": mid,
                    "say": f"The recorder ({pid}) will not stop. The meeting "
                           f"is still being recorded. Try: kill -9 {pid}"}
    try:
        CURRENT.unlink()
    except Exception:
        pass
    rec = load(mid)
    rec["ended"] = time.time()
    rec["seconds"] = max(_seconds(_dir(mid) / "them.wav"),
                         _seconds(_dir(mid) / "me.wav"))
    save(mid, rec)
    return {"id": mid, "seconds": rec["seconds"]}


def forget(mid: str) -> bool:
    """Delete a recording, and mean it.

    A meeting recording is other people's voices, so "forget" has to be more
    than dropping a row. Every file is overwritten IN FULL before it is
    unlinked, which defeats anything that reads the directory back off the
    filesystem. It cannot defeat an SSD's own wear levelling, and saying it
    could would be a lie, so the README says so.

    It used to overwrite the first and last megabyte only, while the docstring,
    the command and the README all said "every file". Measured on an 11MB file,
    82% of the audio was still there at unlink time; an hour of meeting is
    about 115MB a track, so roughly 98% of other people's voices survived a
    delete that told the user they had not. A wrong claim here is worse than no
    claim, because the sentence exists to tell somebody it is safe.

    Returns False if any file could not be overwritten, because a caller that
    is about to repeat the promise needs to know it was not kept."""
    d = _dir(mid)
    if not d.is_dir():
        return False
    # Deleting the directory out from under a running recorder does not stop
    # it. Its files stay open on unlinked inodes, its status writes fail into
    # nothing, and because CURRENT goes too there is no longer any way to find
    # it: the same unstoppable orphan `stop` used to leave.
    live = running()
    if live.get("id") == mid:
        got = stop()
        if got.get("problem"):
            core.log(f"meeting: refusing to forget {mid}, it is still "
                     f"recording ({got.get('problem')})")
            return False
    ok = True
    for p in sorted(d.rglob("*"), reverse=True):
        if p.is_file():
            try:
                n = p.stat().st_size
                with open(p, "r+b") as f:
                    left = n
                    while left > 0:
                        block = min(1 << 20, left)
                        f.write(os.urandom(block))
                        left -= block
                    f.flush()
                    os.fsync(f.fileno())
                    f.truncate(0)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                core.log(f"meeting: could not overwrite {p.name}: {e}")
                ok = False
    shutil.rmtree(d, ignore_errors=True)
    try:
        if CURRENT.read_text().strip() == mid:
            CURRENT.unlink()
    except Exception:
        pass
    return ok


# ---- reading the audio -----------------------------------------------------

RATE = 16000                 # what the recorder writes and what whisper wants
STEP = 0.1                   # resolution of the loudness envelope, seconds

# How much audio goes into one whisper run. whisper.cpp will happily take an
# hour long file, but then there is one process, one answer at the end, no
# progress and nothing to retry when it goes wrong. Two minutes is small enough
# to report progress on and large enough that the per run cost (process start
# and a 1.6GB model load) is a few percent rather than most of the bill.
CHUNK = 120.0
# Repeated at every seam so a word spoken across a cut is heard whole by at
# least one side of it. Removed again by _dedup.
OVERLAP = 3.0
# How far either side of the target we look for a quiet moment to cut at.
SEEK = 10.0
# Peak amplitude below which a stretch is treated as nobody talking. Whisper
# does not return nothing for silence, it INVENTS: real logs here have
# "[BLANK_AUDIO]" but also whole fabricated sentences. On the microphone track
# of a meeting most of the audio is silence, because most of a meeting is
# somebody else talking, so this is both the accuracy guard and the single
# biggest speed win available.
SILENT = 0.012
# A silence at least this long is where a chunk ends. Longer than a pause for
# breath, shorter than waiting for somebody else to finish their point.
GAP = 3.0
# Kept either side of a stretch of speech, so nothing is clipped by the
# envelope's tenth of a second resolution.
PAD = 0.4
# The longest silence two stretches of talking may be joined across. Joining
# keeps the number of whisper runs down; joining too eagerly puts the silence
# back inside a chunk, which is the thing that made whisper invent a sentence
# in the first place. Six seconds is a long pause in a conversation and far
# short of the twenty that caused it.
MERGE = 6.0


def _seconds(wav) -> float:
    try:
        with wave.open(str(wav)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def envelope(wav, step: float = STEP) -> list:
    """Peak amplitude (0..1) every `step` seconds, read in one pass.

    An hour of audio is 36000 numbers this way, which is small enough to hold
    and to scan repeatedly, and it is the only thing both the cut points and
    the silence skipping need."""
    out = []
    try:
        with wave.open(str(wav)) as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                return []
            block = max(1, int(w.getframerate() * step))
            while True:
                raw = w.readframes(block)
                if not raw:
                    break
                a = array.array("h")
                a.frombytes(raw[:len(raw) - len(raw) % 2])
                out.append((max(abs(x) for x in a) / 32768.0) if a else 0.0)
    except Exception as e:
        core.log(f"meeting: could not read {wav}: {e}")
    return out


def cuts(env: list, chunk: float = CHUNK, seek: float = SEEK,
         step: float = STEP, lo_sec: float = 0.0, hi_sec: float = 0.0) -> list:
    """Where to cut an unbroken stretch of talking, at the quietest moment
    near each target.

    Only needed when somebody talks for longer than a whole chunk without a
    real pause. Cutting on the clock puts the seam inside a word about as often
    as not; cutting at the quietest moment within ten seconds of the target
    puts it in a breath, which is what makes a few seconds of overlap enough to
    recover the rest."""
    hi_sec = hi_sec or len(env) * step
    out = []
    at = lo_sec + chunk
    while at < hi_sec - seek:
        lo = max(int(lo_sec / step) + 1, int((at - seek) / step))
        hi = min(int(hi_sec / step) - 1, len(env) - 1, int((at + seek) / step))
        if hi <= lo:
            break
        best = min(range(lo, hi), key=lambda i: env[i])
        cut = best * step
        if cut <= (out[-1] if out else lo_sec) + chunk / 4:
            break               # no progress being made, stop rather than loop
        out.append(cut)
        at = cut + chunk
    return out


def speech(env: list, gap: float = GAP, step: float = STEP) -> list:
    """The stretches where somebody is actually talking, as (start, end).

    This is what the chunking is built on, and it replaced building it on the
    clock after a real recording showed why. Whisper does not return nothing
    for silence, it fills it: a chunk whose middle held twenty seconds of
    nothing came back having quietly dropped the forty words spoken after it
    and invented a sentence in their place. Chunks that begin and end at speech
    never contain a silence long enough to provoke that, and on a meeting they
    are also most of the saving, because most of the microphone track is the
    owner listening."""
    out, start, quiet_at = [], None, None
    for i, v in enumerate(env):
        if v >= SILENT:
            if start is None:
                start = i * step
            quiet_at = None
        elif start is not None:
            if quiet_at is None:
                quiet_at = i * step
            elif i * step - quiet_at >= gap:
                out.append((start, quiet_at))
                start, quiet_at = None, None
    if start is not None:
        out.append((start, quiet_at if quiet_at is not None
                    else len(env) * step))
    return out


# Working out where the chunks are means reading the whole track to build its
# loudness envelope, and three different callers want the answer: the progress
# total, and each track's own pass. An hour of audio is 115MB per track, so
# reading it six times to answer the same question is a few seconds of nothing.
# Keyed on the file's size as well as its name, because a recording that is
# still being written is a different file a moment later.
_PIECES: dict = {}


def pieces(wav, chunk: float = CHUNK, overlap: float = OVERLAP,
           seek: float = SEEK, gap: float = GAP) -> list:
    """The chunks a track is transcribed in, and nothing else.

    Each is {start, end, keep_from}. Silence between chunks is simply not in
    any of them: it is not transcribed, not paid for and not given to a model
    that would fill it in. `keep_from` is where this chunk's words start
    counting, which matters only where a chunk had to be cut through somebody
    still talking: everything before it was already heard by the chunk before,
    and is in this file only so that a word across the cut is heard whole once.
    """
    total = _seconds(wav)
    if total <= 0:
        return []
    key = (str(wav), os.path.getsize(wav), chunk, overlap, seek, gap)
    if _PIECES.get(key) is not None:
        return _PIECES[key]
    env = envelope(wav)
    if not env:
        return []

    # Atoms: stretches of talking, with any stretch longer than a whole chunk
    # already cut down. `forced` marks a cut made through live speech, which is
    # the only kind that needs an overlap.
    atoms = []
    for a, b in speech(env, gap):
        inner = cuts(env, chunk, seek, STEP, a, b) if b - a > chunk else []
        prev, forced = a, False
        for c in inner:
            atoms.append((prev, c, forced))
            prev, forced = c, True
        atoms.append((prev, b, forced))

    out, ended = [], 0.0
    for a, b, forced in atoms:
        if (out and not forced and b - out[-1]["keep_from"] <= chunk
                and a - ended <= MERGE):
            out[-1]["end"] = min(total, b + PAD)
            ended = b
            continue
        start = max(0.0, a - (overlap if forced else PAD))
        out.append({"start": start,
                    "end": min(total, b + PAD),
                    "keep_from": a if forced else start})
        ended = b
    _PIECES[key] = out
    return out


def _slice(wav, start: float, end: float, out) -> bool:
    """Write [start, end) of a 16kHz mono WAV to `out`."""
    try:
        with wave.open(str(wav)) as w:
            rate = w.getframerate()
            w.setpos(min(w.getnframes(), int(start * rate)))
            n = max(0, int((end - start) * rate))
            raw = w.readframes(n)
        if len(raw) < 2:
            return False
        with wave.open(str(out), "wb") as o:
            o.setnchannels(1)
            o.setsampwidth(2)
            o.setframerate(rate)
            o.writeframes(raw)
        return True
    except Exception as e:
        core.log(f"meeting: could not slice {wav}: {e}")
        return False


# ---- turning it into words -------------------------------------------------

# How many chunks go into one whisper process. whisper-cli takes a list of
# files and loads the model ONCE for all of them, and that load is measured at
# 2.0 to 3.4 seconds here against a few seconds of actual work per chunk, so
# running them one at a time spends a third of a long meeting on loading the
# same 1.6GB. Eight is a compromise: the load is amortised, and a failure or an
# interruption costs eight chunks rather than the whole meeting.
BATCH = 8


# How long whisper may go without saying anything before it is treated as
# wedged. It prints a percentage every five percent of every file, and the
# longest gap in normal running is the model load between files, which is three
# seconds. Five minutes of silence is not slowness.
STALL = 300.0


def _watchdog(proc, heard: list) -> None:
    """Kill `proc` if it stops saying anything at all.

    A total time limit would be the obvious thing and is useless here: a batch
    of eight two minute chunks is legitimately allowed to take several minutes,
    so any limit loose enough not to fire on a busy machine is too loose to
    catch a wedge inside a working day. What a wedged whisper actually does is
    stop printing, so that is what is watched. `heard` is a one element list
    holding the time of the last thing it said."""
    import threading

    def watch():
        while True:
            try:
                proc.wait(timeout=30)
                return                      # it finished on its own
            except Exception:
                pass
            if time.time() - heard[0] > STALL:
                core.log("meeting: whisper stopped responding, stopping it")
                try:
                    proc.kill()
                except Exception:
                    pass
                return

    threading.Thread(target=watch, daemon=True).start()


def _whisper(paths, lang: str, progress=None) -> dict:
    """Several chunks through one whisper. {path: [{at, until, text}, ...]}.

    Timestamps are why this does not simply call `stt.transcribe_ex`: that
    returns one string, which is the right answer for a hold of a key and the
    wrong one for an hour of two people, where WHEN something was said is what
    lets the two tracks be interleaved into a conversation. Everything else
    about the decision (which model, which prompt) is stt's, because having two
    opinions about that is how a router stops routing.

    Parakeet is not consulted even on the English path, and that is deliberate
    rather than an oversight: it is faster and more verbatim, and it returns no
    timestamps at all, so a transcript built on it could not say who spoke when.
    """
    wb = stt.whisper_bin()
    model, _ = stt.stt_lang_mode()
    if not wb or not model.exists() or not paths:
        return {}
    cmd = [wb, "-m", str(model), "-l", lang, "-pp",
           "--prompt", stt.whisper_prompt(), "-oj"]
    for p in paths:
        cmd += ["-f", str(p)]
    try:
        # Streamed rather than collected, so the percentage whisper prints can
        # drive a progress line. An hour of meeting is minutes of waiting, and
        # a command that sits there silently reads as a command that has hung.
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True)
        # Reading a pipe has no timeout of its own, so a whisper that wedged
        # would hold the command open forever with nothing to look at.
        heard = [time.time()]
        _watchdog(proc, heard)
        seen, last = 0, 101
        for line in proc.stderr:
            heard[0] = time.time()
            hit = re.search(r"progress\s*=\s*(\d+)%", line)
            if not hit:
                continue
            pct = int(hit.group(1))
            if pct < last:
                seen += 1           # the percentage restarted: a new file
            last = pct
            if progress:
                progress(min(seen, len(paths)), len(paths), pct)
        proc.wait(timeout=60)
    except Exception as e:
        core.log(f"meeting: whisper failed on a batch: {e}")
        return {}
    out = {}
    missing = []
    for p in paths:
        js = Path(str(p) + ".json")
        try:
            data = json.loads(js.read_text())
        except Exception as e:
            # whisper-cli stops processing the remaining files when one of them
            # fails, so a single bad chunk took every chunk after it in the same
            # batch with it. An empty list here is indistinguishable from "this
            # stretch was silent", which is how up to BATCH * CHUNK minutes of a
            # meeting went missing with one line in a log nobody reads.
            core.log(f"meeting: no transcript for {p}: {e}")
            missing.append(p)
            continue
        finally:
            try:
                js.unlink()
            except OSError:
                pass
        segs = []
        for seg in data.get("transcription", []) or []:
            text = " ".join((seg.get("text") or "").split())
            if not text or stt.is_silence(text):
                continue
            offs = seg.get("offsets") or {}
            at = float(offs.get("from", 0)) / 1000.0
            # The end matters as much as the start: a segment that begins
            # inside the overlap and ends well past it holds real speech, and
            # dropping it by its start time is how a whole sentence disappears
            # at a seam. That is not hypothetical, it happened on the first
            # real recording this was tried on.
            until = float(offs.get("to", offs.get("from", 0))) / 1000.0
            if segs and segs[-1]["text"] == text:
                continue    # a repetition loop, not somebody saying it twice
            segs.append({"at": at, "until": until, "text": text})
        out[str(p)] = segs

    # Anything the batch dropped gets its own run. One bad chunk should cost
    # that chunk, not the seven behind it in the queue.
    if missing and len(paths) > 1:
        core.log(f"meeting: {len(missing)} chunk(s) came back empty, "
                 f"running them one at a time")
        for p in missing:
            got = _whisper([p], lang, None)
            out[str(p)] = got.get(str(p), [])
            if not out[str(p)]:
                core.log(f"meeting: {Path(p).name} produced nothing on its "
                         f"own either, so that stretch is lost")
    else:
        for p in missing:
            out[str(p)] = []
    return out


def _words(text: str) -> list:
    return re.findall(r"[\w']+", text.lower())


# How far into the new chunk the repeat is allowed to begin. A chunk starts
# three seconds before the cut, which lands the recogniser mid word, and what
# it makes of that half word is not what the other pass made of the whole one.
# Measured on a real recording: "...rediscovering it. Please do." came back as
# "I'm covering it. Please do.", so the repeat began at the FOURTH word and a
# match anchored at the first word could not see it at all.
SKEW = 6


def dedup(prev: str, nxt: str, most: int = 30, skew: int = SKEW) -> str:
    """Drop from `nxt` the opening it shares with the end of `prev`.

    The overlap means the last few seconds of one chunk are the first few
    seconds of the next, so without this every seam reads as a stutter. Matched
    on words rather than characters because the two passes are separate
    decodings of the same audio and their punctuation and casing never agree
    even where the words do."""
    a, b = _words(prev), _words(nxt)
    if not a or not b:
        return nxt
    best = (0, 0)               # (words matched, where the repeat started)
    for off in range(0, min(skew, len(b)) + 1):
        for n in range(min(most, len(a), len(b) - off), 1, -1):
            # A match that starts partway in has to be longer to be believed:
            # at the very start two words in common is already the overlap,
            # further in it is a coincidence, and acting on a coincidence
            # deletes real speech.
            if n < (4 if off else 2) or n <= best[0]:
                break
            if a[-n:] == b[off:off + n]:
                best = (n, off)
                break
    if not best[0]:
        return nxt
    # Walk the original string forward past the last repeated word, so casing
    # and punctuation in the part that is kept are untouched.
    kept, upto = 0, best[0] + best[1]
    for m in re.finditer(r"[\w']+", nxt):
        kept += 1
        if kept == upto:
            return nxt[m.end():].lstrip(" ,.")
    return nxt


def track(wav, who: str, progress=None, done: int = 0, total: int = 0) -> list:
    """One whole track as timed, de-duplicated lines."""
    import tempfile
    parts = pieces(wav)
    if not parts:
        return []
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        cut = []
        for i, p in enumerate(parts):
            part = Path(tmp) / f"{i:04d}.wav"
            if _slice(wav, p["start"], p["end"], part):
                cut.append((p, part))
        if not cut:
            return []
        # The language is pinned once for the whole track rather than per
        # chunk, using the longest piece. whisper's own `-l auto` runs the
        # encoder twice on EVERY chunk, which on an hour of meeting is a second
        # model's worth of work for an answer that cannot change halfway
        # through: a meeting is one setting, not one per minute.
        longest = max(cut, key=lambda cp: cp[0]["end"] - cp[0]["start"])[1]
        lang = stt.pinned_language(str(longest), stt.stt_lang_mode()[1])

        for at in range(0, len(cut), BATCH):
            batch = cut[at:at + BATCH]

            def note(n, of, pct, _at=at, _batch=batch):
                if progress:
                    here = _batch[min(max(n, 1), len(_batch)) - 1][0]
                    progress(who, done + _at + max(n, 1), total,
                             here["start"], pct)

            got = _whisper([p for _, p in batch], lang, note)
            for piece, path in batch:
                for s in got.get(str(path), []):
                    a = piece["start"] + s["at"]
                    until = piece["start"] + s.get("until", s["at"])
                    # Dropped only when the WHOLE of it lies in the stretch the
                    # previous chunk already heard. A segment that starts in the
                    # overlap and runs past it is real speech, and dropping
                    # those by their start time lost an entire sentence at the
                    # first seam this was tried on.
                    if until <= piece["keep_from"] and out:
                        continue
                    text = s["text"]
                    # Only inside the overlap, which is the only place a repeat
                    # can come from. Applied to every pair of consecutive
                    # segments it deletes real speech instead: somebody said
                    # "something we have to pay for" twice in one breath, and a
                    # dedup with no idea where the seam was removed the second
                    # one. Nothing whisper emits inside one chunk overlaps
                    # anything else in it.
                    if out and a < piece["keep_from"]:
                        # Against the tail rather than the last line alone,
                        # because whisper cuts an overlap into two or three
                        # segments as often as one.
                        text = dedup(" ".join(x["text"] for x in out[-3:]),
                                     text)
                    if text.strip():
                        out.append({"at": a, "who": who, "text": text.strip()})
    return out


def chunks_expected(mid: str) -> int:
    d = _dir(mid)
    return len(pieces(d / "them.wav")) + len(pieces(d / "me.wav"))


def transcribe(mid: str, progress=None) -> dict:
    """Both tracks, interleaved into one conversation. Updates meeting.json.

    Slow, and honest about it: an hour of meeting is an hour of audio through a
    1.6GB model. `progress` is called for every chunk so the command can say
    where it is instead of sitting there looking hung."""
    d = _dir(mid)
    rec = load(mid)
    if not rec:
        return {}
    t0 = time.time()
    total = chunks_expected(mid)
    lines = track(d / "them.wav", "them", progress, 0, total)
    n_them = len(pieces(d / "them.wav"))
    lines += track(d / "me.wav", "me", progress, n_them, total)
    lines.sort(key=lambda x: x["at"])
    rec["transcript"] = lines
    rec["took"] = time.time() - t0
    rec["seconds"] = max(_seconds(d / "them.wav"), _seconds(d / "me.wav"))
    save(mid, rec)
    (d / "transcript.txt").write_text(as_text(rec))
    return rec


def as_text(rec: dict) -> str:
    """The transcript as a person reads it, one speaker per paragraph."""
    out, who = [], ""
    for ln in rec.get("transcript", []):
        if ln["who"] != who:
            who = ln["who"]
            out.append(f"\n[{_clock(ln['at'])}] "
                       f"{'you' if who == 'me' else 'them'}:\n")
        out.append("  " + ln["text"] + "\n")
    return "".join(out).lstrip("\n")


def _clock(secs: float) -> str:
    return f"{int(secs) // 60:02d}:{int(secs) % 60:02d}"


# ---- what it was about -----------------------------------------------------

# Three questions, not one, because "summarise this" of an hour of conversation
# produces a paragraph that is true and useless. These are the three things
# somebody actually wants the next morning, and each is checked separately, so
# an invented action item cannot ride in on a correct summary of the discussion.
_DISCUSSED = (
    "You summarise a meeting transcript for one of the people who was in it. "
    "Lines marked 'you' are that person; lines marked 'them' are everybody "
    "else. Say what was discussed, in two to four short sentences of plain "
    "past tense. Every fact must come from the transcript. Do not invent "
    "names, numbers, decisions, outcomes or reasons. No preamble, no lists, no "
    "markdown, no headings.")

_DECIDED = (
    "You read a meeting transcript and report only what was DECIDED. A "
    "decision is something the transcript says was agreed, chosen or settled. "
    "Do not report what was merely discussed, suggested or considered. Do not "
    "invent anything. If nothing was decided, answer with exactly: nothing was "
    "decided. Otherwise one to three short sentences, no lists, no markdown.")

_YOURS = (
    "You read a meeting transcript and report only what the person marked "
    "'you' agreed to DO afterwards. Only tasks that person took on, not tasks "
    "anybody else took on and not things that merely came up. Do not invent "
    "anything. If there is nothing, answer with exactly: nothing for you. "
    "Otherwise one to three short sentences, no lists, no markdown.")

_NOTHING = ("nothing was decided", "nothing for you")

# A meeting transcript is much longer than a dictation session, so the model is
# shown it in stretches. The context is 8192 tokens and the answer needs room,
# so this leaves a wide margin: roughly 3000 tokens of transcript per call.
STRETCH = 12000

# Longer than the recap's, because the prompt is twenty times the size. Reading
# three thousand tokens before writing a word took more than the recap's thirty
# second budget on a just loaded model, and the symptom was a "Discussed"
# section that was silently missing while the other two were fine.
THINK = 180.0


def _block(rec: dict) -> str:
    """The transcript as the model is shown it."""
    return "".join(
        f"{'you' if ln['who'] == 'me' else 'them'}: {ln['text']}\n"
        for ln in rec.get("transcript", []))


def _stretches(block: str, size: int = STRETCH) -> list:
    """Split on line boundaries, so no call ever sees half a sentence."""
    out, cur = [], ""
    for line in block.splitlines(keepends=True):
        if cur and len(cur) + len(line) > size:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out or [""]


def _answer(system: str, parts: list, whole: str, what: str) -> tuple:
    """Ask one question of a whole transcript, however long it is.

    Returns (what it said, whether anything was thrown away). Each stretch is
    answered separately and the answers are joined, and every answer is checked
    back against the WHOLE transcript rather than against the stretch it came
    from, which is the same guard recap uses and the reason an invented name
    cannot survive being summarised twice.

    The second half of the answer matters as much as the first. An empty
    section has two very different causes: nothing was decided, or something
    was said and could not be believed. Printing the same blank for both leaves
    the reader thinking the meeting had no decisions in it."""
    said, dropped = [], False
    for part in parts:
        if not part.strip():
            continue
        got = recap.prose_for(part, system=system, max_tokens=220,
                              limit=STRETCH, against=whole,
                              what=f"meeting/{what}", timeout=THINK,
                              exempt=_NOTHING)
        if not got:
            dropped = True
        elif got.strip().lower().rstrip(".") not in _NOTHING:
            said.append(got)
    text = " ".join(said).strip()
    return text, (dropped and not text)


def notes(mid: str, prose: bool = True) -> dict:
    """What was discussed, what was decided, what you have to do.

    Returns the notes and where they came from. `source` is "model" when the
    local model wrote them, "rejected" when it answered and the answer did not
    trace back to the transcript, "no-model" when there is nothing on this
    machine to write them with, and "no-transcript" when there is nothing to
    summarise."""
    rec = load(mid)
    if not rec:
        return {}
    whole = _block(rec)
    if not whole.strip():
        rec["notes"] = {"source": "no-transcript"}
        save(mid, rec)
        return rec
    if not prose or not recap.available():
        rec["notes"] = {"source": "no-model"}
        save(mid, rec)
        return rec
    parts = _stretches(whole)
    out = {"source": "rejected", "dropped": []}
    with recap.model_up() as answering:
        if answering:
            for key, system in (("discussed", _DISCUSSED),
                                ("decided", _DECIDED), ("yours", _YOURS)):
                out[key], lost = _answer(system, parts, whole, key)
                if lost:
                    out["dropped"].append(key)
            if any(out.get(k) for k in ("discussed", "decided", "yours")):
                out["source"] = "model"
    rec["notes"] = out
    save(mid, rec)
    return rec


# ---- what gets printed -----------------------------------------------------

def render(rec: dict, transcript: bool = False) -> str:
    """One meeting, as it is read."""
    mid = rec.get("id", "")
    when = time.strftime("%A %d %B, %H:%M",
                         time.localtime(rec.get("started", 0)))
    mins = rec.get("seconds", 0.0) / 60.0
    head = f"{when}"
    if rec.get("title"):
        head += f"  ({rec['title']})"
    out = [f"{head}\n  {mins:.0f} minutes, {mid}\n"]

    n = {"me": 0, "them": 0}
    for ln in rec.get("transcript", []):
        n[ln["who"]] = n.get(ln["who"], 0) + 1
    if n["me"] or n["them"]:
        out.append(f"  {n['them']} things they said, {n['me']} things you "
                   f"said.\n")

    notes_ = rec.get("notes") or {}
    for key, label in (("discussed", "Discussed"), ("decided", "Decided"),
                       ("yours", "Yours to do")):
        if notes_.get(key):
            out.append(f"\n  {label}\n")
            out.append(_wrap(notes_[key], "    "))
    if notes_.get("source") == "model":
        # Name what was thrown away. A blank section otherwise reads as "there
        # were no decisions", when what happened was that the answer did not
        # trace back to the transcript and was dropped for it.
        lost = [l for k, l in (("discussed", "what was discussed"),
                               ("decided", "what was decided"),
                               ("yours", "what you took on"))
                if k in (notes_.get("dropped") or [])]
        if lost:
            out.append("\n")
            out.append(_wrap("Nothing is shown for " + " or ".join(lost)
                             + ", because what came back did not match what "
                               "was actually said and was thrown away rather "
                               "than shown with a warning.", "  "))
        out.append("\n")
        out.append(_wrap("Written by a model on this machine, out of the "
                         "transcript and nothing else, and thrown away "
                         "wherever it said something the transcript does not. "
                         "Nothing left the Mac.", "  "))
    else:
        why = {"no-model": "there is no local model on this machine",
               "rejected": "the local model did not return anything that "
                           "matched what was actually said",
               "no-transcript": "nothing was transcribed",
               }.get(notes_.get("source", ""), "")
        if why:
            out.append("\n")
            out.append(_wrap("No notes, because " + why + ". The transcript "
                             "is there either way: dictator meeting show "
                             + mid + " --full", "  "))

    if transcript:
        out.append("\n")
        out.append(as_text(rec))
    elif rec.get("transcript"):
        out.append(f"\n  Whole transcript: dictator meeting show {mid} --full\n")
    return "".join(out)


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


def listing() -> str:
    rows = ids()
    if not rows:
        return ("No meetings recorded.\n"
                "  Start one with: dictator meeting start\n")
    out = []
    for mid in rows:
        rec = load(mid)
        when = time.strftime("%d %b %H:%M", time.localtime(rec.get("started", 0)))
        mins = rec.get("seconds", 0.0) / 60.0
        size = sum(p.stat().st_size for p in _dir(mid).glob("*") if p.is_file())
        state = "transcribed" if rec.get("transcript") else "audio only"
        if (rec.get("notes") or {}).get("source") == "model":
            state = "with notes"
        out.append(f"  {mid}   {when}   {mins:5.1f} min   "
                   f"{size / 1e6:6.1f} MB   {state}"
                   + (f"   {rec['title']}" if rec.get("title") else "") + "\n")
    return "".join(out)
