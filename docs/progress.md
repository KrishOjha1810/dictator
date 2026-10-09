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
      inside the .dmg") (2026-10-08, `7737ede`; the meeting
      helper keeps the repo's name, `Dictator Meeting.app`)
- [x] Environment: `DICTATOR_BUNDLE`, `PYTHONPATH` (2026-10-08, `7737ede`;
      bundled Python imports dictator and jellyfish with only these set)
- [x] `~/.dictator/status.json` fields: state, model progress, last error
      (2026-10-08, `a9c9b37`, tests only; not yet seen written by a running
      app). Each model now also carries `"essential": true|false`, added
      after review so onboarding waits only for the English models; an
      additive change, and the app falls back to the file name without it
- [x] `--json` output for the commands the UI reads (2026-10-08, `a9c9b37`;
      `stats --json` run from the bundle, the others by test)

---

## M1: Working .dmg

### Lane A: Runtime

- [x] Fetch standalone Python (pinned version, SHA256 checked) (2026-10-08,
      `4518884`; CPython 3.12.14, python-build-standalone 20260924)
- [x] jellyfish installed into the bundle's `site-packages` (2026-10-08,
      `4518884`)
- [x] `core.BUNDLE`, and helper paths point into `Contents/Helpers`
      (2026-10-08, `a9c9b37`; doctor from the bundle lists all nine helpers as
      "app bundle")
- [x] `swiftbuild.py`: never compiles in bundle mode (2026-10-08, `a9c9b37`; a
      blocking swiftc shim was never reached)
- [x] `stt.py`: finds bundled whisper and parakeet first (2026-10-08,
      `a9c9b37`)
- [ ] `always.py`: login item points at `/Applications/Dictator.app`
      (2026-10-08: written and tested against a fake bundle, never installed)
- [x] `signing.py`: skips local signing in bundle mode (2026-10-08, `a9c9b37`,
      tests)
- [x] `doctor` reports "app bundle" or "repo install" (2026-10-08, `a9c9b37`)
- [x] Tests for bundle mode pass, existing tests still pass (2026-10-08,
      `7737ede`; 665 passed, 17 failed, 6 skipped, the 17 the same jellyfish
      and test_standalone failures as the baseline. After the review fixes:
      673 passed, 16 failed, 6 skipped; the 16 are the jellyfish ones, the
      test_standalone failure is fixed)

- [x] Models downloaded on first launch in bundle mode, English first, each
      checked against Hugging Face's SHA256 and size (2026-10-08, `e13cd35`)

### Lane B: Native

- [x] Swift helpers built ahead of time: hotkey, rec, paste, orb, readback
      (2026-10-08, `11ebfc3`)
- [x] Meeting.app built ahead of time (2026-10-08, `11ebfc3`; as `Dictator
      Meeting.app`, identifier `com.dictator.meeting`, not per account)
- [x] whisper.cpp built from source, pinned tag, Metal on (2026-10-08,
      `11ebfc3`; v1.9.1, commit checked; Metal transcription seen by lane B,
      not rerun here)
- [x] parakeet-cli built from the same tree (2026-10-08, `11ebfc3`; `--help`
      only, no parakeet transcription yet)
- [x] Static ggml, or dylibs in `Frameworks/` with `@rpath` fixed (2026-10-08,
      `11ebfc3`; static, `Frameworks/` empty, `otool -L` clean on all 14
      Mach-O files)

### Lane D: Pipeline

- [ ] `tools/build_dmg.sh` runs end to end on a clean checkout
      (2026-10-08: runs end to end in 59 s on this tree, with the Python
      tarball and whisper.cpp clone cached; not yet from a clean checkout)
- [x] Signs inside out, `codesign --verify --deep --strict` passes
      (2026-10-08, `7737ede`; still valid after running the bundled CLI)
- [x] Produces `Dictator-<version>.dmg` with an Applications link (2026-10-08,
      `7737ede`; `hdiutil verify` passes, mounted read-only, app inside
      verifies)
- [x] SHA256 printed for the release notes (2026-10-08, `7737ede`)
- [x] Measured app size and .dmg size recorded below (2026-10-08, `7737ede`)

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

