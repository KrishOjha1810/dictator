# Contributing

Dictator is local push-to-talk dictation for macOS: a Python package
(`dictator/`) plus Swift helpers (`native/`). Read
[`architecture.md`](architecture.md) before changing how the pieces fit
together, and [`findings.md`](findings.md) before changing engines, latency or
permissions logic. Much of what looks like a simple improvement there has
already been measured and rejected.

## Set up

You need an Apple silicon Mac with macOS 14 or newer, and:

- Apple's command line tools: `xcode-select --install`
- [Homebrew](https://brew.sh), for `whisper-cpp`
- Python 3 (CI runs 3.12)

```bash
git clone https://github.com/cc-vb/dictator.git ~/dictator
cd ~/dictator && scripts/install.sh
```

The installer is safe to run again. It puts `dictator` on your `PATH`, builds
the Swift helpers and downloads the speech models.

## Test

```bash
python3 -m pip install pytest jellyfish
python3 -m pytest -q tests
```

CI runs the same command on every push and pull request. The tests never touch
your real `~/.dictator`: `tests/conftest.py` points the state directory at a
temporary folder. Keep it that way in any test you add.

## Build

```bash
tools/build_native.sh build/native   # Swift helpers and the pinned whisper.cpp
tools/build_app.sh build/appbin      # the app executable
tools/build_dmg.sh [VERSION]         # bundle, sign, package -> build/Dictator-<VERSION>.dmg
```

`tools/build_dmg.sh` signs ad-hoc by default, which is fine for a local build.
Releases are covered in [`releasing.md`](releasing.md).

To look at the app's windows without starting dictation, run the built binary
with `DICTATOR_FAKE=1`. The header of `tools/build_app.sh` lists the other
switches.

## Rules

These are the things that are easy to break and expensive to get wrong.

- **No audio or text leaves the machine.** No network calls for speech, recap
  or meetings. A feature that needs a server is a different product.
- **Keep the public library stable.** `Dictator`, `Transcript`, `transcribe`
  and `VERSION` (`dictator/__init__.py`) are the public surface. Everything
  else is internal.
- **The pipeline lives in one place.** The order of steps in `dictator/api.py`
  is the hard part. The key listener calls the library; do not copy the
  pipeline anywhere else.
- **Never change the signing identity.** macOS ties each user's Microphone and
  Accessibility grants to it. A new identity silently drops every grant on the
  next update. See `dictator/signing.py`, `dictator/tcc.py` and
  [`architecture.md`](architecture.md#why-it-is-signed).
- **State lives in `~/.dictator`**, overridable with `DICTATOR_STATE`.
- **Measure, do not guess.** A number added to `findings.md` comes from a real
  run on a real machine and says where it came from.

## Branches and pull requests

- Branch off `main`. Name branches `feat/...`, `fix/...`, `docs/...` and so on.
- Open a pull request into `main`. CI must pass.
- **Merge with a merge commit, never squash.** The app's build number is the
  commit count of `main`; a squash lowers it, and installed copies then ignore
  every later update.
- Update the docs in the same pull request as the behaviour they describe.

## Commit messages

```
type: short summary in the imperative

- what changed, one point per line
- and why, when it is not obvious
```

`type` is one of `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`.

## Layout

| Path | What lives there |
|---|---|
| `dictator/` | the Python package: dictation loop, CLI, library |
| `native/` | Swift: key listener, recorder, indicator, paste, the app, the meeting recorder |
| `bin/dictator` | the command line entry point |
| `scripts/install.sh` | the from-source installer |
| `tools/` | build, release and benchmark scripts |
| `tests/` | the pytest suite |
| `docs/` | user and developer documentation |
| `website/` | the public site (Astro), see [`website/README.md`](../website/README.md) |
