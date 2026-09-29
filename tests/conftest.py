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
            ("api", "CAPTURE_FLAG", tmp_path / "capturing"),
            ("api", "FORMAT_FILE", tmp_path / "format.json"),
            ("snippets", "STORE", tmp_path / "snippets.json"),
            ("profiles", "FILE", tmp_path / "app-format.json"),
            # Same shape again. The app bundle writes what it can see of its
            # own Accessibility trust here, and a test that asserts on the
            # broken state must not be able to tell the real listener it is
            # fine, or overwrite the one file that says it is not.
            ("tcc", "WAITING_FILE", tmp_path / "permission.json"),
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
