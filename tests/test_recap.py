"""The recap, and mostly the things it must never do.

A summary of your own day is believed. That is what makes it useful and it is
also what makes it dangerous: an invented name in a paragraph of true ones is
read as a fact about your own work, and nothing in the report tells you which
sentence to doubt. So most of what is tested here is refusal.

Three of them matter more than the rest:

  nothing invented   a summary that says more than was dictated is thrown away
  nothing padded     an empty day says so, and four sentences stay four
                     sentences rather than becoming a report
  nothing sent       there is no call off this machine, at all, ever
"""
import re
import time
from pathlib import Path

import pytest

from dictator import Dictator, history, recap

ROOT = Path(__file__).resolve().parent.parent
DAY = 86400

# Captured before any fixture can replace it, so the one test that exercises
# the real thing gets the real thing.
REAL_START = recap._start


@pytest.fixture(autouse=True)
def _no_model_and_no_network(monkeypatch):
    """No test may reach the network or start a 2.5GB server.

    urlopen is not made to raise, it is made to RECORD: a failure would be
    swallowed by the same try/except that makes this module fail soft, and the
    test would pass while the call had actually gone out."""
    calls = []

    def spy(req, *a, **kw):
        url = req if isinstance(req, str) else getattr(req, "full_url", "")
        calls.append(url)
        raise OSError("no network in tests")

    # `_fetch` rather than `urlopen`, because that is the one choke point every
    # HTTP call in the module goes through, and it is where the redirect
    # refusal lives. Spying one layer down meant a call that stopped using
    # urlopen would stop being seen, which is the opposite of what this is for.
    monkeypatch.setattr(recap, "_fetch", spy)
    monkeypatch.setattr(recap, "server_bin", lambda: "")
    monkeypatch.setattr(recap, "model_path", lambda: Path("/nonexistent.gguf"))
    monkeypatch.setattr(recap, "_start", lambda: pytest.fail(
        "a test tried to start the local model"))
    recap.calls = calls
    yield calls


def _sometime_today() -> float:
    """A moment that is inside today and already past, at any hour.

    Every "today" test measures backwards from now, so a suite run just after
    midnight put its own fixtures into YESTERDAY and failed: `ago=300` at 00:03
    is 23:58 the day before. Anchoring to noon fails the other way, because at
    00:03 noon has not happened yet and a recap ends at now.

    So: shortly after midnight, pulled back to just before now when now is
    itself shortly after midnight."""
    import datetime
    now = time.time()
    start = datetime.datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    return min(start + 600, now - 10)


def _say(text, ago=60.0, app="Terminal", secs=4.0, at=None):
    """A row in the history, at a time of our choosing. Written straight into
    the database because `at` is otherwise always now."""
    when = at if at is not None else time.time() - ago
    con = history._db()
    con.execute("INSERT INTO said (at, heard, shown, kept, app, lang, engine, "
                "secs, conf) VALUES (?,?,?,?,?,?,?,?,?)",
                (when, text, text, "", app, "en", "turbo", secs, 0.9))
    con.commit()
    con.close()


def _work(n=8, ago=3600.0, app="Terminal"):
    for i in range(n):
        _say(f"fix the paste helper case number {i}", ago=ago - i * 30, app=app)


# ---- what must not happen --------------------------------------------------

def test_an_empty_period_is_not_summarised(_no_model_and_no_network):
    """The most basic invention is a report about a day with nothing in it."""
    r = recap.report("today")
    assert not r and r.utterances == 0
    assert "Nothing dictated today" in r.text
    assert "Kept coming up" not in r.text
    assert r.sessions == []
    assert _no_model_and_no_network == []


def test_a_handful_of_utterances_is_not_padded_into_a_report(
        _no_model_and_no_network):
    """Three sentences are three sentences. A heading, a theme and a
    conclusion drawn from them is writing, not reporting."""
    base = _sometime_today()
    _say("check the migration", at=base)
    _say("rerun the suite", at=base + 1)
    _say("push it to the branch", at=base + 2)

    r = recap.report("today")
    assert r.utterances == 3
    assert "not enough to summarise" in r.text
    assert "check the migration" in r.text and "rerun the suite" in r.text
    assert "Kept coming up" not in r.text
    assert _no_model_and_no_network == [], "the model was consulted anyway"


