"""M2 — Connect/Disconnect Gmail (incremental gmail.send authorization)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from applyfirst.saas import db, google_oauth, session
from applyfirst.saas.app import create_app


def _client_user(saas_cfg):
    app = create_app(saas_cfg)
    conn = db.init_db(saas_cfg.db_path)
    user = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    conn.close()
    c = TestClient(app, follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(saas_cfg.session_secret, {"uid": user.id}))
    c.headers["X-CSRF-Token"] = session.issue_csrf(saas_cfg.session_secret, user.id)
    return c, user


def test_connect_gmail_url_requests_send_scope_offline(saas_cfg):
    qs = parse_qs(urlparse(
        google_oauth.build_connect_gmail_url(saas_cfg, state="st", code_challenge="ch")).query)
    assert qs["scope"] == [google_oauth.GMAIL_SCOPE]
    assert qs["access_type"] == ["offline"]
    assert qs["prompt"] == ["consent"]             # force a refresh token
    assert qs["include_granted_scopes"] == ["true"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["redirect_uri"] == ["https://localhost:8000/auth/gmail-callback"]


def test_connect_gmail_requires_auth(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    assert c.get("/auth/connect-gmail").status_code == 401


def test_connect_gmail_redirects_and_sets_txn_cookie(saas_cfg):
    c, _ = _client_user(saas_cfg)
    r = c.get("/auth/connect-gmail")
    assert r.status_code == 302
    assert r.headers["location"].startswith(google_oauth.AUTH_URI)
    assert "applyfirst_oauth" in r.cookies


def test_gmail_callback_stores_encrypted_token(saas_cfg, master_key, monkeypatch):
    c, user = _client_user(saas_cfg)
    state = parse_qs(urlparse(c.get("/auth/connect-gmail").headers["location"]).query)["state"][0]
    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail",
                        lambda cfg, **kw: "refresh-XYZ")

    cb = c.get("/auth/gmail-callback", params={"code": "c", "state": state})
    assert cb.status_code == 302 and cb.headers["location"] == "/onboarding"

    conn = db.connect(saas_cfg.db_path)
    try:
        assert db.gmail_connected(conn, user.id) is True
        assert db.get_gmail_refresh_token(conn, user.id, master_key) == "refresh-XYZ"
        raw = conn.execute(
            "SELECT refresh_token_ciphertext FROM oauth_credentials WHERE user_id=?",
            (user.id,)).fetchone()[0]
        assert b"refresh-XYZ" not in raw          # stored encrypted, not raw
    finally:
        conn.close()


def test_gmail_callback_state_mismatch_rejected(saas_cfg, master_key):
    c, _ = _client_user(saas_cfg)
    c.get("/auth/connect-gmail")
    assert c.get("/auth/gmail-callback",
                 params={"code": "c", "state": "WRONG"}).status_code == 400


def test_gmail_callback_no_refresh_token_rejected(saas_cfg, master_key, monkeypatch):
    c, user = _client_user(saas_cfg)
    state = parse_qs(urlparse(c.get("/auth/connect-gmail").headers["location"]).query)["state"][0]

    def boom(cfg, **kw):
        raise google_oauth.OAuthError("no refresh token")

    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail", boom)
    assert c.get("/auth/gmail-callback",
                 params={"code": "c", "state": state}).status_code == 400
    conn = db.connect(saas_cfg.db_path)
    assert db.gmail_connected(conn, user.id) is False
    conn.close()


def test_gmail_callback_access_denied_rejected(saas_cfg, master_key):
    c, user = _client_user(saas_cfg)
    c.get("/auth/connect-gmail")
    assert c.get("/auth/gmail-callback",
                 params={"error": "access_denied"}).status_code == 400
    conn = db.connect(saas_cfg.db_path)
    assert db.gmail_connected(conn, user.id) is False
    conn.close()


def test_gmail_callback_master_key_missing_rejected(saas_cfg, monkeypatch):
    """If the master key isn't configured, the callback fails closed and stores nothing."""
    monkeypatch.delenv("APPLYFIRST_MASTER_KEY", raising=False)
    monkeypatch.delenv("MASTER_KEY_PATH", raising=False)
    c, user = _client_user(saas_cfg)
    state = parse_qs(urlparse(c.get("/auth/connect-gmail").headers["location"]).query)["state"][0]
    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail", lambda cfg, **kw: "rt")
    assert c.get("/auth/gmail-callback",
                 params={"code": "c", "state": state}).status_code == 400
    conn = db.connect(saas_cfg.db_path)
    assert db.gmail_connected(conn, user.id) is False
    conn.close()


def test_gmail_callback_expired_txn_rejected(saas_cfg, master_key):
    import time
    c, _ = _client_user(saas_cfg)
    # Forge an oauth txn cookie older than its 10-minute TTL.
    stale = session.sign(saas_cfg.session_secret, {
        "state": "s", "nonce": "n/a", "verifier": "v", "iat": int(time.time()) - 1200})
    c.cookies.set("applyfirst_oauth", stale)
    assert c.get("/auth/gmail-callback",
                 params={"code": "c", "state": "s"}).status_code == 400


def test_disconnect_gmail_revokes_and_clears(saas_cfg, master_key, monkeypatch):
    c, user = _client_user(saas_cfg)
    conn = db.init_db(saas_cfg.db_path)
    db.store_gmail_credential(conn, user.id, refresh_token="rt", master_key=master_key)
    conn.close()

    revoked = {}
    monkeypatch.setattr(google_oauth, "revoke_token", lambda t: revoked.__setitem__("t", t))
    r = c.post("/auth/disconnect-gmail")
    assert r.status_code == 302 and r.headers["location"] == "/dashboard"
    assert revoked.get("t") == "rt"                # the stored token was revoked at Google

    conn = db.connect(saas_cfg.db_path)
    assert db.gmail_connected(conn, user.id) is False
    conn.close()
