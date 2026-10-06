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


def sample(n: int = 40) -> list:
    """`n` recordings, chosen by seed rather than by eye.

    A set made of the holds somebody remembered as bad measures the bad ones,
    and the number that comes out of it is not an error rate."""
    pool = candidates()
    rng = random.Random(SEED)
    rng.shuffle(pool)
    return pool[:n]


def path_for(wav: Path) -> Path:
    return REFS / (wav.stem + ".json")


def done(wav: Path) -> bool:
    return path_for(wav).exists()


def load(wav: Path) -> dict:
    try:
        return json.loads(path_for(wav).read_text())
    except Exception:
        return {}


def save(wav: Path, said: str, heard: str = "") -> None:
    """Write the reference down. `heard` is what the model produced, kept so
    that a later reader can see what was corrected and what was accepted
    unchanged, which is the difference between a reference and a rubber
    stamp."""
    REFS.mkdir(parents=True, exist_ok=True)
    path_for(wav).write_text(json.dumps({
        "said": said,
        "heard": heard,
        "changed": said.strip() != (heard or "").strip(),
        "seconds": round(seconds(wav), 2),
        "seed": SEED,
    }, ensure_ascii=False, indent=1))


def play(wav: Path) -> bool:
    """Play it once. False if nothing could play it, so the caller can say so
    rather than wait for a sound that is not coming."""
    try:
        subprocess.run(["afplay", str(wav)], timeout=180,
                       capture_output=True)
        return True
    except Exception as e:
        core.log(f"truth: could not play {wav.name}: {e}")
        return False


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
