"""Shared pytest fixtures."""

from __future__ import annotations

import base64
import os

import pytest

from applyfirst.saas.config import SaaSConfig


@pytest.fixture
def saas_cfg(tmp_path) -> SaaSConfig:
    """A SaaS config wired to a temp DB with insecure cookies (http TestClient)."""
    return SaaSConfig(
        db_path=str(tmp_path / "saas.db"),
        google_client_id="test-client-id",
        google_client_secret="test-secret",
        session_secret=b"unit-test-session-secret-32-bytes!!",
        base_url="https://localhost:8000",
        secure_cookies=False,  # http TestClient can't carry __Host-/Secure cookies
    )


@pytest.fixture
def master_key(monkeypatch) -> bytes:
    """A 32-byte master key, exposed both as a value and via APPLYFIRST_MASTER_KEY env."""
    key = os.urandom(32)
    monkeypatch.setenv("APPLYFIRST_MASTER_KEY", base64.b64encode(key).decode("ascii"))
    monkeypatch.delenv("MASTER_KEY_PATH", raising=False)
    return key
