# Other platforms

What it would take to put this on a Mac somebody else owns, on Windows, and on
a phone. Same rule as `findings.md`: measured here where it could be measured,
and where a number came from somebody else it says whose and when. Where a
source is a forum post or a vendor's own marketing it says so, because this
area moves and a 2023 answer is often wrong now.

Three of the four answers are no, and they are no for three different reasons,
so they are written separately rather than summarised together.

One constraint decides most of this. **No audio leaves the machine, ever.**
Anything below that would need a server is named as a different product rather
than quietly offered.

The short version:

| | Possible | Cost | What it gives up |
|---|---|---|---|
| macOS, double-clickable | **Only with $99/year** | $99/year plus 2 to 4 days of first-time work | Nothing. It is the same product, installed properly |
| macOS, `.dmg` with one Open Anyway step (added 8 October 2026) | **Yes, free** | Nothing in money. The same bundling work as the row above, minus notarization | A warning on first open, and one trip to Privacy & Security to approve it |
| Windows | **Yes** | about 11 weeks, plus a code signing certificate, and Microsoft's cheap route is closed to India | The gesture, elevated windows, 2 to 3 times the latency, and the readback |
| iOS | **No, and a server would not fix it** | n/a | n/a |
| Android | **Yes, mechanically** | 8 to 10 weeks for English, 16 to 22 for parity | Hinglish, which is the reason the product exists |

---

## macOS, without the 99 dollars

> **Update, 8 October 2026.** The central claim of this section was retested
> on macOS 27.0.1 and did not hold. A quarantined, ad-hoc signed app copied out
> of a `.dmg` is blocked on first open, but Privacy & Security then offers
> **Open Anyway**, and after one approval it opens normally every time. So a
> free `.dmg` is possible, with a warning on first open. The test and its
> limits are in "Retested 8 October 2026" below. Everything else in this
> section is the original text, kept as written so the earlier reasoning stays
> visible; where a sentence is now wrong, the update says so rather than
> deleting it.

**It cannot be a double-clickable app without the 99 dollars.** Not as a
`.dmg`, not as a `.zip`, not as a `.pkg`, and, as of November 2025, not as a
Homebrew cask either. That last one closed while nobody was looking and is the
new fact in this section.

### What Gatekeeper does to a self-signed app, measured here

macOS 26.5.1, Apple silicon, Gatekeeper at its default setting (`spctl
--status` reports `assessments enabled` and `developer id enabled`).

A throwaway `.app` was built in a scratch directory, ad-hoc signed, zipped,
given the quarantine attribute a browser download writes, and extracted again:

```
$ xattr -l out/Probe.app
com.apple.quarantine: 0083;6ac52f8f;Safari;
```

First measured fact: **quarantine propagates through a zip.** Shipping a `.zip`
instead of a `.dmg` does not avoid it.

Apple's own pre-distribution checker, on that bundle:

```
$ syspolicy_check distribution out/Probe.app
Adhoc Signed App
    Severity: Warning
    This app is adhoc signed. While it may run locally, adhoc signed apps are
    not suitable for distribution.
Notary Ticket Missing
    Severity: Fatal
    A Notarization ticket is not stapled to this application.
```

`Fatal`, from Apple's tool, on this machine, today. (An Apple DTS engineer has
said in the developer forums that `Fatal` overstates that line and a bug is
filed about the wording. It overstates it for an app that is otherwise
correctly signed with a Developer ID. It does not overstate it for an ad-hoc
one.)

A `.pkg` does not change the picture:

```
$ spctl -a -vvv -t install probe.pkg
probe.pkg: rejected
source=no usable signature
```

A signed installer package needs a **Developer ID Installer** certificate,
which is the same 99 dollars.

### The escape hatch a normal person is offered is Move to Trash

The authoritative current test is Howard Oakley's, run on macOS 26.6.1 and
published 11 August 2026. His results, for the signing states that matter:

| Code | Quarantined | Default settings | Anywhere enabled |
|---|---|---|---|
| Unsigned | yes | blocked | blocked |
| Ad-hoc signed | yes | **trash prompt** | warning dialog, user can approve |
| Ad-hoc signed | no | runs normally | runs normally |

Read the second row again. On a Mac at its factory setting, a self-signed
Dictator downloaded from a release page does **not** offer Open Anyway. It
offers to move itself to the Trash. There is no button for the user to press
that gets them out of it.

*(Update, 8 October 2026: not reproduced. On macOS 27.0.1 at default settings
the same kind of app was blocked, and Privacy & Security then showed Open
Anyway next to it. See "Retested 8 October 2026" below.)*

"Anywhere" is the only setting under which they could approve it, and
"Anywhere" is not in System Settings any more. It is `sudo spctl
--master-disable` in a terminal, which is a worse thing to ask of somebody than
the install command they are already being asked to paste, and it weakens every
other app on their machine permanently.

### The third row is why the product works today

Ad-hoc signed and **not** quarantined runs normally. That is exactly what
`scripts/install.sh` produces: `curl` and `git` do not set the quarantine attribute, so
the app the installer builds and signs on the user's own machine is never
quarantined and never assessed. The install path that exists is not a
workaround. It is the only path Gatekeeper leaves open for free.

Which reduces the whole problem to one question: can the **installer** be
delivered without a terminal? Measured here, same machine, same script, twice:

```
$ xattr -w com.apple.quarantine "0083;...;Safari;" Install.command
$ open Install.command
_LSOpenURLsWithCompletionHandler() failed with error -128
open exit=1

$ xattr -c Control-no-quarantine.command
$ open Control-no-quarantine.command
open exit=0        # Terminal opens, the script runs
```

Identical file. The quarantine attribute is the whole difference, and -128 is
`userCanceledErr`, which the user never cancelled. So a double-clickable
`Install.command` on a download page is blocked too.

### xattr -d still works, and it is not the win it sounds like

```
$ xattr -d -r com.apple.quarantine Probe.app
$ echo $?
0
```

No sudo, no prompt, works today on 26.5.1. The folk remedy is still real. It is
also still a terminal command, which is the thing being removed, and Howard
Oakley argues against it on the merits: "You shouldn't remove the quarantine
xattr anyway: if that code hasn't been run on that Mac before it does need to be
checked as well as possible."

Walking a non-technical person through
`xattr -dr com.apple.quarantine /Applications/Dictator.app` is strictly worse
than walking them through the install command we already have, because it
teaches them that this is a thing you do to apps macOS refuses.

### Retested 8 October 2026: Open Anyway is there

*(Added 8 October 2026. The sections above are the original text.)*

The trash prompt above came from a published test and was listed at the end of
this document as not reproduced here. It has now been reproduced, and the
result is the opposite.

macOS 27.0.1 (26A434), Apple silicon, `spctl --status` reporting
`assessments enabled`. A throwaway `GKProbe.app` (one Swift file that shows a
window saying it launched) was built in a scratch directory, ad-hoc signed,
packed into a `.dmg` with an Applications link, and given the quarantine
attribute a browser download writes:

```
$ codesign --force --deep -s - GKProbe.app
Signature=adhoc
TeamIdentifier=not set
$ hdiutil create -volname GKProbe -srcfolder dmgsrc -format UDZO GKProbe.dmg
$ xattr -w com.apple.quarantine "0083;...;Chrome;" GKProbe.dmg
```

The `.dmg` was mounted and the app copied out, the way a drag to Applications
would. Quarantine travels with it, and Gatekeeper rejects it:

```
$ xattr -p com.apple.quarantine GKProbe.app
0083;00000000;;
$ spctl -a -vvv -t exec GKProbe.app
GKProbe.app: rejected
```

Then it was opened, and what happened on screen, in order:

