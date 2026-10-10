"""The Scratchpad's notes: one Markdown file each, under STATE_DIR/notes."""
import json
import os
import time

import pytest

from dictator_core import core, notes


def test_a_note_is_a_markdown_file_named_by_when_it_was_made():
    nid = notes.new_id(time.mktime((2026, 10, 9, 14, 23, 1, 0, 0, -1)))
    assert nid == "20261009-142301"
    r = notes.save(nid, "# Groceries\nmilk\n")
    assert (core.STATE_DIR / "notes" / f"{nid}.md").read_text() == "# Groceries\nmilk\n"
    assert r["title"] == "Groceries" and r["words"] == 3


def test_ids_made_in_the_same_second_do_not_collide():
    t = time.time()
    a = notes.new_id(t)
    notes.save(a, "one")
    b = notes.new_id(t)
    assert b == a + "-2"
    notes.save(b, "two")
    assert notes.new_id(t) == a + "-3"


def test_newest_first_and_the_title_is_the_first_line_with_words():
    notes.save("20261001-090000", "\n\n  first thing\nmore")
    notes.save("20261002-090000", "second")
    old = time.time() - 3600
    os.utime(core.STATE_DIR / "notes" / "20261002-090000.md", (old, old))
    rows = notes.all_notes()
    assert [r["id"] for r in rows] == ["20261001-090000", "20261002-090000"]
    assert rows[0]["title"] == "first thing"


def test_saving_nothing_deletes_it():
    notes.save("20261001-090000", "words")
    assert notes.save("20261001-090000", "   \n") is None
    assert notes.all_notes() == []


def test_delete_and_find():
    notes.save("20261001-090000", "Call the dentist on Monday")
    notes.save("20261001-090001", "Monday standup notes")
    assert [r["id"] for r in notes.find("monday dentist")] == ["20261001-090000"]
    assert len(notes.find("MONDAY")) == 2
    assert notes.delete("20261001-090000") is True
    assert notes.delete("20261001-090000") is False
    assert notes.get("20261001-090000") is None


def test_an_id_cannot_reach_outside_the_folder():
    for bad in ("../../etc/passwd", "x", "20261001-090000/../../a", ""):
        with pytest.raises(ValueError):
            notes.save(bad, "nope")
    assert not (core.STATE_DIR / "notes").exists()


def test_other_files_in_the_folder_are_not_notes():
    d = core.STATE_DIR / "notes"
    d.mkdir()
    (d / "README.md").write_text("not a note")
    (d / "20261001-090000.md.tmp").write_text("half written")
    assert notes.all_notes() == []


def _cli():
    # The CLI body lives in dictator_core.cli now; bin/dictator is just a launcher.
    import importlib
    return importlib.import_module("dictator_core.cli")


def test_cli_round_trip_as_the_app_uses_it(monkeypatch, capsys):
    import io, sys
    cli = _cli()
    assert cli.main(["dictator", "notes", "new", "--json"]) == 0
    nid = json.loads(capsys.readouterr().out)["id"]
    monkeypatch.setattr(sys, "stdin", io.StringIO("Ideas\nship the pill"))
    assert cli.main(["dictator", "notes", "save", nid, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "Ideas"
    assert cli.main(["dictator", "notes", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)["notes"]
    assert [r["id"] for r in rows] == [nid] and rows[0]["text"] == "Ideas\nship the pill"
    assert cli.main(["dictator", "notes", "find", "pill", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["notes"]) == 1
    assert cli.main(["dictator", "notes", "delete", nid, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["deleted"] is True
    assert cli.main(["dictator", "notes", "show", "../x"]) == 2


def test_cli_meeting_status_for_the_pill_and_the_app(capsys):
    assert _cli().main(["dictator", "meeting", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "recording": False, "id": "", "title": "", "elapsed": 0.0}
