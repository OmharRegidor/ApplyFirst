"""Google OAuth 2.0 / OIDC sign-in — httpx + stdlib, no Authlib.

M1 requests only ``openid email profile`` (NO gmail.send — that is M2's incremental
authorization). PKCE (S256), ``state`` and ``nonce`` are all enforced.

We trust the ``id_token`` without fetching Google's JWKS because it is delivered
**server-to-server** from Google's token endpoint over TLS (not through the browser),
so a local RSA signature check adds little; we still validate iss / aud / exp / nonce.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx

from applyfirst.saas.config import SaaSConfig

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = "openid email profile"
_VALID_ISS = ("https://accounts.google.com", "accounts.google.com")


class OAuthError(Exception):
    """Raised when the OAuth exchange or claim validation fails."""


def _b64url_nopad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_state() -> str:
    return secrets.token_hex(32)


def make_nonce() -> str:
    return secrets.token_hex(32)


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url_nopad(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_auth_url(cfg: SaaSConfig, *, state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": cfg.google_client_id or "",
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{AUTH_URI}?{urlencode(params)}"


def exchange_code(cfg: SaaSConfig, *, code: str, code_verifier: str) -> dict:
    """Exchange the auth code (+ PKCE verifier) for tokens at Google's token endpoint."""
    data = {
        "client_id": cfg.google_client_id or "",
        "client_secret": cfg.google_client_secret or "",
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": cfg.redirect_uri,
    }
    try:
        resp = httpx.post(TOKEN_URI, data=data, timeout=15)
    except httpx.HTTPError as exc:  # network failure
        raise OAuthError(f"token endpoint unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise OAuthError(f"token exchange failed: {resp.status_code}")
    return resp.json()


def parse_id_token(id_token: str) -> dict:
    """Decode the JWT payload (claims). Does not verify the RSA signature (see module doc)."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise OAuthError("malformed id_token")
    try:
        return json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise OAuthError("undecodable id_token payload") from exc


def verify_claims(claims: dict, cfg: SaaSConfig, *, expected_nonce: str) -> None:
    """Validate iss / aud / exp / nonce. Raises OAuthError on any mismatch."""
    if claims.get("iss") not in _VALID_ISS:
        raise OAuthError("bad issuer")
    # Fail closed if no client_id is configured — never let a token with a missing
    # `aud` slip through because both sides happen to be None.
    if not cfg.google_client_id or claims.get("aud") != cfg.google_client_id:
        raise OAuthError("bad audience")
    exp = claims.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise OAuthError("id_token expired")
    if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise OAuthError("nonce mismatch")


def identity_from_claims(claims: dict) -> dict:
    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise OAuthError("id_token missing sub/email")
    # Google may return unverified emails for some account types; we route mail by
    # this address in M2, so treat an unverified email as untrusted.
    if claims.get("email_verified") not in (True, "true"):
        raise OAuthError("email not verified")
    return {"google_sub": sub, "email": email, "display_name": claims.get("name")}


def fetch_identity(cfg: SaaSConfig, *, code: str, code_verifier: str, expected_nonce: str) -> dict:
    """Full callback exchange: code → tokens → validated identity dict.

    Returns ``{"google_sub", "email", "display_name"}``. Raises OAuthError on failure.
    """
    tokens = exchange_code(cfg, code=code, code_verifier=code_verifier)
    id_token = tokens.get("id_token")
    if not id_token:
        raise OAuthError("no id_token in token response")
    claims = parse_id_token(id_token)
    verify_claims(claims, cfg, expected_nonce=expected_nonce)
    return identity_from_claims(claims)