1. A warning that it could not be verified. The app did not run.
2. **System Settings → Privacy & Security** showed GKProbe as blocked, with an
   **Open Anyway** button.
3. Open Anyway, confirmed, and the app ran.
4. A second `open` with no prompt at all: the process was running three
   seconds later.

`spctl` still says `rejected` after the approval, and the quarantine flag is
unchanged. The approval is stored by the system as an exception for that app,
not by removing the flag.

What this changes: **a free `.dmg` is a real install path.** It is not a
terminal command and not a bypass. It is the approval flow Apple built into
System Settings, and the user goes through it once.

What this test did not cover, and which the real app has to be checked for
before anyone is pointed at it:

- **App Translocation.** On the second launch the process ran from a random
  path under `/private/var/folders/.../AppTranslocation/`, because the copy had
  not been moved by Finder. A user dragging the app into `/Applications` in
  Finder should not get this, but anything in Dictator that finds files next to
  its own bundle must be checked against it.
- **Permissions on an app that was approved this way.** The probe asked for
  nothing. Dictator needs Microphone and Accessibility. Whether those prompts
  and grants behave normally on an app approved with Open Anyway is untested.
- **Updates.** Whether Open Anyway has to be clicked again for every new
  version. Likely yes, since each download is a new quarantined copy.
- **Signature stability across updates.** An ad-hoc signature changes with
  every build, which is the permissions bug `signing.py` exists to fix. A
  `.dmg` built for other people would need one self-signed certificate kept by
  whoever builds releases and used for every release, so the designated
  requirement names the certificate and not the binary. Free, and untested
  across two releases.
- **Why this differs from the published result.** Either macOS changed between
  26.6.1 and 27.0.1, or the published table describes only the first dialog.
  Not known. It should be retested on each new major macOS before relying on
  it.

### The Homebrew cask route closed in November 2025

This was listed as an open option in issue #6 and in the Distribution section
of `findings.md`. It is not an option any more.

Homebrew 5.0.0, released 12 November 2025, from its own announcement:

> `--no-quarantine` and `--quarantine` flags have been deprecated as Homebrew
> does not wish to easily provide circumvention to macOS security features.

> Casks without codesigning are deprecated. We will disable all
> Homebrew/homebrew-cask casks that fail Gatekeeper checks in September 2026.

That date has passed. Checked on this machine:

```
$ brew --version
Homebrew 7.0.6
$ brew install --cask --help | grep -i quarantine
(nothing)
```

The flag is gone. The current Acceptable Casks policy says an app must "pass
Homebrew's Gatekeeper checks and must not require System Integrity Protection
or Gatekeeper to be disabled or bypassed."

So a cask of a self-signed Dictator would be rejected on submission, and a
third-party tap would install an app the user's Mac then refuses, which is
worse than not shipping it.

The competitor that proves the point: **VoiceInk**, the closest open-source
local-only Mac dictation tool, is still in `homebrew/cask` today
(`brew info --cask voiceink` reports version 2.21 and 8,421 installs in the
last year), which means it is signed and notarized. It is GPL and it charges
$39.99. Even free software in this exact category has paid the toll, and
recovers it in three sales.

### What the 99 dollars actually buys

From Apple's own membership comparison, a free Apple Developer account gets
beta software, on-device testing, the forums, and a Personal Team with 7-day
provisioning profiles. **Notarization is listed only under the paid
membership.** There is no Developer ID certificate without it. The price on
Apple's own page is "$99 annual membership".

For this product it buys four things, and the fourth is not obvious:

1. A **Developer ID Application** certificate, so the app is signed with an
   identity other Macs recognise.
2. **Notarization**, which is what lifts the quarantine block. The notary
   service itself is fast: a public analysis of 108 submissions put the median
   turnaround at 2 minutes and the worst case at 24.
3. A **Developer ID Installer** certificate, if a `.pkg` is ever wanted.
4. **A stable TCC identity across releases.** This is the one worth saying out
   loud, because issue #2 is an entire open bug about it. The Accessibility
   grant is written against a code requirement, and today that requirement
   names a certificate generated on one machine. A Developer ID certificate is
   the same certificate for every build and every user, so the grant stays
   valid across updates and the "the tick is on and it does not work" trap
   stops being a thing the product has to detect and explain.

### How long notarization takes to set up, honestly

Not two minutes. The per-release run is two minutes. Getting to the first
successful run is the work, and for this codebase it is more than usual:

- Enrolling and being approved: hours to a couple of days. Apple commits to no
  time for an individual.
- **Hardened runtime is required for notarization**, and hardened runtime is
  where a Python application gets expensive. A bundled interpreter loading
  native extension modules needs `com.apple.security.cs.allow-jit` and
  `com.apple.security.cs.allow-unsigned-executable-memory`, and if any
  third-party native code is loaded,
  `com.apple.security.cs.disable-library-validation`. The last is widely
  reported as the fix for "mapped file has no cdhash, completely unsigned"
  crashes under hardened runtime, and it is also the one that makes Gatekeeper
  treat the app more harshly, so it should be removed if it turns out not to be
  needed.
- **Every nested executable must be signed with the same identity and a secure
  timestamp.** For this app that is five Swift helpers plus whichever of
  `whisper-cli` and `parakeet-cli` end up inside the bundle. Which means the
  static whisper.cpp build that issue #4 investigated and deferred stops being
  optional.
- The models are fine. They are data, downloaded on first run, and outside the
  App Store nothing objects. Rule 2.4.5(iv) is an App Store rule and the App
  Store was already ruled out.

Call it **two to four days of work for someone who has never done it**, spread
over a week because of the enrolment wait, then about ten minutes a release.
The money is the smaller problem. The hardened runtime pass over a Python app
with five helper binaries is the bigger one.

### The App Store, rechecked, and it is now three rules not two

`findings.md` records 2.4.5(i) and 2.4.5(iv). Reading the current guidelines
again, **2.4.5(iii) also applies** and is arguably the cleanest refusal of the
three:

> They may not auto-launch or have other code run automatically at startup or
> login without consent nor spawn processes that continue to run without
> consent after a user has quit the app.

A background listener started at login is the product. The verdict does not
change. It is just now overdetermined.

### Is there a free or cheaper route, today

No, and the two that people suggest both fail on a specific clause.

**The fee waiver is real and does not apply.** Apple waives the fee for
nonprofits, accredited educational institutions and government entities. From
Apple's own eligibility page, you are not eligible if you "are an individual,
sole proprietor, or single-person business". A student is not an accredited
educational institution; the institution is. The waiver also forbids selling
anything through the app, and the named regions do not include India.

**There is no open-source programme.** Apple has never had one for Developer
ID. The old iOS Developer University Program was for institutions and is gone.

**Having somebody else notarize it does not work**, and not for a technical
reason. A Developer ID is an identity claim. An app notarized under another
team's ID is, to every Mac that runs it, their app: the signature, the TCC
entry and the responsibility are all theirs.

### So what can be done for free

In descending order of what it is worth:

1. **Make the one command better, and stop treating it as temporary.** The
   install path that exists is the only free path Gatekeeper leaves open, and
   it works. What improves without a cent: a page with the command behind a
   copy button, a screenshot of each permission dialog, and `dictator doctor`
   named as the thing to run when it goes wrong. This is not a consolation
   prize. It is what Homebrew itself asks of every user on day one.
2. **Ship the helpers and whisper prebuilt.** It removes the Xcode toolchain
   and the last Homebrew package from the user's side, and binaries fetched by
   `curl` are not quarantined, so they run. Issue #6 already records that this
   buys speed and not reach. It is also the same work notarization would need,
   so it is not wasted either way.
