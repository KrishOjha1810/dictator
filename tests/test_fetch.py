"""The app downloads its own models, and never keeps one it cannot verify.

Served from a local HTTP server, so nothing here touches the network or the
real model directory."""
import fcntl
import hashlib
import http.server
import threading

import pytest

from dictator_core import core, fetch, stt


@pytest.fixture
def server():
    files = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = files.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            rng = self.headers.get("Range", "")
            files.setdefault("_ranges", []).append(rng)
            if rng.startswith("bytes=") and files.get("_honour_range", True):
                start = int(rng[6:].rstrip("-"))
                body = body[start:]
                self.send_response(206)
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield files, f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def models(tmp_path, monkeypatch, server):
    """Two fake models, one English (essential) and one not, served locally."""
    files, base = server
    d = tmp_path / "models"
    monkeypatch.setattr(stt, "MODEL_DIR", d)
    monkeypatch.setattr(stt, "SHIPPED", (
        ("en.bin", 1, "English", True),
        ("hi.bin", 1, "Hinglish", False),
    ))
    sources = {}
    for name, body in (("en.bin", b"english" * 1000), ("hi.bin", b"hindi" * 900)):
        files["/" + name] = body
        sources[name] = (base + "/" + name, len(body),
                         hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(fetch, "SOURCES", sources)
    return d, files, sources


def test_missing_models_are_downloaded_english_first(models):
    d, _, _ = models
    assert fetch.fetch_missing() == ["en.bin", "hi.bin"]
    assert (d / "en.bin").read_bytes() == b"english" * 1000
    assert not stt.missing()
    assert not list(d.glob("*.part"))


def test_a_model_that_does_not_match_its_hash_is_not_kept(models):
    d, files, _ = models
    files["/en.bin"] = b"english" * 999 + b"swapped"   # same length, other bytes
    got = fetch.fetch_missing()
    assert "en.bin" not in got
    assert not (d / "en.bin").exists()
    # no stale .part, or the app would say "downloading" forever
    assert not (d / "en.bin.part").exists()
    # and the failure is visible, and the next model was still tried
    assert "could not download en.bin" in core.ERRORS_FILE.read_text()
    assert got == ["hi.bin"]


def test_a_short_download_is_not_kept(models):
    d, files, _ = models
    files["/en.bin"] = b"english" * 10
    fetch.fetch_missing(["en.bin"])
    assert not (d / "en.bin").exists()
    assert not (d / "en.bin.part").exists()


def test_a_model_already_here_is_not_downloaded_again(models):
    d, files, _ = models
    d.mkdir(parents=True)
    (d / "en.bin").write_bytes(b"already")
    assert fetch.fetch_missing() == ["hi.bin"]
    assert (d / "en.bin").read_bytes() == b"already"


def test_a_second_process_does_not_download_the_same_files(models):
    d, _, _ = models
    d.mkdir(parents=True)
    with open(d / ".fetch.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert fetch.fetch_missing() == []
    assert not (d / "en.bin").exists()


def test_nothing_starts_when_nothing_is_missing(models):
    fetch.fetch_missing()
    assert fetch.in_background() is None


def test_the_shipped_models_all_have_a_verified_source():
    for name, *_ in stt.SHIPPED:
        url, size, sha = fetch.SOURCES[name]
        assert url.startswith("https://huggingface.co/")
        assert size > 0 and len(sha) == 64


def test_an_interrupted_download_is_continued_not_restarted(models):
    d, files, _ = models
    d.mkdir(parents=True)
    whole = files["/en.bin"]
    (d / "en.bin.part").write_bytes(whole[:3000])
    fetch.fetch("en.bin")
    assert (d / "en.bin").read_bytes() == whole
    assert files["_ranges"][-1] == "bytes=3000-"


def test_a_server_that_ignores_the_range_still_gives_a_whole_file(models):
    d, files, _ = models
    d.mkdir(parents=True)
    files["_honour_range"] = False
    (d / "en.bin.part").write_bytes(files["/en.bin"][:3000])
    fetch.fetch("en.bin")
    assert (d / "en.bin").read_bytes() == files["/en.bin"]


def test_a_bad_part_is_removed_so_it_is_never_continued(models):
    d, files, _ = models
    d.mkdir(parents=True)
    (d / "en.bin.part").write_bytes(b"x" * 3000)     # not the real start
    with pytest.raises(fetch.Mismatch):
        fetch.fetch("en.bin")
    assert not (d / "en.bin.part").exists()


def test_downloads_run_in_their_own_process(models, monkeypatch):
    started = []

    class P:
        def __init__(self, args, **kw):
            started.append((args, kw))

    monkeypatch.setattr(fetch.subprocess, "Popen", P)
    assert fetch.in_background() is not None
    args, kw = started[0]
    assert args[-2:] == ["models", "fetch"]
    assert kw.get("start_new_session") is True


# --- removing a model, and getting it back -----------------------------------

@pytest.fixture
def here(models, monkeypatch):
    """Both fake models on disk, in the directory this product owns."""
    d, _, _ = models
    monkeypatch.delenv("DICTATOR_MODELS", raising=False)
    assert d == core.STATE_DIR / "models"
    fetch.fetch_missing()
    return d


def test_a_removed_model_is_deleted_and_says_how_much_it_freed(here):
    got = stt.remove("en.bin")
    assert got["freed"] == len(b"english" * 1000)
    assert not (here / "en.bin").exists()
    assert stt.model_status()["en.bin"]["removed"] is True


def test_a_removed_model_is_not_downloaded_back_behind_the_users_back(here):
    stt.remove("hi.bin")
    assert fetch.fetch_missing() == []
    assert fetch.in_background() is None
    assert not (here / "hi.bin").exists()


def test_asking_for_a_removed_model_by_name_brings_it_back(here):
    stt.remove("hi.bin")
    assert fetch.fetch_missing(["hi.bin"], wait=True) == ["hi.bin"]
    assert (here / "hi.bin").exists()
    assert stt.model_status()["hi.bin"]["removed"] is False


def test_a_half_downloaded_model_is_removed_with_its_part_file(here):
    stt.remove("hi.bin")
    (here / "hi.bin.part").write_bytes(b"half")
    stt._set_removed("hi.bin", False)
    stt.remove("hi.bin")
    assert not (here / "hi.bin.part").exists()


def test_removing_the_hinglish_model_moves_the_language_off_hinglish(here):
    (core.STATE_DIR / "lang").write_text("hinglish")
    assert stt.remove("hi.bin")["language"] == "english"
    assert stt.language() == "english"


def test_removing_an_english_model_leaves_the_language_alone(here):
    (core.STATE_DIR / "lang").write_text("hinglish")
    assert stt.remove("en.bin")["language"] is None
    assert stt.language() == "hinglish"


def test_models_shared_with_another_app_are_not_removed(models, monkeypatch,
                                                       tmp_path):
    shared = tmp_path / "voicebridge"
    shared.mkdir()
    (shared / "en.bin").write_bytes(b"x")
    monkeypatch.setattr(stt, "MODEL_DIR", shared)
    monkeypatch.delenv("DICTATOR_MODELS", raising=False)
    with pytest.raises(ValueError, match="another app"):
        stt.remove("en.bin")
    assert (shared / "en.bin").exists()


def test_a_model_that_is_downloading_is_not_removed(here):
    stt.remove("hi.bin")
    import os
    (here / ".fetch.pid").write_text(f"{os.getpid()} hi.bin")
    with pytest.raises(ValueError, match="downloading"):
        stt.remove("hi.bin")
    assert stt.model_status()["hi.bin"]["downloading"] is True


def test_an_unknown_model_name_is_an_error_not_a_quiet_nothing():
    with pytest.raises(ValueError, match="english"):
        stt.resolve_model("englsh")
    assert stt.resolve_model("Hinglish") == "ggml-large-v3-turbo.bin"


def test_a_failed_download_says_why_and_a_retry_clears_it(models):
    d, files, _ = models
    real = files["/en.bin"]
    files["/en.bin"] = b"english" * 10
    fetch.fetch_missing(["en.bin"])
    assert "expected" in stt.model_status()["en.bin"]["error"]
    files["/en.bin"] = real
    assert fetch.fetch_missing(["en.bin"], wait=True) == ["en.bin"]
    assert stt.model_status()["en.bin"]["error"] is None


def test_the_pid_file_is_gone_once_the_download_ends(models):
    d, _, _ = models
    fetch.fetch_missing()
    assert not (d / ".fetch.pid").exists()
    assert stt.fetching() == ""


def test_the_command_removes_only_with_yes(here, capsys, monkeypatch):
    from dictator_core import cli
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    assert cli.main(["dictator", "models", "remove", "hi.bin"]) == 0
    assert (here / "hi.bin").exists()
    assert cli.main(["dictator", "models", "remove", "hi.bin", "--yes"]) == 0
    assert not (here / "hi.bin").exists()
    assert "freed" in capsys.readouterr().out


def test_ready_with_the_english_model_removed_says_so(here, monkeypatch):
    from dictator_core import dictate
    monkeypatch.setattr(stt, "ALIASES", {"english": "en.bin"})
    stt.remove("en.bin")
    dictate.publish("ready")
    st = core.read_status()
    assert st["state"] == "error"
    assert st["error"] == "The English model was removed. Download it in Settings."


def test_the_resident_server_is_released_only_if_it_is_ours(monkeypatch):
    import subprocess as sp
    killed = []
    monkeypatch.setattr(stt.os, "kill", lambda pid, sig: killed.append(pid))
    (core.STATE_DIR / "stt.pid").write_text("4242")
    monkeypatch.setattr(stt.subprocess, "run", lambda *a, **k: sp.CompletedProcess(
        a, 0, stdout="/x/whisper-server -m m.bin --port 7001\n"))
    assert stt.release_server() is True and killed == [4242]
    assert not (core.STATE_DIR / "stt.pid").exists()
    # a pid that now belongs to some other program is left alone
    (core.STATE_DIR / "stt.pid").write_text("4243")
    monkeypatch.setattr(stt.subprocess, "run", lambda *a, **k: sp.CompletedProcess(
        a, 0, stdout="/Applications/Safari.app/Contents/MacOS/Safari\n"))
    assert stt.release_server() is False and killed == [4242]