def test_a_summary_that_names_somebody_who_was_never_mentioned_is_dropped():
    """The dangerous failure is not nonsense, it is one invented fact inside a
    paragraph of true ones."""
    source = ("- ran the migration on staging\n"
              "- the empty case returns null instead of a list\n"
              "- push it to the branch not to main\n")
    faithful = ("Ran the migration on staging, found the empty case returning "
                "null instead of a list, and pushed to the branch.")
    invented = ("Ran the migration on staging with Priya and pushed to the "
                "branch.")
    assert recap.grounded(faithful, source)
    assert not recap.grounded(invented, source)
    assert "priya" in recap.unsupported(invented, source)


def test_a_number_nobody_said_is_dropped():
    source = "- we deposited hundred USDC into the vault\n"
    assert recap.grounded("Deposited 100 USDC into the vault.", source)
    why = recap.unsupported("Deposited 4000 USDC into the vault.", source)
    assert "4000" in why


@pytest.mark.parametrize("said, wrote", [
    ("twenty five USDC", "25 USDC"),
    ("two hundred rupees", "200 rupees"),
    ("two hundred and fifty rupees", "250 rupees"),
    ("twenty five thousand rows", "25000 rows"),
    ("one lakh fifty thousand", "150000"),
    ("hundred USDC", "100 USDC"),
    # And the other way round, because the model is free to write it out.
    ("25 USDC", "twenty five USDC"),
    ("1 and 2", "1 and 2"),
])
def test_an_amount_that_takes_two_words_is_still_one_number(said, wrote):
    """A number word used to count as its own value, so "twenty five" was 20
    and 5 and a summary writing 25 was accused of inventing it. The guard then
    threw away a correct summary and told the user the model had made
    something up, which is the worst shape a false alarm can have: it teaches
    them to stop believing the guard that catches the real thing."""
    source = f"- we moved {said} across this morning\n"
    why = recap.unsupported(f"Moved {wrote} across this morning.", source)
    assert "number nobody dictated" not in why, why


@pytest.mark.parametrize("said, wrote", [
    ("twenty five USDC", "4000 USDC"),
    ("two hundred rupees", "900 rupees"),
    ("12 pull requests", "21 pull requests"),
    ("nothing numeric at all", "3 places"),
])
def test_reading_a_number_properly_does_not_stop_it_catching_one(said, wrote):
    """The loosening above must not cost the check its job. An invented figure
    inside an otherwise faithful paragraph barely moves the ratio, which is
    the reason numbers are checked exactly rather than statistically."""
    source = f"- we moved {said} across this morning\n"
    why = recap.unsupported(f"Moved {wrote} across this morning.", source)
    assert "number nobody dictated" in why



def test_a_summary_about_something_else_entirely_is_dropped():
    source = ("- check the index on the staging database\n"
              "- rerun the suite after the migration\n")
    off_topic = ("Interviewed candidates for the backend role and wrote up "
                 "the hiring notes.")
    assert not recap.grounded(off_topic, source)


def test_a_summary_longer_than_what_it_summarised_is_not_a_summary(monkeypatch):
    """Small models pad when there is little to work with, and padding is the
    whole failure this feature exists to avoid."""
    block = "- fix the loop\n- rerun it\n- ship it\n"
    monkeypatch.setattr(recap, "_ask", lambda b, *a, **k: (
        "The person began by carefully considering the loop, and then, having "
        "given it some thought, decided that rerunning it would be sensible, "
        "before finally shipping the change once they were satisfied with the "
        "result of the rerun, which had by then completed successfully."))
    assert recap.prose_for(block) == ""


def test_the_report_never_shows_a_summary_the_guard_rejected(monkeypatch):
    """End to end: an inventing model produces a report with no prose in it at
    all, rather than a report with one wrong paragraph."""
    _work(8, ago=7200)
    monkeypatch.setattr(recap, "available", lambda: True)
    monkeypatch.setattr(recap, "_start", lambda: False)
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_ask", lambda block, *a, **k:
                        "Met Sanjana to agree the pricing for the launch.")

    r = recap.report("7")
    assert "Sanjana" not in r.text and "pricing" not in r.text
    assert r.source == "rejected"
    assert "Nothing was summarised" in " ".join(r.text.split())
    assert all(not s["prose"] for s in r.sessions)