- [x] "Dictator Release" certificate created (2026-10-08, `tools/release_cert.sh`;
      identity `40C4B74C…`, keychain in `~/.dictator-release`)
- [x] Exported as a password-protected `.p12` outside the repo
      (`~/.dictator-release/release.p12`). Still to do: a second copy somewhere
      that is not this Mac

---

## M2: The app

### Lane C: UI

Code for everything below except the bar is in `75662ed` and compiles with
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
| App installed size | 51.2 MB (python 37.4, helpers 10.0, dictator 1.7, site-packages 0.8, Frameworks 0) | 2026-10-08, v0.1.0, release-signed |
| .dmg size | 24.1 MB (25,295,165 bytes, UDZO zlib-9) | 2026-10-08, v0.1.0, release-signed |
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
- 2026-10-08: The test suite leaves a temporary signing keychain on the
  user's keychain search list on every run (about 20 found on this Mac).
  Pre-existing, from the signing identity test; not fixed yet.

---

## Round 2: the first real install (2026-10-09)

Found by installing v0.1.0 on this Mac and using it. Each line says what was
seen and where, then the fix. Done in this order.

### Bugs

- [x] App never started: the app delegate was a local, released straight
      after assignment under -O, so no menu bar item, no onboarding, no
      dictation, and no error anywhere. Fixed in `main.swift`.
- [x] Windows opened on another Space behind a full-screen app. Fixed with
      `collectionBehavior` in `MenuBar.swift`.
- [x] "Try it" card stays empty: it waits for the text to be pasted into its
      own box, but the paste went to "the front app" with nothing focused
      (history: app empty, saw "gone"). Fix: the loop writes the last result
      into last.json and the card shows it directly, with "Listening…" until
      a hold newer than the card arrives, and the time-to-paste.
- [x] Hinglish model downloaded five times: each key press on the "Your key"
      card restarted the dictation loop, which killed the download thread
      (log: five "downloading ggml-large-v3-turbo.bin" in three seconds).
      Fix: one key change on Continue only, and downloads that resume.
- [ ] Wrong message while the Hinglish model was still arriving: "Speech
      recognition isn't set up. Run setup on the Mac." Fix: say it is still
      downloading, and use the English result meanwhile.
- [ ] Repeated sentence pasted four times ("Yar ye test karke dekho" x4):
      the loop guard noticed and still pasted it. Fix: collapse repeats
      before pasting.
- [x] No Dock icon, so no normal way to quit or force quit. Fix: a regular
      app with a Dock icon and an app menu with Quit, an app icon
      (`tools/make_icon.swift`), and a "Show in Dock" setting. Closing the
      windows leaves it running.
- [x] Opening the copy inside the .dmg: no warning, killed by Gatekeeper
      after 8 seconds (log: "Security policy would not allow process").
      Fix: the app notices it runs from a disk image or a translocated path
      and offers to move itself to Applications; README says so too.
- [x] Fake mode reads sample data from the maintainer's Desktop path built
      into the binary, so macOS asked for Desktop access. Fix: fixtures ship
      inside the app; no source path in a release build.

### Latency

- [ ] Measured: the bundled engines match Homebrew's (turbo 3.9s vs 3.8s,
      parakeet 0.53s vs 0.54s on the same 6s clip), so the build is not it.
      The route is: Hinglish speech goes to parakeet first, is rejected, then
      a language check, then turbo started cold from disk (1.6 GB) for every
      sentence, and a repeat triggers a second full run. Fix: record time
      from key release to paste for every utterance, then keep the
      multilingual model loaded when it is measured to help, and skip the
      parakeet attempt when the setting is Hinglish.

### Accuracy, from the message dictated in this round

- [ ] Immediate repeats left in: "is is", "I I", "the check the". Fix:
      remove stutters before pasting.
- [ ] Mixed English and Hinglish in one long hold goes to the English engine
      and the Hindi part is anglicised ("test vala text jo hai" came out as
      "test while our text view"). Larger problem, tracked separately.
- [ ] Names and slang: "Bro" as "Brooke", "bugs" as "books", "Wispr Flow"
      as "whisper flow". The Words page can teach these; check it works.

