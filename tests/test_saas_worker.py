"""M3 — the worker cycle: baseline, fan-out, tailor (cache), send; cap; auth-revoke."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from applyfirst.models import JobDetail, RawJob
from applyfirst.saas import db, gmail_send, worker
from applyfirst.tailor import TailoringEngine


def _raw(ext="1", title="VA needed"):
    return RawJob(source="onlinejobs.ph", external_id=ext, url=f"http://oj/job-{ext}",
                  title=title, employment_type="Full time", salary_text=None,
                  posted_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
                  preview="p", matched_keyword=None)


class FakeSource:
    name = "onlinejobs.ph"

    def __init__(self, jobs):
        self._jobs = jobs

    def search_latest(self, keyword):
        return list(self._jobs)

    def fetch_detail(self, job):
        return JobDetail(raw=job, description="We need a VA. TO APPLY: say why.", skills=[])


def _engine_factory():
    return TailoringEngine(provider=None)   # rules fallback — deterministic, no key


def _seed(conn, master_key, *, sub="g", email="u@x.com", gmail=True, activated=True,
          keyword="virtual assistant"):
    u = db.upsert_user_by_google(conn, google_sub=sub, email=email, display_name="U")
    db.upsert_profile(conn, u.id, full_name="Omhar", job_type="VA",
                      standard_subject="VA - Omhar", standard_message="Hi, I am Omhar.")
    if activated:
        db.set_activated(conn, u.id)
    if gmail:
        db.store_gmail_credential(conn, u.id, refresh_token="rt", master_key=master_key)
    db.add_keyword(conn, u.id, keyword)
    return u


def _statuses(conn):
    return sorted(r["status"] for r in conn.execute("SELECT status FROM user_job_alerts"))


class _Board(FakeSource):
    """A job board whose page for each term is whatever ``pages`` holds when it is searched."""

    def __init__(self, pages: dict[str, list[str]]):
        self.pages = pages

    def search_latest(self, keyword):
        return [_raw(ext) for ext in self.pages.get(keyword, [])]


def _poll(conn, cfg, master_key, src, sent):
    def sender(cfg_, refresh, *, to, subject, text, html):
        sent.append(to)
        return "m"

    return worker.run_once(conn, src, cfg, master_key, engine_factory=_engine_factory,
                           sender=sender, polite=False)


def _alerted(conn, user):
    """The onlinejobs ids this user has an alert for, sorted."""
    return sorted(r[0] for r in conn.execute(
        "SELECT j.onlinejobs_id FROM user_job_alerts a JOIN jobs j ON j.id = a.job_id "
        "WHERE a.user_id=?", (user.id,)))


def _new_job_later(src, clock, ext="2"):
    """A post nobody has seen goes up on top of the page, a tick after the baseline."""
    src._jobs.insert(0, _raw(ext))
    clock.tick()


def test_first_poll_baselines_no_alerts_no_send(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    sent = []
    r = worker.run_once(conn, FakeSource([_raw()]), saas_cfg, master_key,
                        engine_factory=_engine_factory,
                        sender=lambda *a, **k: sent.append(1) or "m", polite=False)
    assert r.jobs_seen == 1 and r.alerts_created == 0 and r.sent == 0
    assert sent == []
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1  # job stored
    conn.close()


# --- Only jobs that appear after a user starts are theirs (the 2026-09-26 flood) -------------

def test_jobs_the_first_poll_stored_are_never_sent_on_a_later_poll(saas_cfg, master_key, clock):
    """The owner's own run: activated at 23:41:04, the first cycle stored 59 jobs and sent
    nothing, then the next cycle found the same 59 and queued every one of them."""
    clock.now = "2026-09-26T23:41:04Z"
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    src, sent = FakeSource([_raw(str(n)) for n in range(1, 6)]), []
    clock.now = "2026-09-26T23:45:46Z"
    first = _poll(conn, saas_cfg, master_key, src, sent)           # baseline: stores all five
    clock.now = "2026-09-26T23:52:56Z"
    second = _poll(conn, saas_cfg, master_key, src, sent)          # the same five again
    assert first.jobs_seen == second.jobs_seen == 5
    assert (second.alerts_created, second.sent, second.capped) == (0, 0, 0)
    assert sent == [] and _alerted(conn, u) == []
    conn.close()


def test_a_job_that_first_appears_on_a_later_poll_is_sent(saas_cfg, master_key, clock):
    clock.now = "2026-09-27T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    src, sent = FakeSource([_raw("1")]), []
    clock.now = "2026-09-27T01:01:00Z"
    _poll(conn, saas_cfg, master_key, src, sent)                   # baseline
    src._jobs = [_raw("2"), _raw("1")]                             # a new post on top
    clock.now = "2026-09-27T01:06:00Z"
    r = _poll(conn, saas_cfg, master_key, src, sent)
    assert (r.alerts_created, r.sent) == (1, 1)
    assert _alerted(conn, u) == ["2"] and sent == ["u@x.com"]
    conn.close()


def test_a_newcomer_to_a_watched_term_gets_only_jobs_found_after_they_start(
        saas_cfg, master_key, clock):
    """B picks "va" during sign-up, but only starts when B activates. Jobs stored before that,
    by A's polls, are not B's, and B's first real job is the next new one."""
    clock.now = "2026-09-27T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    a = _seed(conn, master_key, sub="a", email="a@x.com", keyword="va")
    board, sent = _Board({"va": ["1"]}), []
    clock.now = "2026-09-27T01:01:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # baseline for "va"
    clock.now = "2026-09-27T01:02:00Z"
    b = _seed(conn, master_key, sub="b", email="b@x.com", keyword="va", activated=False)
    board.pages["va"] = ["2", "1"]
    clock.now = "2026-09-27T01:03:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # job 2 is A's alone
    clock.now = "2026-09-27T01:04:00Z"
    db.set_activated(conn, b.id)                                   # B starts now
    clock.now = "2026-09-27T01:05:00Z"
    r = _poll(conn, saas_cfg, master_key, board, sent)             # nothing new has appeared
    assert r.alerts_created == 0 and _alerted(conn, b) == []
    board.pages["va"] = ["3", "2", "1"]
    clock.now = "2026-09-27T01:06:00Z"
    r = _poll(conn, saas_cfg, master_key, board, sent)
    assert r.alerts_created == 2
    assert _alerted(conn, a) == ["2", "3"] and _alerted(conn, b) == ["3"]
    assert sorted(sent) == ["a@x.com", "a@x.com", "b@x.com"]
    conn.close()