3. **A Shortcuts installer, unproven.** macOS Shortcuts has a Run Shell Script
   action and a shortcut can be shared as an iCloud link somebody adds by
   clicking. Scripting actions sit behind a global switch that is off by
   default: checked here, the `com.apple.shortcuts` preference domain does not
   exist on this machine at all, which is what never having enabled it looks
   like. So the journey would be: open the link, add the shortcut, open
   Shortcuts settings, turn on Allow Running Scripts, run it. Four GUI steps,
   no typing. **Not tested end to end.** It is an odd thing to ask of somebody,
   and it is the only double-clickable, free, non-bypass route found.

Not worth doing: a `.dmg` with a README telling people to run `xattr`, a
third-party tap, and anything that asks a user to enable Anywhere.

*(Update, 8 October 2026: there is now a fourth item, and it goes above the
other three.)*

0. **A free `.dmg`, approved once with Open Anyway.** Measured in "Retested 8
   October 2026" above. Ship a small app with the Swift helpers, whisper, a
   Python runtime and `jellyfish` inside it, signed with one self-signed
   certificate kept for every release, and the models downloaded on first
   launch as `scripts/install.sh` already does. About 60 to 90 MB installed and 30 to
   45 MB as a `.dmg`, estimated rather than measured. The download page shows
   the warning and the Open Anyway screen with a screenshot of each. This is
   not the `xattr` README ruled out above: the user never opens a terminal.
   Item 2 is part of this work anyway, and all of it carries over unchanged to
   a notarized build if the 99 dollars is ever paid.

---

## Windows

**Yes, and it is more feasible than it looks, for one reason that was not
known before this.** About eleven weeks of focused solo work. The engine layer,
which would normally be the frightening part, is a free download. The painful
parts are the gesture, elevated windows, and a signing and reputation tax that
the Mac install was specifically designed to avoid.

### The thing that changes the whole estimate

The official whisper.cpp Windows build was downloaded and its contents listed
here, from release `b5454`, published 6 October 2026,
`whisper-bin-x64.zip`, 8,928,640 bytes, 41 files, 23,147,520 bytes unpacked:

```
Release/whisper-cli.exe           479,744
Release/whisper-server.exe        726,016
Release/parakeet-cli.exe          372,224
Release/parakeet.dll              582,144
Release/ggml-cpu-sse42.dll        862,720
Release/ggml-cpu-sandybridge.dll  1,026,560
Release/ggml-cpu-haswell.dll      1,010,688
Release/ggml-cpu-skylakex.dll     1,049,600
Release/ggml-cpu-icelake.dll      1,061,376
Release/ggml-cpu-cascadelake.dll  1,061,376
Release/ggml-cpu-cannonlake.dll   1,049,600
Release/ggml-cpu-alderlake.dll    1,009,664
Release/ggml-cpu-x64.dll            866,816
```

Three consequences, and the first one kills a question the brief assumed was
hard:

1. **`parakeet-cli.exe` is in the box.** `stt.py` already shells out to
   `parakeet-cli -m <gguf> -f <wav> -np`, and `parakeet-cli` is an example
   target inside whisper.cpp. The Parakeet-on-Windows question assumed
   NeMo, PyTorch and CUDA. It does not apply. There is no Python ML stack, no
   CUDA, and no NVIDIA GPU in this path. It is GGML.
2. **`whisper-server.exe` ships too**, so the warm-server path ports.
3. **Nine runtime-dispatched CPU DLLs** mean one download is correct on a 2013
   ThinkPad and a 2025 Core Ultra. There is no equivalent engineering to do.

llama.cpp publishes the same shape of Windows CPU zip on every build tag, so
`recap.py`'s `llama-server` ports as well. The model files are the identical
GGML and GGUF from the same Hugging Face URLs `scripts/install.sh` already uses.

**The whole ASR and summarisation engine layer ports by changing
`brew install whisper-cpp` into "download a zip".**

One thing measured here that matters later: the PE security directory of the
shipped binaries is empty.

```
whisper-cli.exe    security_dir_rva=0 size=0 -> UNSIGNED
parakeet-cli.exe   security_dir_rva=0 size=0 -> UNSIGNED
```

### The held key

`SetWindowsHookEx(WH_KEYBOARD_LL)` is the `CGEventTap` equivalent. No admin
needed, and uniquely among global hooks it needs no injected DLL. Down and up
edges come free, so hold-to-talk is directly expressible, and `LLKHF_INJECTED`
lets it ignore its own synthetic keys.

**And there is no permission prompt at all.** No TCC, no consent API, no
Settings toggle, no manifest capability. Any process can install a global
keyboard hook silently. That is a genuine Windows advantage over macOS and it
deletes the single most painful part of this product.

Two sharp edges, and the first should worry us most given what this codebase
already believes. From Microsoft's own `LowLevelKeyboardProc` page:

> If the hook procedure times out ... on Windows 7 and later, **the hook is
> silently removed without being called. There is no way for the application to
> know whether the hook is removed.**

Default timeout 300ms. `always.py` already says "a dictation key that silently
stopped working is indistinguishable from a broken keyboard." Windows has a
documented API that produces exactly that failure, permanently, with no signal.
Under Python's GIL, with an audio thread and a transcription subprocess
running, that is a when and not an if. **This is the reason the hook belongs in
a small native helper rather than in ctypes from Python**, with a reinstall
watchdog on top.

