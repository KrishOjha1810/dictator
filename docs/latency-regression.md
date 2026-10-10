# Hold to paste went from 1.9 s to 35 s

Captured 10 October 2026 from `~/.dictator/dictate.log` on this Mac, running
the released app (v0.1.8, installed from the dmg). Parked here so the evidence
is not lost. Nothing is fixed yet and nothing below has been confirmed.

## What the log says

Every landing time in the log, oldest to newest, in milliseconds:

```
10955  6796  2840  5637  5159  3595  19548  31490  34855  30917
```

The reference figure for the same machine is **1.9 s median hold to paste**.
The last four holds are ten to eighteen times that, and they climb within one
session rather than being slow from the start.

## The part that is probably the cause

Every hold in the log says the same thing:

```
12  answered by the multilingual model
```

Not one went to Parakeet. The routing in `docs/findings.md` puts Parakeet at
**72.6%** of holds, turbo at 24.8% and small.en at 2.6%. Turbo is the slow
path and it is now taking everything, so the first question is not "why is
turbo slow" but **why is nothing reaching Parakeet**.

Two candidates, in the order worth checking:

1. **`parakeet-cli` does not resolve inside the app bundle.** `dictator
   doctor` on this Mac lists it at `/opt/homebrew/bin/parakeet-cli`, a
   Homebrew path. The released app ships its own helpers under
   `Contents/Helpers` and its own Python under `Contents/Resources`, so a
   bundle that cannot find the Homebrew binary would fall through to turbo
   silently, which is what the log shows.
2. **The fourth Parakeet guard rejects everything.** `_mangled_stretch` in
   `stt.py` catches Parakeet returning gibberish. If it fires on ordinary
   Hinglish, every hold is transcribed twice and the second one is turbo,
   which costs both times and would also explain the climb.

## The climb within a session

3.6 s to 34.9 s over a handful of holds is not a constant cost, it is
something accumulating. Worth ruling in or out first:

- whether `whisper-server` is reused or a new process starts per hold (model
  load was measured at **906 ms of a 1523 ms hold**, 60%, and a cold load is
  far worse);
- memory pressure, since turbo is the large model and the app now also runs a
  Swift process;
- whether the `audio_ctx` retry path is looping, a known failure mode before
  `WORTH_TRIMMING` was introduced.

## How to reproduce the measurement

```bash
grep -oE "^ *[0-9]+ ms from letting go" ~/.dictator/dictate.log | grep -oE "[0-9]+"
grep -c "answered by the multilingual model" ~/.dictator/dictate.log
```
