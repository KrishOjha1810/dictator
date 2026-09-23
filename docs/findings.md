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
sox                     2.4 MB     but drags in 9 libraries, and is GPL
models                  2261 MB    74 + 638 + 1549
```

The code is 1MB and the download is 2.3GB. It is all models.

**sox cannot be bundled**: `GPL-2.0-or-later AND LGPL-2.1-or-later`.
`AVAudioRecorder` replaces it in 40 to 60 lines of Swift and gives a real
level meter for free.

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
