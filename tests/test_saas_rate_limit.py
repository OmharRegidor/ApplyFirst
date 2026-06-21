"""M5 — DB-backed fixed-window rate limiting on /auth/*."""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from applyfirst.saas import db
from applyfirst.saas.app import create_app


def test_record_auth_hit_allows_then_blocks(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    assert [db.record_auth_hit(conn, "1.2.3.4", 3, 60) for _ in range(3)] == [True, True, True]
    assert db.record_auth_hit(conn, "1.2.3.4", 3, 60) is False
    # a different IP has its own bucket
    assert db.record_auth_hit(conn, "5.6.7.8", 3, 60) is True
    conn.close()


def test_record_auth_hit_window_resets(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    assert db.record_auth_hit(conn, "ip", 1, 60, now=1000.0) is True
    assert db.record_auth_hit(conn, "ip", 1, 60, now=1000.0) is False   # same window
    assert db.record_auth_hit(conn, "ip", 1, 60, now=1060.0) is True    # next window
    conn.close()


def test_record_auth_hit_disabled_when_limit_zero(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    assert all(db.record_auth_hit(conn, "ip", 0, 60) for _ in range(50))
    conn.close()


def test_auth_endpoint_is_rate_limited(saas_cfg):
    cfg = dataclasses.replace(saas_cfg, auth_rate_limit=3, auth_rate_window=60)
    c = TestClient(create_app(cfg), follow_redirects=False)
    hdr = {"X-Forwarded-For": "9.9.9.9"}
    for _ in range(3):
        assert c.get("/auth/login", headers=hdr).status_code == 302
    assert c.get("/auth/login", headers=hdr).status_code == 429
    # a different forwarded IP is unaffected
    assert c.get("/auth/login", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 302


def test_non_auth_paths_are_not_rate_limited(saas_cfg):
    cfg = dataclasses.replace(saas_cfg, auth_rate_limit=1)
    c = TestClient(create_app(cfg), follow_redirects=False)
    for _ in range(5):
        assert c.get("/healthz").status_code == 200


def test_limiter_keys_on_last_xff_hop_not_spoofable(saas_cfg):
    """Caddy APPENDS the real peer to XFF; the limiter must key on the LAST hop, so a client
    rotating the (forged) first hop cannot mint a fresh bucket per request."""
    cfg = dataclasses.replace(saas_cfg, auth_rate_limit=3, auth_rate_window=60)
    c = TestClient(create_app(cfg), follow_redirects=False)
    for i in range(3):
        # forged first hop varies; the real (last) hop is fixed at 5.5.5.5
        assert c.get("/auth/login",
                     headers={"X-Forwarded-For": f"9.9.9.{i}, 5.5.5.5"}).status_code == 302
    # 4th from the same real IP is still blocked despite a brand-new forged first hop
    assert c.get("/auth/login",
                 headers={"X-Forwarded-For": "1.2.3.4, 5.5.5.5"}).status_code == 429
    # a genuinely different real (last) hop has its own bucket
    assert c.get("/auth/login",
                 headers={"X-Forwarded-For": "1.2.3.4, 6.6.6.6"}).status_code == 302


def test_limiter_fails_closed_when_store_unavailable(saas_cfg):
    """If the rate-limit table is gone, /auth/* returns 503 (fail closed), never fail-open 200."""
    cfg = dataclasses.replace(saas_cfg, auth_rate_limit=3)
    app = create_app(cfg)                       # creates auth_rate_hits via migration
    conn = db.connect(cfg.db_path)
    conn.execute("DROP TABLE auth_rate_hits")
    conn.commit()
    conn.close()
    c = TestClient(app, follow_redirects=False)
    assert c.get("/auth/login", headers={"X-Forwarded-For": "9.9.9.9"}).status_code == 503
