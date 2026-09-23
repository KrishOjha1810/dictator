"""Deliver a long transcript into a terminal without it collapsing into a chip.

Pasting works everywhere until the text gets long. Claude Code, running in a
terminal, watches for bracketed paste (the ESC[200~ ... ESC[201~ wrapper a
terminal puts around pasted text so an application can tell a paste from
typing) and, past a size, swallows the whole thing into an attachment:

    [Pasted text #1 +12 lines]

That is the right call for somebody dropping a stack trace in and the wrong
one for somebody who has just spoken a sentence. You cannot read back what you
said, you cannot edit a word of it, and fixing one wrong word means saying the
whole thing again.

The limits are Claude Code's, not ours. They were read out of its shipped
bundle (2.1.280) and then confirmed by pasting into a live session: a paste is
collapsed when it is longer than 800 UTF-16 units OR carries more than two
newlines. 799 characters stayed as words, 801 became a chip, four short lines
became a chip, three did not. Nothing under both limits is ever collapsed,
however much of it there is in total.

So the fix is not a different way of delivering text, it is a smaller one. The
transcript is cut into pieces that each sit under both limits and pasted one
after another into the same field. Every piece arrives as its own paste, under
the threshold, so every piece lands as words, and the field joins them back up
because that is what a text field does with two pastes in a row.

Rejected, and why:

  * Typing the text as synthetic key events. The version that looks obvious
    and is not. Key events are the one path that mangles everything outside
    ASCII, which here means every Devanagari word and every emoji, and a few
    hundred of them is seconds of visible typing during which anything the
    user types interleaves with it. Pasting carried Devanagari and a
    skin-toned emoji through unchanged in the same test.

  * Writing to the terminal's tty with AppleScript `do script`. Terminal.app
    only, and it does not even help: bulk tty input is read as a paste too, so
    it meets the same threshold. The prior art for it in voicebridge is for a
    different job, delivering a prompt into a session nobody is looking at,
    where the collapse does not matter because the text is submitted straight
    away.

Short text is left completely alone: under both limits it is the single paste
it always was. Only a terminal collapses a paste, so only a terminal gets the
cutting up.

Return is never pressed here, for the same reason it is never pressed in the
caller. Putting the words in the field is this program's job; deciding to send
them is the user's.
"""
import re
import subprocess
import time

from . import core, mac

# Claude Code's thresholds are 800 units and 2 newlines. We aim well under the
# character one because the constant belongs to somebody else and can move in
# their next release, and because the cost of being wrong is asymmetric: a few
# extra pastes cost milliseconds, one chip costs the user the whole sentence.
MAX_UNITS = 600
MAX_NEWLINES = 2

# Between pieces. The helper already waits for the previous paste to be read
# before it returns, so this is only breathing room for the app's own input
# handling, and a spoken paragraph still lands in well under a second.
GAP = 0.06

# The apps that collapse a paste. Everything else gets the single paste that
# already works, unchanged.
_TERMINALS = ("terminal", "iterm", "ghostty", "alacritty", "kitty", "wezterm",
              "warp", "hyper", "tabby", "rio")

# Built by the caller on first use. Reused rather than rebuilt here, because
# two processes compiling to the same path is a race for no benefit.
_HELPER = core.STATE_DIR / "bin" / "dictator-paste"

_NEWLINE = re.compile(r"\r\n|\r|\n")


def _is_terminal(app: str) -> bool:
    low = (app or "").strip().casefold()
    return bool(low) and any(t in low for t in _TERMINALS)


