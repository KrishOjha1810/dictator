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

- [ ] Bundle layout and helper names fixed (`implementation.md`, "What is
      inside the .dmg")
- [ ] Environment: `DICTATOR_BUNDLE`, `PYTHONPATH`
- [ ] `~/.dictator/status.json` fields: state, model progress, last error
- [ ] `--json` output for the commands the UI reads

---

## M1: Working .dmg

### Lane A: Runtime

- [ ] Fetch standalone Python (pinned version, SHA256 checked)
- [ ] jellyfish installed into the bundle's `site-packages`
- [ ] `core.BUNDLE`, and helper paths point into `Contents/Helpers`
- [ ] `swiftbuild.py`: never compiles in bundle mode
- [ ] `stt.py`: finds bundled whisper and parakeet first
- [ ] `always.py`: login item points at `/Applications/Dictator.app`
- [ ] `signing.py`: skips local signing in bundle mode
- [ ] `doctor` reports "app bundle" or "repo install"
- [ ] Tests for bundle mode pass, existing tests still pass

### Lane B: Native

- [ ] Swift helpers built ahead of time: hotkey, rec, paste, orb, readback
- [ ] Meeting.app built ahead of time
- [ ] whisper.cpp built from source, pinned tag, Metal on
- [ ] parakeet-cli built from the same tree
- [ ] Static ggml, or dylibs in `Frameworks/` with `@rpath` fixed

### Lane D: Pipeline

- [ ] `tools/build_dmg.sh` runs end to end on a clean checkout
- [ ] Signs inside out, `codesign --verify --deep --strict` passes
- [ ] Produces `Dictator-<version>.dmg` with an Applications link
- [ ] SHA256 printed for the release notes
- [ ] Measured app size and .dmg size recorded below

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
| App installed size | — | |
| .dmg size | — | |
| First launch to first sentence | — | |

---

## What we learned

- 2026-10-08: The published "Move to Trash only" result for ad-hoc apps did
  not reproduce on macOS 27.0.1. Open Anyway is offered.
- 2026-10-08: The test app ran from an `AppTranslocation` path after
  approval, because it was not moved by Finder. Check with a real drag.
