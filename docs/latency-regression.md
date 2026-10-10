# Hold to paste was 4.1 s and is 1.1 s, and the words got better too

Found and fixed 10 October 2026. This file was parked the same day with two
guesses in it, and both were wrong. They are kept below, because being wrong
in a particular way is the useful part.

## What was actually happening

`~/.dictator/lang` says `hinglish`. `_transcribe_ex` opened with:

```python
if language() != "hinglish" and parakeet_ready():
```

So anyone who had asked for Hinglish never reached Parakeet. Every hold went
straight to the 1.6GB multilingual model and paid its load, every time.

That reads like the careful interpretation of the setting, and it is not.
The machinery for trying an English-only model on possibly-Hindi audio sits
directly underneath it: four guards (`_parakeet_lost`, `_too_little`,
`_not_english`, `_mangled_stretch`) and a fallback that sets
`_force_multilingual` and reruns the hold the moment any of them fires. The
gate was stopping the guards from ever getting the chance.

## Measured, on the 40 written references, interleaved, two passes each

```
                          WER     WER-sound   ENG-exact   mean    median
always multilingual     10.32%      10.05%       96.1%    5.34s    4.12s
parakeet first           3.60%       3.32%       98.7%    2.37s    1.27s
```

Then on the real path with nothing patched and `lang` still saying hinglish:

```
WER 3.60%   WER-sound 3.32%   ENG-exact 816/827 = 98.7%
1.89s mean, 1.06s median, 12.11s worst
engines: parakeet 31, turbo 9
```

Better on the words **and** three times faster on the median. 31 of 40 holds
answered by Parakeet, 9 falling through to turbo, which is the guards doing
exactly what they were written to do.

The 1.9 s figure this project has quoted as its reference was always this
path. The Hinglish setting had been quietly costing both accuracy and speed
for as long as it existed.

The setting still decides the fallback: `stt_lang_mode` picks the
multilingual model and the Hindi flag for the holds Parakeet declines, which
is what asking for Hinglish should mean.

## The fix

One condition, in `dictator_core/stt.py`:

```python
-    if language() != "hinglish" and parakeet_ready():
+    if parakeet_ready():
```

## A resident whisper-server is not the answer, and was measured

The obvious theory was a cold model load per hold, so: start the resident
server. `stt.warm()`'s own comment says it was never called from anywhere,
and that "nobody has measured the two populations together, so turning it on
would be a guess dressed as an optimisation". Measured, interleaved, two
passes:

```
holds under 6 s     server up 5.52s   server down 3.35s   server wins 0 of 12
holds 6 s to 25 s   server up 2.56s   server down 2.38s   server wins 1 of 8
weighted            server up 4.34s   server down 2.96s
```

A resident server made it **worse on both populations**, and lost every one
of the twelve short holds. That contradicts the older figure in the same
comment (5.57s CLI against 3.60s server on 57 short holds), so one of the two
was measured under conditions the other was not; this run had a second
Dictator on the machine holding the GPU, and the variance between its passes
was wide (3.86s and 7.18s). Unanimous on twelve is still not noise. Not
started automatically, and the comment stays accurate.

## The two guesses that were wrong

Kept because the way they were wrong is the lesson.

**"Hold to paste went from 1.9 s to 35 s."** The log line is `N ms from
letting go to the words landing`, and I read ten of those without checking
what came before them. Four of the slowest had no `released after Nms` at
all: they were hands free sessions, minute-long voice messages, and thirty
seconds for a minute of audio through turbo is arithmetic, not a regression.
Pairing each landing time with its hold is what showed the real number,
which was a short hold taking three to four times its own length.

**"Nothing is reaching Parakeet, so something is broken."** Nothing was
reaching Parakeet, and nothing was broken. The routing figure of 72.6%
Parakeet in `findings.md` was measured in English mode. Quoting it against a
machine set to Hinglish compared two different products.

## How to see it on your own machine

```bash
grep -oE "released after [0-9]+ms|[0-9]+ ms from letting go" ~/.dictator/dictate.log
grep -c "answered by the multilingual model" ~/.dictator/dictate.log
cat ~/.dictator/lang
```
