"""Tests for the read-only web dashboard (FastAPI TestClient)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # dashboard deps are optional for the core poller
from fastapi.testclient import TestClient  # noqa: E402

from applyfirst.models import RawJob  # noqa: E402
from applyfirst.store import Store  # noqa: E402
from applyfirst.tailor.contract import ScreeningQA, TailoredPackage  # noqa: E402
from applyfirst.tailor.engine import TailorResult  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "web.db"
    store = Store(db)
    store.add_search("react")
    store.set_baselined("react")

    jid = store.insert_job(
        RawJob(source="olj", external_id="job-1", url="https://olj/job/1",
               title="React Developer", employment_type="Full Time",
               salary_text="$1500", matched_keyword="react"),
        raw_description="We need a React dev. To apply, send portfolio.",
    )
    store.save_tailored(jid, TailorResult(
        package=TailoredPackage(
            application_subject="React Developer - Omhar Regidor",
            cover_letter="Hi, I am Omhar from Batangas.",
            screening_questions=[ScreeningQA(question="Years of React?", drafted_answer="3 years")],
            digest="They want a React developer.",
        ),
        provider="gemini", ai_available=True,
    ))

    jid2 = store.insert_job(
        RawJob(source="olj", external_id="job-2", url="https://olj/job/2",
               title="Backend Engineer", matched_keyword="node"),
        raw_description="Node backend role.",
    )
    store.touch_heartbeat()
    store.close()

    monkeypatch.setenv("APPLYFIRST_DB", str(db))
    from applyfirst.web.app import app
    return TestClient(app), jid, jid2


def test_index_lists_jobs(client):
    c, _, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "React Developer" in r.text
    assert "Backend Engineer" in r.text


def test_detail_shows_persisted_package(client):
    c, jid, _ = client
    r = c.get(f"/job/{jid}")
    assert r.status_code == 200
    assert "React Developer - Omhar Regidor" in r.text   # subject
    assert "Hi, I am Omhar from Batangas." in r.text       # cover letter
    assert "Years of React?" in r.text                     # screening question
    assert "3 years" in r.text                             # drafted answer


def test_detail_without_package_shows_note(client):
    c, _, jid2 = client
    r = c.get(f"/job/{jid2}")
    assert r.status_code == 200
    assert "emailed, not stored" in r.text


def test_detail_404_for_missing_or_bad_id(client):
    c, _, _ = client
    assert c.get("/job/999999").status_code == 404
    assert c.get("/job/notanumber").status_code == 404


def test_api_health_shape(client):
    c, _, _ = client
    r = c.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["total_jobs"] == 2
    assert "last_cycle_at" in data
    assert "stale" in data
    assert "ok" in data


def test_limit_param_is_bounded(client):
    c, _, _ = client
    assert c.get("/?limit=500").status_code == 422   # > 100 rejected
    assert c.get("/?limit=25").status_code == 200


def test_healthz(client):
    c, _, _ = client
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"
