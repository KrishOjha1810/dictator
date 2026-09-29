#!/usr/bin/env python3
"""Run two speech models over the same real holds and say which is better.

No reference text, because the audio exists and the references do not. What it
compares is what can be compared honestly:

  gibberish   words in neither dictionary, per tools/nonwords.py. This is the
              one that matters: a mangled English technical word is not a
              different word, it is not a word at all.
  devanagari  how often the output needs the romanisation pass at all, which
              is the stage where an English word committed to Devanagari can
              never be recovered.
  seconds     per hold.
  words       total, because a model that drops speech scores well on
              gibberish by saying less, and this is what catches it.

Where the two disagree, the lines are printed side by side, because that is
the only place a human has to look.

    python3 tools/compare.py --corpus ~/.dictator/corpus \
        --model ~/.voicebridge/models/ggml-large-v3-turbo.bin \
        --model /path/to/apex-q8_0.bin
"""
import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import nonwords                              # noqa: E402
from dictator import roman, stt              # noqa: E402


def transcribe(wav: Path, model: Path, lang: str,
               trim: bool = True, prompt: bool = True) -> "tuple[str, float]":
    wb = stt.whisper_bin()
    if not wb:
        raise SystemExit("whisper-cli not found")
    try:
        with wave.open(str(wav)) as w:
            secs = w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        secs = 0.0
    cmd = [wb, "-m", str(model), "-f", str(wav), "-nt", "-np", "-l", lang]
    if prompt:
        cmd += ["--prompt", stt.whisper_prompt()]
    # Trimming the encoder is a speed trick tuned against one model. A different
    # model can loop on the same setting, so the comparison has to be runnable
    # without it, otherwise we blame the model for our own sizing.
    ac = stt.audio_ctx_for(secs) if trim else 0
    if ac:
        cmd += ["-ac", str(ac)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return (r.stdout or "").strip(), time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--model", action="append", required=True, type=Path)
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-seconds", type=float, default=3.0)
    ap.add_argument("--full-ctx", action="store_true",
                    help="do not shrink the encoder, which is tuned per model")
    ap.add_argument("--no-prompt", action="store_true",
                    help="drop the vocabulary prompt, which is tuned per model")
    a = ap.parse_args()

    wavs = []
    for w in sorted(a.corpus.glob("*.wav")):
        try:
            with wave.open(str(w)) as h:
                secs = h.getnframes() / float(h.getframerate() or 1)
        except Exception:
            continue
        # Very short holds are a word or a mis-press and tell us nothing.
        if secs >= a.min_seconds:
            wavs.append((w, secs))
    if a.limit:
        wavs = wavs[:a.limit]
    if not wavs:
        raise SystemExit(f"no usable audio in {a.corpus}")
    print(f"{len(wavs)} holds, {sum(s for _, s in wavs)/60:.1f} minutes\n")

    said = {}
    for model in a.model:
        if not model.exists():
            print(f"skipping, not there: {model}")
            continue
        rows, secs_total = [], 0.0
        print(f"=== {model.name} ===")
        for i, (wav, dur) in enumerate(wavs, 1):
            text, took = transcribe(wav, model, a.lang,
                                    trim=not a.full_ctx, prompt=not a.no_prompt)
            secs_total += took
            rows.append({"file": wav.name, "text": text, "took": took,
                         "dur": dur, **nonwords.score(text),
                         "deva": roman.has_devanagari(text)})
            if i % 10 == 0:
                print(f"  {i}/{len(wavs)}")
        said[model.name] = rows
        w = sum(r["words"] for r in rows)
        u = sum(r["unknown"] for r in rows)
        print(f"  {w} words, {u} unknown ({u/max(w,1):.2%}), "
              f"{secs_total/len(rows):.1f}s each, "
              f"{sum(1 for r in rows if r['deva'])/len(rows):.0%} Devanagari\n")

    print("=" * 74)
    print(f"{'model':30} {'words':>6} {'gibberish':>10} {'secs':>6} {'देव':>6}")
    print("-" * 74)
    for name, rows in said.items():
        w = sum(r["words"] for r in rows)
        u = sum(r["unknown"] for r in rows)
        print(f"{name[:30]:30} {w:6d} {u/max(w,1):9.2%} "
              f"{sum(r['took'] for r in rows)/len(rows):6.1f} "
              f"{sum(1 for r in rows if r['deva'])/len(rows):5.0%}")
    print("\nLower gibberish is better. Watch the word count: a model that")
    print("drops speech scores well by saying less, which is not better.")

    # The words, not only the number. A dictionary built by reading one
    # model's output flatters that model, and reading what each was actually
    # marked down for is the only way to see whether it did.
    import collections
    print("\n" + "=" * 74)
    print("What each was marked down for. Read these before believing the")
    print("percentages: a word here that is really a word is the instrument")
    print("failing, not the model.\n")
    for name, rows in said.items():
        counts = collections.Counter()
        for r in rows:
            for w in nonwords.unknown(r["text"]):
                counts[w.lower()] += 1
        shown = ", ".join(f"{w} x{c}" if c > 1 else w
                          for w, c in counts.most_common(40))
        print(f"  [{name[:26]}]\n    {shown or 'nothing'}\n")

    names = list(said)
    if len(names) == 2:
        a_rows, b_rows = said[names[0]], said[names[1]]
        print("\n" + "=" * 74)
        print("Where they disagree most, read these yourself:\n")
        pairs = sorted(zip(a_rows, b_rows),
                       key=lambda p: -abs(p[0]["share"] - p[1]["share"]))
        for x, y in pairs[:8]:
            print(f"  [{names[0][:18]}] {x['text'][:96]}")
            print(f"  [{names[1][:18]}] {y['text'][:96]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
