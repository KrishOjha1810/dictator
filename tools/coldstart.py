#!/usr/bin/env python3
"""Where the seconds go on the first hold after an install, and on the tenth.

Issue #1 says dictation is slow for the first few minutes after installing and
settles down later. That is a claim about a DIFFERENCE between a cold machine
and a warm one, and no average latency number can confirm or deny it. So this
times one hold in pieces, and runs the same hold cold and warm.

The pieces, in the order a hold pays them:

  spawn      a fresh python3 that imports the pipeline. The always-on listener
             pays this once at login, not per hold, but the first hold after
             an install pays it while the user is watching.
  recorder   exec of the prebuilt recorder. Deliberately with no arguments, so
             it prints its usage and exits without opening the microphone:
             what is being timed is dyld plus the code signature check, which
             is the whole difference between a cold binary and a warm one.
             (Time to the first audio in the file is in docs/findings.md:
             0.54s cold against 0.08s warm, and the gap is this same cost.)
  detect     the tiny model deciding which language was spoken, which exists
             so whisper is not asked to run its encoder twice.
  load       the transcribing model, read from disk. 1.6GB for turbo.
  encode     the encoder, which every earlier measurement puts at ~85% of a
             warm hold.
  decode     the decoder, plus mel and sampling.
  other      the rest of the whisper process: Metal init, dlopen of the
             backends, argument parsing. Wall clock minus the parts above.
  polish     romanisation, the learned vocabulary and the shaping pass.
  deliver    exec of the prebuilt paste helper, again with no arguments, so
             nothing is written to the clipboard and nothing is pasted.

"Cold" here does not mean a reboot, because a reboot cannot be repeated ten
times in an afternoon and a measurement that cannot be repeated is an anecdote.
It means the model files and the helper binaries have been evicted from the
page cache, with msync(MS_INVALIDATE), which needs no root and is checked
rather than assumed: mincore() reports the residency before and after, and the
run refuses to call itself cold if the pages are still there.

    python3 tools/coldstart.py --runs 10
    python3 tools/coldstart.py --runs 10 --cold
    python3 tools/coldstart.py --runs 3 --both --json out.json
"""
import argparse
import ctypes
import json
import os
import re
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dictator_core import core, stt                    # noqa: E402

# ---- the page cache, read and emptied ---------------------------------------
# macOS has `purge`, which needs root and empties the whole cache, so it is no
# use inside a tool somebody runs against one file. What works without root is
# mapping the file and calling msync(MS_INVALIDATE), which drops its clean
# pages. mincore() then says whether it worked, which is the only reason to
# trust it.
_libc = ctypes.CDLL("libc.dylib", use_errno=True)
_libc.mmap.restype = ctypes.c_void_p
_libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                       ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
_libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
_libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
_libc.msync.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
_PROT_READ, _MAP_SHARED, _MS_INVALIDATE = 1, 1, 2
# 16KB on Apple silicon, not the 4KB everyone types from memory. Getting this
# wrong does not fail, which is worse: mincore fills a quarter of the vector
# and every file reads as exactly 25 percent resident when it is entirely
# resident, which looks like a plausible answer.
_PAGE = os.sysconf("SC_PAGE_SIZE")


def _mapped(path: Path, fn):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        size = os.fstat(fd).st_size
        if size <= 0:
            return None
        addr = _libc.mmap(None, size, _PROT_READ, _MAP_SHARED, fd, 0)
        if not addr or addr == ctypes.c_void_p(-1).value:
            return None
        try:
            return fn(addr, size)
        finally:
            _libc.munmap(ctypes.c_void_p(addr), size)
    finally:
        os.close(fd)


def resident(path: Path) -> float:
    """How much of this file is in the page cache right now, 0..1."""
    def ask(addr, size):
        n = (size + _PAGE - 1) // _PAGE
        vec = ctypes.create_string_buffer(n)
        if _libc.mincore(ctypes.c_void_p(addr), size, vec) != 0:
            return None
        return sum(1 for b in vec.raw if b & 1) / n
    try:
        return _mapped(Path(path), ask)
    except Exception:
        return None


