"""Tests for run-loop heartbeat / health staleness logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from applyfirst.health import health_status, parse_iso


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_fresh_heartbeat_is_ok():
    now = _utc(2026, 1, 1, 12, 0, 0)
    r = health_status(now - timedelta(seconds=100), now, max_stale_seconds=600)
    assert r["ok"] is True
    assert "healthy" in r["message"]


def test_stale_heartbeat_is_not_ok():
    now = _utc(2026, 1, 1, 12, 0, 0)
    r = health_status(now - timedelta(seconds=1200), now, max_stale_seconds=600)
    assert r["ok"] is False
    assert "STALE" in r["message"]


def test_never_run_is_not_ok():
    r = health_status(None, _utc(2026, 1, 1), max_stale_seconds=600)
    assert r["ok"] is False


def test_parse_iso_roundtrip_and_garbage():
    assert parse_iso("2026-01-01 12:00:00") == _utc(2026, 1, 1, 12, 0, 0)
    assert parse_iso(None) is None
    assert parse_iso("not a date") is None
