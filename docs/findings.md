# What we measured

Everything here was checked on a real machine, not reasoned about. Where a
number came from somebody else it says so. Where we could not find something
it says that too, rather than estimating.

The point of this file is to stop us re-deriving the same things, and to stop
us re-trying ideas that have already been measured and rejected.

---

## Speech

### The engines, and what each is for

| | Size | Speed (12s hold) | Good at |
|---|---|---|---|
| Parakeet TDT | 638MB | 0.5s | English. Verbatim. **No Hindi at all** |
| whisper large-v3-turbo | 1549MB | 3 to 5s | Hindi, Hinglish, anything mixed |
| whisper tiny | 74MB | 0.2s | Answering "which language was that" |
| whisper small.en | 488MB | 1.3s | English fallback when Parakeet is absent |

### Parakeet fails in three different ways, and each needed its own detector

It has no Hindi, so on Hinglish it does not degrade, it invents. Every one of
these came from a real hold that came back wrong:

1. **Fused syllable blobs.** "kya tumko sab kuch samajh aa raha hai" became
   "Kyatungko Sabkuch Samach Arahahe". Caught by: unusually long words AND
   Title Case on most of them. Either signal alone has false positives.
2. **Dropped speech.** Twelve seconds of audio produced twelve words. Caught
   by words per second: a working pass runs about **2.7**, turbo on the same
   Hinglish audio **2.1**, Parakeet failing on it **0.96**. Threshold 1.5,
   and only for holds over 3 seconds, because a 2 second hold is usually one
   word.
3. **An answer in a language nobody spoke.** "Менен Телеранде." in Cyrillic,
   and one hold with Polish and Czech diacritics. Neither of the other checks
   sees these. Caught by: any character above ASCII, since an English
   transcriber has no reason to emit even one. Curly quotes and an ellipsis
   are allowed.

There is a test that fails if any of the three is removed, because each closes
a hole the others do not and none of it is obvious from reading the code.

An **empty** answer from Parakeet is also a failure, and was not treated as
one. It fell through to the English model, which then produced
"[NON-ENGLISH SPEECH]" and "[INAUDIBLE]" on real Hinglish holds.

### Language detection: what we tried and what happened

| Approach | Result |
|---|---|
| whisper `-l auto` | Runs the encoder **twice**. Measured: 2447ms over 2 runs vs 1230ms over 1 for a pinned language, identical transcript |
| tiny model `-dl` | 0.2s, and got both test samples right (hi p=0.86, en p=0.67) |
| **Trusting tiny's answer** | **Broke badly.** On short holds with Indian names it returned Malayalam at p=0.80 and Malay at p=0.40, producing confident transcription in Cyrillic and Arabic script |

So: only `en` and `hi` are ever pinned, because this product routes between
those two and any other answer means the detector is confused. Confidence did
not separate the good answers from the bad, so a threshold alone was never
going to fix it. Holds under 4 seconds are not pinned at all.

### Prompting: the hypothesis that was wrong

Measured on the same 12.4s Hinglish hold, same model:

| | Words correct |
|---|---|
| Current English `initial_prompt` | **73%** |
| No prompt at all | 69% |
| The rejected Hinglish steer | 73% |

Dropping the English prompt made things **worse**, because that prompt is what
keeps English technical words intact: without it "accuracy" came back as
"ekyoorisee". On one sample those three are noise. The prompt was never the
problem; the **language setting** was, and it sent Hinglish audio to Parakeet.

Also rejected earlier, and still rejected: a romanized-Hinglish steer prompt.
It works on synthetic speech and does the opposite on a real voice, because it
biases the decoder toward Hindi phonetics for audio that is not Hindi.

### Latency: where the 4.8 seconds goes

The encoder is roughly 85 percent of it. Measured on a 12.4s hold with turbo:

| audio_ctx | window | total |
|---|---|---|
| 1500 (default) | 30s | 4554ms |
| 900 | 18s | 2527ms |
| 700 | 14s | 1840ms |
| 600 | 12s, under the audio | 1885ms **and a word was lost** |

whisper.cpp encodes a full 30 second window however long you spoke. Sizing it
down is the single biggest win available. **Undershooting is dangerous rather
than merely lossy**: below the audio length the decoder can enter a repetition
loop that takes longer than full context. Always round up with margin.

An audio context can only be set when a server is **launched**, not per
request, which is why short utterances take the CLI path even though it pays a
model load.

**The warm server is not automatically faster.** Measured here: 3.2s with no
server running, 5.8s with one up and unused, because it contends for the GPU.
A resident server only helps if it is the one the request actually needs.

### Things that do NOT help, measured

- **Quantisation.** Encode times on this M3: f16 1219ms, q8_0 1271ms, q5_0
  1384ms. Quantised encoders are **slower** on Metal. Decode gets faster, but
  decode is 0.15s of a 2.8s budget. It buys RAM and nothing else.
- **Speculative decoding.** Accelerates decoding, which is 0.15s here. A
  perfect implementation saves under 0.1s.
- **Flash attention.** Already on by default, and worth about 13 percent.
- **Streaming whisper.** Structurally hostile: the encoder takes a fixed 30
  second window and the decoder cross-attends to all of it, so a partial
  decode is a different computation, not a prefix. Every early chunk is paid
  for again. What works instead is pipelining, doing during the hold what you
  would otherwise do after it.

---

## Correcting and learning

### The rule that makes automatic learning safe

Only learn an edit whose replacement **sounds like** what was heard.

```
whisper floor    -> Whisper Flow     learned  (a mishearing)
a man deep       -> Amandra          learned
the loop is slow -> the loop is fast ignored  (changed their mind)
check the code   -> never mind       ignored  (a rewrite)
```

Nothing is learned on first sighting. One edit is as likely to be a typo as a
lesson.

### Matching by sound needs two different sound systems

Metaphone models **English** spelling. On romanized Hindi it returns keys too
short to guess from (`chahiye` to `XHY`, `woh` to `W`), so every Hindi word was
admitted exact-match-only and the generalisation never applied to half of what
this user says.

The variation in romanized Hindi is not arbitrary: there is no standard, so
people differ on which vowel spelling they reached for and which of a few
interchangeable consonants. Normalise exactly that and `chaahie`, `chahiye`
and `chahie` are one word.

The Hindi key must match **exactly**, never approximately. It has already
absorbed the variation it exists for, and these keys are short enough that one
character of slack rewrote "sahi hai" as "chahiye" on the first sentence it
was tried on.

### Guarding against a term that eats a real word

A learned term is dangerous exactly when it can overwrite a word the user
actually uses. The guard is **their own history**, not a dictionary:

- A dictionary would leave "Hinglish" free to eat "English" (0.20 apart,
  exactly the threshold), which they say constantly.
- And it would block "dictator" because the dictionary contains "dictate",
  which they have never once said.

Each key is judged separately. "Amandra" is unsafe by its English sound
(collides with amend, amends, amount) and safe by its Hindi one, so it is
guessed at by the second and never the first.

"Exact match" has to mean the **word**, not the key. Metaphone gives "we" and
"woh" both `W`, so the most cautious admission there is still rewrote one of
the most common words in English.

### The romanisation lexicon is the wrong source of truth for spelling

Dakshina gives `chaahie` for चाहिए, `vo` for वो and `hisab` for हिसाब, which
are the spellings this user considers wrong. A pass built on it normalises
**toward** them. 4473 of its 23587 romanizations are also English words.

The right source of truth is what the user writes, which the learning loop
already records.

---

## Summarising what was dictated

### The local model is good enough, measured rather than assumed

`qwen3-4b-instruct-2507-q4_k_m.gguf` (2.5GB) through Homebrew's `llama-server`,
on this M3, summarising real sessions out of this user's own history:

| | |
|---|---|
| cold start to answering | 3.6s |
| one session, 7 to 39 lines, 700 to 7000 characters | 1.3 to 5.9s |
| a week's recap end to end, 8 sessions summarised | 22.1s |
| a day with nothing worth summarising | 0.08s, model never loaded |

So a recap is a command you wait for once at the end of a day, not something
that can sit on the dictation path. That is also why the server is **stopped
when the command finishes**: we already measured that a resident speech server
makes dictation slower by contending for the same GPU (3.2s against 5.8s), and
leaving 2.5GB resident after a once-a-day command would be paid for by every
hold after it.

### Where to put the grounding threshold, and why 0.7 was wrong

A summary of your own day is believed, so the guard is: throw away anything
whose words do not trace back to the lines it was given. The first threshold
was a guess (70 percent of content words) and it **rejected six of ten good
summaries**.

Measured over ten real sessions, scoring the share of the summary's content
words that appear in its source:

| | Share traced back |
|---|---|
| A summary against the lines it was actually given | 0.47 to 0.82 |
| The same summaries against a DIFFERENT session | median 0.07, 95th 0.42 |
| Three invented summaries (a meeting, an offer, an incident) | max **0.17** |

Honest and invented are two separated populations, and 0.45 sits in the gap.
What the rejected words actually were is the useful part: `confirmed`,
`verified`, `identified`, `decided`, `reviewed`. The model was not inventing,
it was **reporting**, and a threshold high enough to catch reporting verbs
catches nothing else.

### The ratio cannot see the dangerous case, so two exact checks sit above it

One invented name inside a faithful paragraph barely moves the ratio, and that
is exactly the failure that gets believed. So, checked exactly rather than
statistically:

- **Every number** in the summary must appear in the source. One false positive
  in ten (the source said "hundred USDC", the summary said "100"), fixed by
  reading number words as numbers.
- **Every capitalised word** that is not the first word of a sentence must
  appear in the source. One false positive in ten (`Whisper Flow's`), fixed by
  stripping the possessive. It catches `Priya`, `Friday` and `Kubernetes` in
  every fabricated sample.