def test_removing_and_adding_a_term_again_restarts_the_clock(saas_cfg, master_key, clock):
    """B keeps "va" searched while A has it removed. Whatever was stored before A adds it back
    is not A's, even though A was activated long before."""
    clock.now = "2026-09-27T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    a = _seed(conn, master_key, sub="a", email="a@x.com", keyword="va")
    b = _seed(conn, master_key, sub="b", email="b@x.com", keyword="va")
    board, sent = _Board({"va": ["1"]}), []
    clock.now = "2026-09-27T01:01:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # baseline
    clock.now = "2026-09-27T01:02:00Z"
    db.delete_keyword(conn, a.id, db.list_keywords(conn, a.id)[0].id)
    board.pages["va"] = ["2", "1"]
    clock.now = "2026-09-27T01:03:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # job 2 is B's alone
    clock.now = "2026-09-27T01:04:00Z"
    db.add_keyword(conn, a.id, "va")                               # A's clock starts again
    clock.now = "2026-09-27T01:05:00Z"
    r = _poll(conn, saas_cfg, master_key, board, sent)
    assert r.alerts_created == 0 and _alerted(conn, a) == []
    board.pages["va"] = ["3", "2", "1"]
    clock.now = "2026-09-27T01:06:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)
    assert _alerted(conn, a) == ["3"] and _alerted(conn, b) == ["2", "3"]
    conn.close()


