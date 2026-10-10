#!/usr/bin/env python3
"""Why a short hold is worse than a long one, measured instead of argued.

Issue #17 names three candidates and says which dominates is not established.
This runs the short recordings in the corpus under each setting on its own, so
the columns can be compared rather than reasoned about:

  shipped    what the product does now: encoder trimmed by duration, -l auto
  full       the encoder left alone
  pinned     the language decided by the tiny detector instead of by whisper
  both

The number is the share of words in neither dictionary, from dictator_core.known.
Word count sits beside it because a model that drops speech scores well by
saying less, and on short holds that is the likeliest way to look good.
"""
import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictator_core import known, stt                      # noqa: E402


def run(wav: Path, trim: bool, pin: bool) -> "tuple[str, float]":
    wb = stt.whisper_bin()
    model, lang = stt.stt_lang_mode()
    with wave.open(str(wav)) as w:
        secs = w.getnframes() / float(w.getframerate() or 1)
    if pin:
        # What MIN_DETECT_SECS currently refuses to do for these.
        was = stt.MIN_DETECT_SECS
        stt.MIN_DETECT_SECS = 0.0
        try:
            lang = stt.pinned_language(str(wav), "auto")
        finally:
            stt.MIN_DETECT_SECS = was
    else:
        lang = "auto"
    cmd = [wb, "-m", str(model), "-f", str(wav), "-nt", "-np", "-l", lang,
           "--prompt", stt.whisper_prompt()]
    ac = stt.audio_ctx_for(secs) if trim else 0
    if ac:
        cmd += ["-ac", str(ac)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       errors="replace", timeout=300)
    return (r.stdout or "").strip(), time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--under", type=float, default=5.0)
    a = ap.parse_args()

    wavs = []
    for w in sorted(a.corpus.glob("*.wav")):
        try:
            with wave.open(str(w)) as h:
                secs = h.getnframes() / float(h.getframerate() or 1)
        except Exception:
            continue
        if secs <= a.under:
            wavs.append(w)
    print(f"{len(wavs)} holds of {a.under:.0f}s or less\n")

    setups = (("shipped", True, False), ("full encoder", False, False),
              ("pinned language", True, True), ("both", False, True))
    print(f"{'setting':18} {'words':>6} {'gibberish':>10} {'secs':>7}")
    print("-" * 46)
    worst = {}
    for name, trim, pin in setups:
        words = unknown = 0
        took = 0.0
        for w in wavs:
            text, t = run(w, trim, pin)
            took += t
            s = known.score(text)
            words += s["words"]
            unknown += s["unknown"]
            for bad in known.unknown(text):
                worst.setdefault(name, []).append(bad)
        print(f"{name:18} {words:6d} {unknown / max(words, 1):9.2%} "
              f"{took / max(len(wavs), 1):6.2f}s")
    print("\nWhat each was marked down for:")
    for name, _, _ in setups:
        got = ", ".join(worst.get(name, [])[:14]) or "nothing"
        print(f"  [{name}]\n    {got}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
