"""Compiling the Swift helpers, in one place.

There are five (the key listener, the indicator, the recorder, the paste helper
and the readback reader) and each one used to carry its own near identical copy
of this: exists, mtime, swiftc, run, log. Five copies of one decision is five
places for it to drift, and two of them had already drifted in ways nobody
would notice until it mattered.

Both things every copy got wrong are about writing straight to the final path.
macOS refuses to write an executable that is currently running (ETXTBSY), which
is exactly the case on an upgrade, when the source is newer and the old helper
is still up. And a build that fails halfway leaves a truncated binary at the
real path, which the next mtime check reads as "already built" and runs.
Compiling beside it and renaming avoids both: a rename is atomic and unlinks
the old file rather than writing through it, so a running helper keeps the copy
it started with and the next launch gets the new one.

Inside the app none of that applies. The helpers there were built and signed
before the .dmg was made, the user's Mac may have no swiftc at all, and a
helper rebuilt in place would carry a different signature from the one the
user granted. So in bundle mode this never compiles: the prebuilt helper is
used as it is, or it is reported missing.
"""
import os
import shutil
import subprocess
from pathlib import Path

from . import core


def compile_if_needed(src, out, what: str, force: bool = False,
                      timeout: int = 240, hint: str = "") -> str:
    """Build `src` to `out` if it is missing or older. Path, or "" with a
    reason logged. Never raises: a helper that cannot be built has to degrade
    to its fallback, not take the dictation path down with it."""
    src, out = Path(src), Path(out)
    if core.BUNDLE is not None:
        return prebuilt(out, what)
    if not src.exists():
        core.log(f"{what}: source missing at {src}")
        return ""
    if out.exists() and not force and out.stat().st_mtime >= src.stat().st_mtime:
        return str(out)
    if not shutil.which("swiftc"):
        core.log(f"{what}: swiftc not found" + (f"; {hint}" if hint else ""))
        return ""
    tmp = out.with_name(out.name + ".new")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", str(src), "-o", str(tmp)],
                       check=True, capture_output=True, timeout=timeout)
        os.replace(tmp, out)
        return str(out)
    except subprocess.CalledProcessError as e:
        core.log(f"{what}: build failed: {(e.stderr or b'').decode()[:400]}")
    except Exception as e:
        core.log(f"{what}: build failed: {e}")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return ""


def prebuilt(out, what: str) -> str:
    """The helper the app shipped with. Path, or "" with a reason logged.

    Missing means the bundle was assembled wrong, and there is nothing the
    user can do about that from here except get a good copy, so the error says
    so instead of suggesting the Xcode tools."""
    out = Path(out)
    if out.exists() and os.access(out, os.X_OK):
        return str(out)
    core.surface_error(
        what, f"The app is missing its {what} helper ({out.name}).",
        hint="The app bundle is incomplete. Download Dictator again.")
    return ""
