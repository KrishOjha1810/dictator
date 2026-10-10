"""Dictation that is simply always there.

A key you have to switch on with a command is a key you will forget you have.
The promise of hold-to-talk is that it works the way the keyboard works: you
press it and it does the thing, in any app, without having thought about it
beforehand. That means a login item, not a command.

macOS runs this through launchd, which also restarts it if it ever dies, which
matters more here than usual: a dictation key that silently stopped working is
indistinguishable from a broken keyboard.
"""
import os
import plistlib
import subprocess
from pathlib import Path

from . import core

LABEL = "com.dictator.dictate"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


REPO = Path(__file__).resolve().parent.parent
# In a checkout the app is built here, on this Mac, from native/app. Inside the
# downloadable app it is the app: the login item points at the bundle the user
# dragged into Applications, and nothing is built under their home directory.
# REPO is then Contents/Resources, so the CLI below is the one the app ships.
APP = (core.BUNDLE if core.BUNDLE is not None
       else Path.home() / "Applications" / "Dictator.app")


def _cli() -> str:
    return str(REPO / "bin" / "dictator")


def _bundle_points_here() -> bool:
    """Does the installed bundle run THIS checkout's code.

    The mtime check below asks whether the app is older than its own source. It
    never asked whether the app still points at us, and it does not have to be
    stale to be wrong: a bundle built once with the wrong DictatorCLI stays
    wrong forever, because every later `dictator on` sees a fresh enough binary
    and returns early without looking inside.

    That is not hypothetical. On this machine the installed bundle carried a
    path into a DIFFERENT user account's checkout, eleven hours behind, so
    every fix landed in this one and none of them ever ran. The symptom is the
    worst kind: dictation works, so nothing looks broken, and it is quietly the
    wrong program. The comment in build_app already warned that "a guess that
    is wrong runs somebody else's dictation"; this is the check that makes the
    warning true."""
    try:
        info = plistlib.loads((APP / "Contents" / "Info.plist").read_bytes())
    except Exception:
        return False
    return (info.get("DictatorCLI") == _cli()
            and info.get("DictatorLog") == str(core.STATE_DIR / "dictate.log")
            # A bundle still carrying the shared identifier is fighting another
            # account for one TCC row, and nothing else here would notice.
            and info.get("CFBundleIdentifier") == core.bundle_id())


def _register(app: Path) -> None:
    """Tell LaunchServices the bundle is what it now says it is.

    Changing CFBundleIdentifier in place is invisible to LaunchServices: it
    has the path cached under the OLD identifier and nothing asks it to look
    again. The bundle is then in a state where it exists, is correctly signed,
    and cannot be addressed by the name written inside it.

    What that looks like from the outside, on a real machine:
    `tccutil reset Accessibility com.dictator.dictation.<id>` answers
    `No such bundle identifier` with OSStatus -10814, so the permission cannot
    be cleared; and macOS has no registered app to attach a grant to, so the
    prompt has nothing to prompt about.

    Nothing to undo if it fails: an unregistered bundle is where we already
    were, so this logs and moves on."""
    tool = Path("/System/Library/Frameworks/CoreServices.framework/Frameworks"
                "/LaunchServices.framework/Support/lsregister")
    if not tool.exists():
        return
    try:
        subprocess.run([str(tool), "-f", str(app)],
                       capture_output=True, timeout=60)
    except Exception as e:
        core.log(f"could not register the app with LaunchServices: {e}")


