"""M1 — auth-flow edge cases: callback error paths, login 503, replay, secure cookies.

These cover the branches the happy-path/cross-tenant tests don't reach (flagged by
Franco's QA review).
"""

from __future__ import annotations

import dataclasses
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Response
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


# A browser replaces a cookie, and so deletes it, only when the delete carries the same rules
# the cookie was set with: a __Host- cookie is dropped on the floor without Secure and Path=/.
# Starlette's delete_cookie defaults to secure=False and httponly=False, and the httpx cookie jar
# in TestClient does not enforce the __Host- rules, so only the raw header shows a bad delete.

_HOST_RULES = {"path": "/", "secure": "", "httponly": "", "samesite": "lax"}


def _cookie_rules(header: str) -> dict[str, str]:
    """A Set-Cookie header's attributes, names lower-cased, without the two that say when."""
    rules = {}
    for part in header.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        rules[name.lower()] = value
    return {k: v for k, v in rules.items() if k not in ("max-age", "expires")}


def _deletes(headers: list[str], name: str) -> list[str]:
    return [h for h in headers if h.startswith(name + "=") and "Max-Age=0" in h]


@pytest.mark.parametrize("secure", [True, False], ids=["secure", "http"])
@pytest.mark.parametrize("which", ["session", "oauth"])
def test_a_cookie_is_deleted_with_the_rules_it_was_set_with(secure, which):
    made, gone = Response(), Response()
    if which == "session":
        session.set_session(made, b"s" * 32, secure, "u1")
        session.clear_session(gone, secure)
        name = session.session_cookie_name(secure)
    else:
        session.set_oauth_txn(made, b"s" * 32, secure, state="s", nonce="n", verifier="v")
        session.clear_oauth_txn(gone, secure)
        name = session.oauth_cookie_name(secure)
    [set_header] = made.headers.getlist("set-cookie")
    [delete] = _deletes(gone.headers.getlist("set-cookie"), name)
    assert set_header.startswith(name + "=")
    assert _cookie_rules(delete) == _cookie_rules(set_header)
    if secure:
        assert name.startswith("__Host-") and _cookie_rules(delete) == _HOST_RULES


def test_logout_and_a_failed_callback_delete_the_host_cookies_a_browser_holds(saas_cfg):
    """Production: Log out must really sign out, and the D8 page must really clear the OAuth
    transaction (spec 6.4). Both deletes carry Secure, HttpOnly, Path=/ and SameSite."""
    cfg = dataclasses.replace(saas_cfg, secure_cookies=True)
    conn = db.init_db(cfg.db_path)
    user = db.upsert_user_by_google(conn, google_sub="s", email="e@x.com", display_name="N")
    conn.close()
    c = TestClient(create_app(cfg), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("__Host-applyfirst_session", session.sign(cfg.session_secret, {"uid": user.id}))
    _start_login(c)

    out = c.post("/auth/logout",
                 headers={"X-CSRF-Token": session.issue_csrf(cfg.session_secret, user.id)})
    failed = c.get("/auth/callback", params={"error": "access_denied"})

    assert (out.status_code, out.headers["location"]) == (302, "/login")
    assert failed.status_code == 400
    for resp, name in ((out, "__Host-applyfirst_session"), (failed, "__Host-applyfirst_oauth")):
        deletes = _deletes(resp.headers.get_list("set-cookie"), name)
        assert len(deletes) == 1, (name, resp.headers.get_list("set-cookie"))
        assert _cookie_rules(deletes[0]) == _HOST_RULES, deletes[0]


def test_security_headers_present(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    h = c.get("/healthz").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in h["Content-Security-Policy"]
