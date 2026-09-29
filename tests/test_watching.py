"""Whether it can tell that its own learning loop is working.

An empty `kept` used to mean two opposite things: you changed nothing, and we
never managed to look. The loop could therefore be dead for weeks without any
command saying so, which is what these tests are here to stop.
"""
import pytest

from dictator import api, history


def _row(**kw):
    return history.add(heard=kw.get("heard", "deploy the thing"),
                       shown=kw.get("shown", "deploy the thing"),
                       app=kw.get("app", "Terminal"))


def _sdk(monkeypatch, field_result):
    from dictator import readback
    monkeypatch.setattr(readback, "field", lambda: field_result)
    d = api.Dictator()
    d.learning = True
    return d


def test_untouched_text_is_recorded_as_seen_not_as_unknown():
    """The case that made the loop unmeasurable: nothing to learn is still an
    observation, and has to be distinguishable from a failure to observe."""
    rid = _row()
    history.saw(rid, "same")
    assert history.recent(1)[0]["saw"] == "same"
    assert history.watching()["same"] == 1


def test_a_failed_read_is_not_counted_as_the_user_agreeing():
    rid = _row()
    history.saw(rid, "unreadable")
    assert history.watching()["unreadable"] == 1
    assert "same" not in history.watching()


def test_rows_from_before_this_existed_are_not_counted_either_way():
    _row()
    assert history.watching()["unrecorded"] == 1


def test_an_old_database_without_the_column_is_migrated_not_crashed(tmp_path,
                                                                    monkeypatch):
    """The column arrived after real users had a database. Adding it must not
    take their history with it."""
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        "CREATE TABLE said (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, "
        "heard TEXT, shown TEXT, kept TEXT, app TEXT, lang TEXT, "
        "engine TEXT, secs REAL, conf REAL);"
        "INSERT INTO said (at, heard, shown, kept, app, lang, engine, secs, "
        "conf) VALUES (1.0, 'older than the column', '', '', '', '', '', 0, 0);")
    con.commit()
    con.close()
    monkeypatch.setattr(history, "DB", db)
    rows = history.recent(10)
    assert [r["heard"] for r in rows] == ["older than the column"]
    assert rows[0]["saw"] == ""


@pytest.mark.parametrize("field, expected", [
    ("deploy the thing", "same"),
    ("something else entirely, nothing like it", "gone"),
])
def test_the_outcome_is_recorded_when_nothing_was_learned(monkeypatch, field,
                                                          expected):
    rid = _row()
    d = _sdk(monkeypatch, {"ok": True, "value": field})
    d._last = (rid, "deploy the thing", "Terminal")
    assert d.check_corrections("Terminal") == []
    assert history.recent(1)[0]["saw"] == expected


def test_a_real_correction_records_both_the_outcome_and_the_text(monkeypatch):
    rid = _row(shown="whisper floor is good")
    d = _sdk(monkeypatch, {"ok": True, "value": "whisper flow is good"})
    d._last = (rid, "whisper floor is good", "Terminal")
    d.check_corrections("Terminal")
    row = history.recent(1)[0]
    assert row["saw"] == "edited"
    assert row["kept"] == "whisper flow is good"


def test_moving_to_another_application_is_recorded_as_not_having_looked(
        monkeypatch):
    rid = _row()
    d = _sdk(monkeypatch, {"ok": True, "value": "deploy the thing"})
    d._last = (rid, "deploy the thing", "Terminal")
    assert d.check_corrections("Slack") == []
    assert history.recent(1)[0]["saw"] == "moved"


def test_an_unreadable_field_is_recorded_rather_than_swallowed(monkeypatch):
    rid = _row()
    d = _sdk(monkeypatch, {"ok": False, "why": "reader not built"})
    d._last = (rid, "deploy the thing", "Terminal")
    assert d.check_corrections("Terminal") == []
    assert history.recent(1)[0]["saw"] == "unreadable"


def _cli():
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("dcli", "bin/dictator")
    spec = importlib.util.spec_from_loader("dcli", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def test_a_loop_that_has_caught_nothing_says_so(monkeypatch, capsys):
    """Silence here reads as "working". The point of the line is that a
    vocabulary which never grows has a visible reason."""
    monkeypatch.setattr(history, "watching",
                        lambda limit=200: {"same": 60, "unreadable": 2})
    _cli()._watching()
    out = capsys.readouterr().out
    assert "learned nothing from your edits" in out
    assert "60 of your last 62" in out


def test_rows_from_before_it_was_measured_are_left_out_of_the_total(
        monkeypatch, capsys):
    monkeypatch.setattr(history, "watching",
                        lambda limit=200: {"same": 2, "unrecorded": 900})
    _cli()._watching()
    assert "of your last 2 " in capsys.readouterr().out
