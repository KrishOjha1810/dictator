"""The app downloads its own models, and never keeps one it cannot verify.

Served from a local HTTP server, so nothing here touches the network or the
real model directory."""
import fcntl
import hashlib
import http.server
import threading

import pytest

from dictator import core, fetch, stt


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