The second is UIPI. Microsoft's own definition: UIPI "prevents lower-privilege
applications from sending messages or installing hooks in higher-privilege
processes". Practical effect: **the key does nothing while the foreground
window is Task Manager, regedit, or an elevated terminal or editor.** The
workarounds are to run elevated (a UAC prompt at every launch) or to ship a
`uiAccess="true"` manifest, which Microsoft requires be Authenticode signed and
installed under `\Program Files\`, so: a certificate and a real installer and
no portable zip. For a dictation tool, document the limit.

Note honestly: the SendInput direction of UIPI **is** documented (below). That
a medium-integrity hook is not *called* for keystrokes bound for an elevated
window is strongly implied and is stated plainly by AutoHotkey's own FAQ
("Hotkeys are also blocked"), but there is no single Microsoft sentence saying
it. It is a twenty minute experiment on a test machine.

**And there is no Fn key.** On most Windows laptops Fn is consumed by the
keyboard's embedded controller and never reaches the OS. This is the single
biggest UX regression and it cannot be fixed:

| Key | Verdict |
|---|---|
| Right Ctrl | Best single key. Needs tap-passthrough, suppress only past about 200ms and re-inject on a short tap |
| Caps Lock | Workable, must be suppressed or everything capitalises. Wispr Flow does this and documents that Caps Lock stops toggling |
| Right Alt | **Avoid.** AltGr types `@ \ { } [ ]` on international layouts |
| F13 to F24 | Perfect in theory, needs an HKLM scancode remap and a reboot, so admin and machine-wide |
| Copilot key | Emits Left Shift + Win + F23 and is hookable, but only on part of the installed base and no Microsoft source documents it |

Wispr Flow, with far more resources, ships **Ctrl+Win** as its Windows default
and lists standalone Ctrl as unsupported. Nobody on Windows has a one-key
gesture.

Antivirus is the real gate rather than the OS. Microsoft's own malware criteria
do not classify keyboard hooks as malware, but EDR vendors ship analytics named
for them, and their false-positive triage checklists ask whether the process
has a UI and whether it has a visible hotkey settings screen. **So the orb and
a tray icon are not cosmetic on Windows, they are detection-avoidance
features.**

### Audio

Easy, and 16kHz mono 16-bit is directly obtainable.
`AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM` removes the shared-mode mix-format
restriction: Microsoft's own wording is that "a channel matrixer and a sample
rate converter are inserted as necessary". So we ask for the format whisper
wants and the OS resamples, exactly as AVFoundation does today. `sounddevice`
exposes it as `WasapiSettings(auto_convert=True)`, though whether PortAudio
really maps that onto the Windows flag was not verified by reading PortAudio's
source.

**There is no microphone permission prompt for a desktop app**, only the global
"Let desktop apps access your microphone" switch, with no API to request
access. The failure mode when it is off is ambiguous in the available evidence,
splitting between `E_ACCESSDENIED` and silent zeros, so both have to be handled:
check the HRESULT and keep a silence watchdog, or a user with the toggle off
gets an empty transcript and no explanation.

One lifecycle warning: the Windows 11 taskbar microphone indicator names the
app holding the stream. Open on key-down and release on key-up, or the
indicator is lit all day and gets reported as a privacy bug.

### Getting the text in, which is where Windows is genuinely worse

Microsoft, verbatim, on `SendInput`:

> **This function fails when it is blocked by UIPI. Note that neither
> GetLastError nor the return value will indicate the failure was caused by
> UIPI blocking.**

> This function is subject to UIPI. Applications are permitted to inject input
> only into applications that are at an equal or lesser integrity level.

A silent no-op that returns the full success count. This repository has an
entire issue family about receipts that lie (`d2518e4`, "It posted the
keystroke into the void and reported that it had pasted"). Windows ships that
bug as documented API behaviour. Clipboard plus Ctrl+V does not route around
it, because the Ctrl+V is itself a SendInput. The mitigation is to query the
foreground window's integrity level first and say so up front.

Worse for our specific case: **SendInput with `KEYEVENTF_UNICODE` is reported
not to reach terminal TUI apps, Claude Code among them.** The mechanism is that
a synthesised `VK_PACKET` only becomes `WM_CHAR` after `TranslateMessage`, and
a TUI reading ConPTY key events that dispatches on virtual key before reading
`UnicodeChar` drops the character. The source is a third-party issue mirror
(closed "not planned", June 2026), so it is forum grade, but PowerToys Quick
Accent reportedly fails the same way, which is independent corroboration.

Read that against `paste.py`. That file's 327 lines exist because Claude Code
in a terminal is the target. **On Windows, typing is not available as a
fallback there. Clipboard and paste is not a fallback, it is the only path for
the flagship use case**, and it is fragmented: Windows Terminal binds both
Ctrl+V and Ctrl+Shift+V, Shift+Insert is the safest universal key, and users
unbind Ctrl+V deliberately to get vim's blockwise visual mode.

And one thing that is a direct hard-constraint violation if it is not handled:
**Windows clipboard history with cloud sync uploads every clipboard item to
Microsoft.** If Dictator pastes through the clipboard, every transcript leaves
the machine. The fix exists and is what password managers use: register the
clipboard formats `ExcludeClipboardContentFromMonitorProcessing` and
`CanUploadToCloudClipboard` set to 0. **This is non-optional and is not
something anyone would think of without looking.** Third-party clipboard
managers will ignore the hint anyway.

UI Automation is not an alternative. Microsoft states plainly that "the
TextPattern control pattern does not support the setting of text values in a
control", and `ValuePattern.SetValue` replaces the whole value rather than
inserting at the caret, which is close to fatal mid-sentence.

### The indicator, autostart, and the rest

The orb is a `WS_POPUP` with
`WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_NOACTIVATE`, fed by
`UpdateLayeredWindow` for real per-pixel alpha, about 150 to 250 lines of
ctypes. Two things must be got right or it looks broken: declare PerMonitorV2
DPI awareness before any window exists, or it is a blurry blob on a scaled
display; and `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` so it does not
appear in screen shares, gated on build 19041 or later because on older builds
it degrades to a black rectangle.

Autostart is the `HKCU` Run key, written only on explicit opt-in. One trap:
when a user disables an entry in Task Manager, Windows writes to
`StartupApproved\Run` and does not delete the original value, so re-writing the
value does not re-enable it and a settings toggle that does not read
`StartupApproved` will lie about its own state. Another: Task Manager marks a
startup app "High impact" above 1 second of CPU or 3MB of disk I/O, and a
PyInstaller one-file bundle unpacking and importing the world lands there and
gets Windows suggesting the user disable it.

### Speed, which is the other regression

The engine ports for free. The speed does not.

- The best modern laptop datapoint found is from whisper.cpp's iGPU work,
  reported January 2026: on a Ryzen 7 6800H and a Core Ultra 7 155H, "CPU
  realtime factor ~0.3", so about 3 times faster than real time, with the
  Vulkan iGPU path 3 to 4 times better again.
- Against a Mac baseline of roughly 6 to 9 times real time for the same model
  (secondary sources, order of magnitude only), **the same model is roughly 2
  to 3 times slower on a good Windows laptop CPU, and worse on anything
  older.** For a 5 second utterance that is the difference between about 0.6
  seconds and about 1.7.
- **Parakeet is the saving grace and should be the Windows default.**
  Independent CPU measurements put Parakeet int8 at about 30 times real time on
  an i7-12700KF and about 17 on a 2014 i7-4790. `scripts/install.sh` already makes
  Parakeet the English default and calls it "about half a second". That
  survives the port.
- **Hinglish is the casualty, and it already was.** Parakeet has no Hindi, so
  Hinglish goes to large-v3-turbo exactly as on the Mac, except that on Windows
  the fallback is the slow path on a machine 2 to 3 times slower. **Hinglish on
  a GPU-less Windows laptop will feel noticeably worse than on the Mac.**
- Acceleration: CUDA prebuilts exist but the zips are 285MB to 685MB and only
  help the minority with an NVIDIA GPU. Vulkan is the only cross-vendor option
  and is not in the stock zip. OpenVINO accelerates only the encoder and needs
  a per-model Python conversion step, which is a shipping nightmare. **ggml has
  no DirectML backend.** There is no CoreML equivalent. CPU is the honest
  answer for most machines.

Worth knowing for positioning: **Windows' built-in Win+H voice typing is
cloud-based on any non-Copilot+ PC.** The "nothing leaves the machine" pitch is
stronger on Windows than it is on macOS.

### Signing, and the finding that decides it

The Mac install sidesteps notarization because `swiftc` compiles the helpers on
the user's own machine. **Windows has no system compiler, no `xcode-select
--install`, no Homebrew.** Prebuilt binaries must be shipped, so SmartScreen
and signing stop being optional.

From Microsoft's SmartScreen reputation page, updated August 2026:

- Unsigned and self-signed: "Warning, Windows protected your PC; User must
  choose Run anyway before the app can run. **Enterprise policy can prevent
  continuation entirely.**"
- "When a file is not signed, SmartScreen reputation must build for each new
  version of your files, starting with zero reputation." **Every release starts
  from zero.**
- Even signed: "it can take several weeks and hundreds of clean installs from a
  wide audience."
- "Smart App Control will block execution of unsigned files unless the file has
  a positive reputation ... signature checks apply to **all executable files,
  not just those downloaded from the Internet**."
- "**EV certificates no longer bypass SmartScreen.** ... Paying a premium for
  EV solely to avoid SmartScreen warnings is no longer justified."
- And one that lands squarely on this app class: "**Do not sign potentially
  unwanted applications** ... or the certificate may develop **negative**
  reputation." A global keyboard hook plus input injection is exactly that
  heuristic neighbourhood. It is possible to poison your own certificate.

Certificates got more expensive in June 2023, when the CA/Browser Forum
required private keys for both OV and EV to live in a hardware module, which
killed the cheap software-keystore certificate.

And then the finding that decides the section. **Azure Trusted Signing, now
Azure Artifact Signing, is Microsoft's own cheap modern route, and it is
geographically closed.** Verbatim, from the quickstart page, ms.date 21 May
2026, updated 29 September 2026:

> Public Trust certificates are available to organizations in the United
> States, Canada, the European Union, the United Kingdom, Australia, New
> Zealand, Japan, South Korea, Singapore, Switzerland, Norway, and Israel.
> **Individual developers must be located in the United States or Canada.**

India is on neither list. The remaining options are a commercial CA that issues
to individuals (Certum is roughly $50 to $90 a year with cloud signing, vendor
pricing, moves) or SignPath Foundation, which is free but open-source only and
subject to eligibility review.

The Microsoft Store would remove the SmartScreen problem entirely ("Apps
published through the Microsoft Store are re-signed by Microsoft and carry full
reputation. Users will never see a SmartScreen warning"), but the route for
shipping a plain exe requires that "the binary **and all of its Portable
Executable (PE) files** must be digitally signed", and the whisper and parakeet
binaries are, as measured above, unsigned. So that route needs a certificate
anyway, and a full-trust MSIX needs the `runFullTrust` capability justified in
front of a human reviewer looking at a keyboard hook. **Plausible, unreliable,
do not plan v1 around it.**

Last, the packaging trap: **PyInstaller one-file plus a global keyboard hook
plus input injection plus a Run-key write plus unsigned is four independent
antivirus heuristics firing at once.** This is the textbook signature. The
documented remedy is to recompile the PyInstaller bootloader so the binary does
not share the known-bad byte pattern, prefer one-dir over one-file, ship a
visible tray UI and hotkey settings screen, and keep the 2.3GB of models as a
post-install download rather than bundling them.

### What ports and what does not, by line count

| Bucket | Lines | Fate |
|---|---|---|
| Pure Python: `shape` 545, `api` 360, `vocab` 357, `snippets` 297, `history` 271, `known` 207, `search` 161, `core` 154, `learn` 146, `profiles` 145, `script` 122, `review` 105, `roman` 100, `loops` 99, `hindi` 84 | **3,169** | **Unchanged. Stdlib only.** |
| Tests | 6,391 | Most carry over with the modules they test |
| Engine orchestration: `stt` 1,211, `recap` 786, `dictate` 490, `warmup` 165 | 2,652 | About 85% portable, swap binary discovery and paths |
| **Deleted outright**: `tcc.py` 486, `signing.py` 283 | **769** | **Windows has no TCC and no signature-versus-permission problem. These vanish.** |
| Rewritten Python: `always`, `paste`, `hotkey`, `recorder`, `orbnative`, `swiftbuild`, `mac`, `readback` | 1,259 | Rewrite |
| Swift helpers, excluding meetings | 2,132 | 100% rewrite |

About 60% ports with little or no change, about 7% is deleted, about 33% is
rewritten. **Everything that makes Dictator what it is, the formatting rules,
the romanisation, the vocabulary, the learned corrections, the history, the
snippets, the recap, is in the 3,169 pure lines and ports untouched.** What
gets rewritten is plumbing.

### Weeks

| Work | Weeks |
|---|---|
| Hotkey as a native helper: hook, watchdog, key choice, tap-passthrough, injected-event filter | 1.5 to 2 |
| Recorder, level meter, silence watchdog for the privacy-toggle case | 0.5 to 1 |
| Text delivery: clipboard with history and cloud-sync exclusion, integrity check, per-terminal keys | 1 to 1.5 |
| Orb: layered window, PerMonitorV2, multi-monitor, tray icon | 1 |
| Readback through UI Automation, accepting it is worse | 0.5 to 1 |
| Engine wiring: zip download, binary discovery, paths | 0.5 |
| Autostart, installer, first run, a Windows `doctor` | 1 |
| Per-app identity and retuning the formatting rules for Windows app names | 0.5 to 1 |
| Packaging, bootloader rebuild, signing setup, antivirus firefighting | 1 to 2 |
| Testing on real hardware: Intel, AMD, ARM, elevated windows, scaled displays | 1 |
| **Total** | **9 to 13, plan 11** |

That assumes a Windows machine to test on, excludes the meeting feature, and
excludes calendar time that cannot be compressed: SmartScreen reputation takes
"several weeks and hundreds of clean installs" **after** shipping.

### What Windows would be worse at, in one list

1. **The gesture.** No Fn key, so Right Ctrl with tap-passthrough or a chord.
2. **Dead in elevated windows, silently, in both directions.**
3. **The hook can be removed permanently and silently by a 300ms stall**, which
   is the exact failure this codebase considers the worst one possible.
4. **Delivery into Claude Code is clipboard only**, with no typing fallback and
   with per-terminal paste-key fragmentation.
5. **2 to 3 times slower**, worst exactly where Hinglish lives.
6. **Readback is worse.** Chromium accessibility is off by default, so the
   correction-learning loop will mostly not fire in Slack, VS Code or Notion.
7. **It cannot be shipped the way the Mac version is shipped**, and Microsoft's
   cheap signing route is closed to India.
8. **Microphone permission failures are invisible.**

And one it would be better at: **no permission dance at all.** `tcc.py` and
`signing.py`, 769 lines of hard-won knowledge about cdhashes and TCC rows,
exist only to solve a macOS problem and are deleted outright.

---

## iOS

**Not possible, and a server would not fix it either.** This is the one
platform where paying the money and abandoning the privacy promise still does
not buy the feature, so it is worth being exact about why.

### There is exactly one API that writes where the cursor is

`UITextDocumentProxy.insertText(_:)`, and it exists only inside a custom
keyboard extension. There is no iOS equivalent of `AXUIElement` or of posting a
`CGEvent` into another process. Apple's security guide: sandboxing is "designed
to prevent apps from gathering or modifying information stored by other apps",
and cross-app access happens "only by using services explicitly provided by
iOS".

So the whole question is whether a custom keyboard can record and transcribe.

### A custom keyboard has no microphone, in Apple's own words

From Apple's current documentation page *Configuring open access for a custom
keyboard*, listing what the default keyboard sandbox denies:

> No access to microphone and speaker

Turning on Full Access (`RequestsOpenAccess`) adds Location Services, Contacts,
a shared container with the containing app, iCloud, and the ability to "send
keystrokes and other input events for server-side processing". **The microphone
is not on that list.** The archived 2014 extension guide said it plainly:
"Custom keyboards, like all app extensions in iOS 8.0, have no access to the
device microphone, so dictation input is not possible." The 2014 page would be
worth discounting on its own; the current page says the same thing, so the
restriction is live, not stale.

Developers who try anyway get this in the system log:

```
CMSUtility_IsAllowedToStartRecording: ... was NOT allowed to start recording
because it is an extension and doesn't have entitlements to record audio
```

(Apple Developer Forums 742601, December 2023, and 775077, February 2025, where
an Apple engineer suggested a workaround, it did not work, and FB16791704 was
still open in September 2025. Both are forum posts.)

A few vendor marketing pages assert that a keyboard with Full Access can
record. None shows a log, a device or an iOS version. Against them, KeyboardKit,
the dominant commercial iOS keyboard SDK, states in its own documentation that
"microphone access is unavailable" in a keyboard extension and repeated it in a
post dated 3 January 2026.

`hasDictationKey` is not a way in. Apple's documentation says only that setting
it stops iOS drawing its own microphone button "because having two buttons to
perform dictation would be confusing". The button iOS draws over a third-party
keyboard runs **Apple's** dictation, not yours.

### And whisper would not fit even if the microphone worked

A keyboard extension is killed by jetsam, with no crash and no exception, at a
measured **48 to 77MB**. The best evidence is a real jetsam log in a public pull
request dated 24 September 2026: killed at 77MB against a per-process limit of
4,928 pages, with idle snapshots of 52 to 64MB. A device-measured blog post of
9 August 2026 puts the practical ceiling "around 60MB of phys_footprint". Call
the safe budget 50 to 60MB.

whisper.cpp's own README, model table, runtime memory column:

| Model | Disk | Runtime memory | Against 60MB |
|---|---|---|---|
| tiny | 75 MiB | ~273 MB | 4.5x over |
| base | 142 MiB | ~388 MB | 6.5x over |
| small | 466 MiB | ~852 MB | 14x over |
| medium | 1.5 GiB | ~2.1 GB | 35x over |
| large | 2.9 GiB | ~3.9 GB | 65x over |

The models on this machine, measured:

```
ggml-tiny.bin                         74.1 MB
ggml-small.en.bin                    465.0 MB
ggml-parakeet-tdt-0.6b-v3-q8_0.bin   637.8 MB
ggml-large-v3-turbo.bin             1549.3 MB
```

The one that transcribes Hinglish is the 1549MB one. The smallest model in the
product is 74MB on disk and 273MB in memory, **over four times the budget
before a single audio buffer exists.** Quantisation halves runtime memory at
best, which leaves it three times over. There is no engineering that closes a
gap of that size.

### The one thing that changed, and what it does not change

iOS 26 shipped **SpeechAnalyzer and SpeechTranscriber**, Apple's new on-device
speech framework. From the WWDC25 session 277 transcript, verbatim:

> The model is retained in system storage and does not increase the download or
> storage size of your application, nor does it increase the run-time memory
> size. **It operates outside of your application's memory space, so you don't
> have to worry about exceeding the size limit.**

and

> Remember that transcription is entirely on device but the models need to be
> fetched.

That is genuinely new since this project started, and it means the memory
ceiling stops being a blocker **if whisper is given up for Apple's model**. It
is on-device, so it does not break the promise. It is the only speech engine
that could ever run inside a keyboard extension.

It still does not help, because the microphone blocker is independent of it.
And it costs the thing the product exists for: Apple's dictation picks one
language at a time, and whether SpeechTranscriber supports Hindi at all, let
alone Hindi and English inside one sentence, is not stated in Apple's
documentation and was not established here.

### How the shipping products do it, and the answer is they do not

Every iOS dictation keyboard on the store has the same architecture: the mic
key calls `extensionContext.open("theirapp://dictate")`, which **foregrounds
the containing app**, which records and transcribes, writes the text to a
shared App Group container, and then the user manually navigates back and the
keyboard inserts it. Wispr Flow, Superwhisper, Spokenly and Akshar all do this.
**Nobody records in the keyboard.**

Two things follow. It is not system-wide dictation, it is an app switch with
extra steps, and App Store reviews of Superwhisper's iOS keyboard say so:
"totally unreliable, in some apps it records but doesn't paste the dictated
text in, in others it switches over to SuperWhisper and gets stuck there."

And **the return trip has no API, confirmed by Apple in August 2026.** Apple
DTS, in forum thread 826851: there is no public API for a keyboard to identify
its host app, and none for the containing app to find out who called it.
FB22247647 is open with no timeline. KeyboardKit **removed** the feature in
version 10.4 for exactly this reason. The user lands on the home screen, not
back in the message they were typing.

| Product | Shape | Transcription |
|---|---|---|
| Wispr Flow | keyboard plus app switch | **Cloud only.** Their own page: "Transcription always happens in the cloud" |
| Superwhisper iOS | keyboard plus app switch | on-device models, recording in the app |
| Spokenly | keyboard plus app switch | local models claimed, vendor marketing only |
| Akshar, 22 Indic languages | keyboard plus app switch | claims fully on-device, app up to **1.5GB**, needs iOS 26.4 |
| Aiko | **standalone app, no keyboard** | fully on-device whisper, small or medium by available memory |
| Apple's own mic key | system keyboard | on-device since iOS 15 on A12 and later |

Akshar is the closest thing to this product that exists on iOS. It is Indic, it
claims to be offline, it is **still an app switch**, and it carries the model in
the app rather than the extension. That is the proof in one listing.

### For the record, the money

There is no route to another person's iPhone without the $99. A free Apple ID
gets a Personal Team with 7-day provisioning profiles, 3 devices, 3 apps per
device, no TestFlight and no App Store. The EU's alternative distribution rules
do not help: every route still requires Developer Program membership and Apple
notarization. The one genuine 2026 improvement is that the Core Technology Fee
was replaced on 1 October 2026 by a 5% commission on sales, so a free app no
longer pays per install. It still cannot be distributed without the $99.

### The honest iOS alternatives, ranked

1. **A standalone app you dictate into and copy out of.** A normal foreground
   app has the whole memory budget, so whisper small (about 850MB runtime) is
   realistic and base is comfortable. Add an **App Intent** so the Action
   Button, Control Center, Back Tap or a Lock Screen widget opens it straight
   into recording. That is the closest iOS gets to hold-to-talk: one press to
   record, one tap to copy. It is also exactly what Aiko already is, for free.
2. **A share sheet and Shortcuts target.** An Action extension gets about
   120MB, still under whisper tiny's 273MB, so the real work happens in the app
   anyway. Discovery is poor.
3. **A keyboard extension fed from the app.** About four weeks to ship the
   experience the App Store reviews already say people hate, requiring Full
   Access, the most alarming permission on iOS, for a product whose entire
   pitch is privacy, and Guideline 4.4.1 says keyboards "must not launch other
   apps besides Settings", so the core mechanism is one reviewer away from
   being pulled. **Do not build this.**
4. **A companion that pairs with the Mac over the LAN.** Phone records, Mac
   transcribes with the large model, text comes back. Best accuracy of the four
   and the one that **breaks the promise**: audio leaves the device. Even to
   your own Mac, even encrypted, even without the internet, it is a network
   transport of raw voice, and "nothing leaves the machine" stops being true.
   It also only reaches the clipboard, so it buys accuracy and not insertion.

Two things could be settled by half an hour on a real iPhone and neither
changes the verdict: whether a keyboard extension can record at all (Apple's
docs say no, the logs say no, nobody has shown otherwise, and a yes would only
unblock Apple's engine), and whether SpeechTranscriber supports Hindi and
tolerates code-mixing.

---

## Android

**Possible, and it is the only platform where the thing he asked for can
actually exist.** Fully offline, system-wide, text landing where the cursor is,
no server. The mechanism is solved and there is MIT-licensed working prior art
to read. The problem is not the platform. It is that the model that does
Hinglish does not run on the phones the audience has.

### The mechanism, and it is better than the Mac's

An `InputMethodService` is not a sandboxed extension. It is a normal app
process with the normal heap, it can hold `RECORD_AUDIO`, and it inserts text
by **being** the keyboard: `InputConnection.commitText()`. The host app
receives it exactly as if typed. No clipboard, no synthetic Cmd-V, no
accessibility injection, no permission that frightens anybody.

That is a straight upgrade on the macOS design. `paste.py` is 327 lines and
`native/paste.swift` is 175 more, and all of it exists because macOS has no
concept of an input method we could be. On Android that whole subsystem
collapses into one call.

The reference implementation is `woheller69/whisperIME`, MIT, on F-Droid. Its
manifest ships all three routes at once:

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
<service android:name=".WhisperInputMethodService"
         android:permission="android.permission.BIND_INPUT_METHOD"
         android:foregroundServiceType="microphone">
  <intent-filter><action android:name="android.view.InputMethod" /></intent-filter>
</service>
```

