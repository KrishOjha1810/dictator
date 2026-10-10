# Meetings

```bash
dictator meeting start "planning call"
...
dictator meeting stop
```

It records two tracks: your microphone, which is you, and the system audio,
which is everybody else. When you stop it, it transcribes both on your Mac and
writes what was discussed, what was decided, and what you said you would do.

> **You are recording other people.**
>
> Recording a conversation has consent implications, and in some places legal
> ones: several US states, and much of Europe, require everyone in the
> conversation to agree. So this never starts on its own. There is no calendar
> integration, nothing that notices a call has begun, and nothing that resumes
> after a restart. macOS shows its own screen recording indicator in your menu
> bar for as long as it runs, and that is not something this tries to hide.
> Tell the room. It costs one sentence.

## Commands

| Command | What it does |
|---|---|
| `dictator meeting start [title]` | begin, because you said so |
| `dictator meeting stop` | stop, transcribe, write the notes |
| `dictator meeting list` | what is recorded, and how much disk it is |
| `dictator meeting show [id] [--full]` | the notes, or every word |
| `dictator meeting forget id\|all` | delete it |
| `dictator meeting permissions` | walks you to the macOS pane it needs |

## Who said what

Two tracks rather than one mixed track is how each line knows who said it: the
microphone is you, the system is them. It does **not** try to tell the other
people apart. That is diarization, it is a research problem, and guessing at it
would put words in somebody's mouth.

## Permissions

macOS asks the **meeting recorder** rather than Dictator, because they are
separate apps on purpose: a permission is remembered against one application,
so this cannot disturb the Accessibility and Microphone grants the dictation
key already has.

The one it needs is called Screen Recording, or Screen & System Audio Recording
on newer macOS, because macOS files capturing what comes out of your speakers
under the same heading as capturing your display. **No video is recorded**: the
capture is set to two pixels and its frames are never read.

## Speed and size

Transcribing is the slow part and it says so while it works: about one minute
per four minutes of meeting on an M3, so a ten minute call takes roughly two
and a half minutes and an hour roughly fifteen. Recording costs about 3.8 MB
per minute for both tracks together.

## Notes you can trust

The notes go through the same checks the daily recap does. Every number and
every name has to appear in the transcript, and enough of the words have to
trace back to it, or the section is thrown away and you get the transcript
instead. An invented action item is worse than no notes, because somebody acts
on it and nothing on the page says which line to doubt.

## Deleting

`dictator meeting forget` overwrites the audio before it unlinks it, so nothing
reads it back off the filesystem. An SSD moves blocks around underneath us and
no program can promise more than that, which is why this says it rather than
claiming the recording is unrecoverable.

Nothing here touches the network. Not the audio, not the transcript, not the
notes. Recordings live in `~/.dictator/meetings`, one folder per meeting.
