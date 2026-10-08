# Shipping Dictator as a free .dmg

How Dictator becomes an app someone downloads, drags into Applications and
uses, without cloning this repo, without a terminal, and without the 99 dollar
Apple Developer Program. Also what that app looks like, because today there is
nothing to look at: the product is a command, a login item and a 16pt orb.

Why this is possible for free is in `platforms.md`, "Retested 8 October 2026".
In one line: a quarantined, self-signed app from a `.dmg` is blocked on first
open, and Privacy & Security then offers Open Anyway, once.

Where something below is measured it says so. Where it is a plan or an
estimate it says that too.

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Distribution | `.dmg` on GitHub Releases | Free, and the approval flow is Apple's own Open Anyway |
| Signing | One self-signed release certificate, kept by the maintainer, used for every release | Free. Keeps Microphone and Accessibility grants valid across updates (`signing.py` already does this per machine) |
| Notarization | None for now | Needs the 99 dollars. Everything below carries over unchanged if it is paid later |
| Hardened runtime | Off | Only notarization requires it, and it is the expensive part for a Python app (`platforms.md`, "How long notarization takes") |
| Models | Downloaded on first launch, not in the `.dmg` | Keeps the download at 30 to 45 MB instead of 2.2 GB. GitHub Releases also caps one file at 2 GiB |
| UI toolkit | SwiftUI, in the existing app bundle | The Swift toolchain is already used for five helpers. No Electron, no web view, nothing that adds 100 MB |
| Architecture | Apple silicon first | It is what this was measured on. Intel is an open question below |

---

## What is inside the .dmg

```
Dictator.dmg
├── Dictator.app
│   └── Contents/
│       ├── Info.plist              LSUIElement, usage strings, version
│       ├── MacOS/
│       │   └── Dictator            SwiftUI app: menu bar, onboarding, settings
│       ├── Helpers/
│       │   ├── dictator-hotkey     native/hotkey.swift, prebuilt
│       │   ├── dictator-rec        native/record.swift
│       │   ├── dictator-paste      native/paste.swift
│       │   ├── dictator-orb        native/orb.swift
│       │   ├── dictator-readback   native/readback.swift
│       │   ├── Meeting.app         native/meeting.swift + meetingapp/Info.plist (its own bundle today)
│       │   ├── whisper-server      whisper.cpp, built from source
│       │   ├── whisper-cli
│       │   └── parakeet-cli
│       ├── Frameworks/
│       │   └── libggml*.dylib      only if whisper.cpp is not built static
│       └── Resources/
│           ├── python/             standalone Python runtime
│           ├── dictator/           this repo's package, as is
│           ├── bin/dictator        the CLI entry point, as is
│           ├── site-packages/      jellyfish
│           └── AppIcon.icns
└── Applications -> /Applications   so the user can drag across
```

Models stay where they are today, in `~/.dictator/models`, so an existing
install and the app share them and nothing is downloaded twice.

### Size, estimated

| Part | Size | Source of the number |
|---|---|---|
| Python package + data | ~1.2 MB | measured, `du` on this repo |
| Swift helpers + app | ~3 to 6 MB | estimate |
| whisper.cpp binaries + ggml | ~14 MB | measured, the Homebrew install on this machine |
| Python runtime + jellyfish | ~40 to 70 MB | estimate, standalone build trimmed of tests and tkinter |
| **App installed** | **~60 to 90 MB** | |
| **.dmg (UDZO compressed)** | **~30 to 45 MB** | |
| Models, first launch | 712 MB for English, +1,549 MB for Hinglish | `stt.SHIPPED` |

---

## Sources the foundation needs

Everything the app bundles or downloads, where it comes from, and how it gets
into the build. The licence column is from memory and must be checked against
each project before the first release.

