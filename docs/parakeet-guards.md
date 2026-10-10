# The Parakeet guards are already as good as they can get

Measured 10 October 2026. **No code changed.** This exists so the next person
does not spend an afternoon tightening them, as nearly happened here.

## What it looked like

A real log line:

```
answered by the fast English engine
heard: "Zadaj tokens used karo, fatta Torosa karke, final reply me"
```

That is Hinglish dragged through an English-only model, and none of the four
guards on the Parakeet path fired. `_mangled_stretch` wants two unknown words
in a row and this has them scattered, so its longest run is 1, which is also
the longest run in perfectly good Hinglish like "yaar ye function thoda slow
lag raha hai". Adjacency cannot separate them.

## Density cannot either

Both engines were run over all 40 written references and scored against what
was actually said. Splitting on whether Parakeet was badly wrong (WER above
50%):

```
Parakeet badly wrong (6)   unknown word share: median 0.0%, max 43.5%
Parakeet fine       (34)   unknown word share: median 0.0%, max 50.0%
```

The two populations are indistinguishable. Parakeet's bad answers are made of
real English words in the wrong order, which is the exact failure the
`nonwords` instrument was documented as blind to, and the same blindness
applies here.

## The guards already catch five of the six

Looking at the six by hand:

```
WER 100%  said "Slack summary."            got "Слаг сумри."          _not_english     fires
WER  80%  said "aaj mainne break up ki..." got "Ajmene break up ki..." _mangled_stretch fires
WER  71%  said "Everyday plans se sab..."  got "Everyday plans of Linkonachi."   nothing fires
WER 100%  said "When we do this,"          got nothing                falls through to turbo
WER 100%  said "kya ho gya sab kaam..."    got nothing                falls through to turbo
WER 100%  said "kya tum mujhe sun paa..."  got nothing                falls through to turbo
```

An empty answer is already handled: the gate is `if got and not ...`, so
nothing from Parakeet means turbo takes the hold. That leaves exactly one
genuine miss in forty.

## And catching it would win nothing

```
turbo for everything           WER 10.32%   WER-sound 10.05%
today, Parakeet first          WER  3.60%   WER-sound  3.32%
perfect routing (upper bound)  WER  3.60%   WER-sound  3.32%
```

The upper bound takes, for every hold, whichever of the two answers is closer
to what was said. It is identical to what the pipeline already produces. For
the one hold the guards miss, turbo's answer is no better, so routing it
there would cost the three times speed and return nothing.

**The remaining gap is 0.00 points of WER.** Any tightening from here can only
send good English holds to the slow model.

## What would change this

A signal the guards do not have: Parakeet's own confidence. `_parakeet` reads
text and throws the rest away, and `parakeet-cli` may or may not emit a
per-utterance probability. If it does, that is the one thing worth trying,
and it should be measured against these same 40 references before it is
believed.

Reproduce all of the above with `tools/wer.py` and the references in
`~/.dictator/references`.
