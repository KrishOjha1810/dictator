#!/usr/bin/env python3
"""Change one thing at a time and see what it does to the error rate.

Every setting in this pipeline was chosen against a reference free score that
cannot see a model swapping one real word for another. With references written
by `dictator truth` there is finally a number worth tuning against, so this
asks each setting the only question that matters: turn it off, does the error
go up or down.

One variant at a time, each against every reference, and the result written to
disk as it goes so a long run that is interrupted still leaves what it learned.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictator import hindi, known, stt, truth          # noqa: E402

OUT = Path.home() / ".dictator" / "sweep.md"


def _words(t):
    for ch in ",.?!":
        t = (t or "").replace(ch, " ")
    return [w for w in t.lower().split() if w]


def _dist(a, b):
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def score(said, heard):
    ref = _words(said)
    w = _dist(ref, _words(heard)) / max(len(ref), 1)
    k = hindi.key
    s = _dist([k(x) for x in ref], [k(x) for x in _words(heard)]) / max(len(ref), 1)
    got = tot = 0
    hs = set(_words(heard))
    for x in ref:
        if x in known.ENGLISH and x not in known.HINDI:
            tot += 1
            got += x in hs
    return w, s, got, tot


def run(wav, model, trim, lang, prompt):
    wb = stt.whisper_bin()
    cmd = [wb, "-m", str(model), "-f", str(wav), "-nt", "-np", "-l", lang]
    if prompt:
        cmd += ["--prompt", stt.whisper_prompt()]
    secs = truth.seconds(wav)
    ac = (min(1500, max(200, int(secs / 0.02) + 80)) if secs > 0 else 0) if trim else 0
    if ac:
        cmd += ["-ac", str(ac)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       errors="replace", timeout=400)
    took = time.time() - t0
    # Romanise, because the product does. Without it the multilingual model's
    # Devanagari is scored against a Latin reference and every word counts as
    # an error: it reported turbo at 17% when the romanisation it always gets
    # was simply missing from the harness. Fifth time a measurement here has
    # been wrong about its own subject.
    stt._force_multilingual = True
    try:
        text = stt._romanise((r.stdout or "").strip())
    finally:
        stt._force_multilingual = False
    return text, took


def shipped(wav):
    import dictator
    d = dictator.Dictator(remember=False, learn=False, expand=False)
    t0 = time.time()
    return d.transcribe(str(wav)).heard, time.time() - t0


def main():
    refs = truth.written()
    if not refs:
        print("no references")
        return 1
    turbo = Path.home() / ".voicebridge" / "models" / "ggml-large-v3-turbo.bin"

    variants = [
        ("shipped pipeline", None),
        ("turbo only, as shipped", dict(model=turbo, trim=False, lang="auto", prompt=True)),
        ("turbo, encoder trimmed", dict(model=turbo, trim=True, lang="auto", prompt=True)),
        ("turbo, no vocabulary prompt", dict(model=turbo, trim=False, lang="auto", prompt=False)),
        ("turbo, language pinned to hi", dict(model=turbo, trim=False, lang="hi", prompt=True)),
        ("turbo, language pinned to en", dict(model=turbo, trim=False, lang="en", prompt=True)),
    ]

    OUT.write_text(f"# What each setting does to the error rate\n\n"
                   f"{len(refs)} references, written by hand against real "
                   f"recordings.\n\n"
                   f"| variant | WER | WER-sound | ENG-exact | secs |\n"
                   f"|---|---|---|---|---|\n")
    for name, how in variants:
        tw = ts = 0.0
        eg = et = 0
        secs = 0.0
        print(f"  {name}...", flush=True)
        for wav in refs:
            said = json.loads(truth.path_for(wav).read_text())["said"]
            try:
                heard, took = shipped(wav) if how is None else run(wav, **how)
            except Exception as e:
                print(f"    failed on {wav.stem}: {e}", flush=True)
                continue
            w, s, g, t = score(said, heard)
            tw += w
            ts += s
            eg += g
            et += t
            secs += took
        n = len(refs)
        line = (f"| {name} | {tw / n:.1%} | {ts / n:.1%} | "
                f"{eg / max(et, 1):.1%} | {secs / n:.2f} |\n")
        with OUT.open("a") as f:
            f.write(line)
        print("   " + line.strip(), flush=True)
    print(f"\nwritten to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
