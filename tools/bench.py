#!/usr/bin/env python3
"""Compare speech models on YOUR audio, with metrics that fit the problem.

Plain word error rate is the wrong instrument here and would pick the wrong
model. It counts "chahiye" against "chahie" as a mistake when both are correct
and the choice between them is arbitrary, and it counts an English word
written in Devanagari as wrong in the same breath as a word that was simply
misheard. Those are different failures and only one of them matters.

So four numbers:

  WER        plain, on lowercased tokens. The pessimistic one. Reported for
             honesty, not to be optimised.
  WER-sound  the same alignment after mapping both sides through the Hindi
             phonetic key, which already normalises exactly the arbitrary
             variation (aspiration, w against v, doubled vowels, trailing h).
             THIS is the "did it hear the words" number.
  ENG-exact  over only the tokens that are English in the reference, the
             fraction reproduced exactly. THIS is the "pool rekvest" detector,
             and nothing published anywhere measures it.
  T-WER      an English word counts correct whether it came back in Latin or
             transliterated. The one number citable against published work,
             from the MUCS 2021 challenge.

Plus seconds per utterance and the fraction of outputs still carrying
Devanagari, neither of which may be traded for accuracy.

    python3 tools/bench.py --corpus ~/.dictator/corpus --refs refs.tsv \
        --model ~/.voicebridge/models/ggml-large-v3-turbo.bin \
        --model /path/to/apex-q8_0.bin
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictator import hindi, roman, stt          # noqa: E402

_WORD = re.compile(r"[A-Za-zऀ-ॿ']+")
# A word is treated as English if it is ASCII and the romanisation lexicon has
# never seen it as a Hindi word. Crude, and good enough: the point is to catch
# technical vocabulary (pull request, rebase, deployment), which no Hindi
# lexicon contains.
_HINDI_WORDS = None


def _hindi_vocab() -> set:
    global _HINDI_WORDS
    if _HINDI_WORDS is None:
        try:
            _HINDI_WORDS = {
                line.split("\t")[1].strip().lower()
                for line in roman._LEX.read_text().splitlines()
                if "\t" in line and not line.startswith("#")
            }
        except Exception:
            _HINDI_WORDS = set()
    return _HINDI_WORDS


def words(text: str) -> list:
    return [w.lower() for w in _WORD.findall(text or "")]


def looks_english(w: str) -> bool:
    return w.isascii() and w not in _hindi_vocab()


def _wer(ref: list, hyp: list) -> float:
    """Edit distance over tokens, as a fraction of the reference length."""
    if not ref:
        return 0.0 if not hyp else 1.0
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    same = sum(b.size for b in sm.get_matching_blocks())
    # Errors are everything in the reference that did not align, plus anything
    # inserted. Same shape as the usual S+D+I over N.
    return (len(ref) - same + max(0, len(hyp) - same)) / len(ref)


def score(reference: str, hypothesis: str) -> dict:
    ref, hyp = words(reference), words(hypothesis)
    sound_ref = [hindi.key(w) or w for w in ref]
    sound_hyp = [hindi.key(w) or w for w in hyp]

    # T-WER: an English reference word is correct if the hypothesis has it in
    # Latin OR transliterated. We cannot transliterate forward cheaply, so the
    # practical version is: fold Devanagari in the hypothesis to Latin first.
    twer_hyp = words(roman.to_latin(hypothesis)
                     if roman.has_devanagari(hypothesis) else hypothesis)

    eng = [w for w in ref if looks_english(w)]
    got = set(hyp)
    eng_exact = (sum(1 for w in eng if w in got) / len(eng)) if eng else None

    return {
        "wer": _wer(ref, hyp),
        "wer_sound": _wer(sound_ref, sound_hyp),
        "twer": _wer(ref, twer_hyp),
        "eng_exact": eng_exact,
        "eng_words": len(eng),
        "devanagari": bool(roman.has_devanagari(hypothesis)),
    }


def transcribe(wav: Path, model: Path, lang: str) -> "tuple[str, float]":
    """One utterance through whisper-cli, with the window sized as the product
    sizes it, so the model is the only thing that differs between rows."""
    wb = stt.whisper_bin()
    if not wb:
        raise SystemExit("whisper-cli not found")
    try:
        with wave.open(str(wav)) as w:
            secs = w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        secs = 0.0
    cmd = [wb, "-m", str(model), "-f", str(wav), "-nt", "-np", "-l", lang]
    ac = stt.audio_ctx_for(secs)
    if ac:
        cmd += ["-ac", str(ac)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return (r.stdout or "").strip(), time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--refs", required=True, type=Path,
                    help="TSV: filename<TAB>what you actually said")
    ap.add_argument("--model", action="append", required=True, type=Path)
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()

    refs = {}
    for line in a.refs.read_text().splitlines():
        if "\t" in line and not line.startswith("#"):
            name, text = line.split("\t", 1)
            refs[name.strip()] = text.strip()
    if not refs:
        raise SystemExit(f"no references in {a.refs}")

    results = {}
    for model in a.model:
        if not model.exists():
            print(f"skipping, not there: {model}")
            continue
        rows, total_secs = [], 0.0
        print(f"\n=== {model.name} ===")
        for name, reference in sorted(refs.items()):
            wav = a.corpus / name
            if not wav.exists():
                print(f"  missing audio: {name}")
                continue
            hyp, took = transcribe(wav, model, a.lang)
            s = score(reference, hyp)
            s["took"] = took
            s["file"] = name
            s["said"] = hyp
            rows.append(s)
            total_secs += took
            print(f"  {name}  {took:4.1f}s  wer {s['wer']:.2f}  "
                  f"sound {s['wer_sound']:.2f}  "
                  f"eng {('%.2f' % s['eng_exact']) if s['eng_exact'] is not None else ' n/a'}")
        if not rows:
            continue
        eng = [r["eng_exact"] for r in rows if r["eng_exact"] is not None]
        results[model.name] = {
            "wer": sum(r["wer"] for r in rows) / len(rows),
            "wer_sound": sum(r["wer_sound"] for r in rows) / len(rows),
            "twer": sum(r["twer"] for r in rows) / len(rows),
            "eng_exact": (sum(eng) / len(eng)) if eng else None,
            "secs": total_secs / len(rows),
            "devanagari": sum(1 for r in rows if r["devanagari"]) / len(rows),
            "n": len(rows),
            "rows": rows,
        }

    print("\n" + "=" * 78)
    print(f"{'model':32} {'WER':>6} {'sound':>7} {'T-WER':>7} {'ENG':>6} "
          f"{'secs':>6} {'देव':>5}")
    print("-" * 78)
    for name, r in results.items():
        eng = f"{r['eng_exact']:.2f}" if r["eng_exact"] is not None else "  n/a"
        print(f"{name[:32]:32} {r['wer']:6.2f} {r['wer_sound']:7.2f} "
              f"{r['twer']:7.2f} {eng:>6} {r['secs']:6.1f} {r['devanagari']:5.2f}")
    print("\nLower is better for WER, sound, T-WER and the Devanagari column.")
    print("HIGHER is better for ENG, which is the fraction of English words")
    print("that came back as English. That is the one that decides it.")

    if a.json:
        a.json.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        print(f"\nwritten to {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