### Redesign: light, Wispr Flow as the reference

- [x] Light theme throughout: onboarding, Hub, Settings (`Theme.swift`)
- [x] Hub like Wispr Flow's: sidebar with icons, Home with stats and history
      by day with copy, Words, Snippets, Style per app
- [x] Onboarding redesigned, with the Try it card showing the live result
- [x] The bar: a pill with a live waveform, keeping "visible only when our
      microphone is open". Done in Round 3: the waveform look is still drawn
      only when our microphone is open; an idle pill is now shown between
      holds.
- [ ] Better than the reference: time-to-paste shown per sentence, a local
      only badge, a Hinglish switch, and fixing a word in history teaches it.
      Done: the badge, the Hinglish question in onboarding, and time-to-paste
      on Home and on the row of the last sentence. Left: time-to-paste for
      every row needs `history.py` to store it; fixing a word in history.

### Then

- [ ] Rebuild as 0.1.2, install on this Mac, test, then release

---

## Round 3: the indicator, and two apps on one key (2026-10-09)

### The indicator becomes a movable pill, like Wispr Flow's Flow Bar

- [x] Always on screen while dictation runs: a small, faint grey pill when
      idle (no waveform, no animation), a dark pill with moving bars while
      listening, three pulsing dots while the words are worked out
      (`native/orb.swift`).
- [x] Listening is still drawn if and only if our microphone is open
      (CoreAudio presence AND the mic.lock flock; hud.json only sets how
      loud). When our mic is hot the look is listening whatever hud.json
      says, so the idle pill can never stand in for listening. The header
      comment says what the idle pill does and does not mean.
- [x] Drag to move. While dragging, the eight places on the screen under the
      pointer show as translucent slots, the nearest highlighted; on release
      it snaps there in 0.18 s. Top centre (default, under the notch or menu
      bar), bottom centre (above the Dock), left and right edge centres, four
      corners, all inside the visible frame. Multiple displays: the slots
      follow the pointer's screen.
- [x] Never takes focus: a non-activating panel the size of the pill that
      never becomes key; the slot overlay ignores the mouse.
- [x] Kept in `indicator.json` in the state directory
      (`{"position", "hide_idle"}`), read on start and watched, so a change
      moves the running pill. Restored on the focused screen at launch.
- [x] `dictator indicator [position P | hide-idle on|off] [--json]`, and in
      the app, Settings > General: "Indicator position" (eight places) and
      "Hide when not dictating" (default off, which is the old behaviour).
- [x] The helper is given `DICTATOR_STATE` by `orbnative.py`. It used to read
      a hardcoded ~/.dictator, so a loop pointed elsewhere had an orb
      watching another mic.lock.
- [x] `DICTATOR_ORB_SNAPSHOT=DIR dictator-orb` draws every look and the drop
      targets on a made-up screen into PNGs (build/screens/orb-*.png), with no
      window, no microphone and no state.
- [ ] Not checked by hand yet: a real drag on this Mac, and on two displays.
      The shell has no Screen Recording, and the real app was not touched.

### Two dictation apps on fn

- [x] Wispr Flow also holds fn, so both apps pasted the same dictation. The
      app now looks for known dictation apps (Wispr Flow
      `com.electron.wispr-flow`, read from its Info.plist; Superwhisper,
      MacWhisper, Aqua Voice, Willow by identifier or name) at launch, when
      the menu opens, and when any app starts or quits
      (`native/app/Rivals.swift`).
- [x] While our key is fn: a banner at the top of Home and a line in the menu,
      "Wispr Flow is also running and listens to fn, so both will type. Quit
      it, or change Dictator's key.", with "Quit Wispr Flow" and "Change
      key". Nothing is quit without the click; fake mode never quits.
- [ ] The identifiers for Superwhisper and MacWhisper are from memory, and
      Aqua Voice and Willow match by name only; check them against the real
      apps.

### Then

- [x] Built: `tools/build_native.sh`, `tools/build_app.sh`,
      `tools/build_dmg.sh 0.1.3` (ad-hoc).
- [ ] Install 0.1.3 on this Mac and try the drag and the warning for real.