def test_the_only_watcher_adding_a_term_back_gets_nothing_posted_while_it_was_gone(
        saas_cfg, master_key, clock):
    """Nobody searches a term nobody watches. Every post that went up while "va" was gone is
    stored by the first search after A adds it back, so after A's new start. That search must
    record them silently, like a first search, or they are all queued at once (the flood)."""
    clock.now = "2026-09-20T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    a = _seed(conn, master_key, sub="a", email="a@x.com", keyword="va")
    board, sent = _Board({"va": ["1"]}), []
    clock.now = "2026-09-20T01:01:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # baseline
    clock.now = "2026-09-20T01:02:00Z"
    db.delete_keyword(conn, a.id, db.list_keywords(conn, a.id)[0].id)
    board.pages["va"] = [f"gap{n}" for n in range(20)] + ["1"]     # posted while it was gone
    clock.now = "2026-09-23T01:00:00Z"
    assert _poll(conn, saas_cfg, master_key, board, sent).keywords == 0   # nobody searches it
    clock.now = "2026-09-26T09:00:00Z"
    db.add_keyword(conn, a.id, "va")
    clock.now = "2026-09-26T09:05:00Z"
    r = _poll(conn, saas_cfg, master_key, board, sent)
    assert (r.alerts_created, r.sent, r.capped) == (0, 0, 0)
    clock.now = "2026-09-26T09:10:00Z"
    r = _poll(conn, saas_cfg, master_key, board, sent)             # the same page again
    assert (r.alerts_created, r.sent, r.capped) == (0, 0, 0)
    board.pages["va"].insert(0, "new1")
    clock.now = "2026-09-26T09:15:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)
    assert _alerted(conn, a) == ["new1"] and sent == ["a@x.com"]
    conn.close()


def test_a_newcomer_to_a_term_its_last_watcher_left_gets_no_backlog(saas_cfg, master_key,
                                                                    clock):
    """X watched "shopify" and let it go, however the row went. A month of posts later Y picks
    it. Y started after every one of them went up, so Y's first search only records them."""
    clock.now = "2026-08-27T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    x = _seed(conn, master_key, sub="x", email="x@x.com", keyword="shopify")
    board, sent = _Board({"shopify": ["1"]}), []
    clock.now = "2026-08-27T01:01:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # baseline
    clock.now = "2026-08-27T01:02:00Z"
    conn.execute("DELETE FROM user_keywords WHERE user_id=?", (x.id,))
    conn.commit()
    board.pages["shopify"] = [f"old{n}" for n in range(30)] + ["1"]
    clock.now = "2026-09-27T01:00:00Z"
    y = _seed(conn, master_key, sub="y", email="y@x.com", keyword="shopify")
    clock.now = "2026-09-27T01:05:00Z"
    r = _poll(conn, saas_cfg, master_key, board, sent)
    assert (r.alerts_created, r.sent, r.capped) == (0, 0, 0)
    board.pages["shopify"].insert(0, "new1")
    clock.now = "2026-09-27T01:10:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)
    assert _alerted(conn, y) == ["new1"] and _alerted(conn, x) == [] and sent == ["y@x.com"]
    conn.close()


def test_a_quiet_poll_writes_nothing_for_jobs_users_already_have(saas_cfg, master_key, clock):
    """Once the whole page is jobs every watcher already has, a poll with nothing new must not
    try to queue them again. Each try is a write and a commit per watcher per job, every cycle."""
    conn = db.init_db(saas_cfg.db_path)
    for n in range(3):
        _seed(conn, master_key, sub=f"g{n}", email=f"u{n}@x.com")
    src, sent = FakeSource([_raw("1")]), []
    clock.tick()
    _poll(conn, saas_cfg, master_key, src, sent)                   # baseline
    src._jobs = [_raw(str(n)) for n in range(2, 7)]                # the page turns over
    clock.tick()
    assert _poll(conn, saas_cfg, master_key, src, sent).alerts_created == 15
    writes = []
    conn.set_trace_callback(lambda sql: "INTO user_job_alerts" in sql and writes.append(sql))
    clock.tick()
    quiet = _poll(conn, saas_cfg, master_key, src, sent)           # same page, nothing new
    conn.set_trace_callback(None)
    assert quiet.alerts_created == 0 and writes == []
    conn.close()