### What this feature is NOT, and why

Summarising what was **dictated** needs no new capture, no diarization, no new
macOS permission and no network. Recording a **meeting** needs all four. The
competitors ship the second one and summarise it in their cloud, which is the
thing this product exists not to do. Building the first half is not a step
toward the second half, it is the half that is defensible on its own.

The second half was then built anyway, and everything measured while doing it
is below. The paragraph above was right about the cost and wrong about one
thing: diarization was never needed, because two tracks answer the only
question that matters.

---

## Recording a meeting

Measured on macOS 26.5.1 (build 25F80), SDK 26.2, Apple Silicon.

### The constraint that could have killed it did not

**Neither way of capturing system audio needs a paid Apple Developer account.**
That was the thing worth finding out first, and it is the answer:

| | Available since | Entitlement | Permission |
|---|---|---|---|
| ScreenCaptureKit, `capturesAudio` | macOS 13 | none | Screen Recording |
| ScreenCaptureKit, `captureMicrophone` | macOS 15 | none | Microphone |
| `AudioHardwareCreateProcessTap` | macOS 14.2 | none | the same grant |
| A virtual device (BlackHole) | any | none | a kernel driver install |

The app is signed with the same locally generated certificate the dictation app
uses, and `AudioHardwareCreateProcessTap` returned `noErr` under it. There is no
entitlement to buy here, so the $99 wall that closes off notarization does not
close off this.

### Core Audio process taps hand you silence rather than an error

This is the most expensive thing in this section and it is why the tap is not
what shipped. Run without the permission, on a self-signed binary:

```
AudioHardwareCreateProcessTap       st=0    tap=145
tap format                          st=0    48000Hz, 2ch
AudioHardwareCreateAggregateDevice  st=0    agg=146
AudioDeviceCreateIOProcIDWithBlock  st=0
AudioDeviceStart                    st=0
blocks=294   peak=0.0
```

Every status code says it worked. 294 IO blocks arrived. Every sample in all of
them was zero. The control that proves audio really was playing: the microphone
recorded the same speaker output over the same six seconds at peak **0.104**,
while the tap read exactly **0.0**.

No dialog appeared, and what macOS wrote instead was a row in the per-user TCC
database, `kTCCServiceAudioCapture` with `auth_value=0`, **against the
responsible process** (the terminal) rather than against the app.

ScreenCaptureKit, asked the same question with the same permission missing,
answers in words:

```
cannot see the system audio: The user declined TCCs for application,
window, display capture
```

An error you find in an hour. Silence you find three weeks later, when somebody
opens a transcript of a conversation that was never recorded. That is the whole
reason ScreenCaptureKit won, and it is not a performance argument.

### Audio only through ScreenCaptureKit, and what it costs

There is no audio-only content filter: system audio is captured as part of
sharing a display. What there is instead is a video side that can be made
nearly free, and `SCStream` does not require you to consume it:

```
cfg.capturesAudio = true            // everybody else, 48kHz stereo float
cfg.captureMicrophone = true        // you, a SEPARATE output (macOS 15+)
cfg.excludesCurrentProcessAudio = true
cfg.width = 2; cfg.height = 2
cfg.minimumFrameInterval = CMTime(value: 2, timescale: 1)
```

Two outputs are added, `.audio` and `.microphone`, and `.screen` is never
attached, so no frame is ever read. That `captureMicrophone` exists at all is
what makes two tracks cost one permission prompt and one clock, and two tracks
are what make "me" and "them" free. Diarization is never attempted.

### TCC attributes a permission to the RESPONSIBLE process, not the binary

Launching the bundle's executable directly from a terminal, even though it is
correctly signed and inside a correctly identified `.app`, put the microphone
request against **Terminal**. Launching the same bundle with `open` put it
against **com.dictator.meeting**, which is the only name the user can recognise
in the list. So the recorder is started through LaunchServices, and `-n` forces
a new instance because otherwise the arguments go to whatever copy is already
up.

### Asking for two permissions in one run silently denies the second

The screen recording request returns before the user has answered it. The
microphone request that followed it arrived while a decision was pending, and
macOS wrote

```
kTCCServiceMicrophone   com.dictator.meeting   auth_value=0
```

with no dialog ever shown. A denied row is much worse than no row, because the
app never asks again and the user is left with a switch to find rather than a
question to answer. One prompt per run: the microphone is only asked for once
system audio is already allowed.

### Nothing we could do raised a Screen Recording dialog on this machine

Tried, all of them refused instantly with `The user declined TCCs`, and none of
them created a row for the app at all:

- `CGRequestScreenCaptureAccess()` before the run loop, and inside it
- `SCShareableContent.getExcludingDesktopWindows` on its own
- as a plain command line binary, and as an `NSApplication`
- as `.accessory` (no Dock icon) and as `.regular` with `activate()`
- launched directly, and launched through `open`

The evidence for what is actually going on is in the database. Every one of the
**11** `kTCCServiceScreenCapture` rows on this machine has `auth_reason=4`,
which is the user setting it in System Settings. **Not one has `auth_reason` 2
or 3**, which is what a granted prompt writes, while microphone rows on the same
machine do have reason 2. So on this version of macOS this grant looks like a
System Settings action rather than a prompt, and `dictator meeting permissions`
is written for that: it reveals the bundle in Finder for the plus button and
watches for the switch, exactly as the Accessibility walkthrough already does.

**So the capture path is built, signed, wired and unproven on this machine.**
The transcription and notes half below is proven on real audio.

### Chunking: two failures that only showed up on real audio

Both were invisible in tests and obvious the moment a real multi minute
recording went through.

**1. Dropping a segment by its start time loses a whole sentence.** With three
seconds of overlap at each seam, the obvious filter is to ignore anything the
previous chunk already heard. Done by start time, it threw away a segment that
*began* inside the overlap and ran well past it. Measured against a known
script, the words at the 43 percent mark of one track simply vanished. A
segment is only skipped when the **whole** of it lies in the already-heard
stretch; what genuinely repeats is removed from the words instead.

**2. Whisper fills silence rather than reporting it.** A chunk that ended in
about twenty seconds of nothing came back with its last **forty spoken words
replaced** by a fluent sentence nobody said. Not `[BLANK_AUDIO]`, an ordinary
English clause that reads exactly like a transcript.

The fix for the second one is the design, not a filter: **chunk on speech, not
on the clock.** Stretches of talking are found from a loudness envelope, split
at any silence of three seconds or more, and joined back up only across gaps of
six seconds or less and only up to two minutes. Silence between chunks is never
handed to the model at all. On a meeting that is also most of the saving,
because most of the microphone track is the owner listening.

Overlap is still needed where somebody talks for longer than a whole chunk
without pausing. There, and only there, the cut goes to the quietest moment
within ten seconds of the target, three seconds are repeated, and the repeat is
removed by matching **words** rather than characters, because the two passes are
separate decodings of the same audio and their punctuation never agrees.

### whisper-cli loads the model once for a list of files

```
1 file    3.37s        3 files   3.17s
```

Same work, one model load. The load itself is 2.0 to 3.4 seconds with
`small.en`, against a few seconds of real work per chunk, so running chunks one
at a time would spend a third of a long meeting loading the same file. Chunks go
eight at a time: the load is amortised, and an interruption costs eight chunks
rather than the whole meeting.

`-pp` prints a percentage per file, which is what drives the progress line. The
percentage restarting is how the caller knows a file finished.

**The language is pinned once per track, not per chunk.** `-l auto` runs the
encoder twice on every chunk, and a meeting is one language setting, not one per
minute.

**Parakeet is not used here even on the English path**, and that is a decision
rather than an oversight. It is faster and more verbatim, and it returns no
timestamps, so a transcript built on it could not say who spoke when.

### What a meeting actually costs, measured

A 3 minute 24 second two track meeting, on this M3:

| | |
|---|---|
| audio recorded | 407s across two tracks, 13.0 MB |
| of which anybody was talking | 218.6s |
| chunks | 8 on one track, 7 on the other |
| transcription | **55.2s** |
| notes (three questions, model loaded and put away) | **73s** |
| words recovered against a known script | **100%** and **98.7%** |
| duplicated runs at the seams | none |

So roughly **one minute of transcription per four minutes of meeting**, which
puts a ten minute meeting at about 2.5 minutes and an hour at about 15. Disk is
**3.8 MB per minute** of meeting, both tracks, uncompressed 16kHz mono.

The notes call needed a **longer timeout than the recap's 30 seconds**. A
meeting stretch is twenty times the size of a dictation session and reading it
took more than that budget on a just loaded model. The symptom was a
"Discussed" section that was quietly missing while the other two were fine,
which is exactly the shape of failure this file exists for.

---

## macOS

### Permissions are granted to a code signature, not to a path or a name

This is the fact everything else follows from.

| Signing | What a downloaded copy does |
|---|---|
| Unsigned | Does not run at all on Apple Silicon |
| Ad-hoc (`codesign -s -`) | Gatekeeper blocks it. **And** the TCC identity is the binary's cdhash, so every rebuild is a brand new app that has been granted nothing |
| Self-signed | Identical to ad-hoc as far as Gatekeeper is concerned. Buys only a **stable** identity, which is worth everything locally and nothing on anyone else's Mac |
| Developer ID, not notarized | Still blocked. Notarization has been required since Catalina |
| Developer ID + notarized + stapled | One "downloaded from the internet" confirm |

**There is no free path to notarization.** A free Apple account explicitly does
not get Developer ID certificates. It is **$99 a year**, and that is the entire
cash cost of the product existing for non-technical people.

The override is worse than folklore suggests: **control-click Open was removed
in Sequoia**. Apple's own page now says System Settings, Privacy & Security,
scroll, "Open Anyway", then a second warning.

### The tick in System Settings and the trust macOS acts on are two different things

