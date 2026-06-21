"""M1 — auth-flow edge cases: callback error paths, login 503, replay, secure cookies.

These cover the branches the happy-path/cross-tenant tests don't reach (flagged by
Franco's QA review).
"""

from __future__ import annotations

import dataclasses
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from applyfirst.saas import db, google_oauth, session
from applyfirst.saas.app import create_app


def _client(cfg):
    return TestClient(create_app(cfg), follow_redirects=False)


def _start_login(client) -> str:
    """Begin the flow; return the real `state` bound to the oauth cookie."""
    r = client.get("/auth/login")
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0]


def _identity(**over):
    base = {"google_sub": "s", "email": "e@x.com", "display_name": "N"}
    base.update(over)
    return lambda cfg, **kw: base


def test_callback_access_denied_returns_400(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    _start_login(c)
    assert c.get("/auth/callback", params={"error": "access_denied"}).status_code == 400


def test_callback_missing_code_returns_400(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    state = _start_login(c)
    assert c.get("/auth/callback", params={"state": state}).status_code == 400


def test_callback_without_oauth_cookie_returns_400(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    # No /auth/login first → no oauth txn cookie present.
    r = c.get("/auth/callback", params={"code": "x", "state": "anything"})
    assert r.status_code == 400


def test_callback_oauth_error_returns_400_and_clears_cookie(saas_cfg, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    state = _start_login(c)

    def boom(cfg, **kw):
        raise google_oauth.OAuthError("bad nonce")

    monkeypatch.setattr(google_oauth, "fetch_identity", boom)
    r = c.get("/auth/callback", params={"code": "x", "state": state})
    assert r.status_code == 400
    set_cookies = "; ".join(r.headers.get_list("set-cookie"))
    assert "applyfirst_oauth" in set_cookies  # txn cookie cleared on failure


def test_login_returns_503_when_google_not_configured(saas_cfg):
    cfg = dataclasses.replace(saas_cfg, google_client_id=None)
    db.init_db(cfg.db_path).close()
    c = _client(cfg)
    assert c.get("/auth/login").status_code == 503


def test_callback_code_replay_rejected(saas_cfg, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    state = _start_login(c)
    monkeypatch.setattr(google_oauth, "fetch_identity", _identity())
    assert c.get("/auth/callback", params={"code": "c", "state": state}).status_code == 302
    # Replay the same code: the first callback cleared the oauth cookie → no txn → 400.
    assert c.get("/auth/callback", params={"code": "c", "state": state}).status_code == 400


def test_callback_returning_user_updates_profile(saas_cfg, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)

    s1 = _start_login(c)
    monkeypatch.setattr(google_oauth, "fetch_identity",
                        _identity(google_sub="same", email="a@x.com", display_name="First"))
    c.get("/auth/callback", params={"code": "c1", "state": s1})

    s2 = _start_login(c)
    monkeypatch.setattr(google_oauth, "fetch_identity",
                        _identity(google_sub="same", email="a2@x.com", display_name="Second"))
    c.get("/auth/callback", params={"code": "c2", "state": s2})

    conn = db.connect(saas_cfg.db_path)
    rows = conn.execute("SELECT * FROM users WHERE google_sub='same'").fetchall()
    conn.close()
    assert len(rows) == 1                       # no duplicate on return visit
    assert rows[0]["display_name"] == "Second"  # profile refreshed
    assert rows[0]["email"] == "a2@x.com"


def test_logout_get_not_allowed(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    assert c.get("/auth/logout").status_code == 405  # POST-only → CSRF-safe


def test_secure_cookies_use_host_prefix_and_secure_flag(saas_cfg):
    cfg = dataclasses.replace(saas_cfg, secure_cookies=True, session_secret=b"x" * 32)
    db.init_db(cfg.db_path).close()
    c = _client(cfg)
    r = c.get("/auth/login")
    set_cookies = "; ".join(r.headers.get_list("set-cookie"))
    assert "__Host-applyfirst_oauth" in set_cookies
    assert "Secure" in set_cookies


def test_security_headers_present(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    h = c.get("/healthz").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in h["Content-Security-Policy"]