and the subtype that makes it a **voice** keyboard rather than a full one:

```xml
<subtype android:imeSubtypeMode="voice"
         android:isAuxiliary="true"
         android:overridesImplicitlyEnabledSubtype="true" />
```

`isAuxiliary="true"` means it never appears in the normal keyboard rotation,
only as a voice target. Exactly the right shape: the product does not have to
become somebody's keyboard to become their dictation.

A second route is worth having. A real `android.speech.RecognitionService`,
which, if the user selects it under Settings, System, Languages and input,
Speech, Voice input, means **the mic button on the keyboard they already use**
runs our code. whisperIME ships one. With one large caveat, in its own README:

> If after installation you do not find Whisper as voice input or only see a
> limited list (hard-coded ones like Google/Samsung) ... enable USB debugging
> ... `adb shell settings put secure voice_recognition_service ...`

So on Samsung and several other OEM builds the picker is hard-coded and a third
party cannot be chosen through the UI at all. Build it, do not plan around it.

A correction to something widely believed: **FUTO does not ship a working
RecognitionService.** Its manifest has the recogniser block commented out and a
`DummyService` stub in its place, which exists only so other keyboards'
discovery queries find the app. And the two keyboards most Indian users
actually have, **Gboard and Samsung Keyboard, hardcode their own voice
providers and cannot be hooked by either route.**