def test_each_watcher_keeps_their_own_start_when_someone_joins(saas_cfg, master_key, clock):
    """Job 2 is first stored by C's "python" search after A started "va" but before B joined.
    When it shows up under "va" it is A's and not B's, in the same poll as a job for both."""
    clock.now = "2026-09-27T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    a = _seed(conn, master_key, sub="a", email="a@x.com", keyword="va")
    _seed(conn, master_key, sub="c", email="c@x.com", keyword="python")
    board, sent = _Board({"va": ["1"], "python": ["9"]}), []
    clock.now = "2026-09-27T01:01:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # both terms baseline
    board.pages["python"] = ["2", "9"]
    clock.now = "2026-09-27T01:02:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # job 2 stored, C's
    clock.now = "2026-09-27T01:03:00Z"
    b = _seed(conn, master_key, sub="b", email="b@x.com", keyword="va")
    board.pages["va"] = ["3", "2", "1"]
    clock.now = "2026-09-27T01:04:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)
    assert _alerted(conn, a) == ["2", "3"] and _alerted(conn, b) == ["3"]
    kw = conn.execute("SELECT a.keyword FROM user_job_alerts a JOIN jobs j ON j.id = a.job_id "
                      "WHERE a.user_id=? AND j.onlinejobs_id='2'", (a.id,)).fetchone()[0]
    assert kw == "va"
    conn.close()


def test_a_job_stored_in_the_same_second_a_user_starts_is_not_theirs(saas_cfg, master_key,
                                                                     clock):
    """Strictly after: timestamps are to the second, so "the same second" cannot say which
    came first, and the safe answer is to leave the job out."""
    clock.now = "2026-09-27T01:00:00Z"
    conn = db.init_db(saas_cfg.db_path)
    a = _seed(conn, master_key, sub="a", email="a@x.com", keyword="va")
    board, sent = _Board({"va": ["1"]}), []
    clock.now = "2026-09-27T01:01:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)                 # baseline
    clock.now = "2026-09-27T01:05:00Z"
    b = _seed(conn, master_key, sub="b", email="b@x.com", keyword="va")
    board.pages["va"] = ["2", "1"]
    _poll(conn, saas_cfg, master_key, board, sent)                 # job 2 stored this second
    assert _alerted(conn, a) == ["2"] and _alerted(conn, b) == []
    board.pages["va"] = ["3", "2", "1"]
    clock.now = "2026-09-27T01:06:00Z"
    _poll(conn, saas_cfg, master_key, board, sent)
    assert _alerted(conn, b) == ["3"]
    conn.close()


def test_a_new_job_on_a_later_poll_is_tailored_and_sent_to_the_users_inbox(saas_cfg, master_key,
                                                                          clock):
    """The job the baseline stored stays unsent. The one found after it is tailored and sent to
    the user's own inbox with their decrypted token."""
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    src = FakeSource([_raw()])
    sent = []

    def sender(cfg, refresh, *, to, subject, text, html):
        sent.append((refresh, to, subject))
        return "msg1"

    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=sender, polite=False)   # baseline: job 1 was already there
    _new_job_later(src, clock)
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=sender, polite=False)
    assert r.sent == 1
    assert sent[0][0] == "rt" and sent[0][1] == "u@x.com"   # decrypted token, user's inbox
    assert _statuses(conn) == ["sent"]
    assert _alerted(conn, u) == ["2"]                       # never the baselined job 1
    conn.close()


def test_user_without_gmail_is_skipped_no_cap_spent(saas_cfg, master_key, clock):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key, gmail=False)
    src = FakeSource([_raw()])
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline
    _new_job_later(src, clock)
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=lambda *a, **k: "m", polite=False)
    assert r.skipped == 1 and r.sent == 0
    assert conn.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0] == 0  # no tailoring spent
    conn.close()


