"""Connect Gmail only counts when Google really granted gmail.send (unticked box = retry)."""

from __future__ import annotations

import logging

import pytest

from applyfirst.saas import db, google_oauth
from _saas_client import (
    by_id, clean, client_for, db_conn, gmail_callback, is_connected, seed_user,
    txn_cookie_cleared,
)

GRANTED = ("openid https://www.googleapis.com/auth/userinfo.email "
           f"{google_oauth.GMAIL_SCOPE} https://www.googleapis.com/auth/userinfo.profile")
NOT_GRANTED = "openid https://www.googleapis.com/auth/userinfo.email"


def _tokens(monkeypatch, **resp):
    """Fake Google's token endpoint; the real scope check in exchange_code_for_gmail runs."""
    monkeypatch.setattr(google_oauth, "exchange_code", lambda cfg, **kw: dict(resp))


# --- T14 / T15: the OAuth helper ------------------------------------------------------------

@pytest.mark.parametrize("scope", [
    NOT_GRANTED,
    None,                                                  # field missing: fail closed
    "",
    "https://www.googleapis.com/auth/gmail.sendx",         # near misses do not count
    "gmail.send",
    google_oauth.GMAIL_SCOPE.upper(),
])
def test_exchange_rejects_a_grant_without_gmail_send(saas_cfg, monkeypatch, scope):
    resp = {"refresh_token": "rt"}
    if scope is not None:
        resp["scope"] = scope
    _tokens(monkeypatch, **resp)
    with pytest.raises(google_oauth.GmailScopeError):
        google_oauth.exchange_code_for_gmail(saas_cfg, code="c", code_verifier="v")


def test_granted_scopes_parses_the_space_separated_field():
    assert google_oauth.granted_scopes({"scope": f"openid  {google_oauth.GMAIL_SCOPE}"}) == \
        frozenset({"openid", google_oauth.GMAIL_SCOPE})
    assert google_oauth.granted_scopes({"scope": ["not", "a", "string"]}) == frozenset()
    assert google_oauth.granted_scopes({}) == frozenset()


def test_exchange_returns_refresh_token_when_granted(saas_cfg, monkeypatch):
    _tokens(monkeypatch, refresh_token="rt", scope=GRANTED)
    assert google_oauth.exchange_code_for_gmail(saas_cfg, code="c", code_verifier="v") == "rt"


def test_missing_refresh_token_is_still_a_plain_oauth_error(saas_cfg, monkeypatch):
    _tokens(monkeypatch, scope=GRANTED)
    with pytest.raises(google_oauth.OAuthError) as exc:
        google_oauth.exchange_code_for_gmail(saas_cfg, code="c", code_verifier="v")
    assert not isinstance(exc.value, google_oauth.GmailScopeError)


def test_scope_is_checked_before_the_refresh_token(saas_cfg, monkeypatch):
    _tokens(monkeypatch, scope=NOT_GRANTED)                    # neither scope nor refresh token
    with pytest.raises(google_oauth.GmailScopeError):
        google_oauth.exchange_code_for_gmail(saas_cfg, code="c", code_verifier="v")


# --- T16 to T19: the callback route ----------------------------------------------------------

def test_first_time_user_without_send_scope_is_asked_again(saas_cfg, master_key, monkeypatch,
                                                           caplog):
    user = seed_user(saas_cfg)
    c = client_for(saas_cfg, user)
    _tokens(monkeypatch, refresh_token="rt-secret-xyz", scope=NOT_GRANTED)
    with caplog.at_level(logging.WARNING, logger="applyfirst.saas.app"):
        r = gmail_callback(c)
    assert r.status_code == 302
    assert r.headers["location"] == "/onboarding/connect_gmail?gmail_error=scope"
    assert txn_cookie_cleared(r)
    assert is_connected(saas_cfg, user) is False
    logged = [rec for rec in caplog.records if rec.getMessage() == "gmail_scope_missing"]
    assert len(logged) == 1
    fields = str(logged[0].fields)
    assert "userinfo.email" in fields and "rt-secret-xyz" not in fields