def test_nothing_is_ever_sent_off_this_machine():
    """The product's whole claim. A recap is a convenience, and a convenience
    does not get to break it."""
    src = (ROOT / "dictator" / "recap.py").read_text()
    for url in re.findall(r"https?://[^\"'\s{}]*", src):
        assert recap.local_only(url) or "127.0.0.1" in url, url
    assert "https://" not in src

    assert recap.local_only("http://127.0.0.1:6300")
    assert recap.local_only("http://localhost:1234/v1")
    for elsewhere in ("http://api.openai.com/v1", "https://example.com",
                      "http://192.168.1.4:8080", "http://127.0.0.1.evil.com"):
        assert not recap.local_only(elsewhere), elsewhere


def test_a_remote_endpoint_is_refused_rather_than_used(monkeypatch):
    """Even if somebody points the override at a server on the internet, it is
    refused: failing to summarise is the correct outcome, not summarising
    somewhere else."""
    monkeypatch.setattr(recap, "BASE", "http://api.example.com")
    monkeypatch.setattr(recap, "server_bin", lambda: "/usr/bin/llama-server")
    assert recap.available() is False
    assert recap.up() is False
    assert recap._ask("- anything\n") == ""
    assert recap.calls == [], "a remote endpoint was actually contacted"


def test_asking_for_no_prose_consults_nothing(monkeypatch):
    _work(8, ago=7200)
    monkeypatch.setattr(recap, "available",
                        lambda: pytest.fail("availability was checked anyway"))
    r = recap.report("7", prose=False)
    assert r.utterances == 8
    # Exactly one answer, not whichever of two happened to come out. The old
    # form was `in ("no-model", "too-short")`, and only "no-model" was
    # reachable with this fixture, so it was written exactly wide enough to
    # accept the wrong one.
    assert r.source == "not-asked", r.source
    assert recap.calls == []


def test_it_does_not_claim_there_is_no_model_on_a_machine_that_has_one(
        monkeypatch):
    """"--plain" skips the model. It does not mean the model is absent, and
    telling somebody with 2.5GB of it on disk that there is none is a plain
    untruth in the one line that explains itself."""
    _work(8, ago=7200)
    monkeypatch.setattr(recap, "available", lambda: True)
    r = recap.report("7", prose=False)
    assert r.source == "not-asked"
    flat = " ".join(r.text.split())          # the report is wrapped
    assert "no local model on this machine" not in flat
    assert "you asked for it without the model" in flat


def test_a_model_that_will_not_start_is_not_reported_as_a_dishonest_answer(
        monkeypatch):
    """"rejected" means the model answered and the answer was not supported.
    A server that never came up said the same thing, which blames the guard
    for a failure to launch and sends the reader looking in the wrong place."""
    import contextlib
    _work(8, ago=7200)
    monkeypatch.setattr(recap, "available", lambda: True)

    @contextlib.contextmanager
    def never_starts():
        yield False

    monkeypatch.setattr(recap, "model_up", never_starts)
    r = recap.report("7", prose=True)
    assert r.source == "no-server", r.source
    assert "would not start" in " ".join(r.text.split())


def test_the_recap_only_ever_reads(monkeypatch):
    """It must not record itself, or teach the vocabulary anything. A summary
    that shows up in tomorrow's history is a feature writing its own input."""
    _work(6, ago=7200)
    before = len(history.recent(limit=500))
    monkeypatch.setattr(history, "add",
                        lambda **kw: pytest.fail("the recap wrote to history"))
    recap.report("7", prose=False)
    assert len(history.recent(limit=500)) == before


def test_a_server_this_command_did_not_start_is_never_stopped(monkeypatch):
    """Somebody else's resident model is not ours to kill, and the only safe
    way to know the difference is a handle rather than a process name."""
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_start", REAL_START)
    assert recap._start() is False
    recap._proc = None
    recap._stop()          # must be a no-op, not an exception


def test_the_number_of_model_calls_is_bounded(monkeypatch):
    """A week of heavy dictation cannot turn one command into two minutes of
    waiting, because a recap nobody waits for is a recap nobody runs."""
    for day in range(6):
        for hour in range(4):
            _work(4, ago=day * DAY + hour * 3600 + 120)
    asked = []
    monkeypatch.setattr(recap, "available", lambda: True)
    monkeypatch.setattr(recap, "_start", lambda: False)
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_ask",
                        lambda block, *a, **k: asked.append(block) or "")

    r = recap.report("7")
    assert len(r.sessions) > recap.MAX_CALLS
    assert len(asked) == recap.MAX_CALLS