This is the failure that costs days rather than minutes, and it was live on the
owner's own machine while this was written.

TCC keeps a row per (service, client) and stores a **code requirement** next to
it. The list in System Settings is drawn from the row. Trust is decided by the
requirement. Change the app's signature and the row survives with the old
requirement, so:

- the checkbox stays ticked,
- `AXIsProcessTrusted()` stays false,
- and **no prompt ever appears again**, because a row already exists.

The measured state, read straight out of the databases:

```
system TCC.db  kTCCServiceAccessibility  com.dictator.dictation  auth_value=2
               certificate leaf = H"cbd3aabec79d29dcfc329c1bbba154709b13462a"
the bundle     certificate leaf = H"8501b12ce31fe51f7ee209340e355c18398a0d23"
```

Read out of the pane at the same moment, through the accessibility API:
`Dictator :: 1`. The switch really was on. The listener really was waiting.

**Toggling that switch does not fix it.** It rewrites `auth_value` and leaves
the requirement alone, which is the half that is wrong. The entry has to be
**removed** so the next ask writes a fresh one, which is the minus button, and
nothing in the product used to say so.

Two other facts fall out of this and are worth keeping:

- **Accessibility and Input Monitoring live in the machine-wide database**
  (`/Library/Application Support/com.apple.TCC/TCC.db`) and Microphone lives in
  the per-user one. Looking in the wrong one reports "never granted" for a
  permission granted months ago. On the same machine, in the same minute,
  Microphone read `granted` and Accessibility read `stale`, because the mic
  prompt fires again after a signature change and the Accessibility one does
  not.
- **Reading either database needs Full Disk Access for whoever is reading.**
  The app bundle itself does not have it, so the app's own diagnosis is always
  the by-eye version; a terminal that has been given Full Disk Access gets the
  exact answer, including which certificate the grant was written for. There is
  no unprivileged API for this, `tccutil` only resets.

Two system tools do the work and neither needs privileges:

- `/usr/bin/csreq -r <blob> -t` turns a stored requirement back into the text
  `codesign -d -r-` prints, so the two can be shown side by side.
- `codesign --verify -R=<text> <app>` asks the same question TCC asks. Note the
  **equals sign**: `-R <text>` treats the argument as a file path and fails with
  "invalid requirement specification", which reads like a malformed requirement
  rather than a wrong flag.

### Wording, read off the pane rather than remembered

On macOS 26.5.1 the shipped `SecurityPrivacyExtension.appex` localization table
gives the exact strings, which is worth using instead of a screenshot or a
memory:

- the list is headed **"Allow the applications below to control your computer."**
- the two buttons under it are labelled **"Add"** (the plus) and **"Remove"**
  (the minus)
- an empty list reads "Applications that have requested access to control your
  computer will appear here."

### A process launched from a trusted terminal is trusted, which hides this bug

Running the app bundle straight from Terminal reports
`AXIsProcessTrusted() == true` even when its own TCC entry is stale, because
macOS attributes responsibility to the launching application and Terminal has
the grant. Launching the same bundle with `open` or through `launchd` reports
false. So the broken state **cannot be reproduced from a shell**, which is
exactly why it kept being reported as working.

### The signing keychain, and how it can rot

A self-signed certificate in its own keychain under `~/.dictator` gives a
stable identity with no Apple account and no password prompt. Two details are
easy to get wrong and silent when you do:

- **codesign only looks at keychains on the search list.** Passing
  `--keychain` alone reports "no identity found", and with stderr swallowed
  the build looks fine while leaving the ad-hoc signature in place.
- **`list-keychains -s` replaces the list**, it does not append. Read the
  existing entries back and pass them through, or you evict the login
  keychain.

And the failure mode that actually bit: a PKCS12 import failed once, leaving a
keychain that existed and contained nothing. Because the check was whether the
**file** existed, every later run reported the identity as present, codesign
found nothing, and the app was silently ad-hoc signed from then on.

The repair is dangerous in the other direction. **Rebuilding resets every
permission the user has granted**, so an over-eager check is expensive: one
false negative replaced a certificate that had been working for hours and
silently revoked Accessibility and Microphone. Only the certificate being
genuinely **absent** justifies a rebuild. A failed test sign with the
certificate present is logged and otherwise ignored.

### Reading the focused text field

- The documented route, asking the **system-wide** element for
  `kAXFocusedUIElement`, returns `kAXErrorCannotComplete` (-25204) even in a
  process `AXIsProcessTrusted()` reports as trusted.
- Asking the **frontmost application** for the same attribute works.
- Terminals hand back the whole scrollback rather than the line being edited.
- **Terminals are read-only through AX**: both `AXSelectedText` and `AXValue`
  come back `settable=false`. So inserting text directly, which is what a
  competitor almost certainly does, is not available where this is used most.

### Getting words onto the screen

| | Cost |
|---|---|
| Paste (Cmd-V) | One event whatever the length. But it is a paste, and Claude Code turns a long one into an attachment |
| Type (synthetic key events) | Two events per character, needs a gap between them, about half a second per 300 characters |
| Direct AX insertion | Not available in terminals |

**Claude Code's paste threshold, read from the shipped bundle and confirmed
live: 800 UTF-16 units, or more than 2 newlines.** "Five or six lines" is that
character limit seen through terminal wrapping. Verified: 799 characters
inline, 801 a chip, four separate 600 character pastes all inline.

**Synthetic typing does NOT mangle non-ASCII**, which is the usual reason
people reject it. `keyboardSetUnicodeString` carries the character with the
event rather than looking it up from a key code. Devanagari and emoji both
went through.

`osascript` is a separate binary and **never inherits the app's Accessibility
grant**. Falling back to it fails with error 1002 every time, and overwrites
the clipboard on the way out.

---

## Distribution

Checked against eight local-first Mac tools (Ollama, LM Studio, MacWhisper,
VoiceInk, Superwhisper, Wispr Flow, Rectangle, Raycast):

- **Every one ships a plain `.app` in a `.dmg` or `.zip`.** Not one uses a
  `.pkg`. Not one is Mac App Store only.
- **Not one bundles a usable model.** All download on first run with a
  progress UI.
- Step counts to working are 8 to 15. The target is not "fewer steps than
  everyone", it is "the same steps, none of which are a terminal".

**The Mac App Store is closed to this product**, on two independent rules:
2.4.5(i) requires sandboxing, and a session-wide `CGEventTap` plus posting
keystrokes into arbitrary apps is exactly what the sandbox prevents; 2.4.5(iv)
forbids downloading resources that add functionality, which the 2.2GB of
models are.

### Sizes, measured

```
code (whole checkout)   1.0 MB     of which 672KB is the Hindi lexicon
whisper-cli             643 KB     (3.2MB for the whole static set)
sox                     2.4 MB     plus 12 Homebrew packages, and is GPL
dictator-rec              65 KB    what replaced it, using only AVFoundation
models                  2261 MB    74 + 638 + 1549
```

The code is 1MB and the download is 2.3GB. It is all models.

**sox cannot be bundled**: `GPL-2.0-or-later AND LGPL-2.1-or-later`.
`AVAudioRecorder` replaces it in 40 to 60 lines of Swift and gives a real
level meter for free.

### The recorder, replaced and measured

`native/record.swift` is 145 lines including its comments, compiles in **1.4s**
to a **65KB** binary, and depends on nothing that is not already on the machine.
`brew deps sox` lists **12** packages (ca-certificates, flac, lame, libogg,
libpng, libsndfile, libvorbis, mad, mpg123, openssl@3, opus, opusfile) to
capture one mono stream.

Format out of `AVAudioRecorder` with `kAudioFormatLinearPCM`, read back with
Python's `wave`: **16000Hz, 1 channel, 16-bit**, which is exactly what whisper
wants and what sox was being asked for. A sentence played at the speakers and
recorded through the mic came back from `stt.transcribe_ex` as itself, word for
word. macOS does the resampling from the device's own rate; asking for 16kHz is
enough, there is no converter to write.

Latency, same machine, same microphone, time from spawn to the first audio in
the file, and audio captured against 1.5s of wall clock:

```
native, warm      0.08s to first bytes    1.40s captured
sox               0.50s to first bytes    1.25s captured
native, cold      0.54s to first bytes    0.94s captured
```

So the new recorder does not just remove a dependency, it loses **0.15s less of
the start of every sentence** than sox did. "Cold" is the first execution of a
freshly written binary (dyld and signature checks) and is paid once, which is
one more reason to compile at install time rather than on the first hold.

Level metering: `isMeteringEnabled` plus `averagePower(forChannel:)` is the
input itself, whereas the old meter inferred loudness from the RMS of whatever
had reached the disk. The recorder publishes it to `<wav>.lvl` every 0.05s and
deletes it on stop, so a meter can never show the last level it heard while the
microphone is closed. Both paths land on the same 0..1 curve, so nothing
downstream had to change.

**Terminate, never kill.** `AVAudioRecorder` writes the RIFF and data chunk
sizes at `stop()`, so a SIGKILLed recorder leaves a WAV whose header claims no
audio. The recorder handles SIGTERM for exactly this, and sets `SIG_IGN` first
because the default action kills the process before the dispatch source ever
sees the signal.

### A recording that stops on its own, and why the file cannot tell you

`AVAudioRecorder` stops when the input device changes underneath it, which is
what a Bluetooth headset connecting mid sentence does. It leaves a **valid**
WAV: correct header, correct rate, holding the first few seconds. So every
check downstream passes, `loudness` is fine, whisper transcribes it happily,
and the user is handed part of their own sentence with a capital letter at the
front and a full stop at the end. There is nothing in the file that says it is
a fragment. This is the same shape as the paste receipt that lied: silent, and
the wrong answer is the believable one.