def test_daily_cap_caps_extra_alerts(saas_cfg, master_key, clock):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw("0")])              # already there at the baseline
    sender = lambda *a, **k: "m"  # noqa: E731
    worker.run_once(conn, src, cfg, master_key, engine_factory=_engine_factory,
                    sender=sender, polite=False)   # baseline
    _new_job_later(src, clock, "1")
    _new_job_later(src, clock, "2")            # two new jobs in the page
    r = worker.run_once(conn, src, cfg, master_key, engine_factory=_engine_factory,
                        sender=sender, polite=False)
    assert r.sent == 1 and r.capped == 1
    assert _statuses(conn) == ["capped", "sent"]
    conn.close()


def test_invalid_grant_disconnects_user_and_fails_alert(saas_cfg, master_key, clock):
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    src = FakeSource([_raw()])
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline
    _new_job_later(src, clock)

    def revoked(cfg, refresh, **k):
        raise gmail_send.GmailAuthError("revoked")

    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=revoked, polite=False)
    assert r.failed == 1
    assert db.gmail_connected(conn, u.id) is False   # credential cleared → stop retrying
    assert _statuses(conn) == ["failed"]
    conn.close()


def test_transient_send_error_leaves_alert_pending_for_retry(saas_cfg, master_key, clock):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw()])
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline
    _new_job_later(src, clock)

    def flaky(cfg, refresh, **k):
        raise gmail_send.GmailSendError("temporary glitch")

    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=flaky, polite=False)
    assert r.sent == 0
    assert _statuses(conn) == ["pending"]   # not terminally failed on first transient error
    assert conn.execute("SELECT attempts FROM user_job_alerts").fetchone()[0] == 1
    conn.close()


def test_fail_after_max_attempts_terminal(saas_cfg, master_key, clock):
    """A persistently-transient send fails terminally after _MAX_ATTEMPTS — and the
    cached package means no extra daily-cap is spent on the retries."""
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw()])

    def always_flaky(cfg, refresh, **k):
        raise gmail_send.GmailSendError("temporary glitch")

    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline
    _new_job_later(src, clock)
    for _ in range(worker._MAX_ATTEMPTS):                       # 3 flaky cycles
        worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=always_flaky, polite=False)
    row = conn.execute("SELECT status, attempts FROM user_job_alerts").fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] == worker._MAX_ATTEMPTS
    # tailored once (cache miss on the first flaky cycle); retries hit the cache.
    assert conn.execute("SELECT tailoring_calls FROM ai_usage").fetchone()[0] == 1
    conn.close()


def test_deadman_switch_trips_after_consecutive_blind_cycles(saas_cfg, caplog):
    import logging
    from applyfirst.saas.worker import CycleResult, _record_heartbeat
    conn = db.init_db(saas_cfg.db_path)
    blind = CycleResult(keywords=1, jobs_seen=0)
    with caplog.at_level(logging.CRITICAL, logger="applyfirst.saas.worker"):
        _record_heartbeat(conn, blind)
        _record_heartbeat(conn, blind)
        assert db.get_worker_meta(conn, "blind_cycles") == "2"
        assert not any(r.getMessage() == "worker_blind" for r in caplog.records)
        _record_heartbeat(conn, blind)        # 3rd consecutive → trips
    assert db.get_worker_meta(conn, "blind_cycles") == "3"
    assert any(r.getMessage() == "worker_blind" and r.levelno == logging.CRITICAL
               for r in caplog.records)
    # a productive cycle resets the counter; the heartbeat is recorded.
    _record_heartbeat(conn, CycleResult(keywords=1, jobs_seen=5))
    assert db.get_worker_meta(conn, "blind_cycles") == "0"
    assert db.get_worker_meta(conn, "last_cycle_at") is not None
    conn.close()