## Round 4: hover controls, hands free, Notetaker and Scratchpad (2026-10-09)

### The pill disappears when idle and comes back on hover

- [x] Nothing is drawn while nobody is dictating (`idle: "hover"`, the new
      default). The pointer entering a zone 14 pt larger than the stack fades
      it in (0.16 s); leaving it fades out about a second later. The zone is
      checked from `NSEvent.mouseLocation` every 0.1 s, because there is no
      window to hover over. Clicks pass through as soon as it starts fading.
- [x] Listening is still drawn if and only if CoreAudio presence AND the
      mic.lock flock, in every setting; `decide()` is unchanged. hud.json now
      also picks the hands free look, still appearance only.
- [x] "Hide when not dictating" became "When not dictating": Show on hover,
      Always show (the old faint pill), Hide (only while dictating, no
      buttons). An old `hide_idle: true` still means Hide and is still
      written for older readers. `dictator indicator idle hover|always|hide`.
- [x] orb.swift's header says what no pill means now, honestly.

### Orientation

- [x] Top and bottom centre lie flat. The edge centres and all four corners
      stand up: the pill, its buttons, the hands free pill, and the waveform,
      whose bars become flat strokes stacked top to bottom. The drop slots
      are drawn in each place's own orientation, and the pill turns while it
      is dragged across from an edge to the top.

### The buttons

- [x] The pill itself is the Dictate button (a mic on hover): click starts
      hands free dictation, click again finishes and pastes into the app that
      was in front. The panel never takes focus.
- [x] Notetaker (record) and Scratchpad (pencil) stack from the pill toward
      the middle of the screen. Labels slide out to the inside with the
      shortcut in bold. The Notetaker button is red while a meeting records
      (read from meetings/current, its status.json and the recorder's pid).
- [x] Settings > General: which buttons show, and both shortcuts on or off.
      `dictator indicator controls ...` and `dictator indicator shortcut ...`.
- [x] Drag from any part of it, with three points of slack between a click
      and a drag; it snaps to the eight places as before.

### The control channel

- [x] The loop binds a Unix datagram socket at STATE/dictate.sock, guarded by
      an flock on dictate.sock.lock and made owner-only
      (`dictator/control.py`). One datagram is one word: toggle, finish,
      cancel. Nobody bound means the send fails at once. A signal to a pid
      was considered and dropped: after a crash the pid can belong to
      something else, and SIGUSR1's default action kills an older loop.
- [x] The loop does not act on the words itself. It writes TOGGLE, FINISH or
      CANCEL to the key listener's stdin, so a session has one owner (the
      listener, with its cap, lock and tap checks) whether it began with a
      double tap or a click. `dictator hands-free [toggle|finish|cancel]`.
- [x] Checked here: the Swift sender reaches the Python socket, and fails
      once the socket is closed.

### Hands free, like Wispr Flow

- [x] Double-tap the key: two clean taps, the second starting within 350 ms
      of the first ending, each under 300 ms. The second tap's release becomes
      LATCH, so the mic its DOWN opened stays open. A single tap is the short
      DOWN/UP it always was, which the loop discards. A held second press is
      push to talk. Any other key between the taps breaks it.
- [x] One press of the key finishes (transcribe, paste where you were);
      Escape cancels (nothing pasted); the pill's check and cross do the
      same. A press within 0.3 s of the latch is ignored, so a triple tap
      does not stop what it started.
- [x] The cap is the existing one: two minutes, the recorder's MAX_SECS, and
      a session that reaches it is thrown away, as before.
- [x] Hands free pill: a cross at one end, the live waveform, a white check
      at the other; vertical at the side edges and corners (cross on top).
- [x] Tests: the real Swift state machine through `dictator-hotkey --script`
      (double tap latches, one tap is nothing, slow taps are two taps, a hold
      is push to talk, one press finishes, Escape discards, the pill's
      commands), and the loop's side through `dictate.handle()` with the
      lines a listener prints. The Swift self test has 42 scenarios.
