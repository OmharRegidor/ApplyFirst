"""Every non-scope gmail-callback failure shows ONE friendly Step 1 retry page (400 HTML)."""

from __future__ import annotations

import logging
import time

import pytest

from applyfirst.saas import crypto, db, google_oauth, session
from _saas_client import (
    EXPECTED_CSP, by_id, clean, client_for, db_conn, elements, form_inputs, gmail_callback,
    is_connected, post_forms, seed_user, txn_cookie_cleared,
)


def _boom(exc):
    def raise_it(*a, **kw):
        raise exc
    return raise_it


def _fail_state_mismatch(c, cfg, mp):
    c.get("/auth/connect-gmail")
    return c.get("/auth/gmail-callback", params={"code": "c", "state": "WRONG"})


def _fail_expired_txn(c, cfg, mp):
    stale = session.sign(cfg.session_secret, {
        "state": "s", "nonce": "n/a", "verifier": "v", "iat": int(time.time()) - 1200})
    c.cookies.set("applyfirst_oauth", stale)
    return c.get("/auth/gmail-callback", params={"code": "c", "state": "s"})


def _fail_missing_code(c, cfg, mp):
    return gmail_callback(c, code="")


def _fail_exchange(c, cfg, mp):
    mp.setattr(google_oauth, "exchange_code_for_gmail",
               _boom(google_oauth.OAuthError("no refresh token")))
    return gmail_callback(c)


def _fail_crypto(c, cfg, mp):
    mp.setattr(google_oauth, "exchange_code_for_gmail", lambda cfg_, **kw: "rt")
    mp.setattr(crypto, "load_master_key", _boom(crypto.CryptoError("no master key")))
    return gmail_callback(c)


def _fail_cancel(c, cfg, mp):
    c.get("/auth/connect-gmail")
    return c.get("/auth/gmail-callback", params={"error": "access_denied"})


FAILURES = {"cancel": _fail_cancel, "state": _fail_state_mismatch, "expired": _fail_expired_txn,
            "no_code": _fail_missing_code, "exchange": _fail_exchange, "crypto": _fail_crypto}


# --- backend contract (no template dependency) ------------------------------------------

@pytest.mark.parametrize("kind", FAILURES)
def test_every_failure_is_a_400_html_page_not_json(saas_cfg, master_key, monkeypatch, caplog,
                                                   kind):
    user = seed_user(saas_cfg)
    c = client_for(saas_cfg, user)
    with caplog.at_level(logging.WARNING, logger="applyfirst.saas.app"):
        r = FAILURES[kind](c, saas_cfg, monkeypatch)
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert txn_cookie_cleared(r)
    assert is_connected(saas_cfg, user) is False
    assert '"error"' not in r.text[:40]                       # never the old JSON body
    # The reason goes to the server log only.
    logged = [rec for rec in caplog.records if rec.getMessage() == "gmail_connect_failed"]
    assert len(logged) == 1


def test_failure_keeps_an_earlier_working_grant(saas_cfg, master_key, monkeypatch):
    user = seed_user(saas_cfg, gmail_key=master_key)
    c = client_for(saas_cfg, user)
    assert _fail_exchange(c, saas_cfg, monkeypatch).status_code == 400
    with db_conn(saas_cfg) as conn:
        assert db.get_gmail_refresh_token(conn, user.id, master_key) == "rt-old"


def test_retry_page_logout_form_carries_a_valid_csrf(saas_cfg, master_key):
    user = seed_user(saas_cfg)
    r = _fail_cancel(client_for(saas_cfg, user), saas_cfg, None)
    forms = post_forms(r.text, "/auth/logout")
    assert forms, "the 400 page keeps the signed-in header with its logout form"
    tokens = [i.attrs.get("value") for i in form_inputs(forms[0]) if i.attrs.get("name") == "csrf"]
    assert tokens and session.verify_csrf(saas_cfg.session_secret, tokens[0], user.id)


# --- T24: sign-in and signed-out visits never get this page (D8, D9) ----------------------

def test_login_callback_failures_get_their_own_page_not_this_one(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = client_for(saas_cfg).get("/auth/callback", params={"error": "access_denied"})
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert by_id(r.text, "gmail-retry") is None
    assert [clean(e.text) for e in elements(r.text) if e.tag == "h1"] == ["Sign-in didn't finish"]


def test_anonymous_gmail_callback_goes_to_login(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = client_for(saas_cfg).get("/auth/gmail-callback", params={"error": "access_denied"})
    assert r.status_code == 302 and r.headers["location"] == "/login"


# --- T21 to T23: the page (needs Jazelei's Step 1 retry note) ----------------------------

def test_cancel_page_says_it_is_okay_and_offers_connect_again(saas_cfg, master_key):
    r = _fail_cancel(client_for(saas_cfg, seed_user(saas_cfg)), saas_cfg, None)
    note = by_id(r.text, "gmail-retry")
    assert note is not None and note.attrs.get("role") == "alert"
    text = clean(note.text)
    assert "That didn't finish, and nothing was changed." in text
    assert "If you tapped Cancel" in text
    assert "tick the box" not in text
    assert 'href="/auth/connect-gmail"' in r.text
    assert "error" not in text.lower()


def test_no_oracle_every_failure_shows_the_identical_note(saas_cfg, master_key, monkeypatch):
    notes = {}
    for i, (kind, trigger) in enumerate(FAILURES.items()):
        with monkeypatch.context() as mp:
            c = client_for(saas_cfg, seed_user(saas_cfg, sub=f"g{i}", email=f"u{i}@x.com"))
            note = by_id(trigger(c, saas_cfg, mp).text, "gmail-retry")
        assert note is not None, kind
        notes[kind] = clean(note.text)
    assert len(set(notes.values())) == 1, notes


def test_activated_user_cancel_page_offers_back_to_dashboard(saas_cfg, master_key):
    user = seed_user(saas_cfg, activated=True, keywords=("va",))
    r = _fail_cancel(client_for(saas_cfg, user), saas_cfg, None)
    assert r.status_code == 400
    back = [a for a in elements(r.text)
            if a.tag == "a" and a.attrs.get("href") == "/dashboard"]
    assert any(clean(a.text) == "Back to dashboard" for a in back)


def test_first_time_user_cancel_page_has_no_back_to_dashboard(saas_cfg, master_key):
    r = _fail_cancel(client_for(saas_cfg, seed_user(saas_cfg)), saas_cfg, None)
    assert "Back to dashboard" not in r.text
