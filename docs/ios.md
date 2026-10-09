# iOS

A keyboard that hears you, with no speech model of its own.

## What changed, and what was wrong before

Issue #9 recorded mobile as not possible, and gave a reason:

> a keyboard extension has a hard memory limit that a 1.5GB speech model will
> not fit inside

The limit is real. The conclusion was wrong, because it assumed the model has
to be inside the extension. Since iOS 26 it does not. `SpeechTranscriber` runs
in a system process; the extension holds no weights, ships no models and does
no inference. The ceiling it was going to hit is not on its path any more.

That sentence sat in an issue for weeks without anyone checking it, which is
the same mistake made about Gatekeeper and the `.dmg` (see `platforms.md`, the
8 October retest). Twice now a one line conclusion from a true premise has been
the thing standing in the way, and both times the test took under an hour.

## What it costs, measured here

Not quoted from a benchmark. Run on the 40 recordings in this project's own
corpus, against the references a human wrote for them, scored by the same three
numbers `tools/wer.py` reports for the Mac pipeline.

```
40 recordings, identical audio, identical references

  this project   WER   3.60%   WER-sound   3.32%   ENG-exact 98.7%
  Apple          WER  18.00%   WER-sound  16.77%   ENG-exact 96.3%

English-only holds (27)
  this project   WER   1.06%   ENG-exact 99.5%
  Apple          WER  11.45%   ENG-exact 97.2%

Holds containing Hindi words (13)
  this project   WER   8.88%   ENG-exact 97.7%
  Apple          WER  31.59%   ENG-exact 95.2%

Apple latency 456 ms mean over 26.4 s mean audio (real-time factor 0.017)
```

Reproduce it:

```bash
swiftc -O -parse-as-library tools/apple_speech.swift -o /tmp/apple_speech
/tmp/apple_speech en_IN $(ls ~/.dictator/corpus/*.wav) > /tmp/apple.tsv
tools/apple_wer.py /tmp/apple.tsv
```

So the honest summary is **five times the error rate, and about forty times
faster**. On English alone the gap is ten times on WER but only two and a bit
points of English words lost, which is the number that decides whether a coding
tool is usable. On Hinglish it is a different product wearing the same name.

Measured on a Mac's Apple silicon, not on a phone. The iPhone model may differ
and this should be re-run on one.

### The Hindi locale is not the answer

`SpeechTranscriber` has 30 locales and no Hindi. `DictationTranscriber`, the
older path, has 54 including `hi_IN`, so the obvious idea is to transcribe in
Hindi and romanise with `stt._romanise` the way the Mac build does.

It was tried. **69.24% WER, and 9.6% of the English words survived.** A Hindi
model writes English technical words phonetically in Devanagari: "Slack
summary" came back as `स्लिक समिट`, which romanises to "slik smit". The
audience for this says "function", "deploy" and "pull request" in the middle of
Hindi sentences, so the half the Hindi model destroys is the half that matters.

`en_IN` is used instead. It keeps the English intact and romanises the Hindi
half by itself, which is the shape this product already wants.

## The question that is still open

Whether an app extension is allowed to open the microphone at all.

Full Access (`RequestsOpenAccess`) lifts the sandbox that blocks the network,
and is what every keyboard with a cloud feature asks for. Whether it also
reaches `AVAudioEngine` is not written down anywhere load bearing, and it is
not something to assume in either direction.

So `ios/` is built to answer it rather than to assume it:

- The container app runs the same `Dictation` and reports each step
  separately, which gives a baseline. It is expected to pass.
- The keyboard runs it too and prints whatever iOS says when it refuses,
  including which of Full Access, the microphone permission or the model was
  missing.

If the keyboard cannot record, the fallback is not nothing: the app records,
the keyboard reads the result out of a shared container, and the user taps once
more than they should have to. That is a worse product and it is still a
product. It is written down here so that if the probe fails, the next person
does not conclude from one failure that iOS is closed.

## Not a port

Nothing from `native/` crosses. The held key is a CGEventTap, the indicator is
AppKit, the login item is launchd, the permissions are TCC, and the paste is a
synthetic Cmd-V guarded by `AXIsProcessTrusted`. None of it exists here, and
the 500 lines of `paste.py` and `paste.swift` collapse into one call,
`textDocumentProxy.insertText`, because the keyboard is the input method rather
than something faking one.

What does cross is the idea and, eventually, the vocabulary: `vocab.json` and
the corrections in `history.db` are plain files and mean the same thing on any
platform.