The recorder's own exit code is the only place the difference can live, so:
**0 ended when it was meant to** (we terminated it, or max-seconds came up),
**1 never started**, **5 started and was stopped early**. The number is written
down in `native/record.swift` and in `recorder.py` and a test asserts they
still agree, because there is nowhere for Swift and Python to share a constant.

Two things about this were not obvious and both were checked by running it:

- **Calling `stop()` fires the same delegate callback an interruption does.**
  `audioRecorderDidFinishRecording(successfully: true)` arrives for our own
  stop, for reaching max-seconds, and (as far as the callback is concerned)
  for an input that went away. A delegate alone therefore reports every
  ordinary hold as cut short, which is a worse lie than the one being fixed.
  Two things separate them: a `stopping` flag set before `stop()`, and whether
  the recorder's own clock had reached max-seconds. Measured: terminate at
  1.2s of a 60s cap exits **0**, running to a 2s cap exits **0** with 2.0s of
  audio, and an external stop at 1.0s of a 60s cap exits **5** with 1.01s of
  audio and a readable WAV.
- **A route change could not be reproduced on this machine.** There is exactly
  one input device (the built-in microphone) and no second one to switch to,
  so what was tested is the decision, by stopping the recorder from outside,
  which is what losing the device does to it. Whether AVFoundation delivers
  that callback on a real Bluetooth connect is **not verified here**.

What to do about a cut recording is a separate question from detecting one,
and the answer is **transcribe it and say so**, not discard it. This file
already records that never losing what was said is what decides whether people
trust one of these tools, and `paste.py` leaves the whole text on the clipboard
when delivery fails for the same reason. Part of a sentence is worth more than
none of it. What must not happen is delivering it as though nothing went
wrong, so the reason is said before the transcript and written to
`core.surface_error`, which is the channel that survives a listener running
under launchd with no terminal for anyone to be watching.

### What a static whisper.cpp build would take

Not done. Here is what was measured, so the decision does not get re-derived.

The Homebrew binary **cannot be copied and shipped**, and this is the concrete
blocker rather than a licensing one (whisper.cpp is MIT):

```
$ otool -L /opt/homebrew/bin/whisper-cli
  @rpath/libwhisper.1.dylib
  /opt/homebrew/opt/ggml/lib/libggml.0.dylib
  /opt/homebrew/opt/ggml/lib/libggml-base.0.dylib
```

Two of those are absolute paths into another machine's Homebrew prefix, and
`ggml` is a separate formula, so there is no version of "just include the file
we already have" that works.

What it needs: `cmake` (not installed on this machine, so it becomes a build
dependency for whoever cuts a release, not for the user), a checkout of
whisper.cpp, and
`cmake -B build -DBUILD_SHARED_LIBS=OFF -DGGML_METAL_EMBED_LIBRARY=ON`, with
`-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"` if Intel Macs are in scope.
`GGML_METAL_EMBED_LIBRARY` is what removes the loose `.metal` shader file, so
the result is one binary.

Two things that are easy to miss:

1. **`parakeet-cli` has to come too.** The fast English path is Parakeet, and
   it ships from the same formula (`libparakeet.1.9.1.dylib`, 166KB). Shipping
   `whisper-cli` alone would leave every English hold on the slow path while
   doctor reported everything fine.
2. **`_find` only looks on PATH and in the Homebrew prefixes.** A bundled
   binary needs its own directory added there, or it will sit in the checkout
   unused, which is the failure this file already has four entries for.

Gatekeeper does not object on the current install path: `curl` does not set the
quarantine attribute, so a binary fetched by the installer or cloned with the
repo runs. The same binary inside a downloaded `.zip` or `.dmg` is quarantined
and blocked, so this buys nothing towards a double-clickable app until
notarization is paid for. It is worth doing to remove the last Homebrew
package, and it is a release-engineering job (a per-version rebuild, a
universal binary, and about 3.2MB committed or attached to a release) rather
than a code change.

---

## The bug family that keeps recurring

Four times now, in the same shape: **something that knows how to do the work,
and nothing calling it from where the work happens.**

1. `ensure_whisper_server()` had no callers, so every transcription paid a
   cold model load. It only ever looked fast because another install happened
   to be serving the same port.
2. `ensure_model()` had no callers, and would have fetched the wrong model
   anyway. A fresh machine had nothing to transcribe with.
3. `jellyfish` was never installed by the installer and never checked by
   doctor. Without it the entire vocabulary and learning feature does nothing
   at all, silently, because the import is inside a try.
4. The paste helper was only used if it happened to exist. Deleting it once
   sent every delivery down a path that cannot work.

**They all pass every test.** The lesson is that a test which exercises a
function does not prove anything calls it, and the symptom is always the same:
the feature is simply absent while everything reports fine.

Related: **an error handler that itself crashes**. `mac.py` called `core.log`
in its error paths without importing `core`, so any failing osascript raised
`NameError` out of the handler.

---

## Things we assumed and were wrong about

- That the English `initial_prompt` was hurting Hinglish. It helps.
- That a warm whisper server is faster. Not on this machine, once the CLI can
  size its window.
- That synthetic typing mangles non-ASCII. It does not.
- That `find-identity` tells you whether a keychain can sign. It reports zero
  for a working self-signed setup.
- That a missing paste receipt means the paste failed. A busy application just
  takes longer than the timeout.
- That a single modifier tap inside a hold is a usable gesture. It cannot be
  told apart from someone pressing shift while they talk, and it ate several
  dictations before anyone worked out what it was.

---

## The model field (researched, not yet benchmarked)

### Nobody ships a local Hinglish model. Not one.

Checked: Wispr Flow, Superwhisper, MacWhisper, VoiceInk, Aqua Voice.

**Wispr Flow is cloud only**, their own docs: "Wispr Flow processes dictated
audio in the cloud", "Transcription always happens in the cloud". They are a
**router over other people's engines**, their CTO's post: "Flow dynamically
selects the most accurate ASR engine for each language", naming ElevenLabs
Scribe and Gemini as components. Hindi is in their top tier. And romanised
Hinglish sits under a heading that reads **"Ongoing code-mixing experiments"**.
They also route **per utterance, not per word**: "if you switch languages mid
dictation, the language you spoke longest is recorded".

**VoiceInk** is open source, and a search of the whole repo for Hinglish,
romanisation, code-mixing and transliteration returns **zero hits**. Hindi
appears only as a locale string. That is a confident true negative.

So the gap is real and currently unoccupied.

### The candidate: `Oriserve/Whisper-Hindi2Hinglish-Apex`

Apache-2.0. A fine-tune of **the exact checkpoint we already ship**
(whisper-large-v3-turbo, 32-layer encoder, 4-layer decoder, 128 mel bins). It
emits **Latin script only**, never Devanagari. ggml conversions already exist:
q8_0 at **874MB** against our current **1549MB**.

Switching is a filename change in `SHIPPED` and `_ML_MODELS`. No new runtime,
no new code path, and the model is smaller.

The structural win is bigger than the accuracy one: it takes `roman.py` off
the critical path. Our own docstring names the limit we live with, that an
English word the recogniser committed to Devanagari cannot be recovered
("pull request" comes back as "pool rekvest"). **A model that never emits
Devanagari cannot make that error.**

Two real risks: it was trained on Hindi, not on code-mixing, so whether it
holds "pull request" as English inside a Hindi sentence is exactly the
untested thing. And it **cannot produce English prose**, so the router stays.

### Their published numbers are worthless, and here is the proof

The Apex card says, in their own words: "the original Hindi ground truth was
first transliterated to Hinglish. The WER scores below were calculated against
this transliterated reference text." So the references are Latin and the
baseline emits Devanagari.

The proof is on the Swift card, where the baseline scores **106.79, 104.28 and
110.84**. A WER above 100 percent is not a measurement of recognition, it is a
measurement of the alphabet. Every "42 percent improvement" headline from this
family should carry no weight.

What the table **does** say honestly is the part nobody quotes, because Prime
and Apex are the same family in the same script and are mutually comparable:
Prime wins on Common Voice and FLEURS (read speech), **Apex wins on
Indic-Voices by 13 points** (47.64 against 60.82). Indic-Voices is spontaneous.
A hold of the fn key is spontaneous.

**There is no published number anywhere, from anyone, for code-mixed
Hinglish that is both fairly scored and recent.** Not from Oriserve, not from
Sarvam, not from Wispr. That is the most important line in this section.

### The table to show anyone who quotes the 42 percent

Vistaar / IndicWhisper (arXiv:2305.15386), Hindi, all Devanagari, one metric,
seven shared test sets, averaged:

| | Hindi WER |
|---|---|
| Google STT | 23.9 |
| IndicWav2vec | 21.0 |
| Azure STT | 20.0 |
| Nvidia large | 18.6 |
| IndicWhisper | 13.6 |

**Whisper-family Hindi, scored properly against Devanagari references, sits in
the teens.** Oriserve shows Whisper Large V3 at 50.84 to 82.56 on the same
language. The gap between those two pictures is the alphabet, not the
recognition. Show both tables together to anyone citing "42 percent better
than Whisper".

This does not make IndicWhisper a candidate. It is Devanagari-output, so it
keeps roman.py load-bearing. The point is only that the baseline Oriserve
beats was never as bad as their column makes it look.

### Two things that RAISE confidence in Apex

**Indic-Voices deliberately contains code-mixing.** From the dataset paper
(arXiv:2403.01926), translators "were instructed to do a colloquial
translation which contains code-mixing to reflect real world usage". The paper
publishes no WER of its own, so every Indic-Voices number is a downstream
party scoring their own model. But it means Indic-Voices is the one Oriserve
set that actually contains code-mixed spontaneous speech, **and it is the one
where Apex beats Prime by 13 points.**

