# Install

Dictator runs on Apple silicon Macs with macOS 14 or newer. There are two ways
to install it: the app, or from source. The source install has had more use
and is the fallback if anything in the app goes wrong.

- [The app](#the-app)
- [From source](#from-source)
- [The Globe (fn) key](#the-globe-fn-key)
- [Troubleshooting](#troubleshooting)

---

## The app

**[Download Dictator for Mac](https://github.com/cc-vb/dictator/releases/latest/download/Dictator.dmg)**
(about 24 MB). Every version, with its SHA256, is on the
[releases page](https://github.com/cc-vb/dictator/releases).

1. Open `Dictator.dmg` and drag Dictator into Applications. Open it from
   Applications, not from the disk image window: macOS stops a copy run from
   the disk image after a few seconds. If you do open that one, it offers to
   move itself to Applications.
2. Open Dictator. macOS stops it, because Dictator is free and not paid into
   Apple's developer programme. Press **Done**, not Move to Trash (or Move to Bin).
3. Open **System Settings → Privacy & Security**, scroll down, and press
   **Open Anyway** next to Dictator. Confirm. This happens once.
4. Allow the microphone and Accessibility when it asks. The speech models
   download on first launch, English first (about 700 MB), then Hindi and
   Hinglish in the background (1.5 GB). Each is checked against its published
   SHA256 before it is used.
5. Hold **right ⌥ Option** and talk; double-tap it for hands free. That is the
   app's key unless you change it, and it needs no other setup.

The app updates itself. Why the first-open warning exists, and what it does
and does not mean, is in [`platforms.md`](platforms.md).

---

## From source

```bash
git clone https://github.com/cc-vb/dictator.git ~/dictator
cd ~/dictator && scripts/install.sh
```

What the installer needs:

- **Homebrew**, for one package: `whisper-cpp`, to transcribe.
- **Apple's command line tools**, to build the key listener.

It tells you what is missing rather than guessing. Recording needs nothing
installed: it goes through AVFoundation, which is already on your Mac.
`scripts/install.sh` is idempotent, so if it fails halfway, fix the one thing it
complained about and run it again.

English works as soon as it finishes, in about two minutes. The larger model
for Hindi and Hinglish keeps downloading in the background and starts working
when it lands; `dictator doctor` says which half is ready.

macOS then asks to allow **Dictator** to use the microphone and Accessibility.
Say yes to both. There is nothing to restart afterwards.

```bash
dictator on        # start now, and after every restart
```

The source install's key is `fn` by default. `dictator on rightopt` (or
`rightcmd`, `leftcmd`) picks another.

---

## The Globe (fn) key

Only needed if your key is `fn`. Open **System Settings → Keyboard** and set
**Press 🌐 key to** to **Do Nothing**.

macOS acts on every quick tap of fn itself (the emoji picker, the input
source, or Apple's own dictation), and a double tap of fn is how you start
hands free dictation here. Dictator only listens to the keyboard and cannot
stop macOS from acting on it. Holding is never affected. Wispr Flow asks for
the same change. The app's "Choose your key" card has a button that opens the
right pane.

---

## Troubleshooting

### Start here

```bash
dictator doctor
```

It checks the things that actually break and names the one that is wrong.

### The key does nothing, and the Accessibility checkbox is already on

That is a real macOS state and not a mistake anyone made. The list in System
Settings is drawn from an entry; whether an app is trusted is decided by a code
signature stored next to that entry. When the signature changes, the entry
survives with the old one, so the switch stays on, the app stays untrusted, and
macOS never asks again because it already has an answer on file.

Switching that toggle off and on cannot fix it. The entry has to be removed:

```bash
dictator permissions            # says which problem this is, and the steps
dictator permissions --reset    # does the steps for you
```

By hand: System Settings → Privacy & Security → Accessibility, click
**Dictator**, click the **minus** button under the list, then
`dictator off && dictator on` and say yes.

Why this happens at all is in [`architecture.md`](architecture.md#why-it-is-signed).

### Every sentence is pasted twice

Another app is listening to the same key. Dictator says so in its menu and on
Home when it recognises the app: Wispr Flow, Superwhisper, MacWhisper, Aqua
Voice, Willow, and Warp's voice input (`voice_input_toggle_key` in
`~/.warp/settings.toml`, which is fn by default). Quit the other app, change
its key, or change Dictator's key in Settings.

If the second copy reads like a cleaned-up rewrite of the first, it came from
the other app: `dictator history` shows the only copy Dictator wrote.

### Debugging another user account on the same Mac

Every command reads `~/.dictator`. `DICTATOR_STATE` points one at a different
installation:

```bash
DICTATOR_STATE=/Users/someone/.dictator dictator log
DICTATOR_STATE=/Users/someone/.dictator dictator errors
```

It reads whatever that account has left world readable, which is the log and
the error list. The history is not: it holds everything that account has ever
said and is theirs. Put this on the one command, never in a shell profile, or
a listener started from that shell writes into somebody else's directory.
