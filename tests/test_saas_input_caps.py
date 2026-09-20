"""Server-side length caps on the profile and keyword forms (the maxlength is only a hint)."""

from __future__ import annotations

import pytest

from applyfirst.saas import app as app_module
from applyfirst.saas import db
from _saas_client import PROFILE, client_for, db_conn, saved_profile, seed_user

CAPS = [("full_name", 80), ("job_type", 80), ("standard_subject", 150),
        ("standard_message", 5000)]


def _client(cfg):
    user = seed_user(cfg)
    return client_for(cfg, user, csrf_header=True), user


def _keywords(cfg, user):
    with db_conn(cfg) as conn:
        return [k.keyword for k in db.list_keywords(conn, user.id)]


def test_caps_are_the_documented_numbers():
    assert app_module._PROFILE_MAX_LEN == dict(CAPS)
    assert app_module._KEYWORD_MAX_LEN == 60


# --- T35 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("field,limit", CAPS)
def test_profile_field_over_the_cap_is_rejected_and_nothing_saved(saas_cfg, field, limit):
    c, user = _client(saas_cfg)
    r = c.post("/onboarding/profile", data={**PROFILE,field: "x" * (limit + 1)})
    assert (r.status_code == 302
            and r.headers["location"] == f"/onboarding/profile?error=long_{field}")
    assert saved_profile(saas_cfg, user) is None


@pytest.mark.parametrize("field,limit", CAPS)
def test_profile_field_at_the_cap_is_saved(saas_cfg, field, limit):
    c, user = _client(saas_cfg)
    r = c.post("/onboarding/profile", data={**PROFILE,field: "  " + "x" * limit + "  "})
    assert r.headers["location"] == "/onboarding/keywords"     # measured after strip
    assert getattr(saved_profile(saas_cfg, user), field) == "x" * limit


def test_over_the_cap_never_overwrites_a_saved_profile(saas_cfg):
    c, user = _client(saas_cfg)
    c.post("/onboarding/profile", data=PROFILE)
    r = c.post("/onboarding/profile", data={**PROFILE,"full_name": "y" * 81})
    assert r.headers["location"] == "/onboarding/profile?error=long_full_name"
    assert saved_profile(saas_cfg, user).full_name == "Maria Santos"


# --- T36 ----------------------------------------------------------------------------------

def test_crlf_newlines_count_as_one_character(saas_cfg):
    c, user = _client(saas_cfg)
    message = "\r\n".join(["x" * 99] * 50)                  # 4,999 as the browser counts it
    assert len(message) == 5048
    r = c.post("/onboarding/profile", data={**PROFILE,"standard_message": message})
    assert r.headers["location"] == "/onboarding/keywords"


@pytest.mark.parametrize("extra,ok", [("x", True), ("xx", False)])
def test_crlf_boundary_is_exact(saas_cfg, extra, ok):
    c, _ = _client(saas_cfg)
    message = "\r\n".join(["x" * 99] * 50) + extra          # 5,000 then 5,001 counted
    r = c.post("/onboarding/profile", data={**PROFILE,"standard_message": message})
    assert (r.headers["location"] == "/onboarding/keywords") is ok


def test_keyword_over_the_cap_is_silently_ignored(saas_cfg):
    c, user = _client(saas_cfg)
    for kw in ("k" * 61, "j" * 60, "  " + "m" * 60 + "  "):
        r = c.post("/onboarding/keywords", data={"keyword": kw})
        assert r.status_code == 302 and r.headers["location"] == "/onboarding/keywords"
    assert sorted(_keywords(saas_cfg, user)) == ["j" * 60, "m" * 60]


def test_keyword_past_the_count_cap_is_silently_ignored(saas_cfg):
    """F-013: at most 20 keywords per user, so one account cannot stretch every worker cycle."""
    assert app_module._KEYWORD_MAX_COUNT == 20
    c, user = _client(saas_cfg)
    for i in range(21):
        r = c.post("/onboarding/keywords", data={"keyword": f"kw{i:02d}"})
        assert r.status_code == 302 and r.headers["location"] == "/onboarding/keywords"
    assert sorted(_keywords(saas_cfg, user)) == [f"kw{i:02d}" for i in range(20)]
    c.post(f"/onboarding/keywords/{_any_keyword_id(saas_cfg, user)}/delete")
    c.post("/onboarding/keywords", data={"keyword": "kw20"})     # room again after a delete
    assert len(_keywords(saas_cfg, user)) == 20 and "kw20" in _keywords(saas_cfg, user)


def _any_keyword_id(cfg, user):
    with db_conn(cfg) as conn:
        return db.list_keywords(conn, user.id)[0].id