- [x] The Globe key: the listener only listens and cannot swallow a tap, so
      macOS still runs its own action on each tap. README (install step 5 and
      Using it), the onboarding key card (with a button to Keyboard settings)
      and Help tell the user to set "Press 🌐 key to" to "Do Nothing".

### Notetaker and Scratchpad in the app

- [x] dictator://notetaker and dictator://scratchpad (CFBundleURLTypes). The
      pill opens them in the copy of the app that holds STATE/app.lock, which
      the app writes its own path into; without the app those two buttons are
      not shown.
- [x] Notetaker runs `dictator meeting start|stop` through the bundled CLI.
      The first time, the app (not the pill) explains that it records other
      people and waits for "Start Recording". `dictator meeting status --json`.
- [x] Scratchpad window: notes list with search, a large text area with the
      cursor in it, autosave 0.8 s after typing stops, on switching notes and
      on close. One Markdown file per note in STATE/notes
      (`dictator/notes.py`, `dictator notes ...`). A Scratchpad page in the Hub
      sidebar lists them: open, copy, delete, search.
- [x] Option-M and Option-S are Carbon hot keys, registered from
      indicator.json's `shortcuts`, unregistered when switched off, and
      checked again when they fire. Fake mode never registers them.

### Checked

- [x] `tools/build_native.sh`, `tools/build_app.sh`, `tools/build_dmg.sh 0.1.4`
      (ad-hoc). The bundled CLI runs `notes`, `indicator`, `hands-free` and
      `meeting status --json` against a scratch state directory.
- [x] pytest: the known 16 failures (jellyfish), the rest pass.
- [x] Snapshots in build/screens/round4-*.png (the pill helper's
      DICTATOR_ORB_SNAPSHOT, and the app's fake mode). Fake-mode snapshot runs
      no longer activate the app or take the keyboard: one earlier run did,
      and a key typed meanwhile landed in its Scratchpad.

### Not done, or not checked by hand

- [ ] No real click on the pill, hover, drag or label on this Mac: the shell
      has no Screen Recording and the running 0.1.3 was not touched.
- [ ] No real double tap, Escape or stdin command through a live listener
      (only through `--script`), and no live hands free session: the mic was
      never opened.
- [ ] No real meeting started, and the consent alert was not seen on screen.
      Option-M and Option-S were not pressed (fake mode does not register them).
- [ ] The dictator:// URL was not opened against a running app.
- [ ] A repo install without the app (no DICTATOR_UI) shows only the dictate
      control on hover; Notetaker and Scratchpad need the app.
- [ ] The Hub's Meetings page is still a placeholder; a stopped meeting's
      notes are only in `dictator meeting show`.

## Round 5: dark mode, a Dictator look, ⌘K, update hooks (2026-10-09)

### The look, from the icon

- [x] Direction: the icon says "voice becomes text" (a microphone whose grille
      is lines of text, indigo to violet to teal, a glowing teal cursor). So
      indigo ink and violet are the brand, violet is the one accent for
      controls and selection, and teal means live (the cursor, the status
      line, time saved, "listening"). The full gradient is kept for three
      brand moments: the mark, the Home hero, the onboarding welcome.
- [x] Type: SF Pro Rounded for page titles, the hero and stats; SF Pro for
      body text. Every stroke in the icon has a round cap, and the rounded
      face keeps the app away from the serif display other dictation apps use.
- [x] The brand mark is drawn in SwiftUI (`BrandMark`), so a bare build
      without the icon file shows it too (it used to show a folder icon).
- [x] Sidebar: an ink rail in both appearances, with the mark, a "Search or
      jump ⌘K" field, pages grouped (Home; Teach: Words, Snippets, Style;
      Keep: Scratchpad, Meetings, Review), and the selected page marked by a
      teal cursor bar. Footer: status line and "Local only, on this Mac".
- [x] Home is a today view: a gradient hero with the greeting, the key, today's
      words, the last time to paste, and time saved today against typing at
      40 words a minute; then words all time, time saved all time, words a
      minute, day streak; the privacy promise; history rows tagged English or
      Hinglish (from `lang`, else the engine), with seconds spoken and time to
      paste where known.
- [x] The privacy promise is a designed card ("Everything stays on this Mac",
      the state directory, "Speech to text, offline", "Nothing uploaded") on
      Home and at the top of Settings > Privacy.
