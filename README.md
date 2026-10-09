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

### Download the app

**[Download Dictator for Mac](https://github.com/cc-vb/dictator/releases/latest/download/Dictator.dmg)**
(Apple silicon, macOS 14 or newer, about 24 MB). Every version, with its
SHA256, is on the [releases page](https://github.com/cc-vb/dictator/releases).

1. Open `Dictator.dmg` and drag Dictator into Applications. Open it from
   Applications, not from the disk image window: macOS stops a copy run from
   the disk image after a few seconds. If you do open that one, it offers to
   move itself to Applications.
2. Open Dictator. macOS stops it, because Dictator is free and not paid into
   Apple's developer programme. Press **Done**, not Move to Trash.
3. Open **System Settings → Privacy & Security**, scroll down, and press
   **Open Anyway** next to Dictator. Confirm. This happens once.
4. Allow the microphone and Accessibility when it asks. The speech models
   download on first launch, English first (about 700 MB), then Hindi and
   Hinglish in the background (1.5 GB). Each is checked against its published
   SHA256 before it is used.
5. If your key is fn, open **System Settings → Keyboard** and set
   **Press 🌐 key to** to **Do Nothing**. A quick tap of fn (🌐) otherwise
   opens the emoji picker, switches the input source or starts Apple's own
   dictation, and a double tap of fn is how you start hands free dictation
   here. Wispr Flow asks for the same change. The app's "Choose your key"
   card has a button that opens the right pane.

This is a preview. The app is new and has had less use than the install below,
which is still the way to run it if anything here goes wrong. Why the warning
exists and what it does and does not mean is in
[`docs/platforms.md`](docs/platforms.md).

### Install from source

```bash
curl -fsSL https://raw.githubusercontent.com/cc-vb/dictator/main/get.sh | bash
```

Or clone it yourself, if you would rather read it first, which is the same
thing in three steps:

```bash
git clone https://github.com/cc-vb/dictator.git ~/dictator
cd ~/dictator && ./install.sh
```

English works as soon as that finishes, in about two minutes. The larger model
for Hindi and Hinglish keeps downloading in the background and starts working
when it lands; `dictator doctor` says which half is ready.

The installer needs Homebrew for one package (`whisper-cpp`, to transcribe) and
Apple's command line tools to build the key listener. It tells you what is
missing rather than guessing. Recording needs nothing installed: it goes
through AVFoundation, which is already on your Mac.

macOS then asks to allow **Dictator** to use the microphone and Accessibility.
Say yes to both. That is the only part that needs you, and there is nothing to
restart afterwards.

If something is not working:

```bash
dictator doctor
```

It checks the things that actually break and names the one that is wrong.

### If the key does nothing and the checkbox is already on

That is a real macOS state and not a mistake anyone made. The list in System
Settings is drawn from an entry; whether an app is trusted is decided by a code
signature stored next to that entry. When the signature changes, the entry
survives with the old one, so the switch stays on, the app stays untrusted, and
macOS never asks again because it already has an answer on file.

Switching that toggle off and on cannot fix it. The entry has to be removed:

```bash
dictator permissions
```

It says which of the two problems this is, prints the steps for that one, and
`--reset` does them for you. By hand it is: System Settings, Privacy &
Security, Accessibility, click **Dictator**, click the **minus** button under
the list, then `dictator off && dictator on` and say yes.

---

## Using it

| | |
|---|---|
| `dictator on [key]` | start now, and after every restart |
| `dictator off` | stop, and do not start again |
| `dictator status` | is it set up, is it running |
| `dictator doctor` | check everything, say what is wrong |
| `dictator permissions` | why macOS is not trusting it, and how to get out |
| `dictator recap [today\|week\|N]` | what you dictated, summarised here |
| `dictator meeting start\|stop` | record a meeting and get notes from it |
| `dictator find WORDS` | search everything you have ever dictated |
| `dictator snippet "PHRASE" "TEXT"` | say the phrase, get the text |
| `dictator review` | it asks you about the words it got wrong |
| `dictator forget "WORDS"` | erase everything you said containing them |
| `dictator log` | the last thing it did |
| `dictator errors` | failures it noticed |

Every command reads `~/.dictator`. `DICTATOR_STATE` points one at a different
installation, which is what you want when the Mac has two user accounts and
the dictation you are trying to explain happened in the other one:

```
DICTATOR_STATE=/Users/someone/.dictator dictator log
DICTATOR_STATE=/Users/someone/.dictator dictator errors
```

It reads whatever that account has left world readable, which is the log and
the error list. The history is not: it holds everything that account has ever
said and is theirs. Put this on the one command, never in a shell profile, or
a listener started from that shell writes into somebody else's directory.

The key can be `fn` (the default), `rightcmd`, `rightopt` or `leftcmd`.

**Hold to talk.** Hold the key, speak, let go: the words land where your
cursor is.

**Double-tap for hands free.** Two quick taps of the key and the microphone
stays open without holding anything. Press the key once to finish: it stops,
transcribes and pastes into the app you were in. Escape throws it away and
pastes nothing. A session stops on its own after two minutes (the same cap as
a hold) and is thrown away, because a microphone open that long is more
likely forgotten than a monologue. A single tap does nothing.

**Set the Globe key to Do Nothing.** With fn as your key, open **System
Settings → Keyboard** and set **Press 🌐 key to** to **Do Nothing**. macOS
acts on every quick tap of fn itself (the emoji picker, the input source, or
Apple's dictation), so without this a double tap does that as well. Dictator
only listens to the keyboard and cannot stop it. Holding is never affected.

**The pill.** While the microphone is open a small dark pill shows, and its
bars move with your voice. That is not decoration: it is the honest answer to
"is the microphone actually open", so you never talk into a dead mic and find
out afterwards. It is drawn if and only if our microphone is really open, and
in hands free mode it carries a cross (throw it away) and a check (finish and
paste).

When nobody is dictating it is not drawn at all. Move the pointer to its place
and it fades in with its buttons:

| | |
|---|---|
| the pill (mic) | click to start hands free dictation, click again to finish |
| record | start or stop the Notetaker (a meeting recording). The first time, the app explains that it records other people and asks before it starts. Red while recording. `⌥M` from anywhere |
| pencil | open the Scratchpad, a notes window with the cursor ready, so you can dictate into it. Notes are Markdown files in `~/.dictator/notes`. `⌥S` from anywhere |

Hovering a button shows its name and shortcut. Drag the pill to any of eight
places: at the top and bottom centre it lies flat, at the side edges and in
the corners it stands up. Settings → General chooses whether it shows on
hover, always, or only while dictating, which buttons it has, and whether the
two shortcuts are on. From a terminal: `dictator indicator`,
`dictator hands-free`, `dictator notes`.

---

## Phrases you say often

An email address is thirty characters of dots and an at sign that no speech
model will ever produce from speech. Spelling it out loud is slower than
typing it. So give the address a phrase instead:

```bash
dictator snippet "my work email" "krish@example.com"
dictator snippet "the repo path" "/Users/krish/dictator"
```

Say "send it to my work email" and the address is what lands.

The trigger needs at least two words. One spoken word is something you say by
accident a hundred times a day, and a one word trigger is how a text expander
turns into a thing you fight. It also refuses a phrase you have already
dictated, and says how many times, because your own history is the only honest
test of whether a phrase is one you use:

```
$ dictator snippet "check the loop" "https://example.com/loop"
not added: you have already dictated that phrase 7 times, so it would start
replacing things you meant to say.
```

`dictator snippets` lists them, `dictator unsnippet "..."` removes one.

---

## Finding something you said

```bash
dictator find the loop
dictator find deploy --app Slack --days 7
dictator find rebase --copy          # the most recent one, on your clipboard
```

It searches what the recogniser HEARD as well as what landed, which is the
whole reason to keep both. When a sentence came out wrong, the wrong words are
the only ones you can search for.

---

## Different rules in different applications

A spoken list belongs in Slack. At a shell prompt it is four lines with
numbers in front of them, and the shell will try to run the first one. So the
formatting rules can differ by where the words are going:

```bash
dictator format in Slack lists on
dictator format in terminal sentences off
dictator format in Slack default      # back to the global rules
```

`terminal` is a group and covers every terminal emulator, because nobody wants
to configure Ghostty and iTerm separately to say the same thing.

This is deliberately not "tone". The products that sell tone matching send
your sentence to a cloud model and have it rewrite you to sound casual or
formal. Underneath the marketing that feature is mostly two booleans, which
capital letters and which punctuation, and those are worth having without a
model anywhere near them.

---

## What you said today

```
dictator recap today
dictator recap week
dictator recap 3
```

### It asks you about what it got wrong

The correction loop watches what you do to the text after it lands, which
works in a text field and does not work in a terminal: a terminal hands back
its whole scrollback rather than the line you are editing. Most dictation goes
into a terminal, so the words it gets wrong most often are the ones it is
never told about.

`dictator review` goes the other way. It finds the words in neither
dictionary, most often said first, and asks:

```
  it heard "acur" in Google Chrome, 2 times
    ...And that too from the acur interest part...
    what did you say? accuracy
    learned "accuracy". Things that sound like it will come out right.
```

Press Return to skip one, `q` to stop. Nothing is learned from silence, and a
word you have already taught is never raised again.

Names are what this is for. Of the errors left in a hundred real recordings,
the largest single group was names and acronyms, which no speech model will
ever know and one answer here fixes for good.

### Erasing it

```
dictator forget "the deploy key"   # shows what matches, then asks
dictator forget all                # everything, and you have to type ERASE
```

It searches what it heard as well as what it pasted, because the reason to
delete a line is usually that it holds something that should not have been
written down, and the copy holding it may be the one the recogniser produced.


It reads back what you dictated in that period: your day grouped into stretches
of work, with the times and the applications next to each one so every line can
be checked against the sentence that produced it.

This summarises **what you dictated, not what was said in a room**. It is the
half of "meeting notes" that a dictation tool is uniquely placed to do, and it
needs no recording, no second model to work out who spoke, and no new
permission from macOS. Nothing else on your machine knows what you said into
Slack at eleven and into a terminal at noon.

If there is a local model on the machine (llama.cpp and a small instruct model
in `~/.dictator/models` or a voicebridge install) it writes the prose, here,
and puts itself away afterwards. If there is not, you get the same report
grouped by time and application with the words that kept coming up, and it says
plainly that it cannot tell you what you decided, only what you said.

It will not pad. An empty day says so in one line, and four sentences are
printed as four sentences rather than made into a report about four sentences.
A summary that mentions a name, a number or a subject you never dictated is
thrown away rather than shown, and the lines are printed instead.

There is no cloud option and there will not be one. `--plain` skips the model
entirely.

---

## Meetings

```
dictator meeting start "planning call"
...
dictator meeting stop
```

It records two tracks: your microphone, which is you, and the system audio,
which is everybody else. When you stop it, it transcribes both here and writes
what was discussed, what was decided, and what you said you would do.

> **You are recording other people.**
>
> Recording a conversation has consent implications, and in some places legal
> ones: several US states, and much of Europe, require everyone in the
> conversation to agree. So this never starts on its own. There is no calendar
> integration, nothing that notices a call has begun, and nothing that resumes
> after a restart. macOS shows its own screen recording indicator in your menu
> bar for as long as it runs, and that is not something this tries to hide.
> Tell the room. It costs one sentence.

Two tracks rather than one mixed track is also how each line knows who said it:
the microphone is you, the system is them. It does **not** try to tell the other
people apart. That is diarization, it is a research problem, and guessing at it
would put words in somebody's mouth.

macOS asks for two things the first time, and it asks the **meeting recorder**
rather than Dictator, because they are separate apps on purpose: a permission is
remembered against one application, so this cannot disturb the Accessibility and
Microphone grants the dictation key already has.

```
dictator meeting permissions
```

walks you to the pane. The one it needs is called Screen Recording, or Screen &
System Audio Recording on newer macOS, because macOS files capturing what comes
out of your speakers under the same heading as capturing your display. **No
video is recorded**: the capture is set to two pixels and its frames are never
read.

| | |
|---|---|
| `dictator meeting start [title]` | begin, because you said so |
| `dictator meeting stop` | stop, transcribe, write the notes |
| `dictator meeting list` | what is recorded, and how much disk it is |
| `dictator meeting show [id] [--full]` | the notes, or every word |
| `dictator meeting forget id\|all` | delete it |

Transcribing is the slow part and it says so while it works: about one minute
per four minutes of meeting on an M3, so a ten minute call is roughly two and a
half minutes and an hour is roughly fifteen. Recording costs about 3.8 MB per
minute for both tracks together.

The notes go through the same checks the daily recap does. Every number and
every name has to appear in the transcript, and enough of the words have to
trace back to it, or the section is thrown away and you get the transcript
instead. An invented action item is worse than no notes, because somebody acts
on it and nothing on the page says which line to doubt.

`dictator meeting forget` overwrites the audio before it unlinks it, so nothing
reads it back off the filesystem. An SSD moves blocks around underneath us and
no program can promise more than that, which is why this says it rather than
claiming the recording is unrecoverable.

Nothing here touches the network. Not the audio, not the transcript, not the
notes.

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

`polish` takes the application too, and applies whatever formatting rules were
set for it. Snippets are part of `polish` and `Dictator(expand=False)` turns
them off, which is what a caller transcribing somebody else's audio wants:
this user's shorthand has no business firing inside it.

```python
text = d.polish(raw, app="Ghostty")
```

The recap is there too, for anything that wants to say your day back to you:

```python
day = d.recap("today")      # or "week", "yesterday", or a number of days

print(day)                  # the report, as the command prints it
day.sessions                # the same thing structured, with the lines
day.terms                   # what kept coming up
day.source                  # "model", or why nobody wrote prose
```

`d.recap(when, prose=False)` skips the local model, which is what a caller that
is going to do its own wording wants.

The other half of learning is there too. The loop that watches for corrections
reads the text field back after a paste, and a terminal hands back its whole
scrollback rather than the line being edited, so the words it gets wrong most
often are the ones it is never told about. `review` goes the other way and
hands you the words it is least sure of, most often said first, for you to ask
about however suits your interface:

```python
for w in d.review():
    w["word"]   # what it heard
    w["count"]  # how many times
    w["text"]   # an utterance to show it in
d.learn("Whisper Flow", heard="whisper floor")
```

And erasing, because anything holding a record of everything somebody said
needs to offer them a way out of it:

```python
d.forget(containing="the deploy key")   # just those, and it returns how many
d.forget(everything=True)               # has to be asked for by name
```

An empty `containing` erases nothing rather than everything, so a caller
passing a variable that happened to be empty does not lose the history.

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
| `native/record.swift` | the microphone, at 16kHz mono, with a real level meter |
| `native/app/main.swift` | the app bundle that owns the permissions |
| `dictator/stt.py` | records and transcribes, locally |
| `dictator/roman.py` | writes Hindi in Latin script |
| `dictator/dictate.py` | the loop: hold, record, transcribe, paste |
| `dictator/recap.py` | reads your history back to you, summarised locally |

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

It also checks the other half, which is the one that actually trapped somebody
for days: macOS stores that requirement next to the permission, and an entry
written for an older certificate keeps its tick while trusting nothing.
`doctor` reads the requirement the grant was written for, compares it with the
one this build satisfies, and prints both when they differ, because the
difference is invisible everywhere else.

---

## Privacy

Recording goes to a temporary file, is transcribed by a local model, and the
file is replaced on the next hold. Nothing is uploaded and there is no account.

`~/.dictator` holds the log, the indicator's state file, and the signing
keychain. Speech models are shared with any other local whisper install rather
than copied, because the large model alone is 1.6GB. Set `DICTATOR_MODELS` to
put them somewhere specific.

The recap does not change any of that. It reads the history that is already on
the machine, and the model that writes its prose runs here too, for the length
of that one command. Every competitor's version of this feature summarises in
somebody else's cloud, which is the reason this one exists and the one thing it
will not do.

Meetings are the one place this product keeps audio, and it keeps it because
you asked it to. The recordings and their transcripts sit in
`~/.dictator/meetings`, one folder per meeting, and `dictator meeting list`
shows you every one of them with its size. Nothing is uploaded, the
summarisation model runs here, and `dictator meeting forget` overwrites the
files before removing them.

---

## Used by other things

Dictator is a product on its own, and it is also the dictation layer under
voicebridge and Friday. Those speak
back to you; this one only listens. Plenty of people want the second thing
without the first.

---

## Status

Working: the held key, the indicator, local transcription, engine routing
between English and Hinglish, permissions that survive a rebuild, and the
recap of what you dictated.

Being worked on: Hinglish word accuracy, learning the words you correct,
pasting long text without it arriving as an attachment.

Not built, deliberately: recording a meeting. That is system audio, a second
model to tell speakers apart, and a permission this product does not currently
ask for, and it should be judged on its own rather than smuggled in behind a
summary feature.

---

## What we measured

[docs/findings.md](docs/findings.md) is the record: which models are good at
what and by how much, what macOS actually does with permissions and code
signatures, where the latency goes, and the things we assumed and were wrong
about. Every number in it was measured on a real machine, and where a figure
came from somebody else it says so.

It exists so the same things do not get re-derived, and so ideas that have
already been measured and rejected do not get tried again.

---

## Credits

The Hindi romanization lexicon is derived from
[Google Dakshina v1.0](https://github.com/google-research-datasets/dakshina),
used under CC BY-SA 4.0.

Speech recognition runs on [whisper.cpp](https://github.com/ggerganov/whisper.cpp).