def test_a_two_line_session_is_quoted_rather_than_summarised(monkeypatch):
    """There is nothing to compress in two lines, and asking a model to
    compress them is how you get a summary that says more than the source."""
    _say("first thing", ago=7200)
    _say("second thing", ago=7100)
    _say("third thing", ago=3000, app="Slack")
    _say("fourth thing", ago=2900, app="Slack")
    _say("fifth thing", ago=1000, app="Code")
    monkeypatch.setattr(recap, "available",
                        lambda: pytest.fail("the model was offered two lines"))
    r = recap.report("7", prose=False)
    assert r.source == "too-short"
    assert "first thing" in r.text and "fifth thing" in r.text


# ---- what it must actually do ---------------------------------------------

def test_a_faithful_summary_survives_the_guards():
    """The guards would be worthless if they rejected everything: this is a
    real summary the local model produced from real dictation."""
    source = ("Google Chrome, 19:26 to 19:43:\n"
              "- Alice had deposited hundred USDC before and signed the "
              "transaction herself\n"
              "- so we verify the signature and derive her public key\n"
              "- then check the mint is USDC and derive the user deposit PDA\n"
              "- and update the delegate amount in the bookkeeping\n")
    prose = ("Verified Alice's signature and derived her public key, checked "
             "the mint was USDC, derived the user deposit PDA and updated the "
             "delegate amount in the bookkeeping.")
    assert recap.unsupported(prose, source) == ""


def test_the_summary_is_shown_with_a_line_that_was_actually_said(monkeypatch):
    """Evidence, not decoration. Every claim in the prose sits above a time, an
    application and one of the person's own sentences."""
    _work(8, ago=7200, app="Code")
    monkeypatch.setattr(recap, "available", lambda: True)
    monkeypatch.setattr(recap, "_start", lambda: False)
    monkeypatch.setattr(recap, "up", lambda timeout=1.0: True)
    monkeypatch.setattr(recap, "_ask",
                        lambda block, *a, **k: "Fixed the paste helper case.")
    r = recap.report("7")
    assert r.source == "model"
    assert "Fixed the paste helper case." in r.text
    assert "Code" in r.text
    assert 'said: "fix the paste helper case number 0"' in r.text


def test_every_line_in_a_grouped_report_was_really_dictated():
    """Nothing in the deterministic path may be prose we wrote on the user's
    behalf: each quoted line is a line out of the history."""
    said = ["look at the paste helper", "it is never called from dictate",
            "write a test that fails without it", "then push the branch",
            "and check the log afterwards", "one more for the count"]
    for i, s in enumerate(said):
        _say(s, ago=7200 - i * 60)
    r = recap.report("7", prose=False)
    quoted = [ln.strip() for ln in r.text.splitlines()
              if re.match(r"^\s+\d\d:\d\d {2}", ln)]
    assert quoted
    for line in quoted:
        body = line.split("  ", 1)[1].strip()
        assert any(body in s for s in said), body


def test_the_period_is_the_calendar_day_not_the_last_24_hours():
    """"Today" has to mean what the calendar says, or the report disagrees
    with the person reading it."""
    since, until, label = recap.window("today")
    assert label == "today"
    assert time.localtime(since).tm_hour == 0
    assert time.localtime(since).tm_min == 0
    assert until - since <= DAY

    since_w, _, label_w = recap.window("week")
    assert "7 days" in label_w
    assert 5.5 * DAY < until - since_w < 7.5 * DAY

    since_3, _, label_3 = recap.window(3)
    assert "3 days" in label_3
    assert 1.5 * DAY < until - since_3 < 3.5 * DAY

    assert recap.window("nonsense")[2] == "today"
    assert recap.window("yesterday")[2] == "yesterday"


def test_a_long_silence_ends_a_session():
    rows = [{"at": 1000.0, "app": "Terminal", "secs": 3.0, "text": "one"},
            {"at": 1100.0, "app": "Terminal", "secs": 3.0, "text": "two"},
            {"at": 1100.0 + recap.SESSION_GAP + 1, "app": "Terminal",
             "secs": 3.0, "text": "three"}]
    out = recap.sessions(rows)
    assert [len(s["lines"]) for s in out] == [2, 1]


