"""Keep the test suite out of the user's real data.

Running the tests used to write into ~/.dictator: dictation tests call the
history recorder, so the suite filled the user's own utterance history with
"deploy the thing" and the vocabulary would have started learning from it.
State that a test creates has to live somewhere a test can throw away.
"""
import pytest


@pytest.fixture(autouse=True)
def _own_state_dir(tmp_path, monkeypatch):
    from dictator import core
    monkeypatch.setattr(core, "STATE_DIR", tmp_path)
    monkeypatch.setattr(core, "LOG_FILE", tmp_path / "log")
    monkeypatch.setattr(core, "HUD_FILE", tmp_path / "hud.json")
    monkeypatch.setattr(core, "ERRORS_FILE", tmp_path / "errors.jsonl")
    for mod, attr, value in (
            ("history", "DB", tmp_path / "history.db"),
            ("learn", "PENDING", tmp_path / "pending-words.json"),
            ("vocab", "STORE", tmp_path / "vocab.json"),
            # Or the suite fills the user's benchmark corpus with one-byte
            # files that look like recordings and are not. Third time this
            # exact shape has bitten: a module constant computed from
            # STATE_DIR at import, so redirecting STATE_DIR alone misses it.
            ("api", "CORPUS", tmp_path / "corpus"),
            # Fourth time this exact shape has bitten, and the first three are
            # named in the comment above. `truth` computes both of these from
            # STATE_DIR at import, so redirecting STATE_DIR alone left its
            # tests writing fake recordings into the user's real benchmark
            # corpus and real transcripts beside them. 41 of them, before
            # anyone noticed.
            ("truth", "CORPUS", tmp_path / "corpus"),
            ("truth", "REFS", tmp_path / "references"),
            # Harmless on its own, but it is the same shape and the test that
            # looks for this shape should find nothing.
            ("stt", "_MIC_LOCK", tmp_path / "mic.lock"),
            # Written, not read: a test that touches signing would make a real
            # keychain, and one that changes the delivery method would change
            # the user's own setting.
            ("signing", "KEYCHAIN", tmp_path / "signing.keychain-db"),
            ("signing", "PASSFILE", tmp_path / "signing.pass"),
            ("paste", "HOW_FILE", tmp_path / "delivery"),
            ("orbnative", "PID", tmp_path / "orb.pid"),
            ("api", "CAPTURE_FLAG", tmp_path / "capturing"),
            ("api", "FORMAT_FILE", tmp_path / "format.json"),
            ("snippets", "STORE", tmp_path / "snippets.json"),
            ("profiles", "FILE", tmp_path / "app-format.json"),
            # Same shape again. The app bundle writes what it can see of its
            # own Accessibility trust here, and a test that asserts on the
            # broken state must not be able to tell the real listener it is
            # fine, or overwrite the one file that says it is not.
            ("tcc", "WAITING_FILE", tmp_path / "permission.json"),
            # Not under ~/.dictator, and the same problem. A test that reached
            # always.on() or always.off() would unload the user's real login
            # item and stop their dictation; a test that reached build_app()
            # rebuilt the real ~/Applications/Dictator.app and wrote a pytest
            # temporary directory into it as the log path, which has happened.
            ("always", "PLIST", tmp_path / "com.dictator.dictate.plist"),
            # The same shape again, and the most expensive one to get wrong: a
            # meeting directory holds other people's voices, and `forget`
            # overwrites files before it unlinks them, so a test pointed at the
            # real directory would not merely pollute it.
            ("meeting", "MEETINGS", tmp_path / "meetings"),
            ("meeting", "CURRENT", tmp_path / "meetings" / "current"),
            # And the bundle, which is one test away from being the same
            # problem one directory over. Anything that reaches `build_app`
            # would run swiftc, write into ~/Applications and codesign it, and
            # anything reaching `check` or `start` would launch the real
            # recorder through LaunchServices and raise a permission dialog in
            # the middle of a test run. Redirected rather than trusted not to
            # be called, for the same reason always.PLIST is.
            ("meeting", "APP", tmp_path / "app" / "Dictator Meeting.app"),
            ("meeting", "EXE", tmp_path / "app" / "Dictator Meeting.app"
                               / "Contents" / "MacOS" / "DictatorMeeting"),
            ("meeting", "PLIST", tmp_path / "app" / "Dictator Meeting.app"
                                 / "Contents" / "Info.plist"),
    ):
        try:
            m = __import__(f"dictator.{mod}", fromlist=[mod])
            if hasattr(m, attr):
                monkeypatch.setattr(m, attr, value)
        except Exception:
            pass
    # shared() caches a Vocab that has already read the real file.
    try:
        from dictator import vocab
        monkeypatch.setattr(vocab, "_shared", None)
    except Exception:
        pass
    # Same shape, same reason: snippets.shared() holds a store loaded from the
    # real path, so without this a test would expand a phrase out of the
    # user's own file and, worse, write its own back into it.
    try:
        from dictator import snippets
        monkeypatch.setattr(snippets, "_shared", None)
    except Exception:
        pass
    yield