**AI4Bharat does no code-switching at all.** A search of the full Vistaar text
for code-mix, hinglish and roman returns zero hits. That whole family is
monolingual Hindi work, however good it is at that.

### T-WER: the fair metric does exist, and we should use it

From the MUCS 2021 challenge (arXiv:2104.00235): "T-WER will count an English
word in the reference correct if the hypothesis contains either the English
word or its transliterated form in the native script."

That is the honest version of what Oriserve did, and it predates them by
years. It is cheap to implement with the Dakshina lexicon already shipped here,
read in reverse.

Published MUCS Hindi-English code-switched numbers, for scale only: WER 24.66
(GMM-HMM), 29.03 (Kaldi TDNN), 31.19 (Transformer); T-WER 22.72, 26.20, 29.80.
These are 2021 architectures on spoken-tutorial audio. **Do not put them in the
same table as anything modern.**

So the benchmark below should report four numbers, not three. T-WER is the one
citable against published work. WER-sound stays primary, because T-WER does
not solve arbitrary romanisation variance inside Hindi words (chahiye against
chahie), which is the reference-writing problem. And ENG-exact stays the one
to publish if only one is published, because nothing else measures it.

### The runner up, and what it would cost

`moorlee/qwen3-asr-0.6b-hinglish` is the only model trained on genuinely
code-switched audio, and its output shape is arguably the right one: English in
Latin, Hindi in Devanagari (`मेरा favourite festival Diwali है`), which is
exactly what `roman.py` was designed to receive and never got.

But it is a Qwen3-Omni derivative. whisper.cpp cannot load it; it needs
llama.cpp with a separate audio projector, a second resident server, and a
GGUF conversion of the fine-tune that nobody has made. That is a week, not a
filename. Triage it by hand on the HF demo space before building anything.

### Ruled out, with reasons

- **Sarvam Saaras**: API only. Their HF org has 14 repos and **zero ASR
  models**, verified. Using it means audio leaves the machine.
- **indic-seamless, MMS, SeamlessM4T v2**: cc-by-nc, non-commercial.
- **SraVaani, indic-conformer-600m**: MIT but **gated**, which cannot go
  behind `curl | bash`.
- **Vaani, vasista22, collabora, IndicWhisper, IndicConformer**: all
  Devanagari-only, so every one keeps `roman.py` load-bearing and keeps
  "pool rekvest". Better Hindi models, not better Hinglish ones.
- **Parakeet, Canary, Moonshine, Kyutai, distil-whisper, Phi-4**: no Hindi.
- **Voxtral, Qwen2-Audio, Granite**: 4B to 7B, 9GB, fail on latency.

### Fine-tuning on our own corrections is impossible, and that is correct

`history.db` stores heard, shown and kept, which is the right schema. But ASR
fine-tuning needs **audio** paired with corrected text, and we deliberately
store none. The docstring is proud of that and should be.

What the corrections are actually for: they are the **benchmark set** (every
row where kept differs from heard is a real failure on real audio with a
hand-written reference), and they are the `initial_prompt`.

### The benchmark to run before switching anything

40 held utterances, **recorded on a real voice**, never TTS. We already learned
that the hard way: small beat turbo on synthesised speech and lost badly on a
real one.

Composition: 15 work Hinglish with English technical nouns embedded, 10 mostly
Hindi, 5 mostly English with Hindi markers, **5 pure English as a regression
guard**, 5 hard cases.

Three numbers, because plain WER is the wrong instrument (it counts "chahiye"
against "chahie" as an error when both are correct):

1. **WER-strict**, for honesty.
2. **WER-sound**, the same alignment after mapping both sides through
   `hindi.key()`, which already normalises exactly the arbitrary variation.
   This is the "did it hear the words" number.
3. **ENG-exact**, over only the English tokens in the reference. **This is the
   "pool rekvest" detector**, and nothing published anywhere measures it.

Plus seconds per utterance and script-leak rate.

Decision rule, written before seeing results: a model wins if it improves
WER-sound **and** ENG-exact, does not regress the 5 pure-English utterances,
and costs no more than one extra second.


---

## Spokenly, the closest competitor

A solo developer's product doing the same job. They published their own
Parakeet versus Whisper comparison, which is the routing decision this product
already makes, so it is worth reading as a check on our own engineering.

### What the article actually is

**It contains no WER number, no latency number and no hardware.** Every
quantitative claim points at the Hugging Face leaderboard. This file contains
strictly more measured data on the question than the vendor's own comparison
article does.

Where they agree with us, and it is the load-bearing agreement: **Parakeet has
no Hindi**, Whisper is the right answer for code-switching, and **terminals
defeat Accessibility reads**. That last one is two independent teams hitting
the same wall from opposite sides. Their docs say they skip their spacing
rules in terminals because those "draw their own text view"; we measured
`settable=false` on both attributes.

Where they are silent and we have data: Parakeet's failure modes (they do not
mention it can invent text), `audio_ctx` sizing (our 4554ms to 1840ms win
appears nowhere in their material), quantisation being a trap on Metal, and
language detection being unsafe on short holds.

**Nothing in the article contradicts a measured number here.**

### What they got wrong, checked against primary sources

- **"Parakeet leads the Open ASR Leaderboard."** Stale by about a year, beaten
  by NVIDIA's own Canary-Qwen-2.5B (5.63 against Parakeet's 6.05).
- **"Parakeet V3 covers 25 languages."** Verified: all 25 are European. **Zero
  Indic, zero East Asian, zero Middle Eastern.** The table, the recommendation
  box and the FAQ all say bare "25 languages". For anyone in this market that
  is the most misleading line on the page.
- **"Parakeet needs Apple Silicon or an NVIDIA GPU."** That is a property of
  their CoreML implementation, not of the model.
- **"Whisper is slightly behind on clean English."** 6.05 against 7.83 on the
  leaderboard average is a 29 percent relative gap, not "slightly".

### Where they are genuinely better

1. **Distribution, and it is the biggest gap by a distance.** A 19MB `.dmg`,
   a real Homebrew cask in `homebrew/cask` proper, the Mac App Store, Windows,
   Linux and iOS. **They have already paid every toll we have identified and
   not paid.** No amount of Hinglish accuracy closes this.
   They ship **two Mac builds** because the sandboxed App Store one loses
   features, which is exactly the constraint recorded above under rule
   2.4.5(i). They solved it by shipping both rather than choosing.
2. **Insertion polish**: Smart Spacing, Smart Paragraphs, Quick Send. Small,
   felt on every dictation, and we have none of the three.
3. **A legible privacy story.** "Local Only Mode blocks all network
   connections, allowing localhost" is a switch a user can point at. Ours is
   stronger by default and less legible, which is a README problem.

### Where we are better

1. **Hinglish, and it is not close.** One mention of Hindi in their entire
   93KB documentation corpus, and it is about paragraph breaks. No Indic local
   model, no romanisation, no code-mixing, no acknowledgement the problem
   exists.
2. **Automatic routing.** They ask the user to pick a model per task, in
   advance. **A person who mixes two languages inside one sentence cannot
   choose in advance.** Their architecture has nowhere to put this.
3. **Learning from corrections: they have none.** Their vocabulary story is a
   manual dictionary that only works with cloud models and caps at 50 terms.
   This is the clearest place we are ahead.

### Worth taking

- **Quick Send.** Press Return while still recording: it stops, inserts, and
  simulates Return so the message sends. Their docs name Claude Code as the
  best use case. If focus moved, the Return is skipped so it cannot fire in
  the wrong window. Highest value per line on the list.
- **Smart Spacing.** Read the character either side of the cursor via AX,
  insert a space if there is a letter, lowercase the first character if the
  previous one was not `.`, `?` or `!`. No model at all.
- **Smart Paragraphs**, off by default. They published their constants: break
  at 45 words or 4 substantial sentences, always at a sentence boundary.
- One free piece of engineering intel: **Claude Code has a 60 second timeout
  on HTTP MCP connections**, which is why they ship a stdio bridge instead.
  Relevant to voicebridge rather than here.

### Worth refusing

- **A user-facing prompt box.** They ship a docs page teaching users to write
  a 224-token whisper prompt. We measured that the prompt was never the
  problem, and that changing it makes things worse. Exposing it hands users a
  knob instead of a fix.
- **Modes**, a saved profile carrying a model, a provider, a prompt, scripts
  and a shortcut, with a five-level precedence table. That is a settings panel
  wearing a product. For a hold-to-talk tool the router choosing correctly IS
  the feature, and their manual switching is the thing we beat them on.
- Agentic actions, trigger words, tapping the chassis, and the cloud roster.

### The honest summary

They win on everything except the one thing the product exists for. A user
picks us if they mix Hindi and English inside one sentence and want Latin
script out, or if they refuse to send audio anywhere. They pick Spokenly if
they want it working in five minutes with no terminal, or on Windows, or on a
phone.

## Wispr Flow, the market leader, and what of it can exist offline

Researched September 2026 from their own site, help centre, changelog, App
Store and Microsoft Store listings, and their model-hosting vendor's write-up.
Everything quoted below is theirs, verbatim, so that nothing here rests on a
reviewer's paraphrase.

### The one sentence that decides the whole comparison

From wisprflow.ai/data-controls:

> Transcription always occurs on the cloud. This is the best way for us to
> provide accurate, low latency transcription.

There is no offline mode, no on-device model, and a dedicated support article
saying you cannot even upload an audio file. Their security FAQ says the same
thing in different words. So the honest way to read their feature list is not
"what do they have that we do not", it is "which of these could exist at all
without a server", and the answer is: very few of them, and the few that can
are the ones we had not built.

Two smaller facts worth knowing before quoting their privacy page at anyone:
model improvement (training on your audio, transcripts and edits) **defaults
ON for Free and Pro**, and **signing out resets cloud storage to enabled**.

### The inventory, with the only column that matters

