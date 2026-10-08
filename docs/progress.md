# Progress: Dictator as a free .dmg

The plan is `implementation.md`. This file is what has actually happened.

Each item is ticked with the date and the commit that did it. When a test
result is not what was expected, it gets a line under "What we learned" with
the date, so the surprise is not lost.

Branch: `feat/dmg-app`. Nothing merges to `main` until M1 passes its tests.

---

## Already done

- [x] Gatekeeper retest on macOS 27.0.1: ad-hoc signed, quarantined app from
      a `.dmg` gets Open Anyway, runs after one approval (2026-10-08,
      `platforms.md`, "Retested 8 October 2026")
- [x] Plan written: `implementation.md` (2026-10-08)

---

## Contracts (before the lanes start)

- [x] Bundle layout and helper names fixed (`implementation.md`, "What is
      inside the .dmg") (2026-10-08, `faa3a7b`; the meeting
      helper keeps the repo's name, `Dictator Meeting.app`)
- [x] Environment: `DICTATOR_BUNDLE`, `PYTHONPATH` (2026-10-08, `faa3a7b`;
      bundled Python imports dictator and jellyfish with only these set)
- [x] `~/.dictator/status.json` fields: state, model progress, last error
      (2026-10-08, `77f5151`, tests only; not yet seen written by a running
      app). Each model now also carries `"essential": true|false`, added
      after review so onboarding waits only for the English models; an
      additive change, and the app falls back to the file name without it
- [x] `--json` output for the commands the UI reads (2026-10-08, `77f5151`;
      `stats --json` run from the bundle, the others by test)

---

## M1: Working .dmg

### Lane A: Runtime

- [x] Fetch standalone Python (pinned version, SHA256 checked) (2026-10-08,
      `47d2ea8`; CPython 3.12.14, python-build-standalone 20260924)
- [x] jellyfish installed into the bundle's `site-packages` (2026-10-08,
      `47d2ea8`)
- [x] `core.BUNDLE`, and helper paths point into `Contents/Helpers`
      (2026-10-08, `77f5151`; doctor from the bundle lists all nine helpers as
      "app bundle")
- [x] `swiftbuild.py`: never compiles in bundle mode (2026-10-08, `77f5151`; a
      blocking swiftc shim was never reached)
- [x] `stt.py`: finds bundled whisper and parakeet first (2026-10-08,
      `77f5151`)
- [ ] `always.py`: login item points at `/Applications/Dictator.app`
      (2026-10-08: written and tested against a fake bundle, never installed)
- [x] `signing.py`: skips local signing in bundle mode (2026-10-08, `77f5151`,
      tests)
- [x] `doctor` reports "app bundle" or "repo install" (2026-10-08, `77f5151`)
- [x] Tests for bundle mode pass, existing tests still pass (2026-10-08,
      `faa3a7b`; 665 passed, 17 failed, 6 skipped, the 17 the same jellyfish
      and test_standalone failures as the baseline. After the review fixes:
      673 passed, 16 failed, 6 skipped; the 16 are the jellyfish ones, the
      test_standalone failure is fixed)

### Lane B: Native

- [x] Swift helpers built ahead of time: hotkey, rec, paste, orb, readback
      (2026-10-08, `3782a17`)
- [x] Meeting.app built ahead of time (2026-10-08, `3782a17`; as `Dictator
      Meeting.app`, identifier `com.dictator.meeting`, not per account)
- [x] whisper.cpp built from source, pinned tag, Metal on (2026-10-08,
      `3782a17`; v1.9.1, commit checked; Metal transcription seen by lane B,
      not rerun here)
- [x] parakeet-cli built from the same tree (2026-10-08, `3782a17`; `--help`
      only, no parakeet transcription yet)
- [x] Static ggml, or dylibs in `Frameworks/` with `@rpath` fixed (2026-10-08,
      `3782a17`; static, `Frameworks/` empty, `otool -L` clean on all 14
      Mach-O files)

### Lane D: Pipeline

- [ ] `tools/build_dmg.sh` runs end to end on a clean checkout
      (2026-10-08: runs end to end in 59 s on this tree, with the Python
      tarball and whisper.cpp clone cached; not yet from a clean checkout)
- [x] Signs inside out, `codesign --verify --deep --strict` passes
      (2026-10-08, `faa3a7b`; still valid after running the bundled CLI)
- [x] Produces `Dictator-<version>.dmg` with an Applications link (2026-10-08,
      `faa3a7b`; `hdiutil verify` passes, mounted read-only, app inside
      verifies)
- [x] SHA256 printed for the release notes (2026-10-08, `faa3a7b`)
- [x] Measured app size and .dmg size recorded below (2026-10-08, `faa3a7b`)

### Lane E: Verification

- [ ] Downloaded from a real GitHub release, Safari and Chrome
- [ ] Open Anyway appears and works (screenshot kept)
- [ ] No `AppTranslocation` path after a Finder drag
- [ ] Microphone and Accessibility prompts name "Dictator" and work
- [ ] Dictation pastes into Terminal, Safari, Slack, Notes
- [ ] English before the Hinglish model lands, Hinglish after
- [ ] Login item starts after a reboot
- [ ] Repo install and app on the same Mac do not fight

### Release certificate

- [ ] "Dictator Release" certificate created
- [ ] Backed up as an encrypted `.p12` outside the repo

---

## M2: The app

### Lane C: UI

