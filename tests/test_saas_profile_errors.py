"""Owner call (2026-09-19) "Say exactly what's too long": a profile save names the first over-cap
field with a fixed ?error= token, the page builds form_error from a whitelist of those tokens
(no query value is ever reflected), and the Google name prefill is cut to the 80-character cap.
"""

from __future__ import annotations

import html
from pathlib import Path

import pytest

from applyfirst.saas import app as app_module
from applyfirst.saas import db
from _saas_client import (
    PROFILE, by_id, clean, client_for, db_conn, elements, page_text, saved_profile, seed_user,
)

CAPS = [("full_name", 80), ("job_type", 80), ("standard_subject", 150),
        ("standard_message", 5000)]
COPY = {
    "full_name": "Your name is too long. Keep it under 80 characters.",
    "job_type": "Your job type is too long. Keep it under 80 characters.",
    "standard_subject": "Your subject line is too long. Keep it under 150 characters.",
    "standard_message": "Your message is too long. Keep it under 5,000 characters.",
}
BLANK_COPY = "Please fill in all four fields."


def _client(cfg, **seed):
    user = seed_user(cfg, **seed)
    return client_for(cfg, user, csrf_header=True), user


def _record_profile_renders(monkeypatch) -> list[dict]:
    """The route context of every onboarding_profile.html render from here on."""
    seen: list[dict] = []
    original = app_module._TEMPLATES.TemplateResponse

    def recording(request, name, context=None, *args, **kwargs):
        if name == "onboarding_profile.html":
            seen.append(dict(context or {}))
        return original(request, name, context, *args, **kwargs)

    monkeypatch.setattr(app_module._TEMPLATES, "TemplateResponse", recording)
    return seen


def _form_values(markup: str) -> dict[str, str]:
    """What a browser would submit, untouched, from the rendered profile form."""
    values = {}
    for e in elements(markup):
        name = e.attrs.get("name")
        if name in app_module._PROFILE_MAX_LEN:
            values[name] = e.text if e.tag == "textarea" else e.attrs.get("value", "")
    return values


def _fields(markup: str) -> dict:
    return {e.attrs["name"]: e for e in elements(markup)
            if e.tag in ("input", "textarea") and e.attrs.get("name") in app_module._PROFILE_MAX_LEN}


# --- the save: one fixed token per outcome, nothing saved on any error --------------------------

@pytest.mark.parametrize("field,limit", CAPS)
def test_each_over_cap_field_gets_its_own_token_and_nothing_is_saved(saas_cfg, field, limit):
    c, user = _client(saas_cfg)
    r = c.post("/onboarding/profile", data={**PROFILE, field: "x" * (limit + 1)})
    assert r.status_code == 302
    assert r.headers["location"] == f"/onboarding/profile?error=long_{field}"
    assert saved_profile(saas_cfg, user) is None


@pytest.mark.parametrize("field,limit", CAPS)
def test_an_over_cap_field_never_overwrites_a_saved_profile(saas_cfg, field, limit):
    c, user = _client(saas_cfg, profile=True)
    r = c.post("/onboarding/profile", data={**PROFILE, "job_type": "Graphic Designer",
                                            field: "y" * (limit + 1)})
    assert r.headers["location"] == f"/onboarding/profile?error=long_{field}"
    assert saved_profile(saas_cfg, user).job_type == PROFILE["job_type"]


def test_the_first_over_cap_field_in_form_order_is_named(saas_cfg):
    c, _ = _client(saas_cfg)
    everything = {name: "z" * (limit + 1) for name, limit in CAPS}
    assert c.post("/onboarding/profile", data=everything).headers["location"] \
        == "/onboarding/profile?error=long_full_name"
    tail = {**PROFILE, "standard_subject": "z" * 151, "standard_message": "z" * 5001}
    assert c.post("/onboarding/profile", data=tail).headers["location"] \
        == "/onboarding/profile?error=long_standard_subject"


def test_a_crlf_message_is_measured_as_the_browser_counts_it(saas_cfg):
    c, _ = _client(saas_cfg)
    message = "\r\n".join(["x" * 99] * 50) + "xx"                  # 5,001 as the browser counts
    r = c.post("/onboarding/profile", data={**PROFILE, "standard_message": message})
    assert r.headers["location"] == "/onboarding/profile?error=long_standard_message"


@pytest.mark.parametrize("data", [
    {**PROFILE, "job_type": "   "},
    {**PROFILE, "full_name": ""},
    {**PROFILE, "job_type": "", "standard_message": "m" * 5001},    # a blank field wins
], ids=["blank job_type", "empty name", "blank and too long"])
def test_a_blank_field_still_gives_error_1(saas_cfg, data):
    c, user = _client(saas_cfg)
    r = c.post("/onboarding/profile", data=data)
    assert r.status_code == 302 and r.headers["location"] == "/onboarding/profile?error=1"
    assert saved_profile(saas_cfg, user) is None


# --- the page: form_error only from the whitelist ------------------------------------------------

