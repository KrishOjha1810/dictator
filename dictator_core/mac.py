"""The macOS bits: what has focus, and the pasteboard.

Dictation needs to know which application the cursor was in when the key went
down, and it needs to put text on the pasteboard and press Command-V. That is
the entire surface. It used to come from a 644-line OS abstraction layer built
for a voice assistant that also spoke, played audio and converted iPhone
photos, none of which a dictation key does.

macOS only, on purpose. The held key is a CGEventTap, the indicator is
AppKit, the login item is launchd and the permissions are TCC. There is no
part of this that a cross-platform shim would carry over, so pretending
otherwise would only have made the code harder to read.
"""
import subprocess

from . import core

def _pbpaste() -> str:
    try:
        return subprocess.run(["pbpaste"], capture_output=True,
                              text=True).stdout
    except Exception:
        return ""


def _pbcopy(text: str) -> None:
    try:
        subprocess.run(["pbcopy"], input=text, text=True)
    except Exception as e:
        core.log(f"pbcopy failed: {e}")


def _osa(script: str) -> None:
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True)
        if r.returncode != 0:
            core.log(f"osascript rc={r.returncode}: {r.stderr.strip()}")
    except Exception as e:
        core.log(f"osascript failed: {e}")


def frontmost_app() -> str:
    """Name of the app that will receive the paste; logged for diagnosis."""
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first '
             'application process whose frontmost is true'],
            capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return ""
