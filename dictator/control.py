"""A way to reach the running dictation loop from outside it.

The pill's buttons (native/orb.swift) and `dictator hands-free` send one word
to the loop: start or finish a hands free session, or throw it away. The loop
passes it to the key listener on its stdin, so a session has one owner however
it began: a double tap of the key, or a click.

    toggle   no session: open one. In one: finish it, transcribe and paste.
    finish   in a session: finish it, transcribe and paste.
    cancel   in a session: stop and discard. Nothing is pasted.

THE CHANNEL is a Unix datagram socket at STATE_DIR/dictate.sock, bound by the
loop for its whole life.

  * One datagram is one command, so there is no framing to get wrong and no
    partial read.
  * Nobody bound means the send fails at once (ECONNREFUSED, or no file),
    rather than reaching a stranger. A signal to a pid from a file could reach
    whatever process got that pid after a crash, and on an older loop that
    does not handle the signal its default action is to kill it.
  * Only one loop serves: binding is guarded by an flock on dictate.sock.lock,
    which the kernel drops when the loop dies, however it dies. A second loop
    on the same state directory does not steal the socket from the first.
  * The socket file is made owner-only, so another account on the Mac cannot
    open your microphone through it.

Paths are computed at call time from core.STATE_DIR, so a test or a
DICTATOR_STATE run never touches the real one. A sun_path is at most 104
bytes on macOS; a state directory too deep for that gets no channel, and says
so in the log, rather than a socket somewhere else that the pill cannot find.
"""
import fcntl
import os
import socket

from . import core

COMMANDS = ("toggle", "finish", "cancel")
SOCK_NAME = "dictate.sock"
MAX_PATH = 103


def sock_path():
    return core.STATE_DIR / SOCK_NAME


def _lock_path():
    return core.STATE_DIR / (SOCK_NAME + ".lock")


class Server:
    """The loop's end. `fileno()` goes into its select(); `read()` returns the
    commands that arrived, oldest first."""

    def __init__(self):
        self.sock = None
        self._lock = None
        self.path = sock_path()

    def start(self) -> bool:
        """Bind. False, with the reason logged, when another loop already
        serves this state directory or the path is too long."""
        p = str(self.path)
        if len(p.encode()) > MAX_PATH:
            core.log(f"control: {p} is too long for a socket, no pill buttons")
            return False
        try:
            core.STATE_DIR.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(_lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as e:
            core.log(f"control: cannot open the lock: {e}")
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            core.log("control: another dictation loop already serves the pill")
            return False
        self._lock = fd
        try:
            # Ours now: whatever file is there was left by a loop that died.
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            old = os.umask(0o077)
            try:
                s.bind(p)
            finally:
                os.umask(old)
            s.setblocking(False)
            self.sock = s
            return True
        except OSError as e:
            core.log(f"control: cannot bind {p}: {e}")
            self.close()
            return False

    def fileno(self) -> int:
        return self.sock.fileno() if self.sock else -1

    def read(self) -> list:
        """Every command waiting, oldest first. Unknown words are dropped."""
        out = []
        if not self.sock:
            return out
        while True:
            try:
                data = self.sock.recv(64)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            word = data.decode("utf-8", "replace").strip().lower()
            if word in COMMANDS:
                out.append(word)
        return out

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
            try:
                os.unlink(str(self.path))
            except OSError:
                pass
        if self._lock is not None:
            try:
                os.close(self._lock)       # drops the flock
            except OSError:
                pass
            self._lock = None


def send(command: str) -> bool:
    """Send one command to the running loop. True if a loop received it."""
    if command not in COMMANDS:
        raise ValueError(f"command must be one of: {', '.join(COMMANDS)}")
    p = str(sock_path())
    if len(p.encode()) > MAX_PATH:
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.sendto(command.encode(), p)
        return True
    except OSError:
        return False
    finally:
        s.close()


def serving() -> bool:
    """Is a loop holding the channel right now. Asked of the lock, which the
    kernel drops on death, never of the socket file, which a crash leaves."""
    try:
        fd = os.open(str(_lock_path()), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)
