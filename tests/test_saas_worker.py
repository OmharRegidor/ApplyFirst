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


def test_second_poll_fans_out_tailors_and_sends(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw()])
    sent = []

    def sender(cfg, refresh, *, to, subject, text, html):
        sent.append((refresh, to, subject))
        return "msg1"

    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=sender, polite=False)   # baseline
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=sender, polite=False)
    assert r.sent == 1
    assert sent[0][0] == "rt" and sent[0][1] == "u@x.com"   # decrypted token, user's inbox
    assert _statuses(conn) == ["sent"]
    conn.close()


def test_user_without_gmail_is_skipped_no_cap_spent(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key, gmail=False)
    src = FakeSource([_raw()])
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=lambda *a, **k: "m", polite=False)
    assert r.skipped == 1 and r.sent == 0
    assert conn.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0] == 0  # no tailoring spent
    conn.close()


def test_daily_cap_caps_extra_alerts(saas_cfg, master_key):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw("1"), _raw("2")])   # two jobs in the page
    sender = lambda *a, **k: "m"  # noqa: E731
    worker.run_once(conn, src, cfg, master_key, engine_factory=_engine_factory,
                    sender=sender, polite=False)   # baseline (both stored)
    r = worker.run_once(conn, src, cfg, master_key, engine_factory=_engine_factory,
                        sender=sender, polite=False)
    assert r.sent == 1 and r.capped == 1
    assert _statuses(conn) == ["capped", "sent"]
    conn.close()


def test_invalid_grant_disconnects_user_and_fails_alert(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    src = FakeSource([_raw()])
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline

    def revoked(cfg, refresh, **k):
        raise gmail_send.GmailAuthError("revoked")

    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=revoked, polite=False)
    assert r.failed == 1
    assert db.gmail_connected(conn, u.id) is False   # credential cleared → stop retrying
    assert _statuses(conn) == ["failed"]
    conn.close()


def test_transient_send_error_leaves_alert_pending_for_retry(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw()])
    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline

    def flaky(cfg, refresh, **k):
        raise gmail_send.GmailSendError("temporary glitch")

    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=flaky, polite=False)
    assert r.sent == 0
    assert _statuses(conn) == ["pending"]   # not terminally failed on first transient error
    assert conn.execute("SELECT attempts FROM user_job_alerts").fetchone()[0] == 1
    conn.close()


def test_fail_after_max_attempts_terminal(saas_cfg, master_key):
    """A persistently-transient send fails terminally after _MAX_ATTEMPTS — and the
    cached package means no extra daily-cap is spent on the retries."""
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    src = FakeSource([_raw()])

    def always_flaky(cfg, refresh, **k):
        raise gmail_send.GmailSendError("temporary glitch")

    worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m", polite=False)   # baseline
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


def test_cache_shared_across_identical_profiles(saas_cfg, master_key):
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
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=counting_factory,
                        sender=sender, polite=False)
    assert r.sent == 2
    assert calls["n"] == 1   # second user hit the (job_id, profile_hash) cache
    conn.close()