def test_deadman_alerts_owner_once_and_debounces(saas_cfg, monkeypatch):
    """When cfg is supplied, tripping the switch dispatches ONE debounced owner alert."""
    from applyfirst.saas import notify, worker as w
    conn = db.init_db(saas_cfg.db_path)
    calls = []
    monkeypatch.setattr(notify, "send_owner_alert",
                        lambda cfg, subject, body: calls.append(subject) or True)

    blind = w.CycleResult(keywords=1, jobs_seen=0)
    for _ in range(3):
        w._record_heartbeat(conn, blind, saas_cfg)   # 3rd consecutive trips the switch
    assert len(calls) == 1                            # alerted exactly once
    w._record_heartbeat(conn, blind, saas_cfg)        # still blind, but within cooldown
    assert len(calls) == 1                            # debounced — no repeat
    conn.close()


def test_deadman_without_cfg_does_not_alert(saas_cfg, monkeypatch):
    """The cfg=None path (used by older callers/tests) logs but never sends."""
    from applyfirst.saas import notify, worker as w
    conn = db.init_db(saas_cfg.db_path)
    calls = []
    monkeypatch.setattr(notify, "send_owner_alert",
                        lambda *a, **k: calls.append(1) or True)
    blind = w.CycleResult(keywords=1, jobs_seen=0)
    for _ in range(4):
        w._record_heartbeat(conn, blind)              # no cfg → detection/log only
    assert calls == []
    conn.close()


def test_fetch_detail_error_continues_with_preview(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)

    class RaisingDetail(FakeSource):
        def fetch_detail(self, job):
            raise RuntimeError("detail page 500")

    r = worker.run_once(conn, RaisingDetail([_raw()]), saas_cfg, master_key,
                        engine_factory=_engine_factory, sender=lambda *a, **k: "m", polite=False)
    assert r.jobs_seen == 1                                     # cycle did not crash
    job = db.get_job(conn, db.get_job_id(conn, "1"))
    assert job.raw_description == "p"                           # fell back to raw.preview
    conn.close()


def test_search_failure_skips_keyword_not_cycle(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)

    class SearchRaises:
        name = "onlinejobs.ph"

        def search_latest(self, keyword):
            raise RuntimeError("IP blocked")

        def fetch_detail(self, job):
            raise AssertionError("should not be called")

    r = worker.run_once(conn, SearchRaises(), saas_cfg, master_key,
                        engine_factory=_engine_factory, sender=lambda *a, **k: "m", polite=False)
    assert r.keywords == 1 and r.jobs_seen == 0                 # handled, no crash
    conn.close()


def test_oversized_description_is_clamped(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)

    class BigSource(FakeSource):
        def fetch_detail(self, job):
            return JobDetail(raw=job, description="X" * 50_000, skills=[])

    worker.run_once(conn, BigSource([_raw()]), saas_cfg, master_key,
                    engine_factory=_engine_factory, sender=lambda *a, **k: "m", polite=False)
    desc = db.get_job(conn, db.get_job_id(conn, "1")).raw_description
    assert len(desc) <= worker._MAX_DESCRIPTION
    conn.close()


def test_cache_shared_across_identical_profiles(saas_cfg, master_key, clock):
    """Two activated users with IDENTICAL profiles + same job → ONE tailoring call."""
    conn = db.init_db(saas_cfg.db_path)
    for sub, em in [("a", "a@x"), ("b", "b@x")]:
        uu = db.upsert_user_by_google(conn, google_sub=sub, email=em, display_name="U")
        db.upsert_profile(conn, uu.id, full_name="Same", job_type="VA",
                          standard_subject="S", standard_message="M")
        db.set_activated(conn, uu.id)
        db.store_gmail_credential(conn, uu.id, refresh_token="rt", master_key=master_key)
        db.add_keyword(conn, uu.id, "va")

    src = FakeSource([_raw()])
    calls = {"n": 0}

    def counting_factory():
        calls["n"] += 1
        return TailoringEngine(provider=None)

    sender = lambda *a, **k: "m"  # noqa: E731
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=counting_factory,
                    sender=sender, polite=False)   # baseline
    _new_job_later(src, clock)
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=counting_factory,
                        sender=sender, polite=False)
    assert r.sent == 2
    assert calls["n"] == 1   # second user hit the (job_id, profile_hash) cache
    conn.close()