| Component | Source | Licence (to verify) | Into the build by |
|---|---|---|---|
| Python runtime | python-build-standalone (Astral), `install_only_stripped`, aarch64-apple-darwin | PSF + bundled libs | Download pinned release, verify SHA256, copy into `Resources/python` |
| jellyfish | PyPI wheel, macOS arm64 | MIT | `pip install --target Resources/site-packages` with the bundled Python |
| whisper.cpp | github.com/ggml-org/whisper.cpp, pinned tag | MIT | Build from source with CMake, Metal on, static ggml if possible (issue #4) |
| parakeet-cli | same tree as whisper.cpp | MIT | Same build |
| ggml-tiny, large-v3-turbo | huggingface.co/ggerganov/whisper.cpp | MIT | Downloaded on first launch, as `install.sh` does now |
| parakeet-tdt-0.6b-v3 q8_0 | huggingface.co/ggml-org/parakeet-GGUF | CC-BY-4.0 (NVIDIA) | Downloaded on first launch. Needs an attribution line in About |
| Swift helpers | `native/*.swift` | this repo | `swiftc` at build time on the maintainer's Mac, not the user's |
| Update framework (optional) | Sparkle 2 | MIT | Swift Package Manager in the app target |
| DMG layout (optional) | `create-dmg` or plain `hdiutil` | MIT | Build script |
| Local LLM for recap (optional) | llama.cpp `llama-server` + a small instruct model | MIT + model licence | Not bundled. Recap keeps working without it, as today |

Not needed any more on the user's side: Homebrew, Xcode command line tools,
`pip`, `git`, `curl`.

---

## Code changes

The Python package keeps working from the repo exactly as now. The app adds
a second mode, "running from a bundle", detected once in `core.py`:

```python
BUNDLE = os.environ.get("DICTATOR_BUNDLE")  # set by the app before it starts Python
```

| File | Change |
|---|---|
| `core.py` | Add `BUNDLE`. When set, helper paths (today `core.STATE_DIR / "bin" / dictator-*`) point into `Contents/Helpers` |
| `swiftbuild.py` | In bundle mode, never compile. Use the prebuilt helper or report it missing |
| `stt.py` | `_find()` looks in `Contents/Helpers` first, then PATH, then Homebrew |
| `always.py` | The login item points at `/Applications/Dictator.app`, not a built copy under `~/.dictator` |
| `signing.py` | In bundle mode, skip local signing. The app is already signed with the release certificate |
| `tcc.py` | Same checks, the bundle id is now fixed by the release |
| `native/app/main.swift` | Becomes the SwiftUI app (below). Starts `Resources/python/bin/python3 Resources/bin/dictator dictate fn` instead of `/usr/bin/env python3 <cli>`, and sets `PYTHONPATH` and `DICTATOR_BUNDLE` |
| `bin/dictator doctor` | Reports "app bundle" or "repo install", and which helpers came from where |
| new `tools/build_dmg.sh` | Builds everything below, end to end |

`install.sh` and `get.sh` stay. They remain the route for people who want the
source, and for the maintainer.

---

## UX and UI

### Principle

The app is invisible while it works. The product is still: hold fn, talk,
the words land at the cursor. The UI exists for three moments only: the first
five minutes, changing a setting, and something going wrong. Every screen
below maps to an existing CLI command, so nothing is a new feature, only a
new place to reach it.

### The journey, from download to first sentence

1. **Download page.** One button, "Download for Mac (Apple silicon), 38 MB".
   Under it, two screenshots, labelled: the warning, and the Open Anyway
   button in Privacy & Security. One sentence on why: "Dictator is free and
   not paid into Apple's developer programme, so macOS asks you to approve it
   once."
2. **Open the .dmg, drag Dictator to Applications.**
3. **Open Dictator.** macOS blocks it. The user goes to System Settings,
   Privacy & Security, Open Anyway. (Measured on 27.0.1.)
4. **Welcome window** (onboarding, below). The only full window the app shows
   unless asked.
5. **Menu bar icon appears.** The orb appears under the notch while talking,
   as now.

### Onboarding window, four steps

One window, 520 x 420, one step at a time, a Continue button that only
enables when the step is actually done. The app checks the real state, not
whether a button was clicked, the same way `doctor` does.

```
┌─────────────────────────────────────────────┐
│  ●○○○                                       │
│                                             │
│  Dictator needs your microphone             │
│                                             │
│  It records only while you hold the key.    │
│  Audio never leaves this Mac.               │
│                                             │
│            [ Allow microphone ]             │
│                                             │
│                              [ Continue → ] │
└─────────────────────────────────────────────┘
```

| Step | Asks for | Done when | Maps to |
|---|---|---|---|
| 1 Microphone | System mic prompt | `AVCaptureDevice` status is authorized | `askForMicrophone` in `main.swift` |
| 2 Accessibility | System prompt, then a button that opens the right pane | `AXIsProcessTrusted()` is true | `askForAccessibility`, `tcc.py` |
| 3 Speech models | Nothing. Shows the English download with a progress bar, Hinglish continues in the background | `stt.missing(essential_only=True)` is empty | `install.sh` step 4 |
| 4 Try it | "Hold fn and say: testing one two three." A text box on the window receives it | Text appears in the box | `dictate` |

If step 2 hits the stale-entry trap described in the README (switch on, app
not trusted), the step says so in one sentence and offers the fix `doctor`
already knows (`forget`).

### Menu bar

A small monochrome icon. It is the app's only permanent surface.

```
  Dictator                     ● Ready
  ─────────────────────────────
  Hold fn to talk
  Language            Auto  ▸   (Auto · English · Hinglish)
  ─────────────────────────────
  Today's recap…                 (recap)
  History…                       (history, search)
  ─────────────────────────────
  Hinglish model     downloading 41%
  ─────────────────────────────
  Settings…                ⌘,
  Check for updates…
  Pause dictation                (off / on)
  Quit Dictator
```

The status dot is the same truth as `doctor`: Ready, Paused, Needs permission,
Downloading model, or an error in one line that opens the fix.

### Settings window, five tabs

| Tab | Contains | Maps to |
|---|---|---|
| General | Hold key (fn, right ⌘, right ⌥, left ⌘), start at login, show orb | `KEYS` in `bin/dictator`, `on`/`off`, `always.py` |
| Words | Learned words and corrections, add and remove | `learn`, `unlearn`, `words` |
| Snippets | Phrases you say often and what they expand to | `snippet` |
| Apps | Per-application rules | `profiles.py`, `format` |
| Privacy | Where history lives, delete today / all, review what it got wrong | `history`, `forget`, `review` |

And an About pane with the version, the model credits (the parakeet
CC-BY-4.0 attribution goes here), and a "Run diagnostics" button that shows
`doctor` output.

### What stays as it is

- The orb under the notch, and its rule: visible if and only if our
  microphone is open.
- The CLI. The app offers "Install command line tool" in Settings, which
  links `dictator` into `~/.local/bin` without asking for an admin password.
- Meetings and readback, reached from the menu once they are stable.

---

## Build, sign, package

All of it in `tools/build_dmg.sh`, run on the maintainer's Mac. Order matters
for signing: the innermost code first, the app last.

1. **Fetch and verify sources.** Python runtime and whisper.cpp at pinned
   versions, checked against stored SHA256 sums.
2. **Build whisper.cpp** with CMake, `-DGGML_METAL=ON`, static if issue #4's
   static build works, otherwise copy the dylibs into `Frameworks/` and
   rewrite their paths with `install_name_tool` to `@rpath`.
3. **Build the Swift helpers and the app** with `swiftc` (or an Xcode project
   once the SwiftUI app grows), arm64.
4. **Assemble the bundle** in the layout above. Copy `dictator/`, install
   jellyfish into `site-packages` with the bundled Python, remove `__pycache__`,
   tests and unused stdlib modules.
5. **Sign inside out** with the release certificate:
   ```
   codesign --force -s "Dictator Release" Contents/Frameworks/*.dylib
   codesign --force -s "Dictator Release" Contents/Helpers/*
   codesign --force -s "Dictator Release" Contents/Resources/python/bin/python3 \
       $(find Contents/Resources -name '*.so' -o -name '*.dylib')
   codesign --force -s "Dictator Release" Dictator.app
   codesign --verify --deep --strict Dictator.app
   ```
   Not `--deep` for signing: it signs in the wrong order and is deprecated for
   that use. Only for verifying.
6. **Make the .dmg:**
   ```
   hdiutil create -volname Dictator -srcfolder dmgsrc -format UDZO Dictator-1.0.0.dmg
   ```
   (`hdiutil create` printed a deprecation warning on 27.0.1 pointing to
   `diskutil image create`. It still works. Switch when it stops.)
7. **Checksum** and upload to GitHub Releases with the SHA256 in the notes.

### The release certificate

Created once, kept safe, used for every release. If it is lost, the next
release has a new identity and every user's Microphone and Accessibility
grants stop applying, which is the bug `signing.py` exists to prevent.

- Created with Keychain Access, Certificate Assistant, Create a Certificate,
  type Code Signing. Free.
- Backed up as an encrypted `.p12` outside the repo.
- Never committed. Never on CI unless CI has a secret store.

---

## Updates

Two options, cheapest first:

1. **Manual.** The app checks the GitHub Releases API on launch, at most once
   a day, and says "Version 1.1 is available" in the menu. The user downloads
   the new `.dmg`. Each download is quarantined, so Open Anyway is probably
   needed again for every version. Not tested.
2. **Sparkle 2.** Free and works with EdDSA signatures and no Developer ID.
   Whether an update Sparkle installs needs Open Anyway again is not known.
   If it does not, this is the better path. Test before choosing.

Either way the release certificate stays the same, so permissions survive.

---

## Tests before the first release

Run on a separate user account on the same Mac, which starts with no grants
and no `~/.dictator`, and ideally on a second Mac.

- [ ] Download from the real GitHub release in Safari and in Chrome, not a
      local copy, so quarantine is real.
- [ ] Open Anyway appears and works. Screenshot it for the download page.
- [ ] After a Finder drag to `/Applications`, the process does not run from
      an `AppTranslocation` path (it did for the probe, which was not moved
      by Finder).
- [ ] Microphone and Accessibility prompts name "Dictator" and the grants
      work.
- [ ] fn dictation pastes into Terminal, Safari, Slack, Notes.
- [ ] English works before the Hinglish model lands, Hinglish after.
- [ ] Login item starts the app after a reboot.
- [ ] Install 1.0, then 1.1 over it: permissions still work, Open Anyway asked
      again or not (record which).
- [ ] `doctor` from the bundled CLI reports "app bundle" and no missing parts.
- [ ] An existing repo install and the app on the same Mac do not fight over
      the hotkey or the models.

---

## Phases

| Phase | Output | Rough size |
|---|---|---|
| 1 Bundle mode | Python runs from `Resources/`, helpers prebuilt, `doctor` knows the mode. Ad-hoc `.dmg` that dictates. No new UI yet | about a week |
| 2 Signing and release | Release certificate, `build_dmg.sh`, first GitHub release to testers | 2 to 3 days |
| 3 Onboarding | The four-step window | about a week |
| 4 Menu bar and settings | Menu, five tabs, CLI installer | 1 to 2 weeks |
| 5 Updates | Manual check, then Sparkle if it passes the test | 2 to 3 days |

Estimates, for one person, not measured.

---

## Open questions

- **Intel Macs.** A universal build roughly doubles the binaries. Worth it
  only if testers ask.
- **Open Anyway on every update**, and whether Sparkle avoids it.
- **Whether an app approved with Open Anyway** gets normal Microphone and
  Accessibility behaviour. The probe asked for neither.
- **Whether this holds on the next macOS.** The published result on 26.6.1
  disagreed with the measurement on 27.0.1. Retest on every major release.
- **Model hosting.** Hugging Face URLs are third-party. Mirroring them in a
  GitHub release would need splitting large-v3-turbo under 2 GiB, which it
  already is (1,549 MB), so it is possible.
