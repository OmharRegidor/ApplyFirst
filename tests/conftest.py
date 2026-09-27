"""Shared pytest fixtures."""

from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta

import pytest

from applyfirst.saas import db
from applyfirst.saas.config import SaaSConfig

_STAMP = "%Y-%m-%dT%H:%M:%SZ"


class Clock:
    """The SaaS clock (``db._now_iso``), moved by hand. Set ``now``, or ``tick()`` it on."""

    def __init__(self, now: str) -> None:
        self.now = now

    def tick(self, minutes: int = 1) -> str:
        later = datetime.strptime(self.now, _STAMP) + timedelta(minutes=minutes)
        self.now = later.strftime(_STAMP)
        return self.now


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


@pytest.fixture
def clock(monkeypatch) -> Clock:
    """SaaS time held still until the test moves it. Timestamps are to the second, and the worker
    sends a user only jobs first stored after they started, so a job that should count as new must
    be found a tick later than the user started and the term's first search."""
    c = Clock("2026-09-27T01:00:00Z")
    monkeypatch.setattr(db, "_now_iso", lambda: c.now)
    return c