| Theirs | What it is | Can it be local | Ours |
|---|---|---|---|
| Push to talk, hands free | hold a key, or double tap to latch | yes | have both |
| Auto Edits / Backtrack | LLM removes false starts and self-corrections | **no** | filler removal only, deterministic |
| Auto Cleanup, 4 levels | LLM rewrites for "clarity and conciseness" | **no** | refused, see shape.py |
| Smart Formatting | punctuation, capitals, lists | yes, and ours is | have |
| Styles | Formal, Casual, very casual, Excited, per app category | **yes, this is just which caps and punctuation rules are on** | BUILT, see below |
| Transforms | rewrite selected text by prompt, 9 custom | **no** | refused |
| Command Mode | speak an instruction, it edits the text | **no**, and paid tier only | refused |
| Context Awareness | screen text, selected text, code symbols, **screenshots**, uploaded with your audio | capture yes, use no | refused |
| Dictionary | manual words, plus auto-add on spelling correction | yes | have, and ours learns by sound |
| Snippets | say a phrase, get fixed text | **yes, entirely** | BUILT |
| Flow Bar | floating status bubble, dockable | yes | orb, smaller |
| Scratchpad | tabbed local rich text notes | yes | not built, not wanted |
| History | list by date, tap to copy, audio playback 14 days | yes | have list; **search BUILT** |
| Usage dashboard | wpm, totals, heatmap, streaks, leaderboard | yes | not built, see below |
| Whisper mode | dictating quietly | model property | nothing to build |
| 100+ languages | one language per dictation | model property | see the next paragraph |
| Notetaker | meetings, system audio, summaries, MCP | **no** | issue #5 |
| Mobile, teams, SSO, SCIM | | n/a | issue #9 |

### Their multilingual claim is weaker than ours, in writing

Their own docs: **"Flow detects one language per dictation, not per word."**
With Chinese and English both selected, "English words can appear in Chinese
characters or vice versa".

They do have a Hinglish model, and it is a serious bet rather than a checkbox:
they employ linguistics PhDs on it, they say India is their second market by
revenue, and they published the same conclusion we reached independently, that
a Hinglish speaker wants Latin script and not Devanagari. An Indian reviewer's
six month hands-on calls the accuracy "surprisingly good". So this is not a
competitor to be dismissive about on the one axis this project cares about.

But two lines in their own help centre describe the shape of the gap exactly:

> Select Hinglish, not Hindi or English. Auto-detect never produces Hinglish,
> so select it explicitly.

