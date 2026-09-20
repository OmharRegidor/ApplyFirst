"""UI contract of the redesigned pages (plan T46 to T52). These bind to the macro API and test
hooks in plan.md "Types & signatures", not to any particular markup around them."""

from __future__ import annotations

import re

import pytest

from applyfirst.saas import app as app_module
from _saas_client import (
    by_id, clean, client_for, count_class, elements, form_inputs, page_text, post_forms,
    seed_user,
)

UAS = {
    "Facebook": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/450.0.0.38.108;FBDV/"
                 "iPhone15,2;FBMD/iPhone;FBSN/iOS;FBSV/17.0;FBLC/en_US]"),
    "Instagram": ("Mozilla/5.0 (Linux; Android 13; SM-A536E Build/TP1A.220624.014; wv) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 "
                  "Mobile Safari/537.36 Instagram 312.0.0.32.112 Android"),
    "Messenger": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Mobile/15E148 [FBAN/MessengerForiOS;FBAV/440.0.0.33.109]"),
}
CHROME = ("Mozilla/5.0 (Linux; Android 13; SM-A536E) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/128.0.0.0 Mobile Safari/537.36")


def _ui():
    """The owner switches exported by _ui.html (top-level sets)."""
    return app_module._TEMPLATES.env.get_template("_ui.html").module


def _dashboard(cfg, master_key, *, gmail=True, keywords=("virtual assistant",), usage=0):
    user = seed_user(cfg, activated=True, keywords=keywords,
                     gmail_key=master_key if gmail else None, usage=usage)
    return client_for(cfg, user).get("/dashboard").text


def _panels(markup: str) -> list[str]:
    return re.findall(r'data-panel="([^"]*)"', markup)


# --- T46 ----------------------------------------------------------------------------------

def test_home_invite_mode(saas_cfg):
    ui = _ui()
    assert ui.INVITE_ONLY is True and ui.TRIAL_DAYS == 14
    markup = client_for(saas_cfg).get("/").text
    text = page_text(markup)
    invites = [e for e in elements(markup) if e.tag == "a"
               and e.attrs.get("href", "").startswith("mailto:omharregidor@gmail.com?subject=")]
    assert invites and all(clean(e.text) == "Ask for a beta invite" for e in invites)
    assert "&amp;body=" in markup and "&amp;amp;" not in markup     # escaped exactly once
    assert "omharregidor@gmail.com" in text                         # the address is selectable
    assert text.index("Already invited?") < text.index("Continue with Google")
    labels = {clean(e.text) for e in elements(markup)}
    assert {"Beta", "14-day free trial"} <= labels
    assert "Is ApplyFirst free to try?" in text
    assert "nothing is charged automatically" in text
    if not ui.SHOW_PRICE:
        assert "₱" not in markup and "199" not in text


# --- T47 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/login"])
@pytest.mark.parametrize("app_name", list(UAS))
def test_in_app_browser_notice_names_the_app(saas_cfg, path, app_name):
    text = page_text(client_for(saas_cfg, user_agent=UAS[app_name]).get(path).text)
    assert "Open this page in Chrome or Safari" in text
    assert f"inside {app_name}" in text


@pytest.mark.parametrize("path", ["/", "/login"])
def test_no_in_app_notice_in_a_normal_browser(saas_cfg, path):
    assert "Open this page in Chrome or Safari" not in client_for(
        saas_cfg, user_agent=CHROME).get(path).text


# --- T48 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("state,kwargs,panel", [
    ("gmail off", {"gmail": False}, "gmail"),
    ("no keywords", {"keywords": ()}, "empty"),
    ("at the cap", {"usage": 10}, "paused"),
    ("healthy", {}, "live"),
    ("gmail off and at the cap", {"gmail": False, "usage": 10}, "gmail"),
])
def test_dashboard_renders_exactly_one_status_panel(saas_cfg, master_key, state, kwargs, panel):
    markup = _dashboard(saas_cfg, master_key, **kwargs)
    assert _panels(markup) == [panel], state
    capped = kwargs.get("usage", 0) >= saas_cfg.daily_tailor_cap
    assert ("daily limit reached" in markup) is capped
    panel_el = next(e for e in elements(markup) if e.attrs.get("data-panel") == panel)
    assert "daily limit reached" not in panel_el.text


