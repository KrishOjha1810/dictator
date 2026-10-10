# Using Dictator

- [Dictating](#dictating)
- [The pill](#the-pill)
- [Commands](#commands)
- [Phrases you say often](#phrases-you-say-often)
- [Finding something you said](#finding-something-you-said)
- [Different rules in different applications](#different-rules-in-different-applications)
- [What you said today](#what-you-said-today)
- [Teaching it the words it got wrong](#teaching-it-the-words-it-got-wrong)
- [Erasing it](#erasing-it)

Meetings have their own page: [`meetings.md`](meetings.md).

---

## Dictating

**Hold to talk.** Hold the key, speak, let go: the words land where your
cursor is.

**Double-tap for hands free.** Two quick taps of the key and the microphone
stays open without holding anything. Press the key once to finish: it stops,
transcribes and pastes into the app you were in. Escape throws it away and
pastes nothing. A session stops on its own after two minutes (the same cap as
a hold) and is thrown away, because a microphone open that long is more
likely forgotten than a monologue. A single tap does nothing.

The key can be `fn`, `rightopt`, `rightcmd` or `leftcmd`. If it is `fn`, set
the Globe key to Do Nothing first: see [`install.md`](install.md#the-globe-fn-key).

---

## The pill

While the microphone is open a small dark pill shows, and its bars move with
your voice. That is not decoration: it is the honest answer to "is the
microphone actually open", so you never talk into a dead mic and find out
afterwards. It is drawn if and only if the microphone is really open, and in
hands free mode it carries a cross (throw it away) and a check (finish and
paste).

When nobody is dictating it is not drawn at all. Move the pointer to its place
and it fades in with its buttons:

| Button | What it does |
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

## Commands

| Command | What it does |
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

---

## Phrases you say often

An email address is thirty characters of dots and an at sign that no speech
model will ever produce from speech. So give it a phrase instead:

```bash
dictator snippet "my work email" "krish@example.com"
dictator snippet "the repo path" "/Users/krish/dictator"
```

Say "send it to my work email" and the address is what lands.

The trigger needs at least two words. One spoken word is something you say by
accident a hundred times a day. It also refuses a phrase you have already
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

It searches what the recogniser *heard* as well as what landed. When a
sentence came out wrong, the wrong words are the only ones you can search for.

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

`terminal` is a group and covers every terminal emulator.

This is deliberately not "tone". Products that sell tone matching send your
sentence to a cloud model to rewrite it. Underneath, that feature is mostly two
booleans (which capital letters, which punctuation), and those are worth
having without a model anywhere near them.

---

## What you said today

```bash
dictator recap today
dictator recap week
dictator recap 3
```

It reads back what you dictated in that period: your day grouped into
stretches of work, with the times and the applications next to each one, so
every line can be checked against the sentence that produced it.

This summarises **what you dictated, not what was said in a room**. It needs no
recording, no second model to work out who spoke, and no new permission from
macOS.

If there is a local model on the machine (llama.cpp and a small instruct model
in `~/.dictator/models`, or a voicebridge install) it writes the prose, here,
and puts itself away afterwards. If there is not, you get the same report
grouped by time and application with the words that kept coming up, and it
says plainly that it cannot tell you what you decided, only what you said.

It will not pad. An empty day says so in one line. A summary that mentions a
name, a number or a subject you never dictated is thrown away and the lines are
printed instead.

There is no cloud option and there will not be one. `--plain` skips the model
entirely.

---

## Teaching it the words it got wrong

The correction loop watches what you do to the text after it lands. That works
in a text field and does not work in a terminal, which hands back its whole
scrollback rather than the line you are editing. Most dictation goes into a
terminal, so the words it gets wrong most often are the ones it is never told
about.

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

---

## Erasing it

```bash
dictator forget "the deploy key"   # shows what matches, then asks
dictator forget all                # everything, and you have to type ERASE
```

It searches what it heard as well as what it pasted, because the copy holding
something that should not have been written down may be the one the recogniser
produced.
