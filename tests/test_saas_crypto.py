"""M2 — envelope encryption: round-trip, tamper, wrong key, master-key loading."""

from __future__ import annotations

import base64
import os

import pytest

from applyfirst.saas import crypto


def test_envelope_roundtrip():
    mk = os.urandom(32)
    blob = crypto.encrypt_secret(b"refresh-token-xyz", mk)
    assert crypto.decrypt_secret(blob, mk) == b"refresh-token-xyz"
    # The plaintext must not appear in any stored field.
    assert b"refresh-token-xyz" not in blob.ciphertext
    assert b"refresh-token-xyz" not in blob.encrypted_dek


def test_each_encryption_uses_a_fresh_dek_and_iv():
    mk = os.urandom(32)
    a = crypto.encrypt_secret(b"same", mk)
    b = crypto.encrypt_secret(b"same", mk)
    assert a.ciphertext != b.ciphertext      # different DEK+IV → different ciphertext
    assert a.encrypted_dek != b.encrypted_dek


def test_aad_binds_blob_to_context():
    """A blob encrypted under one AAD (e.g. user A) must not decrypt under another."""
    mk = os.urandom(32)
    blob = crypto.encrypt_secret(b"token", mk, aad=b"user-A")
    assert crypto.decrypt_secret(blob, mk, aad=b"user-A") == b"token"
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_secret(blob, mk, aad=b"user-B")   # relocated to another row
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_secret(blob, mk)                  # no AAD at all


def test_wrong_master_key_fails():
    blob = crypto.encrypt_secret(b"secret", os.urandom(32))
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_secret(blob, os.urandom(32))


def test_tampered_ciphertext_fails():
    mk = os.urandom(32)
    blob = crypto.encrypt_secret(b"secret", mk)
    tampered = crypto.EnvelopeBlob(
        ciphertext=blob.ciphertext[:-1] + bytes([blob.ciphertext[-1] ^ 0x01]),
        iv=blob.iv, encrypted_dek=blob.encrypted_dek,
    )
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_secret(tampered, mk)


def test_load_master_key_from_env(monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("APPLYFIRST_MASTER_KEY", base64.b64encode(key).decode())
    monkeypatch.delenv("MASTER_KEY_PATH", raising=False)
    assert crypto.load_master_key() == key


def test_load_master_key_from_file(monkeypatch, tmp_path):
    key = os.urandom(32)
    p = tmp_path / "master.key"
    p.write_bytes(base64.b64encode(key))
    monkeypatch.setenv("MASTER_KEY_PATH", str(p))
    assert crypto.load_master_key() == key


def test_load_master_key_missing_raises(monkeypatch):
    monkeypatch.delenv("APPLYFIRST_MASTER_KEY", raising=False)
    monkeypatch.delenv("MASTER_KEY_PATH", raising=False)
    with pytest.raises(crypto.CryptoError):
        crypto.load_master_key()


def test_load_master_key_wrong_length_raises(monkeypatch):
    monkeypatch.setenv("APPLYFIRST_MASTER_KEY", base64.b64encode(os.urandom(16)).decode())
    monkeypatch.delenv("MASTER_KEY_PATH", raising=False)
    with pytest.raises(crypto.CryptoError):
        crypto.load_master_key()