@pytest.mark.parametrize("token,expected", [
    ("1", {"kind": "blank"}),
    *[(f"long_{name}", {"kind": "too_long", "field": name, "limit": limit})
      for name, limit in CAPS],
])
def test_known_tokens_map_to_their_form_error(saas_cfg, monkeypatch, token, expected):
    seen = _record_profile_renders(monkeypatch)
    c, _ = _client(saas_cfg)
    assert c.get("/onboarding/profile", params={"error": token}).status_code == 200
    assert seen[-1]["form_error"] == expected


def test_no_token_means_no_form_error(saas_cfg, monkeypatch):
    seen = _record_profile_renders(monkeypatch)
    c, _ = _client(saas_cfg)
    markup = c.get("/onboarding/profile").text
    assert seen[-1]["form_error"] is None
    assert by_id(markup, "form-error") is None


@pytest.mark.parametrize("token", [
    "<script>alert(7)</script>", "long_x", "1' OR '1'='1", "LONG_JOB_TYPE",
    'long_full_name"><img src=x onerror=alert(8)>', "long_csrf", " long_job_type", "11",
])
def test_an_unknown_token_is_ignored_and_never_reflected(saas_cfg, monkeypatch, token):
    seen = _record_profile_renders(monkeypatch)
    c, _ = _client(saas_cfg)
    r = c.get("/onboarding/profile", params={"error": token})
    assert r.status_code == 200
    assert seen[-1]["form_error"] is None
    assert by_id(r.text, "form-error") is None
    if len(token.strip()) > 2:                  # long enough that a hit can only be reflection
        for form in {token, html.escape(token), html.escape(token, quote=False)}:
            assert form not in r.text, form


def test_the_form_error_given_to_the_page_is_a_fresh_copy(saas_cfg, monkeypatch):
    """A template (or a later route) mutating form_error cannot change the whitelist."""
    seen = _record_profile_renders(monkeypatch)
    c, _ = _client(saas_cfg)
    c.get("/onboarding/profile?error=long_job_type")
    seen[-1]["form_error"]["limit"] = 1
    c.get("/onboarding/profile?error=long_job_type")
    assert seen[-1]["form_error"]["limit"] == 80


# --- the page: the interface the template renders -----------------------------------------------

@pytest.mark.parametrize("field", list(COPY))
def test_too_long_names_only_that_field_with_the_fixed_copy(saas_cfg, field):
    c, _ = _client(saas_cfg)
    markup = c.get(f"/onboarding/profile?error=long_{field}").text
    alert = by_id(markup, "form-error")
    assert alert is not None
    assert alert.attrs.get("role") == "alert" and alert.attrs.get("tabindex") == "-1"
    assert clean(alert.text) == COPY[field]
    assert BLANK_COPY not in page_text(markup)
    for name, el in _fields(markup).items():
        described = el.attrs.get("aria-describedby", "").split()
        if name == field:
            assert el.attrs.get("aria-invalid") == "true" and "form-error" in described
        else:
            assert "aria-invalid" not in el.attrs and "form-error" not in described, name


def test_each_too_long_copy_sits_on_one_source_line():
    source = (Path(app_module.__file__).parent / "templates"
              / "onboarding_profile.html").read_text(encoding="utf-8")
    for text in COPY.values():
        assert any(text in line for line in source.splitlines()), text


def test_blank_keeps_todays_copy(saas_cfg):
    c, _ = _client(saas_cfg)
    alert = by_id(c.get("/onboarding/profile?error=1").text, "form-error")
    assert alert is not None and BLANK_COPY in clean(alert.text)
    assert not any(copy in clean(alert.text) for copy in COPY.values())


# --- legacy data and the Google name prefill -----------------------------------------------------

def test_a_legacy_over_long_message_resaved_unchanged_names_the_message(saas_cfg, monkeypatch):
    c, user = _client(saas_cfg, activated=True, keywords=("va",))
    legacy = {**PROFILE, "standard_message": "m" * 6000}           # saved before the caps existed
    with db_conn(saas_cfg) as conn:
        db.upsert_profile(conn, user.id, **legacy)
    submitted = _form_values(c.get("/onboarding/profile").text)
    assert submitted == legacy                                     # the form round-trips it as is

    r = c.post("/onboarding/profile", data=submitted)
    assert r.status_code == 302
    assert r.headers["location"] == "/onboarding/profile?error=long_standard_message"
    assert saved_profile(saas_cfg, user).standard_message == "m" * 6000   # nothing saved

    seen = _record_profile_renders(monkeypatch)
    markup = c.get(r.headers["location"]).text
    assert seen[-1]["form_error"] == {"kind": "too_long", "field": "standard_message",
                                      "limit": 5000}
    assert clean(by_id(markup, "form-error").text) == COPY["standard_message"]


