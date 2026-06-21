"""M1 — Google OAuth helpers: PKCE, auth URL, id_token parse + claim validation."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from applyfirst.saas import google_oauth as g


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _make_id_token(claims: dict) -> str:
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(claims).encode())
    return f"{header}.{body}.signature-not-verified"


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = g.make_pkce()
    expected = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    assert challenge == expected
    assert "=" not in challenge  # no padding


def test_state_and_nonce_are_unique_and_long():
    assert g.make_state() != g.make_state()
    assert len(g.make_nonce()) >= 32


def test_build_auth_url_has_required_params(saas_cfg):
    url = g.build_auth_url(saas_cfg, state="st", nonce="no", code_challenge="ch")
    qs = parse_qs(urlparse(url).query)
    assert qs["client_id"] == ["test-client-id"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["openid email profile"]
    assert "gmail" not in qs["scope"][0]            # NO gmail.send in M1
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["code_challenge"] == ["ch"]
    assert qs["state"] == ["st"]
    assert qs["nonce"] == ["no"]
    assert qs["redirect_uri"] == ["https://localhost:8000/auth/callback"]


def test_parse_id_token_roundtrip():
    claims = {"sub": "123", "email": "a@x.com", "name": "Al"}
    assert g.parse_id_token(_make_id_token(claims))["sub"] == "123"


def test_parse_id_token_rejects_malformed():
    with pytest.raises(g.OAuthError):
        g.parse_id_token("only.two")


def _valid_claims(cfg, **over):
    base = {
        "iss": "https://accounts.google.com",
        "aud": cfg.google_client_id,
        "exp": int(time.time()) + 600,
        "nonce": "expected-nonce",
        "sub": "123",
        "email": "a@x.com",
        "name": "Al",
    }
    base.update(over)
    return base


def test_verify_claims_accepts_valid(saas_cfg):
    g.verify_claims(_valid_claims(saas_cfg), saas_cfg, expected_nonce="expected-nonce")


def test_verify_claims_rejects_bad_audience(saas_cfg):
    with pytest.raises(g.OAuthError):
        g.verify_claims(_valid_claims(saas_cfg, aud="someone-else"), saas_cfg,
                        expected_nonce="expected-nonce")


def test_verify_claims_rejects_bad_nonce(saas_cfg):
    with pytest.raises(g.OAuthError):
        g.verify_claims(_valid_claims(saas_cfg), saas_cfg, expected_nonce="WRONG")


def test_verify_claims_rejects_expired(saas_cfg):
    with pytest.raises(g.OAuthError):
        g.verify_claims(_valid_claims(saas_cfg, exp=int(time.time()) - 1), saas_cfg,
                        expected_nonce="expected-nonce")


def test_verify_claims_rejects_bad_issuer(saas_cfg):
    with pytest.raises(g.OAuthError):
        g.verify_claims(_valid_claims(saas_cfg, iss="https://evil.example"), saas_cfg,
                        expected_nonce="expected-nonce")


def test_verify_claims_rejects_when_client_id_unset(saas_cfg):
    import dataclasses
    cfg = dataclasses.replace(saas_cfg, google_client_id=None)
    # aud None + client_id None must NOT pass (fail-closed).
    with pytest.raises(g.OAuthError):
        g.verify_claims(_valid_claims(saas_cfg, aud=None), cfg, expected_nonce="expected-nonce")


def test_identity_from_claims_requires_sub_and_email(saas_cfg):
    with pytest.raises(g.OAuthError):
        g.identity_from_claims({"sub": "123", "email_verified": True})  # no email


def test_identity_from_claims_ok_with_verified_email():
    out = g.identity_from_claims(
        {"sub": "1", "email": "a@x.com", "email_verified": True, "name": "A"})
    assert out == {"google_sub": "1", "email": "a@x.com", "display_name": "A"}


def test_identity_from_claims_rejects_unverified_email():
    with pytest.raises(g.OAuthError):
        g.identity_from_claims({"sub": "1", "email": "a@x.com", "email_verified": False})