Code for everything below except the bar is in `ddebfb6` and compiles with
no warnings. None of it is ticked: the app has not been launched, even with
`DICTATOR_FAKE=1`, so no window has been seen.

- [ ] SwiftUI app shell replaces `native/app/main.swift`, still starts the
      dictation loop as a child
- [ ] Reads `status.json`, works against fake data
- [ ] Onboarding: Welcome, Microphone, Accessibility, Your key, Languages,
      Try it
- [ ] The bar: waveform pill, position setting, rule "visible if and only if
      our microphone is open" kept
- [ ] Hub: Home (stats, recap, history by day, search)
- [ ] Hub: Words, Snippets, Apps, Review, Meetings
- [ ] Settings: General, Language, Microphone, Privacy, Advanced, About
- [ ] Menu bar icon with status
- [ ] Install command line tool into `~/.local/bin`

### Verification

- [ ] Onboarding on a fresh user account, start to first sentence
- [ ] Install 1.0, then 1.1: permissions survive, Open Anyway asked again or
      not (record which)

---

## M3: Public release

- [ ] Download page with the two screenshots
- [ ] Update check: manual first, Sparkle tested
- [ ] Version 1.0 on GitHub Releases

---

## Measurements

| What | Value | Date |
|---|---|---|
| App installed size | 50.9 MB (python 37.3, helpers 9.9, dictator 1.6, site-packages 0.8, Frameworks 0) | 2026-10-08, `faa3a7b` |
| .dmg size | 24.6 MB (25,804,430 bytes, UDZO zlib-9) | 2026-10-08, `faa3a7b` |
| App and .dmg after the review fixes | app 51.0 MB (python 37.3, helpers 9.9, dictator 1.6, site-packages 0.8); .dmg 24.9 MB (26,094,341 bytes) | 2026-10-08, review fixes |
| First launch to first sentence | — | |

---

## What we learned

- 2026-10-08: The published "Move to Trash only" result for ad-hoc apps did
  not reproduce on macOS 27.0.1. Open Anyway is offered.
- 2026-10-08: The test app ran from an `AppTranslocation` path after
  approval, because it was not moved by Finder. Check with a real drag.
- 2026-10-08: The three lanes picked three macOS floors: helpers 15.0, the app
  13.0, the bundle's plist 14.0. The app would have opened on 14 and its
  helpers would not have loaded. Now one variable, `DICTATOR_MIN_MACOS`
  (14.0, because the orb needs `CADisplayLink`); the meeting recorder stays
  at the 15.0 its own plist declares.
- 2026-10-08: The first load of each whisper binary compiles Metal shaders for
  10 to 11 s; after that it is 0.013 s. Homebrew's build does the same.
  Onboarding should warm the server during the model download.
- 2026-10-08: The Command Line Tools have no SwiftUI macro plugin, and in the
  macOS 27 SDK `@State` is a macro. The views keep state in small classes
  under `@StateObject` so the app builds without Xcode.
- 2026-10-08: Python writes a missing `.pyc` beside its source, which is
  inside the signed bundle, and one write breaks the signature. All bytecode
  is compiled at build time with unchecked hashes, and the build checks the
  signature again after running the bundled CLI.
- 2026-10-08: The bundled-Python import check first passed for the wrong
  reason: the repo's own `dictator/` was found from the current directory. It
  now runs with `-P` and from a temporary directory.
- 2026-10-08: `libpython3.12.dylib` is 17 MB that nothing links; the build
  removes it after checking with `otool`. The static whisper.cpp helpers are
  9.9 MB against 4.5 MB for Homebrew copies plus their dylibs, which is why
  the app is 50.9 MB and not the 44.7 MB lane D measured with stand-ins. Both
  are under the plan's 60 to 90 MB and 30 to 45 MB.
- 2026-10-08, review of the merged lanes, fixed:
  - When the key listener died, status.json always ended as "paused": its
    closed stdout reads as ready, so the "listener exited" branch never ran,
    and the stop path wrote "ready" over whatever was there. A missing
    permission now ends as `needs_permission`, a dead listener as `error`
    (exit 1), and only a deliberate stop as `paused`.
  - Three threads wrote status.json through one temporary name per
    process. Under load about a third of reads were invalid JSON. Now one
    name per thread, behind a lock.
  - Nothing rewrote status.json while a model downloaded, so the
    onboarding models card never unlocked by itself, and it also waited for
    the optional 1.5 GB Hinglish model. The loop now republishes while a
    model is missing; the card waits for the essential models only and has
    "Continue, finish in background".
  - The app stopped the loop with SIGTERM, which Python's default kills
    outright: the recorder kept the microphone open for up to 120 s after
    Pause or Quit. The loop now treats SIGTERM as Ctrl-C; Quit waits up to
    2 s for it.
  - In the app, a dictation child that died took the whole menu bar app
    with it, and nothing restarted it. The app now stays, shows the error
    and offers "Restart dictation". A status.json from an earlier run is no
    longer shown as the present.
  - `dictator status` inside the app asked launchd and said "not running"
    and "dictator on". It now reads the loop's pid file; `dictator on`
    refuses inside the app, since it would start a second loop.
  - The release CI could never publish: the tests job always failed on the
    models directory leaking into ~/.dictator (now redirected in
    tests/conftest.py). Actions are pinned to commits, and the release
    keychain is deleted right after signing.
  - Build: the libpython "keep it if linked" check was inverted by
    pipefail; jellyfish is pinned by wheel hash; the whisper.cpp stamp
    hashes the CMake flags; Swift helpers rebuild when the target changes.
