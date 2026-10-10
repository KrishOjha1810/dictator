"""The channel the pill's buttons use to reach the running dictation loop.

A datagram socket in the state directory, bound by one loop at a time under an
flock. These pin the parts that, done wrong, open somebody's microphone or
reach the wrong process: nobody listening means the send fails, a second loop
cannot steal the socket, and only the three known words do anything.
"""
import io
import os
import shutil
import stat
import tempfile
from pathlib import Path

import pytest

from dictator_core import control, core, dictate


@pytest.fixture
def short_state(monkeypatch):
    # A socket path is at most 104 bytes on macOS, and pytest's tmp_path is
    # longer than that, so these run in a short directory of their own.
    d = Path(tempfile.mkdtemp(prefix="dct-", dir="/tmp"))
    monkeypatch.setattr(core, "STATE_DIR", d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_a_command_reaches_the_loop(short_state):
    s = control.Server()
    assert s.start()
    try:
        assert control.serving()
        assert control.send("toggle")
        assert control.send("cancel")
        assert s.read() == ["toggle", "cancel"]
        assert s.read() == []
    finally:
        s.close()


def test_nobody_listening_means_the_send_fails(short_state):
    assert control.send("toggle") is False
    assert control.serving() is False


def test_a_socket_left_by_a_dead_loop_is_not_mistaken_for_a_live_one(short_state):
    s = control.Server()
    assert s.start()
    s.sock.close()           # as if killed: the file stays, nobody reads it
    s.sock = None
    os.close(s._lock)        # the kernel drops the flock on death
    s._lock = None
    assert control.sock_path().exists()
    assert control.serving() is False
    assert control.send("toggle") is False


def test_a_second_loop_cannot_steal_the_socket(short_state):
    first = control.Server()
    assert first.start()
    try:
        second = control.Server()
        assert second.start() is False
        assert control.send("finish")
        assert first.read() == ["finish"]
    finally:
        first.close()


def test_closing_removes_the_socket_and_frees_it(short_state):
    s = control.Server()
    assert s.start()
    s.close()
    assert not control.sock_path().exists()
    assert control.serving() is False
    again = control.Server()
    assert again.start()
    again.close()


def test_only_the_owner_can_use_it(short_state):
    s = control.Server()
    assert s.start()
    try:
        mode = stat.S_IMODE(os.stat(control.sock_path()).st_mode)
        assert mode & 0o077 == 0, oct(mode)
    finally:
        s.close()


def test_unknown_words_do_nothing(short_state):
    import socket
    s = control.Server()
    assert s.start()
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        c.sendto(b"rm -rf", str(control.sock_path()))
        c.sendto(b"TOGGLE\n", str(control.sock_path()))
        c.close()
        assert s.read() == ["toggle"]
    finally:
        s.close()
    with pytest.raises(ValueError):
        control.send("open the mic")


def test_a_state_directory_too_deep_for_a_socket_gets_no_channel(monkeypatch):
    monkeypatch.setattr(core, "STATE_DIR", Path("/tmp/" + "x" * 120))
    assert control.Server().start() is False
    assert control.send("toggle") is False


# ---- the loop passes commands on to the key listener, which owns sessions

class _Listener:
    def __init__(self):
        self.stdin = io.StringIO()

    def poll(self):
        return None


def test_the_loop_hands_each_command_to_the_listener():
    p = _Listener()
    assert dictate.command(p, "toggle")
    assert dictate.command(p, "finish")
    assert dictate.command(p, "cancel")
    assert p.stdin.getvalue() == "TOGGLE\nFINISH\nCANCEL\n"
    assert dictate.command(p, "shout") is False


def test_a_listener_that_is_gone_is_not_written_to():
    class Gone(_Listener):
        def poll(self):
            return 0
    assert dictate.command(Gone(), "toggle") is False


# ---- the command line

def _cli():
    # The CLI body lives in dictator_core.cli now; bin/dictator is just a launcher.
    import importlib
    return importlib.import_module("dictator_core.cli")


def test_cli_says_when_nothing_is_running(short_state, capsys):
    assert _cli().main(["dictator", "hands-free"]) == 1
    assert "not running" in capsys.readouterr().out


def test_cli_sends_to_a_running_loop(short_state, capsys):
    s = control.Server()
    assert s.start()
    try:
        assert _cli().main(["dictator", "hands-free", "cancel"]) == 0
        assert s.read() == ["cancel"]
        assert _cli().main(["dictator", "hands-free", "explode"]) == 2
    finally:
        s.close()