`AccessibilityService` would work technically and must not be used. Google's
policy announcement of 30 October 2025 tightened it so that "any use of this
API that enables an app to autonomously initiate, plan, and execute actions is
prohibited", with stricter review from January 2026. A dictation app writing
into other people's text fields is what that sentence describes.

### No memory cliff, which is the whole difference from iOS

Android caps the Java heap per device (typically 128 to 256MB) but
**whisper.cpp does not allocate there**. ggml mallocs natively through JNI,
outside the ART heap and uncounted. What can kill the process is the low memory
killer looking at total RSS, and a high-priority visible IME is not first in
line. A few hundred MB resident is tolerated on a 4GB phone. One to two GB is
not.

There is no iOS-style 60MB wall. That one fact is why Android is a yes and iOS
is a no.

### And then the model, which is where it falls over

The Hinglish path is `ggml-large-v3-turbo.bin`, measured here at **1549.3MB**.
The one real measurement for that model class on a phone is whisper.cpp issue
#2370, 25 November 2025: a **Pixel 8**, which is a flagship, 30 seconds of
audio in **73 seconds** on CPU and 67 with Vulkan. RTF 2.4. A five second
utterance would take about twelve seconds, on better hardware than the audience
has.

whisper.cpp's own Android example README says it plainly: "I recommend the tiny
or base models for running on an Android device."

