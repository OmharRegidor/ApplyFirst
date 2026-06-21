"""M4 — public homepage + Privacy/Terms pages (reachable without auth; required content)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from applyfirst.saas import db, session
from applyfirst.saas.app import create_app


def _client(cfg):
    db.init_db(cfg.db_path).close()
    return TestClient(create_app(cfg), follow_redirects=False)


def test_homepage_is_public_and_describes_gmail_use(saas_cfg):
    c = _client(saas_cfg)
    r = c.get("/")
    assert r.status_code == 200
    body = r.text
    assert "Continue with Google" in body
    assert "gmail.send" in body                       # explains the scope
    assert 'href="/privacy"' in body                  # footer privacy link (Google checks this)


def test_homepage_redirects_authed_user_to_dashboard(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    user = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    conn.close()
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(saas_cfg.session_secret, {"uid": user.id}))
    r = c.get("/")
    assert r.status_code == 302 and r.headers["location"] == "/dashboard"


def test_privacy_is_public_and_accurate(saas_cfg):
    c = _client(saas_cfg)
    r = c.get("/privacy")
    assert r.status_code == 200
    body = r.text
    # Required Google "Limited Use" affirmation.
    assert "Limited Use" in body
    assert "Google API Services User Data Policy" in body
    # Accurate, honest disclosures.
    assert "gmail.send" in body
    assert "never read" in body.lower() or "never read" in body
    assert "not" in body and "sell" in body            # no-sale language
    assert "omharregidor@gmail.com" in body            # real contact


def test_terms_is_public(saas_cfg):
    c = _client(saas_cfg)
    r = c.get("/terms")
    assert r.status_code == 200
    assert "Terms of Service" in r.text
    assert "review" in r.text.lower()                  # user reviews before sending


def test_legal_pages_need_no_auth(saas_cfg):
    """Privacy/Terms must be reachable with no session cookie at all."""
    c = _client(saas_cfg)
    assert c.get("/privacy").status_code == 200
    assert c.get("/terms").status_code == 200
    assert c.get("/").status_code == 200
