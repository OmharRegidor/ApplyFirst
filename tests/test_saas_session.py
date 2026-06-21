"""M1 — signed-cookie session: roundtrip, tamper, expiry, future-dating."""

from __future__ import annotations

import time

from applyfirst.saas import session

_SECRET = b"session-secret-for-tests-32bytes!"


def test_sign_unsign_roundtrip():
    tok = session.sign(_SECRET, {"uid": "user-123"})
    payload = session.unsign(_SECRET, tok, max_age=3600)
    assert payload is not None
    assert payload["uid"] == "user-123"
    assert isinstance(payload["iat"], int)


def test_tampered_body_rejected():
    tok = session.sign(_SECRET, {"uid": "user-123"})
    body, _, sig = tok.partition(".")
    forged = session.sign(_SECRET, {"uid": "attacker"}).partition(".")[0]
    assert session.unsign(_SECRET, f"{forged}.{sig}", 3600) is None


def test_wrong_secret_rejected():
    tok = session.sign(_SECRET, {"uid": "u"})
    assert session.unsign(b"a-different-secret-of-the-rightlen", tok, 3600) is None


def test_expired_rejected():
    old = {"uid": "u", "iat": int(time.time()) - 10_000}
    tok = session.sign(_SECRET, old)
    assert session.unsign(_SECRET, tok, max_age=3600) is None


def test_future_iat_rejected():
    future = {"uid": "u", "iat": int(time.time()) + 10_000}
    tok = session.sign(_SECRET, future)
    assert session.unsign(_SECRET, tok, max_age=3600) is None


def test_garbage_token_rejected():
    assert session.unsign(_SECRET, None, 3600) is None
    assert session.unsign(_SECRET, "not-a-token", 3600) is None
    assert session.unsign(_SECRET, "a.b.c", 3600) is None


def test_cookie_name_prefix_depends_on_secure():
    assert session.session_cookie_name(True).startswith("__Host-")
    assert not session.session_cookie_name(False).startswith("__Host-")