def _units(text: str) -> int:
    """Length the way Claude Code counts it.

    It measures a JavaScript string, which is UTF-16 units: an emoji is two,
    a Devanagari letter is one. Python counts code points, so counting the
    Python way would let a sentence full of emoji sit over the limit while we
    believed it was comfortably under."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _newlines(text: str) -> int:
    """Newlines the way Claude Code counts them: \\r\\n is one, not two."""
    return len(_NEWLINE.findall(text))


def _cut(text: str, start: int) -> int:
    """Where the piece beginning at `start` has to end."""
    n = len(text)
    end = start
    units = 0
    lines = 0
    while end < n:
        step = 2 if text[end] == "\r" and text[end + 1:end + 2] == "\n" else 1
        piece = text[end:end + step]
        width = _units(piece)
        if units + width > MAX_UNITS:
            break
        if text[end] in "\r\n":
            if lines + 1 > MAX_NEWLINES:
                break
            lines += 1
        units += width
        end += step
    if end >= n:
        return n
    # Always take something, or a piece that starts with the character we are
    # refusing to fit would loop forever.
    if end == start:
        return min(n, start + 1)
    # Break at a space so a word is not split across two pastes. The field
    # joins them anyway, but a word broken in half mid-paste is exactly what
    # somebody reads as a dropped character and reports as a bug.
    space = text.rfind(" ", start + 1, end)
    if space > start:
        return space + 1
    return end


def _plan(text: str, app_name: str):
    """The pieces to paste, in order. One piece means nothing was changed."""
    if not text:
        return []
    if not _is_terminal(app_name):
        return [text]
    if _units(text) <= MAX_UNITS and _newlines(text) <= MAX_NEWLINES:
        return [text]
    pieces = []
    i = 0
    while i < len(text):
        j = _cut(text, i)
        pieces.append(text[i:j])
        i = j
    return pieces


def _osa(script: str) -> bool:
    """Run AppleScript and say whether it worked.

    mac._osa is the same call with the answer thrown away, which is fine for
    a keystroke nobody checks and useless here, where the return value is the
    only thing standing between an honest False and a claimed success."""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True,
                           text=True, timeout=8)
        if r.returncode != 0:
            core.log(f"paste: osascript rc={r.returncode}: {r.stderr.strip()}")
            return False
        return True
    except Exception as e:
        core.log(f"paste: osascript failed: {e}")
        return False


def _paste_once(text: str) -> bool:
    """One paste, and an honest answer about whether it landed.

    The helper publishes the text as a promise and prints `read` only once
    something has actually asked the pasteboard for it, so its output is a
    receipt rather than a hope. Without the helper we are back to guessing,
    and the guess at least reports the one thing it does know, whether the
    keystroke was accepted."""
    if _HELPER.exists():
        try:
            r = subprocess.run([str(_HELPER), text], capture_output=True,
                               text=True, timeout=10)
            if "read" in (r.stdout or "").split():
                return True
            core.log("paste: the helper never saw the text read: "
                     f"{(r.stdout or '').strip()!r}")
        except Exception as e:
            core.log(f"paste: helper failed: {e}")
    # Wrapped because mac._pbcopy reaches for core.log on failure and mac.py
    # never imports core, so its error path raises NameError. A clipboard that
    # could not be written must come back as False, not as an exception out of
    # the thread that was delivering somebody's sentence.
    try:
        saved = mac._pbpaste()
        mac._pbcopy(text)
        time.sleep(0.05)
        ok = _osa('tell application "System Events" to keystroke "v" '
                  'using command down')
        time.sleep(0.25)
        mac._pbcopy(saved)
        return ok
    except Exception as e:
        core.log(f"paste: the fallback paste failed: {e}")
        return False


def deliver(text: str, app_name: str) -> bool:
    """Put `text` where the cursor is, in one piece or several, and say
    whether all of it arrived.

    `app_name` is the app the key was held in. It decides whether the text
    needs cutting up at all, and it is checked again between pieces: a paste
    that takes several steps has several moments in which the user can switch
    windows, and half a sentence in the wrong window is the failure this whole
    program is built around avoiding. When that happens we stop and say False
    rather than finish the sentence somewhere nobody is looking.

    Return is never pressed."""
    if not text:
        return False
    pieces = _plan(text, app_name)
    if len(pieces) > 1:
        core.log(f"paste: {_units(text)} units and {_newlines(text)} newlines "
                 f"into {app_name or 'the front app'}, delivering as "
                 f"{len(pieces)} pastes so none of them is collapsed")
    for i, piece in enumerate(pieces):
        if i:
            time.sleep(GAP)
            now = mac.frontmost_app()
            if app_name and now and now != app_name:
                core.log(f"paste: focus moved {app_name!r} to {now!r} after "
                         f"{i} of {len(pieces)} pieces, stopping there")
                return False
        if not _paste_once(piece):
            core.log(f"paste: piece {i + 1} of {len(pieces)} did not land")
            return False
    return True
