"""The SaaS worker sends a candidate-driven prompt, never reuses a letter an older prompt
wrote, and every per-user prompt input is covered by the tailoring cache key."""

from __future__ import annotations

import ast
import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from applyfirst.models import JobDetail, RawJob
from applyfirst.saas import db, gmail_send, preview, worker
from applyfirst.tailor import TailoringEngine
from applyfirst.tailor.prompt import PROMPT_FINGERPRINT, RESUME_ON_REQUEST, build_user_prompt
from _saas_client import (
    INVENTED_AVAILABILITY, OWNER_MARKERS, RESUME_CLAIMS, RecordingProvider, hits,
)

SAAS_DIR = Path(worker.__file__).parent
FIELDS = ["full_name", "job_type", "standard_subject", "standard_message"]
POST = "VA needed. TO APPLY: send your resume and your availability."


class _Source:
    name = "onlinejobs.ph"

    def search_latest(self, keyword):
        return [RawJob(source="onlinejobs.ph", external_id="1", url="http://oj/job-1",
                       title="VA needed", employment_type="Full time", salary_text=None,
                       posted_at=datetime(2026, 9, 1, tzinfo=timezone.utc), preview="p",
                       matched_keyword=None)]

    def fetch_detail(self, job):
        return JobDetail(raw=job, description=POST, skills=[])


def _recorder():
    return RecordingProvider('{"digest":"d","application_subject":"VA – Maria Santos",'
                             '"cover_letter":"Hi! I am Maria.","screening_questions":[]}')


def _seed(conn, master_key):
    u = db.upsert_user_by_google(conn, google_sub="m", email="maria@x.com", display_name="M")
    db.upsert_profile(conn, u.id, full_name="Maria Santos", job_type="Virtual Assistant",
                      standard_subject="VA – Maria Santos", standard_message="Hi! I am Maria.")
    db.set_activated(conn, u.id)
    db.store_gmail_credential(conn, u.id, refresh_token="rt", master_key=master_key)
    db.add_keyword(conn, u.id, "va")
    return u


def _cycle(conn, cfg, master_key, rec, sent, *, sender=None):
    def ok_sender(cfg_, refresh, *, to, subject, text, html):
        sent.append(subject + text + html)
        return "m"

    return worker.run_once(conn, _Source(), cfg, master_key,
                           engine_factory=lambda: TailoringEngine(provider=rec),
                           sender=sender or ok_sender, polite=False)


# --- T9 -------------------------------------------------------------------------------