What does fit, from GitHub issues (forum grade, dates given, and note that any
benchmark before mid-2026 that does not say "release build" is contaminated,
because debug builds are 7 to 10 times slower and release mode was only forced
in the example in June 2026):

| Device | Model | Result | RTF |
|---|---|---|---|
| Redmi Note 9S (SD720G, mid-range) | base | 48s audio in 37s | 0.77 |
| unnamed, release build | tiny.en f16 | 11s in 5.12s | 0.47 |
| Pixel 8 (flagship) | large-v3-turbo | 30s in 73s | 2.4 |

Tiny is safe. Base is the realistic ceiling on a two or three year old
mid-range phone. Small is unproven and probably out. **No trustworthy recent
mid-range measurement exists for any size**, which is the biggest hole in this
section and the reason the first thing to do is buy a cheap phone and measure.

Acceleration does not rescue it. NNAPI was deprecated in Android 15 and
whisper.cpp never had an NNAPI backend anyway. Vulkan bought 8% on the Pixel 8
and crashes on Adreno 830. OpenCL on Adreno is broken for medium. The Hexagon
NPU path is flagship only.

### The Hindi numbers are the ones that end it

Collabora's measurements of stock Whisper on FLEURS Hindi, published 29 May
2025, word error rate:

| Model | Stock | Fine-tuned on about 3000h Hindi |
|---|---|---|
| tiny | **172.6%** | 10.0% |
| base | **149.2%** | 9.0% |
| small | **67.4%** | 7.2% |
| medium | 26.9% | 6.1% |
| large-v2 | 21.5% | 5.3% |

Read the stock column against the size ladder above. **The models that fit on a
mid-range Android phone emit more errors than there are words.** Tiny and base
are not a bit worse at Hindi, they are useless at it.

The romanised Hinglish models that do exist are large. Oriserve's
Whisper-Hindi2Hinglish-**Apex** is a large-v3 fine-tune, about 834MB as a q8
ggml port, and it does emit Latin script. Their **Swift** model is a
whisper-base fine-tune at about 150MB and self-reports 35 to 39% WER, which is
a demo and not a product. None of these numbers is independently verified, and
the ones scored against a Devanagari reference are close to meaningless for a
Latin-script product.

Two things carry over from our side for free:

- `dictator_core/data/hi_roman.tsv`, 25,002 entries from Google Dakshina, becomes an
  Android asset unchanged. It is the single most directly reusable thing in the
  codebase. **Its CC BY-SA 4.0 attribution and share-alike terms start to bite
  the moment it is distributed in an app**, which `roman.py`'s own docstring
  already flags and which nobody has had to act on yet.
- The one unexplored idea worth a week: **IndicConformer-600M int8 at about
  190MB through sherpa-onnx**, feeding the existing romanisation layer. It is
  the best-scoring open model on the Vaani Hindi benchmark (13 to 20% WER
  against whisper-large-v3's 26 to 33%, which was the worst of ten systems
  tested), it is MIT, it is a fifth the size of what runs on the Mac, and
  unlike whisper it needs no 30 second chunking. **Nobody has measured it on an
  Android phone and nobody has validated it on code-mixed speech.** It is a
  hypothesis. It is the only one with the right shape.

### The one real latency lever, and it is FUTO's and it is MIT

Whisper's encoder always processes 30 seconds, padding a 5 second utterance
with 25 seconds of silence. Trimming `audio_ctx` to the real audio makes stock
whisper produce garbage: FUTO's own table shows tiny.en going from 4.73% WER to
**225.99%**. Their Adaptive Context Finetuning fixes it: 5.50% with dynamic
context, essentially free.

The code is MIT (`futo-org/whisper-acft`) and six models are Apache-2.0 and
already in q8_0 ggml form. FUTO publishes no speedup figure, so the size of the
win is an inference from the architecture and not a measurement, but it is the
difference between base being borderline and base being comfortable.

FUTO itself: offline by their own claim, whisper-based, distributed on Play,
F-Droid and as an APK, under the **FUTO Source First licence, which is
source-available and not OSI open source** and restricts commercial
redistribution. Seventeen languages, **no Hindi**. The standalone Voice Input is
in maintenance mode. So FUTO proves the shape works and is not competition in
this market.

### Distribution is cheap in money and getting hostile

Google Play is **$25 once**. Then a personal account created after 13 November
2023 must run a closed test with **12 testers opted in continuously for 14
days** before it can ship to production, so budget three or four weeks of
calendar time. Identity verification needs a government ID and the legal name
is displayed publicly on the listing.

The bigger thing is new. **Android developer verification for apps installed
outside Play is live.** Enforcement began **30 September 2026** in Brazil,
Indonesia, Singapore and Thailand on certified Android 7 and later, with global
expansion from 2027. India is not in the first wave, which buys time for
exactly this audience. There is a free limited-distribution tier needing only
an email, **capped at 20 devices**, which is fine for a personal tool and
useless for a product. The full tier is $25 and a government ID.

The most telling line in the whole research is in whisperIME's own README:

> Since the developers of this app do not agree to this requirement, this app
> will no longer work on certified Android devices after that time.

The author of the best piece of prior art for this product plans to let it die
rather than send Google his identity documents. Shipping on Android means doing
the thing he refused. Worth knowing before starting, for a product whose whole
premise is that nothing leaves your device.

### What the port actually is