@pytest.mark.parametrize("google_name,prefill", [
    ("x" * 79 + " " + "y" * 40, "x" * 79),          # 120 characters, cut ends on a space
    ("N" * 120, "N" * 80),
    ("Maria Santos", "Maria Santos"),
    (None, ""),
])
def test_the_google_name_prefill_fits_the_name_cap(saas_cfg, monkeypatch, google_name, prefill):
    seen = _record_profile_renders(monkeypatch)
    c, user = _client(saas_cfg, name=google_name)
    markup = c.get("/onboarding/profile").text
    assert seen[-1]["default_name"] == prefill
    rendered = _fields(markup)["full_name"].attrs.get("value", "")
    assert rendered == prefill and len(rendered) <= 80
    if prefill:                                     # an untouched prefill always saves
        r = c.post("/onboarding/profile", data={**PROFILE, "full_name": rendered})
        assert r.headers["location"] == "/onboarding/keywords"
        assert saved_profile(saas_cfg, user).full_name == prefill


def test_a_saved_name_is_shown_in_full_not_trimmed(saas_cfg):
    """Only the Google prefill is cut. A saved (legacy) name is shown as is, so the error that
    names it is honest."""
    c, user = _client(saas_cfg, name="Maria")
    with db_conn(saas_cfg) as conn:
        db.upsert_profile(conn, user.id, **{**PROFILE, "full_name": "L" * 100})
    assert _fields(c.get("/onboarding/profile").text)["full_name"].attrs["value"] == "L" * 100


# --- saved over-cap fields: every one at once, from the stored profile only ----------------------

def _save_legacy(cfg, user, **over) -> None:
    """Store a profile the way a beta row saved before the caps existed can look."""
    with db_conn(cfg) as conn:
        db.upsert_profile(conn, user.id, **{**PROFILE, **over})


@pytest.mark.parametrize("params", [
    {}, {"error": "long_standard_subject"}, {"error": "long_standard_message"}, {"error": "1"},
], ids=["plain load", "after the subject error", "after the message error", "after blank"])
def test_every_saved_over_cap_field_is_named_on_every_load(saas_cfg, monkeypatch, params):
    """Two over-cap saved fields are both named, so the user never loops between them."""
    c, user = _client(saas_cfg, activated=True, keywords=("va",))
    _save_legacy(saas_cfg, user, standard_subject="s" * 170, standard_message="m" * 5294)
    seen = _record_profile_renders(monkeypatch)
    assert c.get("/onboarding/profile", params=params).status_code == 200
    assert seen[-1]["over_cap_fields"] == ["standard_subject", "standard_message"]
    expected = app_module._PROFILE_FORM_ERRORS.get(params.get("error"))
    assert seen[-1]["form_error"] == expected                  # its shape is unchanged


def test_all_four_saved_fields_over_cap_are_named_in_form_order(saas_cfg, monkeypatch):
    c, user = _client(saas_cfg, profile=True)
    _save_legacy(saas_cfg, user, **{name: "z" * (limit + 1) for name, limit in reversed(CAPS)})
    seen = _record_profile_renders(monkeypatch)
    c.get("/onboarding/profile")
    assert seen[-1]["over_cap_fields"] == [name for name, _ in CAPS]


@pytest.mark.parametrize("seed", [{}, {"profile": True}], ids=["no profile", "normal profile"])
@pytest.mark.parametrize("params", [
    {}, {"error": "long_full_name"}, {"error": "long_standard_message"},
    {"over_cap_fields": "job_type"},
])
def test_no_saved_over_cap_field_means_an_empty_list(saas_cfg, monkeypatch, seed, params):
    """The query never adds a field: only the stored profile does."""
    seen = _record_profile_renders(monkeypatch)
    c, _ = _client(saas_cfg, **seed)
    assert c.get("/onboarding/profile", params=params).status_code == 200
    assert seen[-1]["over_cap_fields"] == []


def test_a_saved_field_at_its_cap_is_not_flagged(saas_cfg, monkeypatch):
    c, user = _client(saas_cfg, profile=True)
    _save_legacy(saas_cfg, user, full_name="n" * 80, job_type="j" * 80,
                 standard_subject="s" * 150,
                 standard_message="\r\n".join(["x" * 99] * 50) + "x")  # 5,000 as a browser counts
    seen = _record_profile_renders(monkeypatch)
    c.get("/onboarding/profile")
    assert seen[-1]["over_cap_fields"] == []


@pytest.mark.parametrize("token", ["long_x", "<script>alert(7)</script>", "LONG_FULL_NAME", "11"])
def test_a_bogus_token_with_a_legacy_profile_still_gives_no_form_error(saas_cfg, monkeypatch,
                                                                       token):
    c, user = _client(saas_cfg, profile=True)
    _save_legacy(saas_cfg, user, full_name="L" * 90)
    seen = _record_profile_renders(monkeypatch)
    r = c.get("/onboarding/profile", params={"error": token})
    assert r.status_code == 200
    assert seen[-1]["form_error"] is None
    assert seen[-1]["over_cap_fields"] == ["full_name"]