# --- T49 ----------------------------------------------------------------------------------

def _onboarding_pages(cfg, master_key) -> dict[str, str]:
    fresh = client_for(cfg, seed_user(cfg, sub="a", email="a@x.com"))
    connected = client_for(cfg, seed_user(cfg, sub="b", email="b@x.com", gmail_key=master_key,
                                          profile=True, keywords=("data entry",)))
    ready = client_for(cfg, seed_user(cfg, sub="c", email="c@x.com", profile=True,
                                      keywords=("data entry",)))
    no_kw = client_for(cfg, seed_user(cfg, sub="d", email="d@x.com", profile=True))
    return {
        "connect": fresh.get("/onboarding/connect_gmail").text,
        "connect(scope)": fresh.get("/onboarding/connect_gmail?gmail_error=scope").text,
        "connect(cancel)": fresh.get("/auth/gmail-callback", params={"error": "x"}).text,
        "connect(connected)": connected.get("/onboarding/connect_gmail").text,
        "profile": fresh.get("/onboarding/profile").text,
        "profile(error)": fresh.get("/onboarding/profile?error=1").text,
        "keywords(empty)": no_kw.get("/onboarding/keywords").text,
        "keywords(list)": ready.get("/onboarding/keywords").text,
        "preview(connected)": connected.get("/onboarding/preview").text,
        "preview(not connected)": ready.get("/onboarding/preview").text,
    }


def test_one_primary_button_at_most_per_onboarding_page(saas_cfg, master_key):
    counts = {name: count_class(markup, "btn--primary")
              for name, markup in _onboarding_pages(saas_cfg, master_key).items()}
    assert all(n <= 1 for n in counts.values()), counts
    for name in ("connect", "connect(scope)", "connect(cancel)", "profile", "keywords(list)",
                 "preview(not connected)"):
        assert counts[name] == 1, (name, counts)


@pytest.mark.parametrize("kwargs,expected", [({"gmail": False}, 1), ({"keywords": ()}, 1),
                                             ({"usage": 10}, None), ({}, 0)])
def test_one_primary_button_at_most_per_dashboard_state(saas_cfg, master_key, kwargs, expected):
    n = count_class(_dashboard(saas_cfg, master_key, **kwargs), "btn--primary")
    assert n <= 1 if expected is None else n == expected


def test_retry_state_keeps_connect_gmail_as_the_only_primary(saas_cfg):
    markup = client_for(saas_cfg, seed_user(saas_cfg)).get(
        "/onboarding/connect_gmail?gmail_error=scope").text
    primaries = [e for e in elements(markup) if "btn--primary" in e.attrs.get("class", "")]
    assert len(primaries) == 1 and primaries[0].attrs.get("href") == "/auth/connect-gmail"
    note = by_id(markup, "gmail-retry")
    assert note is not None and markup.index('id="gmail-retry"') < markup.index("<h1")


# --- T50 ----------------------------------------------------------------------------------

def _keyword_value(form) -> tuple[str, str]:
    field = next(i for i in form_inputs(form) if i.attrs.get("name") == "keyword")
    return field.attrs.get("type", "text").lower(), field.attrs.get("value", "")


def test_keywords_page_main_form_first_and_quick_add_hides_used_words(saas_cfg):
    user = seed_user(saas_cfg, profile=True, keywords=("Virtual Assistant", "night shift"))
    markup = client_for(saas_cfg, user).get("/onboarding/keywords").text
    forms = post_forms(markup, "/onboarding/keywords")
    kinds = [_keyword_value(f)[0] for f in forms]
    assert kinds[0] != "hidden"                                  # the main add form comes first
    assert kinds[1:] and all(k == "hidden" for k in kinds[1:])
    quick = [_keyword_value(f)[1] for f in forms[1:]]
    assert "virtual assistant" not in [w.lower() for w in quick]  # used words hidden, any case
    assert set(quick) == set(_ui().QUICK_KEYWORDS) - {"virtual assistant"}
    for f in forms:
        assert any(i.attrs.get("name") == "csrf" for i in form_inputs(f))