def test_worker_prompt_and_email_are_candidate_driven(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    rec, sent = _recorder(), []
    for _ in range(2):                       # baseline, then the real cycle
        _cycle(conn, saas_cfg, master_key, rec, sent)
    assert len(rec.calls) == 1 and len(sent) == 1
    prompt_text = "\n".join(rec.calls[0])
    assert "Maria Santos" in prompt_text
    assert hits(prompt_text, OWNER_MARKERS + RESUME_CLAIMS + INVENTED_AVAILABILITY) == []
    assert RESUME_ON_REQUEST in prompt_text           # the post asks for a resume
    assert hits(sent[0], OWNER_MARKERS + RESUME_CLAIMS + INVENTED_AVAILABILITY) == []
    # No other user data reaches the model (T13): no email address, no user id.
    assert u.email not in prompt_text and u.id not in prompt_text
    conn.close()


def test_worker_fallback_letter_offers_the_resume_on_request(saas_cfg, master_key):
    """No AI key: the email still honours the owner's resume rule and invents nothing."""
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    sent: list[str] = []
    for _ in range(2):
        _cycle(conn, saas_cfg, master_key, None, sent)
    assert len(sent) == 1
    assert RESUME_ON_REQUEST in sent[0]
    assert hits(sent[0], OWNER_MARKERS + RESUME_CLAIMS + INVENTED_AVAILABILITY) == []
    conn.close()


# --- T10 ------------------------------------------------------------------------------

def _build_calls():
    for path in sorted(SAAS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "build"):
                yield path.name, node


def test_every_saas_build_call_says_no_resume_is_attached():
    calls = list(_build_calls())
    assert {name for name, _ in calls} >= {"worker.py", "preview.py"}      # never vacuous
    for name, call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        value = kw.get("resume_attached")
        assert isinstance(value, ast.Constant) and value.value is False, (
            f"{name}:{call.lineno} calls .build( without resume_attached=False")


def test_stale_cache_check_is_the_first_statement_of_run_once():
    fn = ast.parse(inspect.getsource(worker.run_once)).body[0]
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    first = body[0]
    assert (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
            and ast.unparse(first.value) == "_invalidate_stale_cache(conn)")


# --- T11 ------------------------------------------------------------------------------

def test_a_letter_cached_by_an_older_prompt_is_never_reused(saas_cfg, master_key, caplog):
    conn = db.init_db(saas_cfg.db_path)
    u = _seed(conn, master_key)
    rec, sent = _recorder(), []
    _cycle(conn, saas_cfg, master_key, rec, sent)              # baseline: the job is stored
    assert db.get_worker_meta(conn, "prompt_fingerprint") == PROMPT_FINGERPRINT

    # An older release wrote an owner-flavoured package for exactly the coming (job, profile).
    db.set_worker_meta(conn, "prompt_fingerprint", "old-release")
    job_id = db.get_job_id(conn, "1")
    profile_hash = db.get_profile(conn, u.id).profile_hash
    db.cache_put(conn, job_id, profile_hash,
                 '{"application_subject":"Full-Stack Developer – Omhar Regidor",'
                 '"cover_letter":"Live projects I\'ve built. Tailored resume attached."}', "gemini")

    with caplog.at_level(logging.INFO, logger="applyfirst.saas.worker"):
        _cycle(conn, saas_cfg, master_key, rec, sent)
    assert len(rec.calls) == 1                                  # tailored fresh
    assert len(sent) == 1
    assert hits(sent[0], OWNER_MARKERS + RESUME_CLAIMS) == []
    fresh = db.cache_get(conn, job_id, profile_hash)
    assert "Omhar" not in fresh["package_json"] and "Maria Santos" in fresh["package_json"]
    assert db.get_worker_meta(conn, "prompt_fingerprint") == PROMPT_FINGERPRINT
    assert any(r.getMessage() == "tailoring_cache_invalidated" for r in caplog.records)
    conn.close()


def test_invalidate_returns_rows_removed_and_runs_once_per_fingerprint(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    jid = db.insert_job(conn, onlinejobs_id="9", title="t", url="u", employment_type=None,
                        salary_text=None, posted_at=None, raw_description="d")
    db.cache_put(conn, jid, "hash-a", '{"cover_letter":"old"}', "gemini")
    db.cache_put(conn, jid, "hash-b", '{"cover_letter":"old"}', "gemini")
    assert worker._invalidate_stale_cache(conn) == 2            # first start on this prompt
    assert db.cache_get(conn, jid, "hash-a") is None
    db.cache_put(conn, jid, "hash-a", '{"cover_letter":"new"}', "gemini")
    assert worker._invalidate_stale_cache(conn) == 0            # same prompt: keep it
    assert db.cache_get(conn, jid, "hash-a") is not None
    conn.close()


# --- T12 ------------------------------------------------------------------------------

def test_a_retry_after_a_transient_failure_reuses_the_fresh_cache(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    rec, sent = _recorder(), []

    def flaky(cfg_, refresh, **kw):
        raise gmail_send.GmailSendError("temporary glitch")

    _cycle(conn, saas_cfg, master_key, rec, sent)                        # baseline
    _cycle(conn, saas_cfg, master_key, rec, sent, sender=flaky)          # tailor, send fails
    r = _cycle(conn, saas_cfg, master_key, rec, sent)                    # retry
    assert r.sent == 1 and len(sent) == 1
    assert len(rec.calls) == 1                                           # provider called once
    assert conn.execute("SELECT tailoring_calls FROM ai_usage").fetchone()[0] == 1
    conn.close()


# --- T13 ------------------------------------------------------------------------------

def test_every_per_user_prompt_input_is_part_of_the_profile_hash():
    to_profile = list(inspect.signature(preview.to_profile).parameters)
    upsert = [p for p in inspect.signature(db.upsert_profile).parameters
              if p not in ("conn", "user_id")]
    assert to_profile == upsert == FIELDS
    assert len(inspect.signature(db._profile_hash).parameters) == len(FIELDS)
    assert ("_profile_hash(full_name, job_type, standard_subject, standard_message)"
            in inspect.getsource(db.upsert_profile))
    # The worker feeds the prompt exactly those four stored fields, nothing else.
    calls = [n for n in ast.walk(ast.parse(inspect.getsource(worker)))
             if isinstance(n, ast.Call) and ast.unparse(n.func) == "preview.to_profile"]
    assert len(calls) == 1 and not calls[0].args
    assert {k.arg: ast.unparse(k.value) for k in calls[0].keywords} == {
        f: f"profile.{f}" for f in FIELDS}


@pytest.mark.parametrize("field", FIELDS)
def test_changing_any_field_changes_both_the_hash_and_the_prompt(field):
    base = {"full_name": "Maria Santos", "job_type": "VA", "standard_subject": "VA – Maria",
            "standard_message": "Hi! I am Maria."}
    changed = {**base, field: base[field] + " (edited)"}
    assert db._profile_hash(*base.values()) != db._profile_hash(*changed.values())
    assert (build_user_prompt(preview.to_profile(**base), POST, tag="t")
            != build_user_prompt(preview.to_profile(**changed), POST, tag="t"))
