"""What was actually said, written down once so accuracy can be measured.

Every accuracy number in this project so far is reference free: the share of
words in neither dictionary. That catches a model inventing a non-word and is
blind to the failure that matters most, a model replacing one real word with
another. docs/findings.md has the case: a Hindi sentence came back as
"Pirated Copy content, if you can play it, then copy it, PDF, add it, day by
day", every word of which is ordinary English, so it scored zero and was
wrong about all of them.

Telling those apart needs somebody to write down what they said, and that is
the one part of a benchmark that cannot be delegated.

What this does is make it cheap. Rather than forty blank lines to fill, it
plays each recording and offers the model's own transcript already typed in,
so the work is correcting what is wrong rather than writing what is right. On
this corpus 85% of holds need no change at all, which turns hours into
minutes.

The sample is drawn with a fixed seed rather than chosen, because a reference
set made of the holds somebody remembered as bad measures the bad ones. The
seed is recorded beside the references so the same sample can be drawn again.
"""
import json
import random
import subprocess
import wave
from pathlib import Path

from . import core

# Beside the recordings, not in the repository: these are transcripts of
# somebody's own speech and they are theirs.
CORPUS = core.STATE_DIR / "corpus"
REFS = core.STATE_DIR / "references"

# Same sample every time it is run, so stopping halfway and coming back
# continues the set rather than starting a different one.
SEED = 20261006

# Shorter than this is a mis-press or a single word, and neither tells you
# much about a transcriber.
MIN_SECS = 2.0


def seconds(wav: Path) -> float:
    try:
        with wave.open(str(wav)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def candidates() -> list:
    """Every recording worth writing a reference for, longest-lived first."""
    out = []
    for w in sorted(CORPUS.glob("*.wav")):
        if seconds(w) >= MIN_SECS:
            out.append(w)
    return out


PICKED = REFS / "sample.json"


def sample(n: int = 40) -> list:
    """`n` recordings, chosen by seed rather than by eye, and then REMEMBERED.

    A set made of the holds somebody remembered as bad measures the bad ones,
    and the number that comes out of it is not an error rate. Hence the seed.

    But a seed only reproduces a shuffle of the SAME list, and this list grows
    every time the user dictates. Forty references were written and then the
    scorer could not find one of them, because four more recordings had been
    captured in between and the shuffle landed differently. So the choice is
    written down the first time and read back after, which is what "the same
    sample" has to mean for a benchmark somebody fills in over several
    sittings."""
    try:
        stems = json.loads(PICKED.read_text())
        have = {w.stem: w for w in candidates()}
        kept = [have[st] for st in stems if st in have]
        if len(kept) >= min(n, len(stems)):
            return kept[:n]
    except Exception:
        pass
    pool = candidates()
    rng = random.Random(SEED)
    rng.shuffle(pool)
    chosen = pool[:n]
    try:
        REFS.mkdir(parents=True, exist_ok=True)
        PICKED.write_text(json.dumps([w.stem for w in chosen]))
    except Exception as e:
        core.log(f"truth: could not record the sample: {e}")
    return chosen


def written() -> list:
    """Every reference on disk, whatever sample it came from.

    What a scorer should use: a reference somebody took the trouble to write
    is worth scoring even if the sample has since been redrawn."""
    out = []
    for p in sorted(REFS.glob("*.json")):
        if p.name == PICKED.name:
            continue
        w = CORPUS / (p.stem + ".wav")
        if w.exists():
            out.append(w)
    return out


def path_for(wav: Path) -> Path:
    return REFS / (wav.stem + ".json")


def done(wav: Path) -> bool:
    return path_for(wav).exists()


def load(wav: Path) -> dict:
    try:
        return json.loads(path_for(wav).read_text())
    except Exception:
        return {}


class Refused(ValueError):
    """A reference that would be worse than none."""


def save(wav: Path, said: str, heard: str = "") -> None:
    """Write the reference down. `heard` is what the model produced, kept so
    that a later reader can see what was corrected and what was accepted
    unchanged, which is the difference between a reference and a rubber
    stamp."""
    # An empty reference against a transcript that said something is not a
    # correction, it is a lost keystroke recorded as the model being wrong
    # about every word. Five of them were written before this existed, because
    # macOS Python uses libedit and the line the user was meant to edit came
    # up blank. A reference set is only worth the care taken writing it.
    if not (said or "").strip() and (heard or "").strip():
        raise Refused("an empty reference against a non-empty transcript")
    REFS.mkdir(parents=True, exist_ok=True)
    path_for(wav).write_text(json.dumps({
        "said": said,
        "heard": heard,
        "changed": said.strip() != (heard or "").strip(),
        "seconds": round(seconds(wav), 2),
        "seed": SEED,
    }, ensure_ascii=False, indent=1))


def play(wav: Path):
    """Start it playing and return at once, or None if nothing could.

    Not blocking, and the difference matters more than it sounds. Waiting for
    a 60 second recording to finish before the line can be answered turns
    forty references into forty waits, and most holds are recognised in the
    first two seconds. The caller stops it as soon as there is an answer."""
    try:
        return subprocess.Popen(["afplay", str(wav)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except Exception as e:
        core.log(f"truth: could not play {wav.name}: {e}")
        return None


def stop(proc) -> None:
    """Silence whatever is still playing. Never raises: a recording that keeps
    going is annoying, and an exception here would lose the reference the user
    has just typed."""
    try:
        if proc and proc.poll() is None:
            proc.terminate()
    except Exception:
        pass


def guess(wav: Path) -> str:
    """What the model makes of it, to be corrected rather than retyped.

    The transcript kept beside the recording when it was captured, if there is
    one, because that is what the shipped pipeline actually produced. Falling
    back to transcribing it now would offer a different answer from the one
    the user saw, and the point is to correct what the product does."""
    beside = wav.with_suffix(".txt")
    try:
        if beside.exists():
            return " ".join(beside.read_text(errors="ignore").split())
    except Exception:
        pass
    try:
        from . import stt
        return stt.transcribe(str(wav))
    except Exception as e:
        core.log(f"truth: could not transcribe {wav.name}: {e}")
        return ""


def progress(n: int = 40) -> dict:
    picked = sample(n)
    have = [w for w in picked if done(w)]
    changed = sum(1 for w in have if load(w).get("changed"))
    return {"total": len(picked), "done": len(have), "changed": changed,
            "left": len(picked) - len(have)}
