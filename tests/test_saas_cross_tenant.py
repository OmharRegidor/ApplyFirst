"""M1 — the hard security gate: cross-tenant access returns 404 (not 403/200).

Also covers the auth route surface: /me gating, sign-in redirect + oauth cookie,
state-mismatch rejection, and the full happy-path callback with a mocked Google
token exchange.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from applyfirst.saas import db, google_oauth, session
from applyfirst.saas.app import create_app


def _client(cfg):
    return TestClient(create_app(cfg), follow_redirects=False)


def _login_as(client, cfg, user_id):
    token = session.sign(cfg.session_secret, {"uid": user_id})
    client.cookies.set(session.session_cookie_name(cfg.secure_cookies), token)


def _seed_two_users(cfg):
    conn = db.init_db(cfg.db_path)
    alice = db.upsert_user_by_google(conn, google_sub="alice", email="a@x.com", display_name="Alice")
    bob = db.upsert_user_by_google(conn, google_sub="bob", email="b@x.com", display_name="Bob")
    alice_cred = db.insert_oauth_credential(conn, alice.id)
    conn.close()
    return alice, bob, alice_cred


def test_cross_tenant_credential_returns_404_not_403(saas_cfg):
    alice, bob, alice_cred = _seed_two_users(saas_cfg)
    client = _client(saas_cfg)

    # Bob (authenticated) requests Alice's credential → must be 404, never 403/200.
    _login_as(client, saas_cfg, bob.id)
    r = client.get(f"/api/oauth-credentials/{alice_cred}")
    assert r.status_code == 404

    # Sanity: Alice fetching her OWN credential succeeds (proves the test bites).
    _login_as(client, saas_cfg, alice.id)
    r2 = client.get(f"/api/oauth-credentials/{alice_cred}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == alice_cred
    # No token material is ever returned.
    assert "refresh_token" not in body and "refresh_token_ciphertext" not in body


def test_credential_route_requires_auth(saas_cfg):
    _, _, alice_cred = _seed_two_users(saas_cfg)
    client = _client(saas_cfg)
    assert client.get(f"/api/oauth-credentials/{alice_cred}").status_code == 401


def test_me_requires_auth(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)
    assert client.get("/me").status_code == 401


def test_me_returns_identity_when_authed(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    user = db.upsert_user_by_google(conn, google_sub="u", email="u@x.com", display_name="U")
    conn.close()
    client = _client(saas_cfg)
    _login_as(client, saas_cfg, user.id)
    body = client.get("/me").json()
    assert body == {"user_id": user.id, "email": "u@x.com", "display_name": "U", "plan": "free"}


def test_root_serves_public_homepage_when_anonymous(saas_cfg):
    # M4: '/' is the public landing page (was a redirect to /login in M1).
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)
    r = client.get("/")
    assert r.status_code == 200 and "Continue with Google" in r.text


def test_dashboard_redirects_to_login_when_anonymous(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)
    r = client.get("/dashboard")
    assert r.status_code == 302 and r.headers["location"] == "/login"


def test_auth_login_redirects_to_google_and_sets_oauth_cookie(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)
    r = client.get("/auth/login")
    assert r.status_code == 302
    assert r.headers["location"].startswith(google_oauth.AUTH_URI)
    assert session.oauth_cookie_name(saas_cfg.secure_cookies) in r.cookies


def test_callback_rejects_state_mismatch(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)
    client.get("/auth/login")  # sets the oauth cookie with the real state
    r = client.get("/auth/callback", params={"code": "x", "state": "WRONG-STATE"})
    assert r.status_code == 400


def test_callback_happy_path_creates_user_and_session(saas_cfg, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)

    # Start the flow to obtain a valid state bound to the oauth cookie.
    login = client.get("/auth/login")
    real_state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    # Mock the network exchange: code → validated identity.
    monkeypatch.setattr(
        google_oauth, "fetch_identity",
        lambda cfg, **kw: {"google_sub": "new-sub", "email": "new@x.com", "display_name": "New"},
    )

    r = client.get("/auth/callback", params={"code": "auth-code", "state": real_state})
    assert r.status_code == 302 and r.headers["location"] == "/dashboard"
    assert session.session_cookie_name(saas_cfg.secure_cookies) in r.cookies

    # The user now exists and is reachable via the session that callback set.
    conn = db.connect(saas_cfg.db_path)
    row = conn.execute("SELECT * FROM users WHERE google_sub='new-sub'").fetchone()
    conn.close()
    assert row is not None and row["email"] == "new@x.com"

    body = client.get("/me").json()
    assert body["email"] == "new@x.com"


def test_logout_clears_session(saas_cfg, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    client = _client(saas_cfg)

    # Log in through the real callback so the cookie is SERVER-set (correct domain/path),
    # which is what /auth/logout's delete_cookie must match to actually clear it.
    login = client.get("/auth/login")
    real_state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    monkeypatch.setattr(
        google_oauth, "fetch_identity",
        lambda cfg, **kw: {"google_sub": "u", "email": "u@x.com", "display_name": "U"},
    )
    client.get("/auth/callback", params={"code": "c", "state": real_state})
    assert client.get("/me").status_code == 200

    uid = client.get("/me").json()["user_id"]
    client.headers["X-CSRF-Token"] = session.issue_csrf(saas_cfg.session_secret, uid)
    client.post("/auth/logout")
    # Cookie cleared -> /me is unauthenticated again.
    assert client.get("/me").status_code == 401
