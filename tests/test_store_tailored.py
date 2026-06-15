"""Tests for persisting/reading the AI-tailored package + the busy_timeout fix."""

from __future__ import annotations

import json

from applyfirst.models import RawJob
from applyfirst.store import Store
from applyfirst.tailor.contract import ScreeningQA, TailoredPackage
from applyfirst.tailor.engine import TailorResult


def _seed_job(store: Store) -> int:
    return store.insert_job(
        RawJob(source="olj", external_id="job-1", url="https://olj/job/1",
               title="React Developer", employment_type="Full Time",
               salary_text="$1500", matched_keyword="react"),
        raw_description="We need a React dev.",
    )


def test_busy_timeout_is_set(tmp_path):
    store = Store(tmp_path / "t.db")
    assert store.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    store.close()


def test_save_and_get_tailored_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    jid = _seed_job(store)
    pkg = TailoredPackage(
        application_subject="React Developer - Omhar Regidor",
        cover_letter="Hi, I'm Omhar.",
        screening_questions=[ScreeningQA(question="Years?", drafted_answer="3")],
        digest="They want React.",
    )
    store.save_tailored(jid, TailorResult(package=pkg, provider="gemini", ai_available=True))

    row = store.get_tailored(jid)
    assert row is not None
    assert row["application_subject"] == "React Developer - Omhar Regidor"
    assert row["cover_letter"] == "Hi, I'm Omhar."
    assert row["provider"] == "gemini"
    assert row["ai_available"] == 1
    # screening_json is a JSON list of {question, drafted_answer}
    screening = json.loads(row["screening_json"])
    assert screening[0]["question"] == "Years?"
    # package_json is the full TailoredPackage, round-trippable
    pkg_back = json.loads(row["package_json"])
    assert pkg_back["application_subject"] == "React Developer - Omhar Regidor"
    store.close()


def test_save_tailored_upserts(tmp_path):
    store = Store(tmp_path / "t.db")
    jid = _seed_job(store)
    store.save_tailored(jid, TailorResult(
        package=TailoredPackage(cover_letter="v1"), provider="gemini", ai_available=True))
    store.save_tailored(jid, TailorResult(
        package=TailoredPackage(cover_letter="v2"), provider="rules-fallback", ai_available=False))

    assert store.count_jobs() == 1
    row = store.get_tailored(jid)
    assert row["cover_letter"] == "v2"            # overwritten, not duplicated
    assert row["provider"] == "rules-fallback"
    assert row["ai_available"] == 0
    # exactly one tailored row for the job
    n = store.conn.execute("SELECT COUNT(*) FROM tailored WHERE job_id=?", (jid,)).fetchone()[0]
    assert n == 1
    store.close()


def test_get_tailored_missing_returns_none(tmp_path):
    store = Store(tmp_path / "t.db")
    jid = _seed_job(store)
    assert store.get_tailored(jid) is None
    store.close()
