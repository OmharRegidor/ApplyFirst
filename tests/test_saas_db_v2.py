"""M2 — v2 data layer: migration, profile upsert + hash, keyword CRUD, gmail token store."""

from __future__ import annotations

from applyfirst.saas import db
from applyfirst.saas.tenant import tenant_scope


def _user(conn):
    return db.upsert_user_by_google(conn, google_sub="g", email="u@x.com", display_name="U")


def test_v2_migration_creates_tables_and_bumps_version(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db._SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "oauth_credentials", "user_profiles", "user_keywords"} <= tables
    finally:
        conn.close()


def test_v1_db_upgrades_to_v2_idempotently(tmp_path):
    path = str(tmp_path / "x.db")
    # Simulate an existing v1 DB.
    conn = db.connect(path)
    db._migrate_v1(conn)
    conn.execute("PRAGMA user_version=1;")
    conn.commit()
    conn.close()

    conn2 = db.init_db(path)  # should apply v2
    try:
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == db._SCHEMA_VERSION
        db.init_db(path).close()  # run again — no error
    finally:
        conn2.close()


def test_v1_to_v2_preserves_existing_rows(tmp_path):
    """Upgrading a POPULATED v1 DB must keep users + oauth rows intact (data survival)."""
    path = str(tmp_path / "x.db")
    conn = db.connect(path)
    db._migrate_v1(conn)
    conn.execute("PRAGMA user_version=1;")
    conn.execute(
        "INSERT INTO users (id, google_sub, email, display_name, plan, created_at) "
        "VALUES ('u1','sub1','a@x.com','A','free','2026-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO oauth_credentials (id, user_id, provider, gmail_scope_granted, updated_at) "
        "VALUES ('c1','u1','google',1,'2026-01-01T00:00:00Z')")
    conn.commit()
    conn.close()

    conn2 = db.init_db(path)  # upgrade v1 → v2
    try:
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == db._SCHEMA_VERSION
        assert conn2.execute("SELECT email FROM users WHERE id='u1'").fetchone()[0] == "a@x.com"
        assert conn2.execute(
            "SELECT gmail_scope_granted FROM oauth_credentials WHERE id='c1'").fetchone()[0] == 1
    finally:
        conn2.close()


def test_profile_upsert_and_hash_changes_on_edit(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _user(conn)
        p1 = db.upsert_profile(conn, u.id, full_name="A", job_type="VA",
                               standard_subject="S", standard_message="M")
        assert p1.is_complete and not p1.is_activated
        p2 = db.upsert_profile(conn, u.id, full_name="A", job_type="VA",
                               standard_subject="S", standard_message="CHANGED")
        assert p2.profile_hash != p1.profile_hash
        assert db.get_profile(conn, u.id).standard_message == "CHANGED"
        # one row per user
        assert conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()[0] == 1
    finally:
        conn.close()


def test_activation_is_sticky(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _user(conn)
        db.upsert_profile(conn, u.id, full_name="A", job_type="VA",
                          standard_subject="S", standard_message="M")
        db.set_activated(conn, u.id)
        first = db.get_profile(conn, u.id).activated_at
        assert first is not None
        # editing the profile must NOT clear activation
        db.upsert_profile(conn, u.id, full_name="A2", job_type="VA",
                          standard_subject="S", standard_message="M")
        assert db.get_profile(conn, u.id).activated_at == first
    finally:
        conn.close()


def test_keyword_crud_and_dedupe(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _user(conn)
        db.add_keyword(conn, u.id, "virtual assistant")
        db.add_keyword(conn, u.id, "virtual assistant")  # dup → ignored
        db.add_keyword(conn, u.id, "  ")                 # blank → ignored
        db.add_keyword(conn, u.id, "data entry")
        kws = db.list_keywords(conn, u.id)
        assert {k.keyword for k in kws} == {"virtual assistant", "data entry"}
        db.delete_keyword(conn, u.id, kws[0].id)
        assert len(db.list_keywords(conn, u.id)) == 1
    finally:
        conn.close()


def test_keyword_delete_is_tenant_scoped(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        a = db.upsert_user_by_google(conn, google_sub="a", email="a@x", display_name="A")
        b = db.upsert_user_by_google(conn, google_sub="b", email="b@x", display_name="B")
        db.add_keyword(conn, a.id, "kw")
        a_kw = db.list_keywords(conn, a.id)[0]
        db.delete_keyword(conn, b.id, a_kw.id)  # B cannot delete A's keyword
        assert len(db.list_keywords(conn, a.id)) == 1
    finally:
        conn.close()


def test_gmail_credential_store_get_clear(tmp_path, master_key):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _user(conn)
        assert db.gmail_connected(conn, u.id) is False
        db.store_gmail_credential(conn, u.id, refresh_token="rt-123", master_key=master_key)
        assert db.gmail_connected(conn, u.id) is True
        assert db.get_gmail_refresh_token(conn, u.id, master_key) == "rt-123"
        # the raw token is NOT stored
        raw = conn.execute(
            "SELECT refresh_token_ciphertext FROM oauth_credentials WHERE user_id=?",
            (u.id,)).fetchone()[0]
        assert b"rt-123" not in raw
        db.clear_gmail_credential(conn, u.id)
        assert db.gmail_connected(conn, u.id) is False
    finally:
        conn.close()


def test_gmail_credential_replaces_not_duplicates(tmp_path, master_key):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        u = _user(conn)
        db.store_gmail_credential(conn, u.id, refresh_token="rt-1", master_key=master_key)
        db.store_gmail_credential(conn, u.id, refresh_token="rt-2", master_key=master_key)
        assert conn.execute(
            "SELECT COUNT(*) FROM oauth_credentials WHERE user_id=? AND provider='google'",
            (u.id,)).fetchone()[0] == 1
        assert db.get_gmail_refresh_token(conn, u.id, master_key) == "rt-2"
    finally:
        conn.close()


def test_profile_and_keywords_are_tenant_scoped_tables():
    assert {"user_profiles", "user_keywords"} <= db.TENANT_TABLES


def test_tenant_scope_reaches_profile_rows(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        a = db.upsert_user_by_google(conn, google_sub="a", email="a@x", display_name="A")
        b = db.upsert_user_by_google(conn, google_sub="b", email="b@x", display_name="B")
        db.upsert_profile(conn, a.id, full_name="A", job_type="VA",
                          standard_subject="S", standard_message="M")
        a_pid = conn.execute("SELECT id FROM user_profiles WHERE user_id=?", (a.id,)).fetchone()[0]
        with tenant_scope(conn, b.id) as scope:
            assert scope.fetch_by_id("user_profiles", a_pid) is None  # B can't see A's profile
        with tenant_scope(conn, a.id) as scope:
            assert scope.fetch_by_id("user_profiles", a_pid) is not None
    finally:
        conn.close()
