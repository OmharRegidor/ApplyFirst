"""Google OAuth 2.0 / OIDC — httpx + PyJWT, no Authlib.

Sign-in (M1) requests ``openid email profile``; Connect-Gmail (M2) does a separate
**incremental authorization** for ``gmail.send``. PKCE (S256), ``state`` and ``nonce``
are enforced throughout.

id_token: M2 verifies the RS256 signature against Google's JWKS (PyJWT) and **fails
closed** — a token whose signature cannot be verified is rejected, never accepted. PyJWT
caches the JWKS, so transient Google blips don't lock users out. iss / aud / exp / nonce
/ email_verified are all validated on top of the signature.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from applyfirst.saas.config import SaaSConfig

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
SCOPES = "openid email profile"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
_VALID_ISS = ("https://accounts.google.com", "accounts.google.com")

_jwk_client: PyJWKClient | None = None


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


def build_connect_gmail_url(cfg: SaaSConfig, *, state: str, code_challenge: str) -> str:
    """Incremental-authorization URL for the gmail.send scope (Connect Gmail step).

    `prompt=consent` + `access_type=offline` force Google to return a refresh token even
    on a re-grant; `include_granted_scopes=true` keeps the earlier sign-in grant.
    """
    params = {
        "client_id": cfg.google_client_id or "",
        "redirect_uri": cfg.gmail_redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URI}?{urlencode(params)}"


def exchange_code(cfg: SaaSConfig, *, code: str, code_verifier: str,
                  redirect_uri: str | None = None) -> dict:
    """Exchange the auth code (+ PKCE verifier) for tokens at Google's token endpoint."""
    data = {
        "client_id": cfg.google_client_id or "",
        "client_secret": cfg.google_client_secret or "",
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri or cfg.redirect_uri,
    }
    try:
        resp = httpx.post(TOKEN_URI, data=data, timeout=15)
    except httpx.HTTPError as exc:  # network failure
        raise OAuthError(f"token endpoint unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise OAuthError(f"token exchange failed: {resp.status_code}")
    return resp.json()


def exchange_code_for_gmail(cfg: SaaSConfig, *, code: str, code_verifier: str) -> str:
    """Connect-Gmail callback: exchange the code and return the refresh token.

    Raises if Google omitted the refresh token (re-grant without prompt=consent), so we
    never persist a half-credential we can't refresh later.
    """
    tokens = exchange_code(cfg, code=code, code_verifier=code_verifier,
                           redirect_uri=cfg.gmail_redirect_uri)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise OAuthError("Google did not return a refresh token; please re-grant access")
    return refresh


def revoke_token(token: str) -> None:
    """Best-effort revocation at Google. Local credential is cleared regardless."""
    try:
        httpx.post(REVOKE_URI, data={"token": token}, timeout=10)
    except httpx.HTTPError:
        pass


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


def _signing_key_for(id_token: str):
    """Resolve the RSA public key for this token from Google's JWKS (cached).

    Separated so it is easy to monkeypatch in tests and so a JWKS *fetch* failure
    (network) is distinguishable from a *signature* failure (tampering).
    """
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(JWKS_URI, cache_keys=True)
    return _jwk_client.get_signing_key_from_jwt(id_token).key


def verify_id_token(id_token: str, cfg: SaaSConfig, *, expected_nonce: str) -> dict:
    """Verify the id_token signature (RS256 via JWKS) + claims; return the claims.

    **Fails closed**: if the signing key can't be resolved (JWKS unreachable, unknown
    `kid`) or the signature/claims don't verify, the token is rejected — never accepted
    unverified. This closes the attacker-forceable-degrade bypass.
    """
    try:
        key = _signing_key_for(id_token)
    except Exception as exc:
        raise OAuthError(f"could not resolve id_token signing key: {exc}") from exc

    try:
        claims = jwt.decode(
            id_token, key, algorithms=["RS256"],
            audience=cfg.google_client_id,
            options={"require": ["exp", "iat", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise OAuthError(f"id_token verification failed: {exc}") from exc

    # Re-assert iss / aud / exp / nonce (and gate email_verified later in identity).
    verify_claims(claims, cfg, expected_nonce=expected_nonce)
    return claims


def fetch_identity(cfg: SaaSConfig, *, code: str, code_verifier: str, expected_nonce: str) -> dict:
    """Full callback exchange: code → tokens → signature+claim-verified identity dict.

    Returns ``{"google_sub", "email", "display_name"}``. Raises OAuthError on failure.
    """
    tokens = exchange_code(cfg, code=code, code_verifier=code_verifier)
    id_token = tokens.get("id_token")
    if not id_token:
        raise OAuthError("no id_token in token response")
    claims = verify_id_token(id_token, cfg, expected_nonce=expected_nonce)
    return identity_from_claims(claims)