- [x] Empty states are drawn from the icon's motif (`LinesArt`: lines of text
      in the violet-to-teal ink, the teal cursor; a mic for Meetings and an
      empty history), not stock symbols.
- [x] Onboarding: the welcome card is the gradient, full bleed, with the mark;
      the other cards have gradient symbol tiles and a progress row where the
      current step is teal. The "Try it" listening dot is teal.
- [x] Capsule buttons, a brand switch (`BrandSwitch`, violet track) and a brand
      progress bar replace AppKit's, which drew grey whenever the window was
      not in front.
- [x] Scratchpad window: the mark in its header, a teal insertion point,
      colours that follow the appearance.

### ⌘K

- [x] A command palette over the Hub (`native/app/Palette.swift`): ⌘K in the
      Window menu, or the field in the rail. Go to any page; New note;
      dictate hands free into a new note (`dictator hands-free toggle`);
      Notetaker; pause or resume; copy the last thing said; check for updates;
      switch appearance; turn any style rule on or off (`dictator format`).
      Typing two letters or more also searches history (copy), notes (open)
      and words (open Words filtered). ↑↓, Return, Escape.

### Dark mode

- [x] Settings > Appearance: System, Light, Dark (default System), drawn as
      three small window thumbnails. Kept in UserDefaults (`appearance`) and
      applied at once with NSApp.appearance; the forced aqua on the app and
      on every window is gone.
- [x] Every colour in Theme.swift is a light/dark pair
      (NSColor(name:dynamicProvider:)). Dark is designed, not inverted: ink
      background #121124, cards #1B1A31, raised #25233F, borders 10% white,
      hairlines 6% white, violet lightened to #B3A2FF for text and #6E4FF0
      for fills, teal #3FE0CF. Body text contrast is 15:1, secondary about
      7.6:1 and tertiary about 4.7:1 in dark (15, 6.4, 4.6 in light).
- [x] The orb's hover labels were not changed: a 92% black fill, white text
      and a light rim read on light and dark wallpapers alike.

### Updates (hooks only)

- [x] "Check for Updates…" after About in the app menu, and Settings >
      Updates: the version, "Check now", "Automatically check for updates".
      Both call `Updater.shared`. `native/app/UpdaterStub.swift` has the same
      API and does nothing (it logs); delete it when Updater.swift lands.

### Time saved

- [x] `dictator stats --json` also prints `saved_secs`, `today_words` and
      `today_saved_secs` (dictator/views.py): per timed row, the time to type
      its words at 40 a minute minus the seconds spent saying them; never
      below zero; null without a timed row. Tests in tests/test_bundle.py.

### Checked

- [x] `tools/build_app.sh build/appbin` with no warnings; `tools/build_dmg.sh
      0.1.5` (ad-hoc) built and verified; the bundled CLI prints the new stats
      keys.
- [x] pytest: 775 passed, 5 skipped, 0 failed with the tree as it is now (the
      16 jellyfish failures no longer show up).
- [x] Snapshots of every screen in light and dark:
      build/screens/round5-<screen>-<light|dark>.png (Hub pages, the full
      Settings and Help pages, the palette empty and searching, the
      Scratchpad window, onboarding cards 0 to 5).
- [x] Snapshot runs can no longer be activated: the activation policy is
      `.prohibited` and their windows cannot become key, so a key typed
      meanwhile goes where the person was typing. (One run before this
      change did become key; nothing was typed into it.) Fake-only helpers:
      DICTATOR_APPEARANCE=light|dark, DICTATOR_PALETTE=<query>,
      DICTATOR_HUB_SIZE=WxH.

### Not done, or not checked by hand

- [ ] Nothing was looked at in the real app with a mouse and keyboard: the ⌘K
      keys, the switches, and switching appearance live were only drawn.
- [ ] The rival banner, the "move to Applications" alert and the Notetaker
      consent alert were not snapshotted (they follow NSApp.appearance).
- [ ] The menu bar menu is the system's and follows the system appearance,
      not the app's setting.
- [ ] Meetings and Review are still placeholders.
