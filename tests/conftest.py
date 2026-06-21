"""Shared pytest fixtures."""

from __future__ import annotations

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
