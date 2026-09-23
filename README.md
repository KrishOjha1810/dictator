# Dictator

Hold a key. Talk. The words land where your cursor is.

Anywhere on your Mac: a terminal, a browser, Slack, a text field written
before any of this existed. There is no per-application integration because
there is nothing to integrate with. It pastes the way you would have typed.

Everything runs on your machine. No audio leaves it.

```
dictator on
```

Then hold **fn** and speak.

---

## Why it exists

Dictation on a Mac is either built in and bad at anything that is not plain
English, or it is a subscription that sends your voice to a server.

The specific gap is Hinglish. Say "yaar ye function thoda slow lag raha hai,
can you check the loop" and most tools give you either mangled English or
Devanagari you cannot paste into a terminal. Dictator recognises the sentence
as it was spoken and writes it in Latin script, because that is how people
actually type it.

It is not finished at this. Word-level accuracy on Hinglish is still rough and
is the thing being worked on.

---

## Install

```bash
git clone https://github.com/KrishOjha1810/dictator.git ~/dictator
cd ~/dictator
./install.sh
```

The installer needs Homebrew for two packages (`sox` to record, `whisper-cpp`
to transcribe) and Apple's command line tools to build the key listener. It
tells you what is missing rather than guessing.

macOS then asks to allow **Dictator** to use the microphone and Accessibility.
Say yes to both. That is the only part that needs you, and there is nothing to
restart afterwards.

If something is not working:

```bash
dictator doctor
```

It checks the things that actually break and names the one that is wrong.

---

## Using it

| | |
|---|---|
| `dictator on [key]` | start now, and after every restart |
| `dictator off` | stop, and do not start again |
| `dictator status` | is it set up, is it running |
| `dictator doctor` | check everything, say what is wrong |
| `dictator log` | the last thing it did |
| `dictator errors` | failures it noticed |

The key can be `fn` (the default), `rightcmd`, `rightopt` or `leftcmd`.

**Hold, do not tap.** macOS fires the Globe key's own action on a clean tap and
never on a hold, so holding is the one gesture that cannot collide with
anything the system already does.

While you hold it, a small indicator appears and its bars move with your
voice. That is not decoration: it is the honest answer to "is the microphone
actually open", so you never talk into a dead mic and find out afterwards.

---

## Using it from your own code

Dictator is a library as well as a key. Anything that can get audio into a
`.wav` can get finished text back out, without the key, the indicator or the
login item.

```python
from dictator import Dictator

d = Dictator()
said = d.transcribe("recording.wav")

said.text        # "Jiske liye mujhe tumhari ek line chahiye"
said.heard       # "jiske liye mujhe tumaree ek line chaahie"
said.engine      # which model actually answered
said.confidence  # 0 to 1
```

`text` is what you would have typed. `heard` is what the model returned before
your own corrections were applied, which is the difference worth showing a
user when something changes under them.

Turn off the parts you do not want. A tool transcribing a hundred archived
files should not write a hundred rows into somebody's personal history:

```python
d = Dictator(remember=False, learn=False)
```

The pieces are there on their own too, when you only want one of them:

```python
raw, confidence = d.hear("recording.wav")   # just the model
text = d.polish(raw)                        # your words, then punctuation
d.learn("Whisper Flow")                     # teach it a word
d.paste(text)                               # into the frontmost app
```

`Dictator`, `Transcript`, `transcribe` and `VERSION` are the public surface.
Everything else inside the package is internal and will move.

The key listener is simply the first caller of this, which is deliberate: the
order of those steps is the hard part, and a second copy of it would drift.

---

## How it works

| Piece | What it does |
|---|---|
| `native/hotkey.swift` | watches for the held key. A `CGEventTap`, because nothing else sees the Globe key |
| `native/orb.swift` | the indicator. Reads the microphone's real state, not a guess |
| `native/app/main.swift` | the app bundle that owns the permissions |
| `dictator/stt.py` | records and transcribes, locally |
| `dictator/roman.py` | writes Hindi in Latin script |
| `dictator/dictate.py` | the loop: hold, record, transcribe, paste |

### The app bundle is not decoration

macOS grants Microphone and Accessibility **per application**, and it decides
what counts as "the same application" from the code signature. A login item
started by `launchd` is not the terminal you granted, so without a real bundle
the user is asked to approve something called `/usr/bin/env` through a file
picker.

With a bundle there is one entry called **Dictator**, it asks for itself, and
there is nothing to set up.

### Why it is signed

An ad-hoc signature identifies an app by the hash of its own binary:

```
designated => cdhash H"dc19729a..."
```

So every rebuild is, to macOS, an application that has never been granted
anything. The checkbox in System Settings stays switched on next to an app
that no longer works, and there is nothing for anyone to see or fix.

Dictator signs against a self-signed certificate kept in its own keychain
under `~/.dictator`, which makes the identity the certificate instead:

```
designated => identifier "com.dictator.dictation" and certificate leaf = H"cfb501b5..."
```

Rebuilding does not touch that. `dictator doctor` checks it and says so if it
ever regresses.

---

## Privacy

Recording goes to a temporary file, is transcribed by a local model, and the
file is replaced on the next hold. Nothing is uploaded and there is no account.

`~/.dictator` holds the log, the indicator's state file, and the signing
keychain. Speech models are shared with any other local whisper install rather
than copied, because the large model alone is 1.6GB. Set `DICTATOR_MODELS` to
put them somewhere specific.

---

## Used by other things

Dictator is a product on its own, and it is also the dictation layer under
voicebridge and Friday. Those speak
back to you; this one only listens. Plenty of people want the second thing
without the first.

---

## Status

Working: the held key, the indicator, local transcription, engine routing
between English and Hinglish, permissions that survive a rebuild.

Being worked on: Hinglish word accuracy, learning the words you correct,
pasting long text without it arriving as an attachment.

---

## Credits

The Hindi romanization lexicon is derived from
[Google Dakshina v1.0](https://github.com/google-research-datasets/dakshina),
used under CC BY-SA 4.0.

Speech recognition runs on [whisper.cpp](https://github.com/ggerganov/whisper.cpp).
