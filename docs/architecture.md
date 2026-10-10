# How it works

## The pieces

| Piece | What it does |
|---|---|
| `native/hotkey.swift` | watches for the held key. A `CGEventTap`, because nothing else sees the Globe key |
| `native/orb.swift` | the indicator. Reads the microphone's real state, not a guess |
| `native/record.swift` | the microphone, at 16kHz mono, with a real level meter |
| `native/app/main.swift` | the app bundle that owns the permissions |
| `native/meeting.swift` | the meeting recorder: microphone plus system audio |
| `dictator/dictate.py` | the loop: hold, record, transcribe, paste |
| `dictator/stt.py` | records and transcribes, locally |
| `dictator/roman.py` | writes Hindi in Latin script |
| `dictator/recap.py` | reads your history back to you, summarised locally |
| `dictator/api.py` | the public Python library ([`library.md`](library.md)) |
| `dictator/cli.py` | every `dictator ...` command |

The speech engines, and which one answers which kind of sentence, are in
[`findings.md`](findings.md#speech).

## The app bundle is not decoration

macOS grants Microphone and Accessibility **per application**, and it decides
what counts as "the same application" from the code signature. A login item
started by `launchd` is not the terminal you granted, so without a real bundle
the user is asked to approve something called `/usr/bin/env` through a file
picker.

With a bundle there is one entry called **Dictator**, it asks for itself, and
there is nothing to set up.

## Why it is signed

An ad-hoc signature identifies an app by the hash of its own binary:

```
designated => cdhash H"dc19729a..."
```

So every rebuild is, to macOS, an application that has never been granted
anything. The checkbox in System Settings stays switched on next to an app
that no longer works, and there is nothing for anyone to see or fix.

The source install signs against a self-signed certificate kept in its own
keychain under `~/.dictator`, which makes the identity the certificate instead:

```
designated => identifier "com.dictator.dictation" and certificate leaf = H"cfb501b5..."
```

Rebuilding does not touch that. Released builds are signed with one release
certificate for the same reason: a new identity per build would drop every
user's grants on update.

`dictator doctor` checks this, and the other half, which is the one that
actually trapped somebody for days: macOS stores that requirement next to the
permission, and an entry written for an older certificate keeps its tick while
trusting nothing. `doctor` reads the requirement the grant was written for,
compares it with the one this build satisfies, and prints both when they
differ, because the difference is invisible everywhere else.

## Privacy

Recording goes to a temporary file, is transcribed by a local model, and the
file is replaced on the next hold. Nothing is uploaded and there is no account.

`~/.dictator` holds the history, the log, the indicator's state file, and the
signing keychain. Speech models are shared with any other local whisper install
rather than copied, because the large model alone is 1.6 GB. Set
`DICTATOR_MODELS` to put them somewhere specific.

The recap reads the history that is already on the machine, and the model that
writes its prose runs here too, for the length of that one command.

Meetings are the one place this product keeps audio, and it keeps it because
you asked it to. Recordings and transcripts sit in `~/.dictator/meetings`, and
`dictator meeting forget` overwrites the files before removing them.