def test_scope_retry_note_on_step_one(saas_cfg, master_key):
    """T16 page half: needs Jazelei's gmail_retry_note on Step 1."""
    c = client_for(saas_cfg, seed_user(saas_cfg))
    page = c.get("/onboarding/connect_gmail?gmail_error=scope")
    assert page.status_code == 200
    note = by_id(page.text, "gmail-retry")
    assert note is not None and note.attrs.get("role") == "alert"
    assert note.attrs.get("tabindex") == "-1"
    assert "tick the box" in clean(note.text)
    assert "Your earlier Gmail connection still works." not in page.text
    assert 'href="/auth/connect-gmail"' in page.text


def test_activated_user_without_send_scope_lands_on_the_dashboard(saas_cfg, master_key,
                                                                  monkeypatch):
    user = seed_user(saas_cfg, activated=True, keywords=("va",))
    c = client_for(saas_cfg, user)
    _tokens(monkeypatch, refresh_token="rt", scope=NOT_GRANTED)
    r = gmail_callback(c)
    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard?gmail_error=scope"
    assert txn_cookie_cleared(r)
    assert is_connected(saas_cfg, user) is False


def test_scope_retry_note_on_the_dashboard(saas_cfg, master_key):
    """T17 page half: needs Jazelei's dashboard (note above the gmail status panel)."""
    c = client_for(saas_cfg, seed_user(saas_cfg, activated=True, keywords=("va",)))
    page = c.get("/dashboard?gmail_error=scope")
    assert page.status_code == 200
    note = by_id(page.text, "gmail-retry")
    assert note is not None and "tick the box" in clean(note.text)
    assert 'data-panel="gmail"' in page.text
    assert 'href="/auth/connect-gmail"' in page.text
    assert page.text.index('id="gmail-retry"') < page.text.index("data-panel=")


def test_failed_reconnect_keeps_the_working_grant(saas_cfg, master_key, monkeypatch):
    user = seed_user(saas_cfg, gmail_key=master_key)             # stores "rt-old"
    c = client_for(saas_cfg, user)
    _tokens(monkeypatch, refresh_token="rt-new", scope=NOT_GRANTED)
    assert gmail_callback(c).headers["location"] == "/onboarding/connect_gmail?gmail_error=scope"
    with db_conn(saas_cfg) as conn:
        assert db.get_gmail_refresh_token(conn, user.id, master_key) == "rt-old"


def test_retry_note_tells_a_connected_user_the_old_grant_still_works(saas_cfg, master_key):
    """T18 page half: needs Jazelei's gmail_retry_note(kind, connected=true)."""
    c = client_for(saas_cfg, seed_user(saas_cfg, gmail_key=master_key))
    note = by_id(c.get("/onboarding/connect_gmail?gmail_error=scope").text, "gmail-retry")
    assert note is not None
    assert "Your earlier Gmail connection still works." in clean(note.text)


def test_callback_with_send_scope_stores_the_token_encrypted(saas_cfg, master_key, monkeypatch):
    user = seed_user(saas_cfg)
    c = client_for(saas_cfg, user)
    _tokens(monkeypatch, refresh_token="rt-real", scope=GRANTED)
    r = gmail_callback(c)
    assert r.status_code == 302 and r.headers["location"] == "/onboarding"
    with db_conn(saas_cfg) as conn:
        assert db.gmail_connected(conn, user.id) is True
        assert db.get_gmail_refresh_token(conn, user.id, master_key) == "rt-real"
        raw = conn.execute("SELECT refresh_token_ciphertext FROM oauth_credentials "
                           "WHERE user_id=?", (user.id,)).fetchone()[0]
        assert b"rt-real" not in raw


# --- T20: flag hygiene -------------------------------------------------------------------

@pytest.mark.parametrize("query", ["gmail_error=Scope", "gmail_error=failed",
                                   "gmail_error=%3Cscript%3Ezq9x%3C%2Fscript%3E",
                                   "error=scope", "gmail_error=scope%20", ""])
@pytest.mark.parametrize("path", ["/onboarding/connect_gmail", "/dashboard"])
def test_only_the_exact_scope_flag_shows_a_note_and_nothing_is_reflected(saas_cfg, path, query):
    c = client_for(saas_cfg, seed_user(saas_cfg, activated=True, keywords=("va",)))
    page = c.get(f"{path}?{query}")
    assert page.status_code == 200
    assert by_id(page.text, "gmail-retry") is None
    assert "tick the box" not in page.text and "If you tapped Cancel" not in page.text
    assert "zq9x" not in page.text                     # the raw value is never rendered