def test_moving_to_another_application_starts_a_new_session():
    """Terminal to Slack in the same minute is a change of task, and merging
    them would put two unrelated pieces of work under one summary."""
    rows = [{"at": 1000.0, "app": "Terminal", "secs": 3.0, "text": "one"},
            {"at": 1030.0, "app": "Slack", "secs": 3.0, "text": "two"},
            {"at": 1060.0, "app": "Terminal", "secs": 3.0, "text": "three"}]
    out = recap.sessions(rows)
    assert [s["app"] for s in out] == ["Terminal", "Slack", "Terminal"]


def test_a_word_said_once_is_not_a_theme():
    """Promoting a single long word to a theme invents a pattern that was not
    there, which is the deterministic version of making something up."""
    rows = [{"at": float(i), "app": "Terminal", "secs": 1.0, "text": t}
            for i, t in enumerate([
                "the migration is slow", "the migration needs an index",
                "check the migration again", "quicksort", "okay please just"])]
    found = dict(recap.terms(rows))
    assert "migration" in found
    assert "quicksort" not in found
    for filler in ("okay", "please", "just", "the"):
        assert filler not in found


def test_what_you_kept_beats_what_we_showed_you():
    """`kept` is what the sentence had become once the user was done with it,
    which is closer to what they meant than what the recogniser produced."""
    con = history._db()
    con.execute("INSERT INTO said (at, heard, shown, kept, app) "
                "VALUES (?,?,?,?,?)",
                (time.time() - 300, "whisper floor", "whisper floor",
                 "Whisper Flow", "Terminal"))
    con.commit()
    con.close()
    rows = recap.utterances(time.time() - 3600)
    assert rows[0]["text"] == "Whisper Flow"


def test_a_period_with_no_local_model_says_so_plainly(monkeypatch):
    """Degrading is fine. Degrading quietly is not: a grouped report that
    looks like a summary is worse than one that says what it is."""
    _work(8, ago=7200)
    r = recap.report("7")
    assert r.source == "no-model"
    flat = " ".join(r.text.split())
    assert "no local model on this machine" in flat
    assert "Grouping only" in flat


# ---- the library surface ---------------------------------------------------

def test_the_library_exposes_it(monkeypatch):
    """voicebridge and Friday read this, and they hold a Dictator rather than
    running a command."""
    _work(8, ago=7200)
    r = Dictator().recap("7", prose=False)
    assert isinstance(r, recap.Recap)
    assert r.utterances == 8
    assert str(r) == r.text and bool(r) is True
    assert r.sessions and r.terms is not None
    assert recap.calls == []


def test_the_public_surface_did_not_grow():
    """Recap is reached through the method that returns it. The four names in
    __all__ are the promise and a fifth is a new thing to keep working."""
    import dictator
    assert dictator.__all__ == ["Dictator", "Transcript", "transcribe", "VERSION"]
    assert hasattr(Dictator, "recap")


def test_a_redirect_is_refused_rather_than_followed(monkeypatch):
    """Checking the URL before the call is not enough. `urlopen` follows
    redirects by default and a 307 re-issues the POST WITH THE BODY, so a
    process on the loopback port could have the whole transcript forwarded
    anywhere it liked. The promise this feature makes is absolute, so it
    cannot rest on the local server being well behaved."""
    import http.server
    import threading
    import urllib.error
    import urllib.request

    seen = []

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(self.path)
            self.send_response(307)
            self.send_header("Location", "http://example.com/steal")
            self.end_headers()

        def do_GET(self):
            self.do_POST()

        def log_message(self, *a):
            pass

    # The real one: the fixture replaces `_fetch` with a spy for every other
    # test, and the whole point here is the behaviour of the thing itself.
    monkeypatch.setattr(recap, "_fetch",
                        lambda req, timeout: recap._opener.open(req,
                                                                timeout=timeout))
    srv = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
        req = urllib.request.Request(url, data=b"{}",
                                     headers={"Content-Type": "application/json"})
        try:
            recap._fetch(req, 5).read()
        except urllib.error.HTTPError as e:
            assert "refusing a redirect" in str(e), e
        else:
            raise AssertionError("the redirect was followed")
        assert seen, "the local server was never reached at all"
    finally:
        srv.shutdown()
