"""M2 — id_token RS256 signature verification (PyJWT against Google's JWKS)."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from applyfirst.saas import google_oauth as g


@pytest.fixture
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return priv, pub


def _token(priv_pem, cfg, **over):
    claims = {
        "iss": "https://accounts.google.com", "aud": cfg.google_client_id,
        "exp": int(time.time()) + 600, "iat": int(time.time()), "nonce": "NONCE",
        "sub": "123", "email": "a@x.com", "email_verified": True, "name": "A",
    }
    claims.update(over)
    return jwt.encode(claims, priv_pem, algorithm="RS256")


def test_accepts_valid_signature(saas_cfg, rsa_keys, monkeypatch):
    priv, pub = rsa_keys
    monkeypatch.setattr(g, "_signing_key_for", lambda t: pub)
    claims = g.verify_id_token(_token(priv, saas_cfg), saas_cfg, expected_nonce="NONCE")
    assert claims["sub"] == "123" and claims["email"] == "a@x.com"


def test_rejects_wrong_signing_key(saas_cfg, rsa_keys, monkeypatch):
    priv, _ = rsa_keys
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pub = other.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setattr(g, "_signing_key_for", lambda t: other_pub)
    with pytest.raises(g.OAuthError):
        g.verify_id_token(_token(priv, saas_cfg), saas_cfg, expected_nonce="NONCE")


def test_rejects_bad_nonce(saas_cfg, rsa_keys, monkeypatch):
    priv, pub = rsa_keys
    monkeypatch.setattr(g, "_signing_key_for", lambda t: pub)
    with pytest.raises(g.OAuthError):
        g.verify_id_token(_token(priv, saas_cfg), saas_cfg, expected_nonce="WRONG")


def test_rejects_expired(saas_cfg, rsa_keys, monkeypatch):
    priv, pub = rsa_keys
    monkeypatch.setattr(g, "_signing_key_for", lambda t: pub)
    with pytest.raises(g.OAuthError):
        g.verify_id_token(_token(priv, saas_cfg, exp=int(time.time()) - 10),
                          saas_cfg, expected_nonce="NONCE")


def test_fails_closed_when_signing_key_unresolvable(saas_cfg, rsa_keys, monkeypatch):
    """JWKS unreachable / unknown kid → reject (no attacker-forceable degrade)."""
    priv, _ = rsa_keys

    def jwks_down(_token):
        raise RuntimeError("JWKS endpoint unreachable")

    monkeypatch.setattr(g, "_signing_key_for", jwks_down)
    with pytest.raises(g.OAuthError):
        g.verify_id_token(_token(priv, saas_cfg), saas_cfg, expected_nonce="NONCE")
