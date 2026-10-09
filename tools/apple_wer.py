#!/usr/bin/env python3
"""Score Apple's on-device transcriber against this project's own references.

The point is not Apple. The point is that `ios/` ships no speech model and
leans on `SpeechTranscriber` instead, and a product decision that size should
rest on a number measured here rather than on a benchmark measured elsewhere on
other people's audio.

Same recordings, same references, same three numbers `tools/wer.py` reports, so
the two are comparable line for line.

    tools/apple_speech.swift   transcribes; build it with
        swiftc -O -parse-as-library tools/apple_speech.swift -o /tmp/apple_speech
        /tmp/apple_speech en_IN $(ls ~/.dictator/corpus/*.wav) > /tmp/apple.tsv
    tools/apple_wer.py /tmp/apple.tsv
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dictator import known, truth                               # noqa: E402

_spec = importlib.util.spec_from_file_location("wer", ROOT / "tools" / "wer.py")
wer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wer)


def read(tsv: Path) -> dict:
    out = {}
    for line in tsv.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            out[Path(parts[0]).stem] = (int(parts[1]), parts[2])
    return out


def score(rows: list, which: int) -> str:
    n = len(rows)
    if not n:
        return "no rows"
    w = sum(wer.wer(r[0], r[which]) for r in rows) / n
    ws = sum(wer.wer_sound(r[0], r[which]) for r in rows) / n
    got = tot = 0
    for r in rows:
        a, b = wer.eng_exact(r[0], r[which])
        got, tot = got + a, tot + b
    return (f"WER {w * 100:6.2f}%   WER-sound {ws * 100:6.2f}%   "
            f"ENG-exact {got}/{tot} = {got / max(tot, 1) * 100:5.1f}%")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    theirs = read(Path(sys.argv[1]))

    # (said, ours, theirs). `heard` and not `text`: the references were written
    # against raw output, and `text` has had the fillers removed, so scoring one
    # against the other counts every dropped "uh" as an error. Same reason
    # tools/wer.py gives.
    rows, secs, ms = [], 0.0, 0
    for wav in truth.written():
        ref = json.loads((truth.REFS / (wav.stem + ".json")).read_text())
        said = (ref.get("said") or "").strip()
        if not said or wav.stem not in theirs:
            continue
        took, text = theirs[wav.stem]
        rows.append((said, ref.get("heard", ""), text))
        secs += ref.get("seconds", 0.0)
        ms += max(took, 0)

    if not rows:
        print("No references with matching transcripts.")
        return 1

    english = [r for r in rows if not any(
        t in known.HINDI and t not in known.ENGLISH for t in wer._words(r[0]))]
    mixed = [r for r in rows if r not in english]

    print(f"{len(rows)} recordings, identical audio, identical references\n")
    print(f"  this project   {score(rows, 1)}")
    print(f"  Apple          {score(rows, 2)}")
    print(f"\nEnglish-only holds ({len(english)})")
    print(f"  this project   {score(english, 1)}")
    print(f"  Apple          {score(english, 2)}")
    print(f"\nHolds containing Hindi words ({len(mixed)})")
    print(f"  this project   {score(mixed, 1)}")
    print(f"  Apple          {score(mixed, 2)}")
    print(f"\nApple latency {ms / len(rows):.0f} ms mean over {secs / len(rows):.1f} s "
          f"mean audio (real-time factor {ms / 1000 / max(secs, 1e-9):.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