The Python pipeline does not run on Android, and not marginally. CPython gets
there only through Chaquopy, BeeWare or Kivy, all of which add tens of
megabytes and all of which are painful inside an `InputMethodService`, which is
a Service with a cold-start budget measured in milliseconds because somebody is
holding a key.

Counted here on 6 October 2026: `dictator/` is 9,128 lines of Python across 31
modules, `tests/` is 6,391 lines, `native/` is 2,687 lines of Swift, and
`hi_roman.tsv` is 25,002 lines.

| Bucket | What | Cost |
|---|---|---|
| Copies verbatim | `hi_roman.tsv` as an asset | 1 day, plus getting the licence right |
| Rewritten in Kotlin | `shape`, `vocab`, `known`, `hindi`, `roman`, `learn`, `history`, `snippets`, `profiles`, `search`, `script`, `review`: about 2,500 lines | 4 to 5 weeks |
| Rewritten, and underestimated by everyone | the 6,391 lines of tests, which are the actual specification | 2 to 3 weeks |
| Deleted, not ported | `mac.py`, `tcc.py`, `paste.py`, `hotkey.py`, `orbnative.py`, `signing.py`, `swiftbuild.py`, `recorder.py`, `readback.py`, `warmup.py` plus every line of Swift. Seven of those files alone are 1,573 lines, and `native/` is 2,687 | zero, but they are gone |
| Should not be ported | `meeting.py` (1,279) and `recap.py` (786): continuous background audio capture on Android is restricted and policy-fraught | cut it |

Solo, full time:

- **8 to 10 weeks** for an English-only offline push-to-talk keyboard with an
  ACFT base model, basic shaping and a RecognitionService. A credible,
  shippable thing.
- **16 to 22 weeks** to approach parity with the Mac text pipeline, minus
  meetings and recap.
- **Hinglish parity is not a schedule item, it is a research risk**, and the
  honest prior is that it fails. No model under about 800MB has demonstrated
  good romanised Hinglish, and 800MB does not run at an acceptable latency on
  the phones the audience owns.

One thing degrades that is easy to miss: the correction-learning loop watches
what the user does to the text after it lands. Through `InputConnection` that is
less reliable than the macOS accessibility readback, which is already the
weaker half of that feature.

### The two weeks that decide whether this is real

Before a line of Kotlin:

1. Buy a two or three year old mid-range Android phone, not a flagship and not
   his own. Build `examples/whisper.android` **in release mode**. Measure tiny,
   base and small with FUTO's ACFT q8_0 models at trimmed `audio_ctx`. Every
   number above is 2023-era or anecdotal and none of it is for that hardware.
2. Convert IndicConformer-600M int8 for sherpa-onnx, run it on the same phone
   against twenty real Hinglish utterances, pipe the Devanagari through
   `roman.py`, and read the output.

Step two decides whether the reason the product exists survives the port.
Nothing else here matters more.

---

## What a phone can have today, for nothing

Two things already work, need no code, and are worth saying out loud before
anybody commits a quarter to a port.

**iPhone Mirroring.** macOS can show and control the iPhone, including typing
into iPhone apps with the Mac keyboard. The Mac's dictation key is already
pointed at whatever has focus. So dictating into an iPhone app, offline, with
the large model, works today with nothing built. It is not mobile dictation: it
needs the Mac in front of you and the phone nearby. It is also unavailable in
the EU, which does not affect this user. **Whether a synthetic Cmd-V lands
inside the iPhone Mirroring window is untested and is a ten minute
experiment.**

**Universal Clipboard.** Dictate on the Mac, paste on the phone. Needs
Bluetooth, Wi-Fi and the same Apple Account on both. Whether the clipboard
contents traverse a server was not established, so it is not free of the
promise: it is the user's own choice to copy, which is different from the
product sending anything, but it should be described honestly rather than
advertised as local.

Both are consolation prizes. They are worth naming because they cost nothing
and because they are better than the fourth-ranked iOS option, which costs a
month and breaks the promise.

---

## The ranking

Including doing nothing, because doing nothing is a real option and is better
than two of these.

**1. Pay the $99 and notarize the Mac build.** Two to four days of work, mostly
the hardened runtime pass, plus $99 a year. It converts the product from
something only a developer can install into something anybody can install, it
fixes issue #4 and issue #6 completely, and it **also closes issue #2**,
because a Developer ID certificate is stable across builds and users so the
TCC requirement stops rotting. Nothing else on this page delivers three open
issues for four days. The money is real and he has said it is not there now; it
is also what VoiceInk, a GPL competitor in the same niche, pays and recovers at
three sales of $39.99. **This is what I would do, and I would do it before any
port.**

**2. Do nothing about platforms, and fix Hinglish.** The free list for macOS is
short and mostly already done, and the product's one genuine advantage over
everything else on the market is Hinglish, which the README calls "still rough"
and which issue #3 says has no benchmark to judge a model by. Every hour spent
on Windows is an hour not spent on the only thing a user would choose this tool
for. Doing nothing ranks second, above both ports, and should not be
embarrassing.

**3. Windows.** Eleven weeks. Real reach, a genuinely stronger privacy pitch
than on macOS, 60% of the code ports untouched, and 769 lines of the most
painful macOS code are deleted outright. Against that: no Fn key, silently dead
in elevated windows, clipboard-only delivery into the flagship use case, 2 to 3
times slower exactly where Hinglish lives, and a signing route where Microsoft's
cheap option is closed to India. **Do it for reach. Do not do it expecting
parity.**

**4. Android, English first.** Eight to ten weeks to a credible offline voice
keyboard, on the one platform where the full feature is actually possible, with
MIT prior art to read and an insertion path better than the Mac's. It ranks
below Windows only because the thing that makes this product worth choosing,
Hinglish, is the thing that does not survive the port. **Do the two week
measurement first.** If IndicConformer at 190MB plus the existing romanisation
produces readable Hinglish on a cheap phone, Android moves above Windows. If it
does not, Android becomes a different product with the same name.

**5. An iOS standalone app.** A few weeks for an app that is one press to
record and one tap to copy, which cannot paste for you, in a category where
Aiko already does it for free. Only worth it as a companion to a Mac product
people already use.

**Not ranked, do not do:** an iOS keyboard extension, anything that enables
Gatekeeper's Anywhere setting, a `.dmg` with `xattr` instructions in the
README, a Homebrew tap, and any phone-to-server route including a phone-to-Mac
one.

---

## What is written here that was not verified

- That a quarantined `.app` shows the trash prompt rather than Open Anyway on
  the **default** Gatekeeper setting is taken from a published test on macOS
  26.6.1, not reproduced here. *(Update, 8 October 2026: since tested here on
  macOS 27.0.1, and it did not hold. Open Anyway was offered. See "Retested 8
  October 2026".)* What was reproduced here is the quarantine
  propagation, the `syspolicy_check` verdict, the `.pkg` rejection, the
  `.command` refusal with error -128 and its control, and that `xattr -d` still
  works.
- The Shortcuts installer route, end to end.
- On Windows: whether a medium-integrity keyboard hook is not called for
  keystrokes bound for an elevated window (the SendInput direction is
  documented, the hook direction is not); whether PortAudio's `auto_convert`
  really maps onto `AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM`; the exact failure mode
  when the microphone privacy switch is off; and the Claude Code SendInput
  report, which is a third-party issue mirror.
- On iOS: whether a keyboard extension can record audio at all, and whether
  SpeechTranscriber supports Hindi or code-mixing.
- On Android: any trustworthy recent real-time factor for any whisper size on a
  mid-range phone, which is the biggest hole in this document; peak resident
  memory per model on Android; the size of the ACFT dynamic context speedup;
  and IndicConformer on a phone, which nobody appears to have measured.
