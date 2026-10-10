# Dictator

Hold a key. Talk. The words land where your cursor is.

Local, private dictation for macOS that works in any app (terminal, browser,
Slack, any text field) and understands English, Hindi and Hinglish. Everything
runs on your Mac. No audio leaves it, and there is no account.

**[Download for Mac](https://github.com/mynk03/dictator/releases/latest/download/Dictator.dmg)**
· Apple silicon · macOS 14+ · [All releases](https://github.com/mynk03/dictator/releases)

---

## Why

Built-in Mac dictation is poor at anything that is not plain English, and the
good alternatives are subscriptions that send your voice to a server.

The specific gap is Hinglish. Say "yaar ye function thoda slow lag raha hai,
can you check the loop" and most tools give you mangled English or Devanagari
you cannot paste into a terminal. Dictator writes it in Latin script, the way
people actually type it.

## Features

- **Hold to talk, double-tap for hands free.** Works in every app, because it
  pastes the way you would have typed.
- **English, Hindi and Hinglish**, with the engine picked per sentence.
- **Learns your words.** `dictator review` asks about the words it got wrong;
  one answer fixes a name for good.
- **Snippets.** Say "my work email", get the address.
- **Per-app formatting.** Lists in Slack, plain sentences in the terminal.
- **Search and recap** of everything you dictated, summarised on your Mac.
- **Meeting notes** from your mic and system audio, transcribed locally.
- **A Python library**: `.wav` in, finished text out.

## Install

**The app.** Download the `.dmg`, drag Dictator into Applications, and open it
from there. Because the app is free and not notarized, macOS blocks the first
open: press **Done**, then **System Settings → Privacy & Security → Open
Anyway**. This happens once. Full steps: [`docs/install.md`](docs/install.md).

**From source.** Needs Homebrew and Apple's command line tools.

```bash
git clone https://github.com/cc-vb/dictator.git ~/dictator
cd ~/dictator && scripts/install.sh
```

Allow the microphone and Accessibility when macOS asks. English works in about
two minutes; the Hindi and Hinglish model keeps downloading in the background.

## Quick start

```bash
dictator on          # start now, and after every restart
dictator doctor      # if anything is wrong, this names it
```

Hold the key, speak, let go. The app's key is **right ⌥ Option**; the source
install's is **fn** (set the Globe key to Do Nothing first, see
[install](docs/install.md#the-globe-fn-key)).

| Command | What it does |
|---|---|
| `dictator on [key]` / `off` | start or stop |
| `dictator status` / `doctor` | is it running, what is wrong |
| `dictator find WORDS` | search everything you dictated |
| `dictator recap [today\|week\|N]` | what you dictated, summarised locally |
| `dictator snippet "PHRASE" "TEXT"` | say the phrase, get the text |
| `dictator review` | teach it the words it got wrong |
| `dictator meeting start\|stop` | record a meeting and get notes |
| `dictator forget "WORDS"` | erase what you said containing them |

Every command: [`docs/usage.md`](docs/usage.md).

## Documentation

| Doc | For |
|---|---|
| [Install](docs/install.md) | app and source install, troubleshooting, the permissions trap |
| [Usage](docs/usage.md) | dictating, the pill, snippets, search, formatting, recap, review |
| [Meetings](docs/meetings.md) | recording meetings, consent, permissions |
| [Library](docs/library.md) | using Dictator from Python |
| [Architecture](docs/architecture.md) | how it works, code signing, privacy |
| [Findings](docs/findings.md) | measured results: models, latency, macOS behaviour |
| [Platforms](docs/platforms.md) | Windows, iOS, Android, and Mac distribution |
| [Contributing](docs/CONTRIBUTING.md) | dev setup, tests, rules, branches and commits |
| [Releasing](docs/releasing.md) | publishing a signed, self-updating release |
| [Cloudflare R2](docs/cloudflare-r2.md) | serving releases from R2 instead of GitHub, switched off for now |

## Development

```bash
python3 -m pip install pytest jellyfish
python3 -m pytest -q tests        # the test suite CI runs
tools/build_native.sh build/native   # Swift helpers and whisper.cpp
tools/build_dmg.sh                   # the app bundle and .dmg
```

| Path | What lives there |
|---|---|
| `dictator/` | the Python package: the dictation loop, CLI, library |
| `native/` | Swift: key listener, recorder, indicator, the app |
| `tools/` | build, release and benchmark scripts |
| `tests/` | pytest suite |
| `website/` | the public site (Astro), see [`website/README.md`](website/README.md) |

Before opening a pull request, read [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).
Releases are cut from `main` only; see [`docs/releasing.md`](docs/releasing.md).

## Status

**Working:** the held key and hands free mode, the indicator, local
transcription with English/Hinglish routing, permissions that survive a
rebuild, recap, meetings, and the self-updating app.

**In progress:** Hinglish word accuracy, learning corrected words, and pasting
long text without it arriving as an attachment.

The app is a preview and has had less use than the source install, which is
the fallback if anything goes wrong.

## Credits

Speech recognition runs on [whisper.cpp](https://github.com/ggerganov/whisper.cpp).
The Hindi romanization lexicon is derived from
[Google Dakshina v1.0](https://github.com/google-research-datasets/dakshina),
used under CC BY-SA 4.0.

Dictator is also the dictation layer under voicebridge and Friday.
