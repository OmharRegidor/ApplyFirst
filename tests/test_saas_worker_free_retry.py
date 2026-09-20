"""Owner call (2026-09-19) "Retries are free": one job costs one daily-cap slot. A retried alert
(attempts > 0) is never charged again, even when its cached letter is gone (the prompt-change
wipe, or an edited profile), so a user already at the cap still gets it. A first attempt still
charges and still caps."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from applyfirst.models import JobDetail, RawJob
from applyfirst.saas import db, gmail_send, worker
from applyfirst.tailor import TailoringEngine
from applyfirst.tailor.prompt import PROMPT_FINGERPRINT
from _saas_client import RecordingProvider

REPLY = ('{"digest":"d","application_subject":"VA – Maria Santos",'
         '"cover_letter":"Hi! I am Maria.","screening_questions":[]}')


class _Source:
    """A job board whose page is whatever ``ids`` holds when it is searched."""

    name = "onlinejobs.ph"

    def __init__(self, *ids: str) -> None:
        self.ids = list(ids)

    def search_latest(self, keyword):
        return [RawJob(source="onlinejobs.ph", external_id=i, url=f"http://oj/job-{i}",
                       title="VA needed", employment_type="Full time", salary_text=None,
                       posted_at=datetime(2026, 9, 1, tzinfo=timezone.utc), preview="p",
                       matched_keyword=None) for i in self.ids]

    def fetch_detail(self, job):
        return JobDetail(raw=job, description="VA needed. TO APPLY: say why.", skills=[])


def _seed(conn, master_key) -> db.User:
    u = db.upsert_user_by_google(conn, google_sub="m", email="maria@x.com", display_name="M")
    db.upsert_profile(conn, u.id, full_name="Maria Santos", job_type="Virtual Assistant",
                      standard_subject="VA – Maria Santos", standard_message="Hi! I am Maria.")
    db.set_activated(conn, u.id)
    db.store_gmail_credential(conn, u.id, refresh_token="rt", master_key=master_key)
    db.add_keyword(conn, u.id, "va")
    return u


def _cycle(conn, cfg, master_key, src, rec, sent, *, fail=False):
    def sender(cfg_, refresh, *, to, subject, text, html):
        if fail:
            raise gmail_send.GmailSendError("temporary glitch")
        sent.append(subject)
        return "m"

    return worker.run_once(conn, src, cfg, master_key,
                           engine_factory=lambda: TailoringEngine(provider=rec),
                           sender=sender, polite=False)


def _usage(conn, user) -> int:
    return db.get_ai_usage_today(conn, user.id)


def _alert(conn, external_id="1"):
    return conn.execute(
        "SELECT a.status, a.attempts, a.last_error FROM user_job_alerts a "
        "JOIN jobs j ON j.id = a.job_id WHERE j.onlinejobs_id=?", (external_id,)).fetchone()


def _wipe_by_prompt_change(conn, user):
    db.set_worker_meta(conn, "prompt_fingerprint", "old-release")    # next cycle wipes the cache


def _wipe_by_profile_edit(conn, user):
    db.upsert_profile(conn, user.id, full_name="Maria Santos", job_type="Virtual Assistant",
                      standard_subject="VA – Maria Santos",
                      standard_message="Hi! I am Maria. (edited)")    # new profile_hash


@pytest.mark.parametrize("lose_cache", [_wipe_by_prompt_change, _wipe_by_profile_edit],
                         ids=["prompt-change-wipe", "profile-edit"])
def test_a_retry_at_the_cap_is_sent_and_not_charged_again(saas_cfg, master_key, lose_cache):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    user = _seed(conn, master_key)
    src, rec, sent = _Source("1"), RecordingProvider(REPLY), []
    _cycle(conn, cfg, master_key, src, rec, sent)                      # baseline
    _cycle(conn, cfg, master_key, src, rec, sent, fail=True)           # first attempt, send fails
    assert tuple(_alert(conn))[:2] == ("pending", 1)
    assert _usage(conn, user) == 1 == cfg.daily_tailor_cap            # charged once, now AT cap

    lose_cache(conn, user)
    r = _cycle(conn, cfg, master_key, src, rec, sent)                  # the retry

    assert (r.sent, r.capped) == (1, 0) and len(sent) == 1
    assert tuple(_alert(conn))[:2] == ("sent", 1)
    assert len(rec.calls) == 2                        # re-tailored fresh, not an old letter
    assert _usage(conn, user) == 1                    # the retry did not charge the cap again
    assert db.get_worker_meta(conn, "prompt_fingerprint") == PROMPT_FINGERPRINT
    conn.close()


def test_retries_stay_free_up_to_the_attempt_limit(saas_cfg, master_key):
    """Every retry misses the cache here, and still none of them is charged."""
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    user = _seed(conn, master_key)
    src, rec, sent = _Source("1"), RecordingProvider(REPLY), []
    _cycle(conn, cfg, master_key, src, rec, sent)                      # baseline
    for _ in range(worker._MAX_ATTEMPTS):
        conn.execute("DELETE FROM tailoring_cache")
        conn.commit()
        _cycle(conn, cfg, master_key, src, rec, sent, fail=True)
    assert tuple(_alert(conn))[:2] == ("failed", worker._MAX_ATTEMPTS)
    assert len(rec.calls) == worker._MAX_ATTEMPTS                     # bounded by the limit
    assert _usage(conn, user) == 1
    conn.close()


def test_a_first_attempt_still_charges_and_still_caps(saas_cfg, master_key):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    user = _seed(conn, master_key)
    src, rec, sent = _Source("1"), RecordingProvider(REPLY), []
    _cycle(conn, cfg, master_key, src, rec, sent)                      # baseline

    r = _cycle(conn, cfg, master_key, src, rec, sent)                  # first attempt, job 1
    assert r.sent == 1 and len(rec.calls) == 1
    assert _usage(conn, user) == 1                                     # it charged

    src.ids.append("2")                                                # a new job, first attempt
    r = _cycle(conn, cfg, master_key, src, rec, sent)
    assert (r.sent, r.capped) == (0, 1)
    status, attempts, last_error = _alert(conn, "2")
    assert (status, attempts) == ("capped", 0) and last_error == "daily cap 1 reached"
    assert len(rec.calls) == 1 and len(sent) == 1                      # no AI call, no email
    assert _usage(conn, user) == 1
    conn.close()


def test_a_first_attempt_after_the_prompt_wipe_still_caps(saas_cfg, master_key):
    """The free pass is for retries only: a fresh alert at the cap is capped, wipe or not."""
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    user = _seed(conn, master_key)
    src, rec, sent = _Source("1"), RecordingProvider(REPLY), []
    _cycle(conn, cfg, master_key, src, rec, sent)                      # baseline
    db.try_increment_ai_usage(conn, user.id, cfg.daily_tailor_cap)     # already at the cap
    _wipe_by_prompt_change(conn, user)
    r = _cycle(conn, cfg, master_key, src, rec, sent)
    assert (r.sent, r.capped) == (0, 1)
    assert tuple(_alert(conn))[:2] == ("capped", 0)
    assert rec.calls == [] and _usage(conn, user) == 1
    conn.close()


def test_a_cap_of_zero_stops_retries_too(saas_cfg, master_key):
    """APPLYFIRST_DAILY_TAILOR_CAP=0 switches the AI off for every attempt: a retry whose cached
    letter is gone is capped with no AI call and no charge, as before retries became free."""
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    conn = db.init_db(cfg.db_path)
    user = _seed(conn, master_key)
    src, rec, sent = _Source("1"), RecordingProvider(REPLY), []
    _cycle(conn, cfg, master_key, src, rec, sent)                      # baseline
    _cycle(conn, cfg, master_key, src, rec, sent, fail=True)           # first attempt, send fails
    assert tuple(_alert(conn))[:2] == ("pending", 1) and len(rec.calls) == 1

    off = dataclasses.replace(cfg, daily_tailor_cap=0)                 # the owner turns AI off
    conn.execute("DELETE FROM tailoring_cache")                        # the retry misses the cache
    conn.commit()
    r = _cycle(conn, off, master_key, src, rec, sent)

    assert (r.sent, r.capped) == (0, 1) and sent == []
    status, attempts, last_error = _alert(conn)
    assert (status, attempts) == ("capped", 1) and last_error == "daily cap 0 reached"
    assert len(rec.calls) == 1                                         # the engine was not called
    assert _usage(conn, user) == 1                                     # ai_usage unchanged
    conn.close()
