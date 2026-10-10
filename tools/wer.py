#!/usr/bin/env python3
"""Score a model against what was actually said.

The reference free number this project has used until now (`tools/nonwords.py`)
counts words in neither dictionary. It is blind by construction to a model
swapping one real word for another, which docs/findings.md shows is the worst
failure here: a Hindi sentence came back as fluent English and scored zero.

With references written by `dictator truth`, three numbers are possible, and
plain WER is the least useful of them:

  WER          every difference, including spelling. Honest and pessimistic:
               it counts "chahiye" against "chahie" as an error when both are
               correct, and romanised Hindi has no settled spelling.

  WER-sound    the same alignment after both sides are put through
               `hindi.key()`, which normalises exactly that variation. This is
               the "did it hear the words" number and the one to compare
               models on.

  ENG-exact    over the English tokens of the reference only. This is the
               "pool rekvest" detector, and nothing published measures it.
               It is the one to quote if only one is quoted, because a coding
               tool that mangles technical English is useless whatever its
               average looks like.

Usage:
    tools/wer.py                      score the shipped pipeline
    tools/wer.py --model PATH         score one model directly
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictator_core import hindi, known, truth              # noqa: E402


def _words(text: str) -> list:
    return [w for w in (text or "").lower().replace(",", " ")
            .replace(".", " ").replace("?", " ").replace("!", " ").split() if w]


def _distance(a: list, b: list) -> int:
    """Levenshtein over word lists: substitutions, insertions and deletions."""
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(said: str, heard: str) -> float:
    ref = _words(said)
    return _distance(ref, _words(heard)) / max(len(ref), 1)


def wer_sound(said: str, heard: str) -> float:
    """The same, after both sides are reduced to how they sound.

    `chahiye` and `chahie` are the same word spelled two ways, and romanised
    Hindi has no settled spelling, so counting that as an error measures the
    speaker's keyboard rather than the model."""
    k = hindi.key
    return _distance([k(w) for w in _words(said)],
                     [k(w) for w in _words(heard)]) / max(len(_words(said)), 1)


def eng_exact(said: str, heard: str) -> "tuple[int, int]":
    """(got right, total) over the English words of the reference.

    English is the half with one correct spelling, so an exact match is a fair
    test of it, and it is the half a coding tool cannot afford to lose."""
    heard_set = set(_words(heard))
    got = total = 0
    for w in _words(said):
        if w in known.ENGLISH and w not in known.HINDI:
            total += 1
            got += w in heard_set
    return got, total


def transcribe(wav: Path, model: "Path|None") -> "tuple[str, float]":
    from dictator_core import stt
    t0 = time.time()
    if model is None:
        import dictator_core
        d = dictator_core.Dictator(remember=False, learn=False, expand=False)
        # `.heard`, not `.text`. The references were written by correcting what
        # the model produced, which is the raw transcript, and `.text` is that
        # after the shaping pass has removed the fillers. Scoring one against
        # the other counts every deliberately dropped "uh" as an error: it put
        # a hold at the top of the worst list whose only difference from its
        # reference was two fillers the product is supposed to remove.
        return d.transcribe(str(wav)).heard, time.time() - t0
    wb = stt.whisper_bin()
    cmd = [wb, "-m", str(model), "-f", str(wav), "-nt", "-np", "-l", "auto",
           "--prompt", stt.whisper_prompt()]
    ac = stt.audio_ctx_for(truth.seconds(wav))
    if ac:
        cmd += ["-ac", str(ac)]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       errors="replace", timeout=300)
    return (r.stdout or "").strip(), time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=None)
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()

    # Every reference on disk, not the current sample. A reference somebody
    # took the trouble to write is worth scoring, and the sample was being
    # redrawn whenever the corpus grew.
    refs = truth.written()
    if not refs:
        print("No references yet. Write some with:  dictator truth")
        return 1
    print(f"{len(refs)} references\n")

    tot_w = tot_s = 0.0
    eng_got = eng_tot = 0
    secs = 0.0
    worst = []
    for wav in refs:
        said = json.loads(truth.path_for(wav).read_text())["said"]
        heard, took = transcribe(wav, a.model)
        secs += took
        w, s = wer(said, heard), wer_sound(said, heard)
        tot_w += w
        tot_s += s
        g, t = eng_exact(said, heard)
        eng_got += g
        eng_tot += t
        worst.append((s, said, heard))

    n = len(refs)
    print(f"{'WER':14} {tot_w / n:6.1%}   every difference, spelling included")
    print(f"{'WER-sound':14} {tot_s / n:6.1%}   after romanisation is "
          f"normalised")
    print(f"{'ENG-exact':14} {eng_got / max(eng_tot, 1):6.1%}   of the "
          f"{eng_tot} English words in the references")
    print(f"{'seconds':14} {secs / n:6.2f}   per hold\n")

    worst.sort(reverse=True)
    print("Where it went most wrong, read these yourself:\n")
    for s, said, heard in worst[:5]:
        if s <= 0:
            break
        print(f"  said:  {said[:88]}")
        print(f"  heard: {heard[:88]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
