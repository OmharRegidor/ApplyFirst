"""M2 — onboarding state machine + wizard routes + dashboard gating."""

from __future__ import annotations

from fastapi.testclient import TestClient

from applyfirst.saas import db, onboarding, session
from applyfirst.saas.app import create_app


def _client_user(saas_cfg):
    app = create_app(saas_cfg)
    conn = db.init_db(saas_cfg.db_path)
    user = db.upsert_user_by_google(conn, google_sub="g", email="u@x.com", display_name="U")
    conn.close()
    c = TestClient(app, follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(saas_cfg.session_secret, {"uid": user.id}))
    return c, user


def _fill_profile(c):
    return c.post("/onboarding/profile", data={
        "full_name": "Omhar", "job_type": "VA",
        "standard_subject": "VA - Omhar", "standard_message": "Hi!",
    })


def test_onboarding_requires_auth(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    assert c.get("/onboarding").status_code == 401


def test_state_machine_progresses_with_data(saas_cfg):
    conn = db.init_db(saas_cfg.db_path)
    u = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    assert onboarding.next_step(conn, u.id) == "connect_gmail"
    db.upsert_profile(conn, u.id, full_name="A", job_type="VA",
                      standard_subject="S", standard_message="M")
    assert onboarding.next_step(conn, u.id) == "keywords"
    db.add_keyword(conn, u.id, "va")
    assert onboarding.next_step(conn, u.id) == "preview"
    db.set_activated(conn, u.id)
    assert onboarding.next_step(conn, u.id) == "done"
    conn.close()


def test_onboarding_entry_routes_to_connect_gmail_first(saas_cfg):
    c, _ = _client_user(saas_cfg)
    assert c.get("/onboarding").headers["location"] == "/onboarding/connect_gmail"


def test_full_wizard_walk_to_activation(saas_cfg):
    c, _ = _client_user(saas_cfg)
    assert _fill_profile(c).headers["location"] == "/onboarding/keywords"
    assert c.post("/onboarding/keywords", data={"keyword": "virtual assistant"}) \
        .headers["location"] == "/onboarding/keywords"
    assert c.get("/onboarding/preview").status_code == 200
    assert c.post("/onboarding/activate").headers["location"] == "/dashboard"
    assert c.get("/dashboard").status_code == 200  # activated → dashboard renders


def test_profile_post_requires_all_four_fields(saas_cfg):
    c, _ = _client_user(saas_cfg)
    r = c.post("/onboarding/profile", data={
        "full_name": "A", "job_type": "", "standard_subject": "S", "standard_message": "M"})
    assert r.status_code == 302 and "error=1" in r.headers["location"]


def test_keywords_page_redirects_without_profile(saas_cfg):
    c, _ = _client_user(saas_cfg)
    assert c.get("/onboarding/keywords").headers["location"] == "/onboarding/profile"


def test_preview_redirects_without_keywords(saas_cfg):
    c, _ = _client_user(saas_cfg)
    _fill_profile(c)
    assert c.get("/onboarding/preview").headers["location"] == "/onboarding/keywords"


def test_activate_blocked_without_requirements(saas_cfg):
    c, _ = _client_user(saas_cfg)
    assert c.post("/onboarding/activate").headers["location"] == "/onboarding"


def test_dashboard_redirects_to_onboarding_when_not_activated(saas_cfg):
    c, _ = _client_user(saas_cfg)
    assert c.get("/dashboard").headers["location"] == "/onboarding"


def test_keyword_delete_route(saas_cfg):
    c, user = _client_user(saas_cfg)
    _fill_profile(c)
    c.post("/onboarding/keywords", data={"keyword": "va"})
    conn = db.connect(saas_cfg.db_path)
    kw = db.list_keywords(conn, user.id)[0]
    conn.close()
    c.post(f"/onboarding/keywords/{kw.id}/delete")
    conn = db.connect(saas_cfg.db_path)
    assert db.list_keywords(conn, user.id) == []
    conn.close()


def _activate(c):
    _fill_profile(c)
    c.post("/onboarding/keywords", data={"keyword": "va"})
    c.post("/onboarding/activate")


def test_profile_edit_after_activation_keeps_activation(saas_cfg):
    c, user = _client_user(saas_cfg)
    _activate(c)
    conn = db.connect(saas_cfg.db_path)
    activated_at = db.get_profile(conn, user.id).activated_at
    conn.close()
    assert activated_at is not None

    # Edit the profile again through the route — activation must stick.
    c.post("/onboarding/profile", data={
        "full_name": "New Name", "job_type": "VA",
        "standard_subject": "S", "standard_message": "M2"})
    conn = db.connect(saas_cfg.db_path)
    p = db.get_profile(conn, user.id)
    conn.close()
    assert p.activated_at == activated_at      # unchanged
    assert p.full_name == "New Name"           # edit applied
    assert c.get("/dashboard").status_code == 200


def test_delete_all_keywords_after_activation_stays_activated(saas_cfg):
    """Documented behavior: an activated user who removes all keywords stays activated;
    the dashboard renders with an empty watch list (does NOT bounce to onboarding)."""
    c, user = _client_user(saas_cfg)
    _activate(c)
    conn = db.connect(saas_cfg.db_path)
    kw = db.list_keywords(conn, user.id)[0]
    conn.close()
    c.post(f"/onboarding/keywords/{kw.id}/delete")

    assert c.get("/dashboard").status_code == 200   # not bounced
    conn = db.connect(saas_cfg.db_path)
    assert db.list_keywords(conn, user.id) == []
    assert db.get_profile(conn, user.id).is_activated
    conn.close()


def test_preview_escapes_html_in_message(saas_cfg):
    """A <script> in the standard message must be escaped in the rendered preview (XSS)."""
    c, _ = _client_user(saas_cfg)
    c.post("/onboarding/profile", data={
        "full_name": "A", "job_type": "VA", "standard_subject": "S",
        "standard_message": "<script>alert(1)</script>"})
    c.post("/onboarding/keywords", data={"keyword": "va"})
    r = c.get("/onboarding/preview")
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
