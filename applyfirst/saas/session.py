"""Signed cookies + the session helpers — stdlib hmac, no external dependency.

Two signed cookies:
- the **session** cookie: ``{"uid": <user_id>, "iat": <epoch>}`` — who is logged in.
- the **oauth** cookie: ``{"state", "nonce", "verifier", "iat"}`` — the in-flight
  OAuth transaction, set at /auth/login and cleared at /auth/callback. Signed +
  HttpOnly so it is tamper-proof and not reachable from JS; chosen over server-side
  storage so it survives across the multiple uvicorn workers in prod.

Cookie naming: with secure cookies on (prod) we use the ``__Host-`` prefix, which the
browser only honors for Secure, Path=/, host-only cookies — a strong binding. Over
plain http (dev/tests) the prefix is illegal, so we fall back to an unprefixed name.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Request, Response

_SESSION_MAX_AGE = 7 * 24 * 3600     # 7 days
_OAUTH_MAX_AGE = 10 * 60             # 10 minutes — an OAuth round-trip is seconds


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sign(secret: bytes, payload: dict) -> str:
    """Return ``<b64(body)>.<b64(hmac)>``. ``iat`` is stamped if absent."""
    data = dict(payload)
    data.setdefault("iat", int(time.time()))
    body = _b64e(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64e(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def unsign(secret: bytes, token: str | None, max_age: int) -> dict | None:
    """Verify signature + freshness. Returns the payload, or None if invalid."""
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    expected = _b64e(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    iat = payload.get("iat")
    if not isinstance(iat, int) or (int(time.time()) - iat) > max_age or iat > int(time.time()) + 60:
        return None
    return payload


def issue_csrf(secret: bytes, user_id: str) -> str:
    """Mint a synchronizer CSRF token bound to the session user (stateless, signed)."""
    return sign(secret, {"csrf": user_id})


def verify_csrf(secret: bytes, token: str | None, user_id: str) -> bool:
    """True if ``token`` is a fresh signature minted for ``user_id``."""
    payload = unsign(secret, token, _SESSION_MAX_AGE)
    return bool(payload) and payload.get("csrf") == user_id


def _name(base: str, secure: bool) -> str:
    return f"__Host-{base}" if secure else base


def session_cookie_name(secure: bool) -> str:
    return _name("applyfirst_session", secure)


def oauth_cookie_name(secure: bool) -> str:
    return _name("applyfirst_oauth", secure)


def _set(response: Response, name: str, value: str, secure: bool, max_age: int) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )


def set_session(response: Response, secret: bytes, secure: bool, user_id: str) -> None:
    _set(response, session_cookie_name(secure), sign(secret, {"uid": user_id}),
         secure, _SESSION_MAX_AGE)


def clear_session(response: Response, secure: bool) -> None:
    response.delete_cookie(session_cookie_name(secure), path="/")


def read_session(request: Request, secret: bytes, secure: bool) -> str | None:
    """Return the logged-in user_id, or None."""
    token = request.cookies.get(session_cookie_name(secure))
    payload = unsign(secret, token, _SESSION_MAX_AGE)
    uid = payload.get("uid") if payload else None
    return uid if isinstance(uid, str) else None


def set_oauth_txn(response: Response, secret: bytes, secure: bool,
                  *, state: str, nonce: str, verifier: str) -> None:
    _set(response, oauth_cookie_name(secure),
         sign(secret, {"state": state, "nonce": nonce, "verifier": verifier}),
         secure, _OAUTH_MAX_AGE)


def read_oauth_txn(request: Request, secret: bytes, secure: bool) -> dict | None:
    token = request.cookies.get(oauth_cookie_name(secure))
    return unsign(secret, token, _OAUTH_MAX_AGE)


def clear_oauth_txn(response: Response, secure: bool) -> None:
    response.delete_cookie(oauth_cookie_name(secure), path="/")
