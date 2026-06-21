"""Envelope encryption for at-rest secrets — specifically the gmail.send refresh token.

Per-row data key (DEK): each secret is encrypted under its own random AES-256-GCM key;
that DEK is then encrypted under the **master key** (KEK). The DB stores only the
ciphertext, the IV, and the encrypted DEK — never the plaintext secret and never the
master key. A stolen database without the master key is useless.

Master key: loaded once from ``MASTER_KEY_PATH`` (a 0600 file outside the DB, in prod)
or ``APPLYFIRST_MASTER_KEY`` (base64, dev/tests). Must be 32 bytes (AES-256). The
process holds it in memory only.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_LEN = 32   # AES-256
_IV_LEN = 12    # 96-bit nonce, the GCM standard


class CryptoError(Exception):
    """Master-key loading or encrypt/decrypt failure."""


@dataclass(slots=True, frozen=True)
class EnvelopeBlob:
    """What gets persisted. The GCM auth tag is appended inside each ciphertext."""
    ciphertext: bytes      # AESGCM(dek).encrypt(iv, secret)
    iv: bytes              # the DEK's nonce
    encrypted_dek: bytes   # dek_iv(12) || AESGCM(master).encrypt(dek_iv, dek)


def _coerce_key(raw: bytes) -> bytes:
    """Accept either 32 raw bytes or a base64 blob that decodes to 32 bytes."""
    raw = raw.strip()
    if len(raw) == _KEY_LEN:
        return raw
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise CryptoError("master key is neither 32 raw bytes nor valid base64") from exc
    return decoded


def load_master_key() -> bytes:
    """Load the master key from MASTER_KEY_PATH (prod) or APPLYFIRST_MASTER_KEY (dev)."""
    path = os.getenv("MASTER_KEY_PATH")
    if path:
        try:
            with open(path, "rb") as fh:
                key = _coerce_key(fh.read())
        except OSError as exc:
            raise CryptoError(f"cannot read MASTER_KEY_PATH={path!r}: {exc}") from exc
    else:
        b64 = os.getenv("APPLYFIRST_MASTER_KEY")
        if not b64:
            raise CryptoError(
                "no master key configured — set MASTER_KEY_PATH (prod) or "
                "APPLYFIRST_MASTER_KEY (base64, dev). Generate with `openssl rand -base64 32`."
            )
        key = _coerce_key(b64.encode("ascii"))
    if len(key) != _KEY_LEN:
        raise CryptoError(f"master key must be {_KEY_LEN} bytes, got {len(key)}")
    return key


def encrypt_secret(plaintext: bytes, master_key: bytes, aad: bytes | None = None) -> EnvelopeBlob:
    """Envelope-encrypt a secret. Returns the three columns to persist.

    ``aad`` (additional authenticated data, e.g. the owning user_id) binds the ciphertext
    to its context: a blob relocated onto another row fails to decrypt under that row's
    AAD, even with the right master key.
    """
    dek = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(_IV_LEN)
    ciphertext = AESGCM(dek).encrypt(iv, plaintext, aad)

    dek_iv = os.urandom(_IV_LEN)
    encrypted_dek = dek_iv + AESGCM(master_key).encrypt(dek_iv, dek, None)
    return EnvelopeBlob(ciphertext=ciphertext, iv=iv, encrypted_dek=encrypted_dek)


def decrypt_secret(blob: EnvelopeBlob, master_key: bytes, aad: bytes | None = None) -> bytes:
    """Reverse :func:`encrypt_secret`. Raises CryptoError on wrong key / AAD / tampering."""
    dek_iv, enc_dek = blob.encrypted_dek[:_IV_LEN], blob.encrypted_dek[_IV_LEN:]
    try:
        dek = AESGCM(master_key).decrypt(dek_iv, enc_dek, None)
        return AESGCM(dek).decrypt(blob.iv, blob.ciphertext, aad)
    except InvalidTag as exc:
        raise CryptoError("decryption failed — wrong master key, AAD, or tampered data") from exc
