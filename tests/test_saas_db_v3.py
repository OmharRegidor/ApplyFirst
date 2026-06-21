"""M3 — v3 data layer: migration, job dedupe, fan-out, atomic cap, cache, baseline."""

from __future__ import annotations

from applyfirst.saas import db


def _activated_user(conn, sub="g", email="u@x"):
    u = db.upsert_user_by_google(conn, google_sub=sub, email=email, display_name="U")
    db.upsert_profile(conn, u.id, full_name="A", job_type="VA",
                      standard_subject="S", standard_message="M")
    db.set_activated(conn, u.id)
    return u


def _job(conn, ext="1"):
    return db.insert_job(conn, onlinejobs_id=ext, title="T", url="u",
                         employment_type=None, salary_text=None, posted_at=None,
                         raw_description="d")


def test_v3_migration_creates_tables(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"jobs", "user_job_alerts", "ai_usage", "tailoring_cache",
                "worker_keyword_state", "worker_meta"} <= tables
    finally:
        conn.close()


def test_insert_job_dedupes_by_onlinejobs_id(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        a = db.insert_job(conn, onlinejobs_id="111", title="First", url="u",
                          employment_type=None, salary_text=None, posted_at=None,
                          raw_description="d")
        b = db.insert_job(conn, onlinejobs_id="111", title="Second", url="u2",
                          employment_type=None, salary_text=None, posted_at=None,
                          raw_description="d2")
        assert a == b
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert db.get_job(conn, a).title == "First"   # first write wins (DO NOTHING)
    finally:
        conn.close()


def test_active_keywords_only_activated_subscribers(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _activated_user(conn, "a", "a@x")
        db.add_keyword(conn, u.id, "va")
        # an UN-activated user's keyword must not be polled
        u2 = db.upsert_user_by_google(conn, google_sub="b", email="b@x", display_name="B")
        db.upsert_profile(conn, u2.id, full_name="B", job_type="X",
                          standard_subject="S", standard_message="M")
        db.add_keyword(conn, u2.id, "ghost")
        assert db.active_keywords_all(conn) == ["va"]
        assert db.users_for_keyword(conn, "va") == [u.id]
        assert db.users_for_keyword(conn, "ghost") == []
    finally:
        conn.close()


def test_alert_fanout_dedupe(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _activated_user(conn)
        jid = _job(conn)
        db.insert_alert(conn, u.id, jid, "va")
        db.insert_alert(conn, u.id, jid, "va")   # same (user, job) → ignored
        assert conn.execute("SELECT COUNT(*) FROM user_job_alerts").fetchone()[0] == 1
        assert len(db.pending_alerts(conn)) == 1
    finally:
        conn.close()


def test_daily_cap_is_atomic_and_bounded(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _activated_user(conn)
        assert db.try_increment_ai_usage(conn, u.id, 2) is True
        assert db.try_increment_ai_usage(conn, u.id, 2) is True
        assert db.try_increment_ai_usage(conn, u.id, 2) is False   # capped at 2
        assert conn.execute("SELECT tailoring_calls FROM ai_usage").fetchone()[0] == 2
        assert db.try_increment_ai_usage(conn, u.id, 0) is False    # cap 0 → always False
    finally:
        conn.close()


def test_tailoring_cache_roundtrip(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        jid = _job(conn)
        assert db.cache_get(conn, jid, "hash") is None
        db.cache_put(conn, jid, "hash", '{"cover_letter":"x"}', "gemini")
        got = db.cache_get(conn, jid, "hash")
        assert got["package_json"] == '{"cover_letter":"x"}'
        assert got["provider"] == "gemini"
    finally:
        conn.close()


def test_keyword_baseline_is_sticky(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert db.is_keyword_baselined(conn, "va") is False
        db.mark_keyword_polled(conn, "va", baselined=True)
        assert db.is_keyword_baselined(conn, "va") is True
        db.mark_keyword_polled(conn, "va", baselined=False)   # later polls keep the baseline
        assert db.is_keyword_baselined(conn, "va") is True
    finally:
        conn.close()


def test_worker_meta_roundtrip(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert db.get_worker_meta(conn, "k") is None
        db.set_worker_meta(conn, "k", "v1")
        db.set_worker_meta(conn, "k", "v2")
        assert db.get_worker_meta(conn, "k") == "v2"
    finally:
        conn.close()


def test_alerts_and_ai_usage_are_tenant_scoped():
    assert {"user_job_alerts", "ai_usage"} <= db.TENANT_TABLES
    assert "jobs" not in db.TENANT_TABLES            # cross-tenant pool, no user_id
    assert "tailoring_cache" not in db.TENANT_TABLES  # internal worker cache


def test_v2_to_v3_preserves_existing_rows(tmp_path):
    """Upgrading a POPULATED v2 DB to v3 must keep users/profiles/keywords intact."""
    path = str(tmp_path / "x.db")
    conn = db.connect(path)
    db._migrate_v1(conn)
    db._migrate_v2(conn)
    conn.execute("PRAGMA user_version=2;")
    conn.execute("INSERT INTO users (id, google_sub, email, display_name, plan, created_at) "
                 "VALUES ('u1','s1','a@x','A','free','2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO user_profiles (id, user_id, full_name, job_type, "
                 "standard_subject, standard_message, updated_at) "
                 "VALUES ('p1','u1','A','VA','S','M','2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO user_keywords (id, user_id, keyword, is_active, created_at) "
                 "VALUES ('k1','u1','va',1,'2026-01-01T00:00:00Z')")
    conn.commit()
    conn.close()

    conn2 = db.init_db(path)  # upgrade v2 → v3
    try:
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn2.execute("SELECT email FROM users WHERE id='u1'").fetchone()[0] == "a@x"
        assert conn2.execute(
            "SELECT keyword FROM user_keywords WHERE id='k1'").fetchone()[0] == "va"
    finally:
        conn2.close()
