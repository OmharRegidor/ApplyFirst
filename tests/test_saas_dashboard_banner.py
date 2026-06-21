"""M5 — daily-cap dashboard banner + the read-only usage helper."""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from applyfirst.saas import db, session
from applyfirst.saas.app import create_app


def test_get_ai_usage_today_counts_and_defaults_zero(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    u = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    assert db.get_ai_usage_today(conn, u.id) == 0
    db.try_increment_ai_usage(conn, u.id, 10)
    db.try_increment_ai_usage(conn, u.id, 10)
    assert db.get_ai_usage_today(conn, u.id) == 2
    conn.close()


def _activated_client(cfg, *, usage=0):
    app = create_app(cfg)
    conn = db.init_db(cfg.db_path)
    u = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    db.upsert_profile(conn, u.id, full_name="A", job_type="VA",
                      standard_subject="S", standard_message="M")
    db.set_activated(conn, u.id)
    for _ in range(usage):
        db.try_increment_ai_usage(conn, u.id, 1000)
    conn.close()
    c = TestClient(app, follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(cfg.session_secret, {"uid": u.id}))
    return c


def test_dashboard_shows_usage_vs_cap(saas_cfg):
    c = _activated_client(saas_cfg, usage=1)
    r = c.get("/dashboard")
    assert r.status_code == 200
    assert "1 / 10" in r.text
    assert "daily limit reached" not in r.text


def test_dashboard_flags_cap_reached(saas_cfg):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=1)
    c = _activated_client(cfg, usage=1)
    r = c.get("/dashboard")
    assert r.status_code == 200
    assert "1 / 1" in r.text
    assert "daily limit reached" in r.text
