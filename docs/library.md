# Using Dictator from your own code

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

## Public surface

`Dictator`, `Transcript`, `transcribe` and `VERSION` are the public surface.
Everything else inside the package is internal and will move.

The key listener is simply the first caller of this, which is deliberate: the
order of those steps is the hard part, and a second copy of it would drift.

## Options

Turn off the parts you do not want. A tool transcribing a hundred archived
files should not write a hundred rows into somebody's personal history:

```python
d = Dictator(remember=False, learn=False)
```

Snippets are applied by `polish`. `Dictator(expand=False)` turns them off,
which is what a caller transcribing somebody else's audio wants: this user's
shorthand has no business firing inside it.

## The pieces on their own

```python
raw, confidence = d.hear("recording.wav")   # just the model
text = d.polish(raw)                        # your words, then punctuation
text = d.polish(raw, app="Ghostty")         # with that app's formatting rules
d.learn("Whisper Flow")                     # teach it a word
d.paste(text)                               # into the frontmost app
```

## Recap

```python
day = d.recap("today")      # or "week", "yesterday", or a number of days

print(day)                  # the report, as the command prints it
day.sessions                # the same thing structured, with the lines
day.terms                   # what kept coming up
day.source                  # "model", or why nobody wrote prose
```

`d.recap(when, prose=False)` skips the local model, for a caller that will do
its own wording.

## Review

`review` hands you the words it is least sure of, most often said first, for
you to ask about however suits your interface:

```python
for w in d.review():
    w["word"]   # what it heard
    w["count"]  # how many times
    w["text"]   # an utterance to show it in
d.learn("Whisper Flow", heard="whisper floor")
```

## Forget

Anything holding a record of everything somebody said needs to offer them a
way out of it:

```python
d.forget(containing="the deploy key")   # just those, and it returns how many
d.forget(everything=True)               # has to be asked for by name
```

An empty `containing` erases nothing rather than everything, so a caller
passing a variable that happened to be empty does not lose the history.