def test_each_remove_button_names_its_keyword(saas_cfg):
    words = ("virtual assistant", "a" * 60)
    user = seed_user(saas_cfg, profile=True, keywords=words)
    markup = client_for(saas_cfg, user).get("/onboarding/keywords").text
    forms = post_forms(markup, r"/onboarding/keywords/[^/]+/delete")
    assert len(forms) == len(words)
    names = []
    for f in forms:
        button = next(c for c in f.children if c.tag == "button")
        names.append(clean(button.attrs.get("aria-label") or button.text))
    for word in words:
        assert any(word in name and "Remove" in name for name in names), (word, names)


def test_empty_keywords_page_shows_the_empty_state_instead_of_next(saas_cfg):
    empty = client_for(saas_cfg, seed_user(saas_cfg, profile=True)).get("/onboarding/keywords")
    assert 'href="/onboarding/preview"' not in empty.text
    assert "No keywords yet" in page_text(empty.text)
    listed = client_for(saas_cfg, seed_user(saas_cfg, sub="b", email="b@x.com", profile=True,
                                            keywords=("va",))).get("/onboarding/keywords")
    assert 'href="/onboarding/preview"' in listed.text


# --- T51 ----------------------------------------------------------------------------------

def _fields(markup: str) -> dict:
    return {e.attrs["name"]: e for e in elements(markup)
            if e.tag in ("input", "textarea") and e.attrs.get("name") in app_module._PROFILE_MAX_LEN}


def test_profile_error_state_is_announced_and_tied_to_every_field(saas_cfg):
    c = client_for(saas_cfg, seed_user(saas_cfg))
    markup = c.get("/onboarding/profile?error=1").text
    alert = by_id(markup, "form-error")
    assert alert is not None
    assert alert.attrs.get("role") == "alert" and alert.attrs.get("tabindex") == "-1"
    fields = _fields(markup)
    assert set(fields) == set(app_module._PROFILE_MAX_LEN)
    for name, el in fields.items():
        assert "form-error" in el.attrs.get("aria-describedby", "").split(), name
    plain = c.get("/onboarding/profile").text
    assert by_id(plain, "form-error") is None
    assert all("form-error" not in e.attrs.get("aria-describedby", "")
               for e in _fields(plain).values())


def test_browser_maxlength_equals_the_server_caps(saas_cfg):
    user = seed_user(saas_cfg, profile=True)
    c = client_for(saas_cfg, user)
    for name, el in _fields(c.get("/onboarding/profile").text).items():
        assert el.attrs.get("maxlength") == str(app_module._PROFILE_MAX_LEN[name]), name
    main = post_forms(c.get("/onboarding/keywords").text, "/onboarding/keywords")[0]
    field = next(i for i in form_inputs(main) if i.attrs.get("name") == "keyword")
    assert field.attrs.get("maxlength") == str(app_module._KEYWORD_MAX_LEN)


# --- T52 ----------------------------------------------------------------------------------

def test_ai_letter_copy_matches_the_shipped_prompt_fix(saas_cfg):
    assert _ui().AI_LETTER_COPY is True          # the prompt fix and T1 to T13 ship together
    assert "A message written from your own words for this job" in page_text(
        client_for(saas_cfg).get("/").text)


def test_preview_never_calls_the_sample_ai_written(saas_cfg):
    user = seed_user(saas_cfg, profile=True, keywords=("va",))
    text = page_text(client_for(saas_cfg, user).get("/onboarding/preview").text).lower()
    for claim in ("ai-written", "written by ai", "ai wrote", "ai-generated", "generated by ai"):
        assert claim not in text