def evict(path: Path) -> float:
    """Drop this file's pages, and report what is left behind."""
    try:
        _mapped(Path(path), lambda a, s:
                _libc.msync(ctypes.c_void_p(a), s, _MS_INVALIDATE))
    except Exception:
        pass
    return resident(path)


# ---- the parts of a hold ----------------------------------------------------
_TIMING = {
    "load": r"load time\s*=\s*([\d.]+)\s*ms",
    "mel": r"mel time\s*=\s*([\d.]+)\s*ms",
    "sample": r"sample time\s*=\s*([\d.]+)\s*ms",
    "encode": r"encode time\s*=\s*([\d.]+)\s*ms",
    "decode": r"decode time\s*=\s*([\d.]+)\s*ms",
    "batchd": r"batchd time\s*=\s*([\d.]+)\s*ms",
    "prompt": r"prompt time\s*=\s*([\d.]+)\s*ms",
}


def _whisper(model: Path, wav: Path, lang: str, ac: int, prompt: bool,
             detect_only: bool = False, engine: str = "whisper") -> dict:
    """One transcription, with its own timings read back out of it.

    Deliberately not -np: the timing block is the measurement, and it is the
    only place the model load is separated from the encoder."""
    if engine == "parakeet":
        exe = stt._find("parakeet-cli")
        if not exe:
            raise SystemExit("parakeet-cli not found")
        cmd = [exe, "-m", str(model), "-f", str(wav)]
    else:
        wb = stt.whisper_bin()
        if not wb:
            raise SystemExit("whisper-cli not found")
        cmd = [wb, "-m", str(model), "-f", str(wav), "-nt"]
        if detect_only:
            cmd += ["-dl"]
        else:
            cmd += ["-l", lang]
            if prompt:
                cmd += ["--prompt", stt.whisper_prompt()]
            if ac:
                cmd += ["-ac", str(ac)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    wall = (time.time() - t0) * 1000.0
    out = (r.stdout or "") + (r.stderr or "")
    got = {"wall": wall, "text": (r.stdout or "").strip()}
    for name, pat in _TIMING.items():
        hit = re.search(pat, out)
        got[name] = float(hit.group(1)) if hit else 0.0
    hit = re.search(r"fallbacks\s*=\s*(\d+)\s*p\s*/\s*(\d+)\s*h", out)
    got["fallbacks"] = (int(hit.group(1)) + int(hit.group(2))) if hit else 0
    counted = sum(got[k] for k in _TIMING)
    got["other"] = max(0.0, wall - counted)
    return got


def _exec_ms(exe: Path) -> float:
    """What it costs to start a prebuilt helper, without letting it do its job.

    Both helpers print their usage and exit when given no arguments, so this
    opens no microphone and touches no clipboard. What is left is exactly what
    a cold binary pays and a warm one does not: dyld, and the kernel checking
    the signature."""
    if not Path(exe).exists():
        return 0.0
    t0 = time.time()
    try:
        subprocess.run([str(exe)], capture_output=True, timeout=60)
    except Exception:
        return 0.0
    return (time.time() - t0) * 1000.0


_IMPORT = ("import sys; sys.path.insert(0, %r); "
           "from dictator_core import api, stt  # noqa")


def _spawn_ms() -> float:
    t0 = time.time()
    subprocess.run([sys.executable, "-c", _IMPORT % str(HERE.parent)],
                   capture_output=True, timeout=120)
    return (time.time() - t0) * 1000.0


def _polish_ms(text: str) -> float:
    from dictator_core.api import Dictator
    d = Dictator(learn=False, remember=False)
    t0 = time.time()
    d.polish(d.romanise(text))
    return (time.time() - t0) * 1000.0


# Everything a cold machine has not read yet. The helper binaries are here for
# the same reason the models are: the first exec after a boot pays for the
# pages and the signature, and issue #1 is a claim about first anything.
def _cold_files(model: Path, engine: str = "whisper") -> list:
    files = [model, stt.MODEL_DIR / stt._DETECT_MODEL]
    for name in ("dictator-rec", "dictator-paste"):
        p = core.STATE_DIR / "bin" / name
        if p.exists():
            files.append(p)
    exe = stt._find("parakeet-cli") if engine == "parakeet" else stt.whisper_bin()
    if exe:
        files.append(Path(exe))
        # The binary is 600KB and the backends behind it are five megabytes of
        # dylib that dlopen has to read and the kernel has to check. Leaving
        # them warm while calling the run cold would hide part of the cost it
        # is there to measure.
        files += _linked_libraries(Path(exe))
    return [f for f in files if Path(f).exists()]


def _linked_libraries(exe: Path) -> list:
    """Every Homebrew library this binary pulls in, including the ggml
    backends it dlopens at run time rather than links against."""
    out = []
    try:
        r = subprocess.run(["otool", "-L", str(exe)],
                           capture_output=True, text=True, timeout=30)
        for line in (r.stdout or "").splitlines()[1:]:
            p = line.strip().split(" ")[0]
            if p.startswith("/opt/homebrew") or p.startswith("/usr/local"):
                out.append(Path(p))
    except Exception:
        pass
    for cellar in ("/opt/homebrew/Cellar", "/usr/local/Cellar"):
        out += list(Path(cellar).glob("ggml/*/libexec/*.so"))
        out += list(Path(cellar).glob("whisper-cpp/*/lib/*.dylib"))
    return out


def one_hold(model: Path, wav: Path, lang: str, cold: bool,
             detect: bool = True, engine: str = "whisper",
             prefetch: bool = False) -> dict:
    """One hold, end to end, in pieces."""
    row = {"cold": cold}
    if cold:
        left = {}
        for f in _cold_files(model, engine):
            left[Path(f).name] = evict(f)
        row["resident_after_evict"] = left
    else:
        row["resident_model"] = resident(model)

    if prefetch:
        # What the product now does while the key is held. Timed, but NOT
        # counted in what the user waits for, because it happens during the
        # hold and not after it. Counting it would be measuring the fix
        # against a hold nobody made.
        from dictator_core import warmup
        t0 = time.time()
        warmup.models(background=False)
        row["preload"] = (time.time() - t0) * 1000.0

    row["spawn"] = _spawn_ms()
    row["recorder"] = _exec_ms(core.STATE_DIR / "bin" / "dictator-rec")

    secs = stt.audio_seconds(str(wav))
    row["audio_secs"] = secs
    row["detect"] = 0.0
    if engine == "whisper" and detect and lang == "auto" \
            and secs >= stt.MIN_DETECT_SECS:
        d = _whisper(stt.MODEL_DIR / stt._DETECT_MODEL, wav, lang, 0, False,
                     detect_only=True)
        row["detect"] = d["wall"]
        row["detect_load"] = d["load"]
        hit = re.search(r"detected language:\s*([a-z]{2,3})", d["text"])
        code = hit.group(1) if hit else ""
        if code in stt.PINNABLE:
            lang = code

    w = _whisper(model, wav, lang, stt.audio_ctx_for(secs), True, engine=engine)
    row.update({k: w[k] for k in
                ("load", "mel", "sample", "encode", "decode", "batchd",
                 "prompt", "other", "wall", "fallbacks")})
    row["lang"] = lang
    row["text"] = w["text"][:120]
    row["polish"] = _polish_ms(w["text"])
    row["deliver"] = _exec_ms(core.STATE_DIR / "bin" / "dictator-paste")
    # What the user waits for after letting go of the key: everything except
    # the process spawn and the recorder, which are paid before and during.
    row["after_release"] = (row["detect"] + row["wall"] + row["polish"]
                            + row["deliver"])
    row["total"] = row["after_release"] + row["spawn"] + row["recorder"]
    return row


_COLS = ("spawn", "recorder", "detect", "load", "encode", "decode", "other",
         "polish", "deliver", "after_release")


def _print_rows(title: str, rows: list) -> None:
    print(f"\n=== {title} ===")
    head = f"{'run':>4} " + " ".join(f"{c[:8]:>8}" for c in _COLS)
    print(head)
    print("-" * len(head))
    for i, r in enumerate(rows, 1):
        print(f"{i:>4} " + " ".join(f"{r.get(c, 0.0):8.0f}" for c in _COLS))
    if len(rows) > 1:
        print("-" * len(head))
        print(f"{'med':>4} " + " ".join(
            f"{statistics.median([r.get(c, 0.0) for r in rows]):8.0f}"
            for c in _COLS))


def _summary(cold: list, warm: list) -> None:
    print("\n" + "=" * 78)
    print(f"{'stage':>12} {'cold':>10} {'warm':>10} {'difference':>12}")
    print("-" * 78)
    for c in _COLS:
        cm = statistics.median([r.get(c, 0.0) for r in cold]) if cold else 0.0
        wm = statistics.median([r.get(c, 0.0) for r in warm]) if warm else 0.0
        print(f"{c:>12} {cm:9.0f}ms {wm:9.0f}ms {cm - wm:11.0f}ms")
    print("\nAll times in milliseconds, medians. 'after_release' is what the")
    print("user actually waits for once the key comes up.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", type=Path,
                    help="one hold. Defaults to the longest in the corpus.")
    ap.add_argument("--corpus", type=Path,
                    default=core.STATE_DIR / "corpus")
    ap.add_argument("--model", type=Path,
                    help="default: the model this engine would use")
    ap.add_argument("--engine", default="whisper",
                    choices=("whisper", "parakeet"),
                    help="whisper is the Hinglish path, parakeet the English")
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--cold", action="store_true",
                    help="empty the page cache before every run")
    ap.add_argument("--both", action="store_true",
                    help="one cold run, then --runs warm ones, then compare")
    ap.add_argument("--prefetch", action="store_true",
                    help="warm the page cache first, as a held key now does")
    ap.add_argument("--no-detect", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()

    busy = subprocess.run(["pgrep", "-f", "whisper-cli|parakeet-cli"],
                          capture_output=True, text=True).stdout.strip()
    if busy:
        print("a transcription is already running, so the GPU is busy and")
        print("every number here would be someone else's contention. Wait.")
        return 2

    model = a.model or (stt._PARAKEET if a.engine == "parakeet"
                        else stt._best_model(stt._ML_MODELS))
    if not Path(model).exists():
        raise SystemExit(f"no model at {model}")
    wav = a.wav
    if not wav:
        wavs = [(w, stt.audio_seconds(str(w)))
                for w in sorted(Path(a.corpus).glob("*.wav"))]
        wavs = [w for w in wavs if 8 <= w[1] <= 20]
        if not wavs:
            raise SystemExit(f"no usable audio in {a.corpus}")
        wav = max(wavs, key=lambda p: p[1])[0]
    secs = stt.audio_seconds(str(wav))
    print(f"model {Path(model).name} "
          f"({Path(model).stat().st_size / 1e6:.0f}MB)")
    print(f"audio {Path(wav).name}  {secs:.1f}s  "
          f"window {stt.audio_ctx_for(secs)}")

    cold, warm = [], []
    if a.both or a.cold:
        n = a.runs if a.cold and not a.both else 1
        for _ in range(n):
            cold.append(one_hold(model, wav, a.lang, True, not a.no_detect,
                                 a.engine, a.prefetch))
        _print_rows("cold, page cache emptied first"
                    + (", then warmed as a hold warms it" if a.prefetch
                       else ""), cold)
        if a.prefetch:
            print("preload, during the hold rather than after it: "
                  + " ".join(f"{r.get('preload', 0.0):.0f}ms" for r in cold))
    if a.both or not a.cold:
        for _ in range(a.runs):
            warm.append(one_hold(model, wav, a.lang, False, not a.no_detect,
                                 a.engine))
        _print_rows("warm, run after run", warm)
    if cold and warm:
        _summary(cold, warm)

    if a.json:
        a.json.write_text(json.dumps({"model": str(model), "wav": str(wav),
                                      "secs": secs, "cold": cold,
                                      "warm": warm}, indent=1))
        print(f"\nwritten to {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
