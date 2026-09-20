"""F-034 / F-035: saving "Your details" after activation is an edit, not a setup step.

An activated user who saves goes back to the dashboard (its "Your details" card is the
confirmation) and the button says "Save changes". A first-timer still continues to Step 3
with "Save and continue", and a bad save still returns ?error=1 for everyone.
"""

from __future__ import annotations

import pytest

from _saas_client import (
    PROFILE, clean, client_for, has_class, page_text, post_forms, saved_profile, seed_user,
)

EDITED = {**PROFILE, "job_type": "Graphic Designer"}


def _primary_labels(markup: str) -> list[str]:
    form = post_forms(markup, r"/onboarding/profile")
    assert len(form) == 1, "the profile page must have exactly one profile form"
    return [clean(e.text) for e in form[0].children
            if e.tag == "button" and has_class(e, "btn--primary")]


def test_activated_valid_save_goes_back_to_the_dashboard(saas_cfg):
    user = seed_user(saas_cfg, activated=True, keywords=("va",))
    activated_at = saved_profile(saas_cfg, user).activated_at
    c = client_for(saas_cfg, user, csrf_header=True)
    r = c.post("/onboarding/profile", data=EDITED)
    assert r.status_code == 302 and r.headers["location"] == "/dashboard"
    saved = saved_profile(saas_cfg, user)
    assert saved.job_type == "Graphic Designer" and saved.activated_at == activated_at
    assert "Graphic Designer" in page_text(c.get("/dashboard").text)   # the confirmation


@pytest.mark.parametrize("has_profile", [False, True], ids=["new", "returning-mid-setup"])
def test_first_timer_valid_save_still_continues_to_keywords(saas_cfg, has_profile):
    user = seed_user(saas_cfg, profile=has_profile)
    c = client_for(saas_cfg, user, csrf_header=True)
    r = c.post("/onboarding/profile", data=EDITED)
    assert r.status_code == 302 and r.headers["location"] == "/onboarding/keywords"
    assert saved_profile(saas_cfg, user).job_type == "Graphic Designer"


def test_activated_blank_field_still_returns_the_error(saas_cfg):
    user = seed_user(saas_cfg, activated=True, keywords=("va",))
    c = client_for(saas_cfg, user, csrf_header=True)
    r = c.post("/onboarding/profile", data={**EDITED, "job_type": "   "})
    assert r.status_code == 302 and r.headers["location"] == "/onboarding/profile?error=1"
    assert saved_profile(saas_cfg, user).job_type == PROFILE["job_type"]     # nothing saved


def test_save_button_label_follows_the_activated_flag(saas_cfg):
    """F-035 (Jazelei's label), tested here because the tests lane is Omhar's."""
    active = client_for(saas_cfg, seed_user(saas_cfg, sub="a", email="a@x.com", activated=True,
                                            keywords=("va",)))
    fresh = client_for(saas_cfg, seed_user(saas_cfg, sub="b", email="b@x.com"))
    active_html = active.get("/onboarding/profile").text
    fresh_html = fresh.get("/onboarding/profile").text
    assert _primary_labels(active_html) == ["Save changes"]
    assert "Save and continue" not in page_text(active_html)
    assert _primary_labels(fresh_html) == ["Save and continue"]
    assert "Save changes" not in page_text(fresh_html)