def build_app() -> str:
    """Build the .app that OWNS the permissions.

    Without it, macOS asks the user to approve something called "/usr/bin/env"
    and makes them add it through a file picker, because permissions are
    granted per application and a login item started by launchd is not the
    terminal they granted. With it, there is one entry called "Dictator",
    it asks for itself on first run, and there is nothing to set
    up. That is the entire reason this exists.

    In bundle mode there is nothing to build: the app was built, signed and
    handed over in the .dmg, and rebuilding it here would cost the user the
    permissions they granted to that signature. It is returned as it is."""
    if core.BUNDLE is not None:
        exe = core.BUNDLE / "Contents" / "MacOS" / "Dictator"
        if exe.exists():
            return str(core.BUNDLE)
        core.log(f"dictation app: no executable at {exe}")
        return ""
    src = REPO / "native" / "app"
    if not (src / "main.swift").exists():
        return ""
    import shutil
    if not shutil.which("swiftc"):
        return ""
    # Every file in the directory, not just main.swift: the menu bar, the
    # onboarding cards and the Hub live beside it, and main.swift alone no
    # longer compiles.
    sources = sorted(src.glob("*.swift"))
    # Do not rebuild what has not changed. Every rebuild produces a different
    # binary, and macOS drops the Accessibility grant when the binary changes
    # even though the designated requirement is unchanged, so an unconditional
    # rebuild cost the user their permission on EVERY `dictator on`. The
    # installer ends with `dictator on`, which is why a fresh install spent its
    # first few minutes losing a permission it had just been given.
    macos = APP / "Contents" / "MacOS"
    exe = macos / "Dictator"
    if exe.exists() and _bundle_points_here():
        newest = max((f.stat().st_mtime for f in
                      (*sources, src / "Info.plist") if f.exists()),
                     default=0)
        if exe.stat().st_mtime >= newest:
            return str(APP)
    macos.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["swiftc", "-O", *map(str, sources),
                        "-o", str(macos / "Dictator")],
                       check=True, capture_output=True, timeout=300)
        # Tell the bundle where its own code is. Without this the app has to
        # guess, and a guess that is wrong runs somebody else's dictation.
        info = plistlib.loads((src / "Info.plist").read_bytes())
        info["DictatorCLI"] = _cli()
        info["DictatorLog"] = str(core.STATE_DIR / "dictate.log")
        # Per account. The template in the repo stays generic; the identifier
        # that decides which system-wide TCC row this app owns is written here.
        # See core.bundle_id for why sharing one is unfixable.
        info["CFBundleIdentifier"] = core.bundle_id()
        (APP / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
        _sign(APP)
        _register(APP)
        return str(APP)
    except Exception as e:
        core.log(f"dictation app build failed: {e}")
        return ""


def build_all(force: bool = False) -> dict:
    """Compile every helper now, rather than one at a time on first use.

    There are five, and each one used to be built the first time something
    reached for it: the key listener when dictation starts, the recorder on
    the first hold, the indicator a moment later, the paste helper when the
    first sentence is ready, the reader after that. swiftc takes one to three
    seconds each, and they land in the middle of the first few holds, which is
    the exact window where somebody is deciding whether this works. That is
    the slow first few minutes in issue #1, and the installer is a far better
    place to spend those seconds than the first sentence is.

    Returns {name: path or ""}. Order matters: the app bundle goes last,
    because it is the one whose rebuild costs a permission, and build_app
    skips it when nothing changed."""
    from . import hotkey, media, orbnative, paste, readback, recorder
    built = {
        "hotkey": hotkey.build(force),
        "orb": orbnative.build(force),
        "recorder": recorder.build(force),
        "paste": paste.helper(),
        "readback": readback.build(force),
        "media": media.build(force),
    }
    # Deliberately NOT forced. Every rebuild of the bundle is, to macOS, an
    # application that has never been granted anything, so forcing it here
    # would trade a slow first minute for the Accessibility permission the
    # user just granted. See build_app.
    built["app"] = build_app()
    return built


def _sign(app: Path) -> None:
    """Sign the bundle so macOS keeps recognising it after a rebuild.

    An ad-hoc signature identifies the app by the hash of its own binary, so
    rebuilding it revokes Microphone and Accessibility without warning and
    without changing anything the user can see. Signing against a local
    certificate makes the identity the certificate instead, which rebuilding
    does not touch. See signing.py."""
    from . import signing
    if not signing.local():
        return
    who = signing.identity()
    args = ["codesign", "--force", "-s", who or "-", str(app)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        # Falling back matters more than signing well: an unsigned app cannot
        # hold a permission at all, while an ad-hoc one at least works until
        # the next rebuild.
        core.log(f"dictation app signing failed ({who or 'ad-hoc'}): "
                 f"{r.stderr.strip()[:200]}")
        if who:
            subprocess.run(["codesign", "--force", "-s", "-", str(app)],
                           capture_output=True, timeout=120)
        return
    # Say so out loud when the identity is still the binary hash, because the
    # symptom otherwise is a permission that stops working for no visible
    # reason several rebuilds later.
    if "cdhash" in signing.requirement(app):
        core.log("dictation app is ad-hoc signed: macOS will forget its "
                 "permissions on the next rebuild")


def installed() -> bool:
    return PLIST.exists()


def running() -> bool:
    try:
        r = subprocess.run(["launchctl", "list", LABEL],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def on(key: str = "fn") -> str:
    """Install and start. Returns a message to print.

    Stops whatever is already running first. Without that this was not
    idempotent, and it looked like it was: running the installer twice left
    two listeners, both watching the same key, so every hold was handled twice
    and every sentence was pasted twice. The symptom reads as a bug in the
    paste path, which is where the time goes looking for it."""
    _stop_everything()
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    log = str(core.STATE_DIR / "dictate.log")
    # Prefer the bundle: it carries its own permission entry, so the user is
    # asked once, by name, with a reason, and never has to find a checkbox.
    app = build_app()
    if app:
        args = [str(Path(app) / "Contents" / "MacOS" / "Dictator")]
    else:
        args = ["/usr/bin/env", "python3", _cli(), "dictate", key]
    core.STATE_DIR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        # NOT --quiet. With no terminal attached this is the only record of
        # what happened, and "it silently did nothing" is the failure we are
        # most likely to hit here.
        "ProgramArguments": args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": log,
        "StandardErrorPath": log,
        # launchd hands a process almost no PATH, and whisper lives in
        # Homebrew. This is the single most common reason a thing that works
        # in a terminal does nothing as a login item.
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(Path.home()),
        },
    }
    # Clear any previous copy FIRST. Doing it after writing deletes the file
    # we just wrote, which is exactly what it did.
    off(quiet=True)
    with open(PLIST, "wb") as f:
        plistlib.dump(plist, f)
    try:
        subprocess.run(["launchctl", "load", "-w", str(PLIST)],
                       capture_output=True, timeout=15)
    except Exception as e:
        return f"wrote {PLIST} but could not start it: {e}"
    how = ("It will ask for the microphone and for Accessibility the first "
           "time, by name.\n" if app else
           "No app bundle (needs Xcode tools), so the permission prompt will "
           "name python3.\n")
    head = (f"Dictation is on, and stays on after a restart.\n"
            f"  Hold {key} anywhere and talk.\n"
            f"  {how}"
            f"  Off:  dictator off\n"
            f"  Log:  {log}")
    return head + _permission_warning()


def _permission_warning() -> str:
    """Say it in the terminal that just ran `dictator on`, not only in a log.

    The state this exists for is a listener that starts, finds it is not
    trusted, and waits forever. All the evidence for that used to be one line
    in a file nobody had been told to open, so from the outside `dictator on`
    printed a cheerful paragraph and dictation was dead. Whatever else is
    true, the terminal the user is looking at is where this belongs.

    Given a second to settle, because the app writes its answer the moment it
    finds out and that is quick."""
    import time
    try:
        from . import tcc
        time.sleep(2.0)
        info = tcc.state("accessibility")
        if info["state"] == tcc.GRANTED:
            return ""
        if info["state"] == tcc.UNREADABLE and not tcc.stuck():
            return ""          # nothing to report and no evidence of trouble
        return ("\n\n" + "-" * 68 + "\n"
                + tcc.report() + "\n" + "-" * 68)
    except Exception as e:
        core.log(f"could not check the Accessibility grant: {e}")
        return ""


def off(quiet: bool = False) -> str:
    try:
        subprocess.run(["launchctl", "unload", str(PLIST)],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    try:
        PLIST.unlink()
    except Exception:
        pass
    # Leave nothing holding the microphone behind.
    # dictator-orb too: leaving it behind means the next start finds it "already
    # running" and keeps a stale build on screen, which is how an orb that had
    # been fixed went on behaving like the broken one.
    _stop_everything()
    return "" if quiet else "Dictation is off."


def _stop_everything() -> None:
    """Leave nothing holding the microphone or the key.

    Scoped to this user, because a second account on the same Mac runs its own
    copy and killing theirs is not ours to do."""
    import getpass
    me = getpass.getuser()
    for pat in ("bin/dictator dictate", "dictator-hotkey", "dictator-orb"):
        try:
            subprocess.run(["pkill", "-u", me, "-f", pat],
                           capture_output=True, timeout=10)
        except Exception:
            pass


def status() -> str:
    if not installed():
        return "Dictation is not set to start on its own.  (dictator on)"
    return ("Dictation starts on login and is running now."
            if running() else
            "Dictation is installed but not running. Check: dictator log")