And selecting Hinglish removes Hindi as an option, because the two conflict.
So for them Hinglish is a **third discrete mode the user picks by hand**, it is
invisible to their own language detection, and a person who dictates Hinglish
into one field and plain English into the next is changing a setting between
them. That is the second competitor in a row (after Spokenly's Modes) whose
architecture puts the language decision in front of the user, and it is the
same argument in both cases: somebody who mixes two languages inside one
sentence cannot choose in advance. Automatic routing is not a convenience
here, it is the feature.

### "Styles" is a marketing word for a boolean

Their Styles feature reads as tone control and is not. Reading the actual
definitions: Formal is "caps and punctuation everywhere", Casual is "caps,
reduced punctuation", very casual is "no caps, minimal punctuation". That is
two flags, chosen by an app category their client already knows. Everything
above the flags (which words to use, how to sound) is the Auto Cleanup LLM,
which is a different feature with a different switch.

So the buildable half is per-application formatting flags, and it is
deterministic, and it is `profiles.py`. The rule that makes it safe is that an
override may only move a flag the caller already had: these flags are passed
to `shape()` as keyword arguments, so a stray key in a hand-edited file would
not be a formatting mistake, it would be a `TypeError` inside the delivery
thread, and the only symptom the user would see is a hold that produced
nothing.

Terminals are one group rather than an entry per emulator, and the membership
test is `paste.py`'s, which already had to know what a terminal was. Two lists
of terminal emulators in one codebase drift the first time somebody installs
a new one.

### Snippets are the clearest thing they charge for that needs no server

Voice triggered text expansion, on every tier including free: trigger up to 60
characters, expansion up to 4000. There is no part of this that needs a model,
and we did not have it.

It is also the single most requested thing in the user chatter, in a way that
crosses products. People end up building a replacement table by hand and then
talk about it as though it were a hack rather than the feature:

- a Wispr Flow user keeping a dictionary rule mapping "asian" to "agent",
  which is a phonetic correction done with a string replacement
- somebody listing what the free alternatives lack: "dictionary, shortcuts
  (say 'linkedin link' and it pastes your actual link)"
- Superwhisper shipping the same thing under two names, Vocabulary (hints fed
  to the model) and Replacements (deterministic, no AI), and leading their
  documentation of it with symbols: say "at sign", get `@`
- VoiceInk shipping "Smart Replace" alongside its dictionary

Three of the four are deterministic substitution, not recognition. Which is
the point: for a term the model cannot be taught, a table is not a fallback,
it is the correct mechanism.

Ours differs in one place that matters. Theirs blocks duplicate triggers.
Ours refuses a trigger **you have already dictated**, with the count, checked
against your own history at the moment you create it:

```
$ dictator snippet "check the loop" "https://example.com/loop"
not added: you have already dictated that phrase 7 times, so it would start
replacing things you meant to say.
```

This is the same move `vocab.admit` makes with `spoken()`, and for the same
reason. A guard the user meets while making the mistake can explain itself; a
guard that fires silently three weeks later cannot. `--anyway` overrides it.

Both new stages sit on the hold path, so their cost was measured rather than
assumed. With 30 snippets stored, against a 19 word Hinglish line:

| | |
|---|---|
| expansion, nothing matched | 0.12 ms median of 200 |
| expansion, one match (includes writing the use count back) | 0.38 ms median of 200 |
| `shaping_flags(app)` with a per application rule set | 0.03 ms median of 500 |

Dictation itself is 4.8 seconds on this machine (see "Latency: where the 4.8
seconds goes"), so all three are four orders of magnitude below the thing they
sit next to. No caching, no lazy loading, nothing to tune.

The other rule is a two word minimum. One spoken word is something a person
says by accident a hundred times a day, and every text expander horror story
is a one word trigger.

### Searching the history: measured, and no index is needed

`dictator find` scans every row in Python rather than keeping a full text
index. Measured on this machine with a synthetic history of 20,004 rows, which
is roughly six months of heavy dictation:

| | |
|---|---|
| SQLite fetch of all 20,004 rows | 67 ms |
| the whole of `find()`, matching query | 117 to 152 ms |
| the whole of `find()`, matching nothing | 114 ms |

An index would save at most a tenth of a second on a command a person runs a
few times a week, and would cost a second copy of the text and a way for it to
fall out of step with the rows. Revisit at roughly 200k rows.

It searches `heard`, `shown` and `kept`, not just what landed. Searching only
the final text fails precisely when the recogniser did, which is the case
where the history is the only record of what actually happened.

### What was deliberately not built, and why

- **Auto Cleanup, Transforms, Command Mode, Backtrack.** All four are an LLM
  rewriting the user's words. Three of them need a cloud model. The fourth,
  Backtrack, has a deterministic core ("scratch that" as a spoken command,
  like "new paragraph") and is the only one worth revisiting; the rest of it,
  inferring a self-correction from "actually", is a guess about meaning and
  shape.py exists to refuse those.
- **Context Awareness.** Their own privacy page lists screenshots, on-screen
  text and conversation history among what is captured and says it "can
  accompany your dictation". On this product it would need a new macOS
  permission and would break the one promise being made.
- **The usage dashboard.** Words dictated, streaks, a heatmap and a team
  leaderboard. `history.stats()` already computes the honest half of it and
  nothing asks for it, which is the correct amount of demand. A streak counter
  is a retention mechanic for a subscription, and this is not one.
- **Scratchpad.** A note editor inside a dictation tool, for a user who
  already has an editor open.

### What the complaints say to build next, which is not in this change

Reading what people say rather than what is marketed, the ranking is not the
one the feature list suggests.

1. **Streaming.** The sharpest and most repeated complaint about the market
   leader is not accuracy, it is that it "does the entire transcription in one
   pass after you finish speaking". We have the same shape and issue #7 is
   already about it. One user reports moving to a LOCAL Whisper Large and
   getting lower latency than the cloud product, which is worth knowing: the
   round trip is not free and local is not automatically slower.
2. **Never losing what was said.** Stated repeatedly as the thing that decides
   whether a tool is trusted. `paste.py` already leaves the whole text on the
   clipboard when a delivery fails, which is this, and it is worth keeping
   that way.
3. **Minimal context, opt in.** Several people say in almost the same words
   that a tool needing screenshots to work is one they stop using everywhere.

Also worth recording because it will come up: there is a detailed independent
teardown of the market leader's client (wensenwu.com, September 2026) claiming
a system wide keystroke tap, accessibility tree scraping of the focused app,
a 694MB local database holding raw audio and captured field contents, and
hourly uploads that continue with usage sharing switched off. It is one
person's analysis of their own machine and is not verified here, so it is a
thing to be aware of rather than a thing to repeat as fact. The defensible
version of the same claim, and the only one worth making, is about this
product rather than theirs: no keystroke logging, no accessibility scraping
beyond the one field we just pasted into, no analytics, and no upload of
anything, ever.


---

## The Apex benchmark, and the mistake in the first run of it

Run on 20 real held recordings from `~/.dictator/corpus`, using `tools/compare.py`
and `tools/nonwords.py`, against `Marquestra/Whisper-Hindi2Hinglish-Apex-GGML`
q8_0. No references were written by hand: the score is the share of tokens in
neither an English nor a romanised Hindi dictionary, and the word count sits
next to it because a model that says less scores well by saying less.

| configuration | turbo gibberish | turbo secs | Apex gibberish | Apex secs |
|---|---|---|---|---|
| A, trimmed encoder, vocabulary prompt, `-l auto` | 1.30% | 5.1 | **3.56%** | 10.5 |
| B, full encoder, vocabulary prompt, `-l auto` | 1.49% | 5.7 | **1.64%** | 6.7 |
| C, full encoder, no prompt, `-l auto` | 1.68% | 7.3 | 2.03% | 6.6 |
| D, full encoder, no prompt, `-l en` | | | 2.03% | **4.1** |

### The first run was measuring our own setting, not the model

Configuration A is what the product ships, and under it Apex looks far worse
than turbo: 3.56% against 1.30%, at double the latency, with output like
`iririririririr` and `semesnirkkorpray`. The obvious conclusion is that Apex is
bad.

It is the wrong conclusion. `audio_ctx_for()` shrinks the whisper encoder by
duration, and that sizing was tuned against turbo. This document already
records that **undershooting `audio_ctx` causes decoder repetition loops**, and
`iririririr` is exactly that failure. Running the same audio through the same
model with the full encoder takes Apex from 3.56% to **1.64%**, level with
turbo, while producing **more** words (487 against 469), which rules out the
"scored well by saying less" explanation.

So a benchmark that leaves a per-model speed setting on is not comparing
models. `tools/compare.py` now has `--full-ctx` and `--no-prompt` for exactly
this reason. **Turbo is robust to the trimming and Apex is not**, which is
itself worth knowing: it is a fact about turbo that the sizing was fitted to
turbo, and it means the shipped setting cannot be reused when the model
changes.

### The vocabulary prompt helps both models

Configuration C drops it and both get worse: turbo 1.49% to 1.68%, Apex 1.64%
to 2.03%. This confirms the earlier note in this document that the English
`initial_prompt` helps rather than hurts, now on a second model.

### `-l auto` costs 2.5 seconds, measured

Configuration D differs from C only in pinning the language, and is identical
on every accuracy number (2.03%, 492 words) while dropping from 6.6s to
**4.1s**. That is the double encoder pass this document predicted, now with a
price on it: **38% of the wall clock of a hold**, for a decision that is
already known for a Hinglish-output model, because Apex only ever emits Latin
script.

### Where this leaves the model question

Not yet decided, and deliberately so. What is settled:

1. The first measurement was invalid and the conclusion drawn from it would
   have been wrong.
2. On equal terms Apex and turbo are within noise of each other on 20 holds,
   which is too few to separate them.
3. The remaining candidates are not tested: Apex at **fp16** (q8_0 was used
   first, and this document already records that quantisation buys nothing on
   Metal, so a quantised model was the wrong thing to judge the family by) and
   **Prime**, the sibling that wins on read speech where Apex wins on
   conversational audio.

The decision rule stated earlier in this document still stands and has not
been met by anything yet.


---

## The measuring instrument was wrong by a factor of six

Everything above about model accuracy was scored with `tools/nonwords.py`,
which counts the share of words in neither an English nor a romanised Hindi
dictionary. On the 130 real recordings in `~/.dictator/corpus` it reported
**2.35%**. The true figure is **0.37%**.

The difference was not the speech model. It was the tool not knowing English.

### What it was actually counting

Listing the words it objected to, rather than only the number, made it obvious
within a minute. The most common were `pda` (17 times), `usdc` (16), `struct`
(8), then `delegated`, `approved`, `preparing`, `liquidated`, `completed`,
`including`, `managed`, `deriving`, `updating`, `arriving`, `liked`,
`introduced`. Every one of those is correct.

Four separate faults, each systematic:

1. **No silent e restoration.** English drops a silent `e` before a vowel
   suffix, so `delegated` stems to `delegat`, which is in no dictionary. This
   one fault accounted for most of the English false alarms on its own.
2. **No comparatives, superlatives or adverbs.** `-er`, `-est` and `-ly` were
   not in the suffix list at all, so `earlier`, `simplest` and `smallest`
   counted as invented words.
3. **The length floor was measured against the wrong string.** It required the
   whole word to be longer than the suffix plus two, so `using` (five letters,
   `-ing` wanting six) was gibberish, along with every other short stem.
4. **The system word list is not a record of English.** It does not contain
   `has`. Nor `held`, `paid`, `became`, `repaid` or `hang`. Checking a list of
   the most common English words against it is how to find these, rather than
   waiting for each to turn up in a transcript.

Plus vocabulary: `pda` and `usdc` alone were a third of everything being
counted, and both are words this person says several times a day.

### What was left once it was fixed

21 occurrences in 5664 words. Every remaining one is a genuine failure:
`accura`, `acur` and `collater` (truncations), `ndernderndernder` and
`ondernder` (repetition loops), `lrdr`, `rjmn`, `bnvay`, `sval`, `klo`,
`checkmone`, `landborough`, `kaite`, `dismatched`, and five mangled attempts
at real people's names, which are not written out here for the same reason
this file contains no transcripts of anyone else: they are other people's.

**So the shipped pipeline is already at 0.37% on real Hinglish, and the noise
floor of the instrument had been six times the signal it was measuring.**

### What this invalidates

The Apex comparison in the section above. Turbo at 1.49% against Apex at 1.64%
was a difference of 0.15 points inside an instrument whose own error was 2.0
points. **That comparison could not have separated the two models and should
not be read as if it did.** The configuration findings from the same run
survive, because they are large effects measured against themselves: the
encoder trimming (3.56% against 1.64%), the vocabulary prompt, and the 2.5
seconds that `-l auto` costs.

### The rule this gives

**Print the words, not only the number.** A summary statistic over a
dictionary you did not write will measure the dictionary. The list of
offending words took a minute to read and moved the answer by a factor of six;
the number alone had been believed for a day.

The second guard matters as much as the first: a dictionary loose enough to
accept anything scores every model as perfect. `tests/test_nonwords.py` asserts
both directions, including that 60 random letter strings still score at least
90% unknown, and that real truncations like `collater` are still caught. That
last one is why `-er` deliberately does not get the silent e rule: it would
turn `collater`, a genuine truncation of "collateral", into `collate`.


---

## What the remaining errors actually are, and why a better model fixes few of them

Once the instrument stopped counting its own dictionary, only **16 of the 130
recordings contain a single error**, and the 21 errors in them fall into four
kinds. Listing them is more useful than the number, because they do not have
the same cure.

### Proper nouns and acronyms, 8 of 21

Five are mangled attempts at people's names and are not reproduced here,
because they are recognisable and they belong to somebody else. The other
three are `Glentworthy`, `LRDR` and `Checkmone`: a place, an acronym, and two
ordinary words run together.

**No speech model fixes these.** They are not in any model's vocabulary and
they never will be. The cure is `dictator learn`, which already exists, and
the reason it has not learned them is the subject of a different finding: the
learning loop had no way of knowing whether it had ever seen a correction.

One of them is worth reading closely. `Checkmone` is "check once", and **the
same recording says "check once" correctly a few words later**:

> Checkmone again full PDF full HTML and all video links and all things check
> once again everything should be at the point

Same speaker, same two words, same hold, right the second time and wrong the
first. So this is not a vocabulary failure at all, it is a **failure at the
start of an utterance**, where the decoder has no preceding context to condition
on. That points at the first moments of audio rather than at the model.

### Truncations, 3 of 21

`accura` and `acur` for "accuracy", `collater` for "collateral". One of them
gives the mechanism away:

> the collater collateral vault thing

The model produced a broken attempt and then the correct word immediately
after. That is a restart, not a mishearing. Combined with the `Checkmone`
case above, the pattern is that the **beginning of a word or an utterance is
where this pipeline loses information**, which is a recording and context
problem rather than a weights problem.

Relevant, and already measured elsewhere in this document: the native recorder
loses about 0.15s less of the start of every sentence than sox did.

### Compressed romanised Hindi, 5 of 21

`sval` for "sawaal", `bnvay` for "banvaao", `klo` for "karlo", `kaite` for
"kehte", `rjmn`. The model hears Hindi and writes it in a Latin spelling too
short to read. **This is the one category a Hinglish-specific model should
actually improve**, and it is five errors in 5664 words.

### Repetition loops on near-silent audio, 3 of 21

`ndernderndernder`, `Ondernder`, `Oof`, all from recordings that are nearly
empty. This is the `audio_ctx` failure mode documented above, and it is ours
rather than the model's.

### What this means for the model question

The case for changing models rests on **five errors in 5664 words**, which is
0.09%. Eight of the errors are proper nouns that no model knows, three are
utterance-start truncations, and three are our own encoder sizing on silence.

**So the model is not the biggest lever left, and the benchmark that was
supposed to choose one has instead argued against needing to.** The larger
wins available are, in order: feeding the vocabulary (the proper nouns),
protecting the start of an utterance (the truncations), and not running the
decoder on silence (the loops).

That is not a reason to skip the comparison, which is still worth finishing
because a model that is equally accurate and meaningfully faster would still
be worth having. It is a reason not to expect much from it.


---

## Catching the decoder talking to itself, and why it is not a loudness check

Three of the errors in the corpus are the decoder repeating itself rather than
transcribing, in two shapes:

    Oof, ndernderndernder
    and then, it's a little bit. It's a little bit. It's a little bit.

All three came from `cli:ggml-large-v3-turbo.bin`, confirmed in `history.db`,
so this is the whisper CLI path and not Parakeet. The cause is recorded above:
undershooting `audio_ctx` makes the decoder loop, and the same audio through
the full encoder produces words. **The setting is ours, so a loop is a reason
to run it again, not a reason to paste it.**

### The obvious fix does not work, and it was measured rather than assumed

The instinct is to reject quiet audio before transcribing it, and `loudness()`
was already sitting in `stt.py` with **no callers at all**. Measuring the
corpus kills the idea outright:

| recording | RMS | what it is |
|---|---|---|
| `ndernderndernder` | 0.0323 | a loop |
| `Ondernder` | 0.0176 | a loop |
| "I don't know" | 0.0079 | real speech |
| "Yeah, we're going to." | 0.0089 | real speech |
| "Who is trying?" | 0.0115 | real speech |
| a 26 second Hinglish hold, 71 words | 0.0139 | real speech |

**The loops are louder than a dozen recordings of real speech.** A loudness
gate set anywhere that caught them would have thrown away every short answer
the user gives, which is the failure this product is least able to afford. The
idea was killed in four minutes by printing the numbers.

### What does separate them is the shape of the output

`dictator/loops.py` reads the text rather than the audio, in two ways: one
short unit repeated inside a single token (`nder` four times), and the same
clause repeated three times in a row. Both thresholds were set against real
text rather than chosen:

- **Three repeats, not two.** Twice is a stutter or a real repetition. "murmur"
  is "mur" twice and "couscous" is "cous" twice.
- **Eight characters minimum** inside a token, so "hahaha" is left alone.
- **Six characters minimum** for a repeated clause, so "okay, okay, okay" and
  "right, right, right", which people genuinely say, are left alone. Four was
  the first value and it caught both.
- Clause splitting is on commas as well as full stops, because the loop turbo
  actually produced was "I think, I think, I think, I think", which a
  full-stop split reads as one sentence and lets through.

Run over all 130 real recordings it flags **2**, both genuine, and nothing
else. The false positive half is the half that matters: saying "this is a
loop" costs the user a working dictation, so `tests/test_loops.py` spends more
assertions on ordinary speech than on loops.

### The retry

On a loop, `_transcribe_ex` runs the same command again with `-ac` removed,
and keeps the second answer **only if it is not also a loop**. A loop on both
passes means the audio is the problem, and the first answer is then no worse
than the second. The cost is one extra pass on roughly 2% of holds.

### The failure is not deterministic, which is the argument for a retry

Running all three recordings through the pipeline as it stands now, they do
not loop. They come back as "Sousharshan.in.", "Slack summary." and "What
happened? Everything is done.", which are plausible.

That is not because the sizing was fixed afterwards. `audio_ctx_for()` took
its current shape on 23 September, and both loops were recorded on the 24th
and the 27th, **under exactly this sizing**. The same audio, the same model
and the same sizing loop on one run and not on another.

So the encoder size is not a switch between working and looping, it is a
pressure that makes looping more likely, and whisper's temperature fallback
decides the rest. That means **no static setting prevents this**, which is the
case for catching it at the output instead. It is also why it is worth having
even though turbo now passes all three: the Apex comparison run above produced
`iririririr` and `plplplplar` under the current sizing on the same day, so the
failure is live for any model the sizing was not fitted to.

Written down plainly because the first version of this section claimed the
retry fixes three current failures. It does not. It catches an intermittent
one, which is a weaker claim to make and a better reason to keep the code.


---

## The honest limit of the 0.37% figure

The allowlist was chosen by looking at which words this corpus was being
penalised for. `pda`, `usdc` and `struct` were the three most common words the
tool objected to, and all three are now in `ALLOW`. So part of the move from
2.35% to 0.37% is the instrument being fitted to the data it measures, and
there is no held-out set to check it against.

Worth separating the two halves, because they are not equally guilty:

- **The four morphology faults are real bugs and their fix is not fitting.**
  Restoring a silent e, adding `-er`, `-est` and `-ly`, measuring the length
  floor against the stem, and admitting that the system word list has no `has`
  in it. Each is defensible without reference to any corpus, and each was
  found by reading the output rather than by chasing a number.
- **The vocabulary additions are individually defensible and collectively
  fitted.** Every word added is a real word, which is easy to check one at a
  time. What is not defensible is the selection: a different speaker's corpus
  would have produced a different list, and a word nobody here happens to say
  is still missing.

What that means for how the number may be used:

- **0.37% is a figure for this word list on this corpus.** It is not
  comparable to anyone else's number, and quoting it as an accuracy score is
  wrong.
- **Comparing two models on the same corpus with the same frozen allowlist is
  still valid**, because both models are scored by the same ruler and the
  ruler's errors fall on both. That is the actual use, and it is what the
  model comparison above relies on.
- **Adding to `ALLOW` after seeing a model's output invalidates that
  comparison.** The list has to be frozen before a benchmark run, not tuned
  during one.

Said plainly because the section above ends with "print the words, not only
the number", and the fix to that lesson was partly to write the dictionary.
Both things are true.


---

## Two commands that came out of reading the errors rather than counting them

### `dictator review`, because the correction loop cannot see a terminal

The learning loop reads the text field back after a paste and keeps the
difference. That works where the field can be read, and a terminal is not such
a place: it hands back the whole scrollback rather than the line being edited,
and most dictation here goes into one. So the words it gets wrong most often
are exactly the words it is never told about, and instrumenting that path
measures the problem rather than fixing it.

The count that justified building the other direction: **8 of the 21 genuine
errors are names and acronyms**, the largest single category, and no speech
model will ever know them. `dictator learn` fixes each in one line, and
nothing was asking.

Four things that decided the shape, each from running it on the real history:

1. **One question per word, not per utterance.** Walking utterances asks about
   the same name forty times. Walking words asks once and fixes forty. On the
   real history this is the difference between 56 prompts and a list the user
   can work down.
2. **Most frequent first**, so stopping halfway has still got the value.
3. **The longest example, not the first.** The shortest utterance containing a
   word is often the word on its own, which is unanswerable. Nobody can say
   what a mangled name was meant to be; everybody can say it when they can see
   it was a greeting.
4. **Nothing is learned from silence.** A guess accepted quietly would rewrite
   correct words in every later dictation.

### `dictator forget`, which had exactly one setting and no question

It deleted the entire history, with no argument and no confirmation. Both
halves were wrong. The usual reason to reach for this command is one thing
somebody wishes they had not said out loud, and an irreversible delete of
every word they have ever dictated should take more than four letters and a
Return.

It now takes text, shows what matches before deleting it, and asks. `all`
still exists and now requires typing the word out.

Two bugs found by its own tests, both worth recording because both are shapes
that recur:

- **A deadlock.** `forget(containing=...)` read through `matching`, which takes
  the same lock, and `threading.Lock` is not reentrant. The obvious way to
  write it hangs the calling process, which on the dictation path is the one
  holding the user's words. The rows are now found before the lock is taken.
- **An empty search meant everything.** `forget(containing="")` fell through to
  `DELETE FROM said`, so a mistyped argument erased the lot. `containing` is
  now `None` for "no search was asked for" and `""` for "a search was asked
  for and matched nothing", which deletes nothing.

Searching `heard` as well as `shown` matters more here than in an ordinary
search: the reason to delete a line is often that it holds something that
should not have been written down, and the copy holding it may be the one the
recogniser produced rather than the one that landed.


---

## The model decision: turbo stays, and the benchmark says so clearly

Full corpus, 111 holds over three minimum seconds, 5200 words. Full encoder on
every model so the sizing fitted to turbo is not doing the comparing.
Vocabulary prompt on, language auto, `tools/nonwords.py` after the four
morphology fixes.

| model | words | gibberish | secs | Devanagari |
|---|---|---|---|---|
| **ggml-large-v3-turbo** (shipped) | 5214 | **0.17%** | 7.5 | 4% |
| Whisper-Hindi2Hinglish-Apex fp16 | 5300 | 0.30% | 7.8 | 0% |
| Whisper-Hindi2Hinglish-Apex q8_0 | 5196 | 0.29% | 7.4 | 0% |

**Turbo wins at roughly half the error rate, at the same speed.** The decision
rule written before any of this ran (improve and not regress, cost no more
than one extra second) is not met, and it is not close. **Nothing is being
switched.**

Apex is not winning by saying more or less: it produces 5300 words against
turbo's 5214, within 2%, so neither is scoring well by dropping speech.

### What Apex actually buys, and why it is not enough

**0% Devanagari against turbo's 4%.** That is the whole reason Apex exists: it
writes Hindi in Latin script and never makes `roman.py` load bearing. On four
holds in a hundred, turbo emits Devanagari and `roman.py` converts it.

That conversion evidently works, because turbo still wins on the final number
with the conversion included. **The pipeline beats the model that would have
made the pipeline unnecessary.** Which is the more useful result: it says the
romanisation layer, not the weights, is what this product is getting its
Hinglish accuracy from.

### Quantisation, corrected

fp16 0.30% at 7.8s, q8_0 0.29% at 7.4s. On 111 holds these are the same model:
**quantisation costs nothing measurable in accuracy and is not slower here**,
which contradicts the earlier note in this document that quantisation makes
the encoder slower on Metal (f16 1219ms, q8_0 1271ms). That earlier
measurement was a single encoder timing; this is 111 end to end holds. Both
can be true, and the end to end number is the one that matters.

That also means the very first Apex run, on q8_0, was not handicapped by the
quantisation. It was handicapped entirely by the encoder sizing.

### How much of turbo's win is the instrument being fitted to turbo

Worth asking, because the allowlist was built by reading the corpus, and the
corpus transcripts were produced by turbo. A word turbo gets wrong often
enough was likely to end up excused; a word only Apex produces was not. The
size of that advantage is unknown and it is not zero.

`tools/compare.py` now prints the words each model was marked down for, which
is the same lesson as above applied to the comparison itself. The check is to
read both lists and ask whether anything on Apex's is really a word.

**Until that has been read, the honest statement is: turbo wins on this
instrument, and the instrument has a structural bias towards turbo of unknown
size.** The gap is 0.13 points and the whole error rate is 0.17, so a bias of
that size is not implausible.
