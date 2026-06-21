"""M5 — /health readiness probe (db check + worker staleness)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from applyfirst.saas import db
from applyfirst.saas.app import create_app


def _client(cfg):
    return TestClient(create_app(cfg))


def test_healthz_liveness_unchanged(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    assert _client(saas_cfg).get("/healthz").text == "ok"


def test_health_starting_when_worker_never_ran(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = _client(saas_cfg).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok" and body["worker"] == "starting"


def test_health_ok_when_recent_cycle(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    db.set_worker_meta(conn, "last_cycle_at", db._now_iso())
    conn.close()
    r = _client(saas_cfg).get("/health")
    assert r.status_code == 200 and r.json()["worker"] == "ok"


def test_health_stale_returns_503(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    old = (datetime.now(timezone.utc) - timedelta(seconds=saas_cfg.worker_interval * 10)
           ).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.set_worker_meta(conn, "last_cycle_at", old)
    conn.close()
    r = _client(saas_cfg).get("/health")
    assert r.status_code == 503 and r.json()["worker"] == "stale"
