"""M5 — CSRF synchronizer tokens on state-changing POSTs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from applyfirst.saas import db, session
from applyfirst.saas.app import create_app


def _auth_client(cfg):
    """An authenticated client that does NOT auto-send a CSRF token."""
    app = create_app(cfg)
    conn = db.init_db(cfg.db_path)
    user = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    conn.close()
    c = TestClient(app, follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(cfg.session_secret, {"uid": user.id}))
    return c, user


def test_post_without_token_is_rejected(saas_cfg):
    c, _ = _auth_client(saas_cfg)
    assert c.post("/onboarding/keywords", data={"keyword": "va"}).status_code == 403


def test_post_with_form_field_token_accepted(saas_cfg):
    c, user = _auth_client(saas_cfg)
    token = session.issue_csrf(saas_cfg.session_secret, user.id)
    r = c.post("/onboarding/keywords", data={"keyword": "va", "csrf": token})
    assert r.status_code == 302


def test_post_with_header_token_accepted(saas_cfg):
    c, user = _auth_client(saas_cfg)
    token = session.issue_csrf(saas_cfg.session_secret, user.id)
    r = c.post("/onboarding/keywords", data={"keyword": "va"},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 302


def test_token_minted_for_another_user_is_rejected(saas_cfg):
    c, _ = _auth_client(saas_cfg)
    foreign = session.issue_csrf(saas_cfg.session_secret, "someone-else")
    r = c.post("/onboarding/keywords", data={"keyword": "va", "csrf": foreign})
    assert r.status_code == 403


def test_tampered_token_is_rejected(saas_cfg):
    c, user = _auth_client(saas_cfg)
    token = session.issue_csrf(saas_cfg.session_secret, user.id)
    r = c.post("/onboarding/keywords", data={"keyword": "va", "csrf": token + "x"})
    assert r.status_code == 403


def test_render_pages_embed_the_hidden_csrf_input(saas_cfg):
    c, _ = _auth_client(saas_cfg)
    html = c.get("/onboarding/profile").text
    assert 'name="csrf"' in html


def test_unauthenticated_post_is_401_not_403(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    # require_user runs before the CSRF check → auth failure surfaces first.
    assert c.post("/onboarding/keywords", data={"keyword": "va"}).status_code == 401
