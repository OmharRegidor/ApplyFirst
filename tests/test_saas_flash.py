"""The one-shot confirmation after Google sign-in and after Gmail connects (UX directive, option 1).

A quiet green banner, the app's own success alert, on the first page a person lands on after
"Continue with Google" ("Signed in as <email>.") or "Connect Gmail" ("Gmail connected.
Applications will go to <email>."). Server-rendered from a short-lived signed cookie that the two
callbacks set on success only. Redirects never read it, the first of the five journey pages to
render shows it and deletes it in the same response, and nothing ever shows it twice.
"""

from __future__ import annotations

import dataclasses
import json
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient

from applyfirst.saas import db, google_oauth, session
from applyfirst.saas.app import create_app
from _journey_css import JOURNEY_CSS, STATIC, decls, iter_rules, read_css
from _saas_client import Element, clean, count_class, elements, has_class, page_text, seed_user

EMAIL = "maria@example.com"
LONG_EMAIL = "maria.clara.santos.dlcruz@gmail.com"          # 35 characters (R7)
SIGNED_IN = f"Signed in as {EMAIL}."
GMAIL_ON = f"Gmail connected. Applications will go to {EMAIL}."
FIVE_PAGES = ("/onboarding/connect_gmail", "/onboarding/profile", "/onboarding/keywords",
              "/onboarding/preview", "/dashboard")
REDIRECTS = (301, 302, 303, 307, 308)

# The rules a browser needs to replace, and so delete, a __Host- cookie (see test_saas_auth_flow).
HOST_RULES = {"path": "/", "secure": "", "httponly": "", "samesite": "lax"}
HTTP_RULES = {"path": "/", "httponly": "", "samesite": "lax"}


# --- helpers ---------------------------------------------------------------------------------

def _name(secure: bool) -> str:
    return "__Host-applyfirst_flash" if secure else "applyfirst_flash"


def _client(cfg, user: db.User | None = None) -> TestClient:
    """A client on https when the config wants secure cookies, signed in as ``user``."""
    base = "https://testserver" if cfg.secure_cookies else "http://testserver"
    c = TestClient(create_app(cfg), base_url=base, follow_redirects=False)
    if user is not None:
        c.cookies.set(session.session_cookie_name(cfg.secure_cookies),
                      session.sign(cfg.session_secret, {"uid": user.id}))
    return c


def _hand_flash(c: TestClient, cfg, code: str = "signed_in", **extra) -> TestClient:
    """Plant a flash cookie by hand, signed like the app's. The server's delete does not match a
    hand-set cookie in the test jar, so tests that plant one read the delete header instead."""
    c.cookies.set(_name(cfg.secure_cookies),
                  session.sign(cfg.session_secret, {"flash": code, **extra}))
    return c


def _follow(c: TestClient, path: str) -> list:
    """GET ``path`` and follow redirects by hand, like a browser; every response, in order."""
    out = []
    for _ in range(6):
        r = c.get(path)
        out.append(r)
        if r.status_code not in REDIRECTS:
            return out
        path = r.headers["location"]
    raise AssertionError(f"redirect loop: {[x.headers.get('location') for x in out]}")


def _headers(resp, name: str) -> list[str]:
    return [h for h in resp.headers.get_list("set-cookie") if h.startswith(name + "=")]


def _sets(resp, name: str) -> list[str]:
    return [h for h in _headers(resp, name) if "Max-Age=0" not in h]


def _deletes(resp, name: str) -> list[str]:
    return [h for h in _headers(resp, name) if "Max-Age=0" in h]


def _rules(header: str) -> dict[str, str]:
    """A Set-Cookie header's attributes, names lower-cased, without the two that say when."""
    rules = {}
    for part in header.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        rules[key.lower()] = value
    return {k: v for k, v in rules.items() if k not in ("max-age", "expires")}


def _max_age(header: str) -> int:
    return int(re.search(r"Max-Age=(\d+)", header).group(1))


def _banners(markup: str) -> list[Element]:
    return [e for e in elements(markup) if has_class(e, "flash")]


def _banner_text(markup: str) -> str:
    """The words of the one banner's status box (everything before its close button)."""
    [banner] = _banners(markup)
    assert [e.attrs.get("role") for e in banner.children if has_class(e, "alert")] == ["status"]
    [inside] = re.findall(r'<div class="flash">(.*?)<button', markup, flags=re.S)
    return page_text(inside)


def _index(markup: str, pred) -> int:
    return next(i for i, e in enumerate(elements(markup)) if pred(e))


def _start_login(c: TestClient) -> str:
    return parse_qs(urlparse(c.get("/auth/login").headers["location"]).query)["state"][0]


def _sign_in(c: TestClient, monkeypatch, *, sub="s", email=EMAIL, name="Maria"):
    state = _start_login(c)
    monkeypatch.setattr(google_oauth, "fetch_identity",
                        lambda cfg, **kw: {"google_sub": sub, "email": email,
                                           "display_name": name})
    return c.get("/auth/callback", params={"code": "c", "state": state})


def _connect_gmail(c: TestClient, monkeypatch):
    loc = c.get("/auth/connect-gmail").headers["location"]
    state = parse_qs(urlparse(loc).query)["state"][0]
    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail", lambda cfg, **kw: "rt-new")
    return c.get("/auth/gmail-callback", params={"code": "c", "state": state})


# The landing states of the directive's journey: (user seed, where /dashboard sends them).
LANDINGS = {
    "new": ({}, "/onboarding/connect_gmail"),
    "gmail-no-details": ({"gmail": True}, "/onboarding/profile"),
    "details-no-keywords": ({"profile": True}, "/onboarding/keywords"),
    "ready-no-gmail": ({"profile": True, "keywords": ("virtual assistant",)},
                       "/onboarding/preview"),
    "ready-with-gmail": ({"profile": True, "keywords": ("virtual assistant",), "gmail": True},
                         "/onboarding/preview"),
    "activated": ({"activated": True, "keywords": ("virtual assistant",), "gmail": True},
                  "/dashboard"),
}


def _seed(cfg, master_key, spec: dict, *, sub="s", email=EMAIL) -> db.User:
    return seed_user(cfg, sub=sub, email=email, profile=spec.get("profile", False),
                     keywords=spec.get("keywords", ()), activated=spec.get("activated", False),
                     gmail_key=master_key if spec.get("gmail") else None)


# --- the cookie (session.py) --------------------------------------------------------------------

@pytest.mark.parametrize("secure", [True, False], ids=["secure", "http"])
@pytest.mark.parametrize("code", ["signed_in", "gmail_connected"])
def test_the_flash_is_deleted_with_the_rules_it_was_set_with(secure, code):
    made, gone = Response(), Response()
    session.set_flash(made, b"s" * 32, secure, code)
    session.clear_flash(gone, secure)
    name = session.flash_cookie_name(secure)
    assert name == _name(secure)
    [set_header] = made.headers.getlist("set-cookie")
    [delete] = [h for h in gone.headers.getlist("set-cookie") if "Max-Age=0" in h]
    assert set_header.startswith(name + "=") and delete.startswith(name + "=")
    assert _rules(set_header) == _rules(delete) == (HOST_RULES if secure else HTTP_RULES)
    assert 0 < _max_age(set_header) <= 120, "a flash is read on the very next page"


def test_the_flash_carries_only_its_code():
    made = Response()
    session.set_flash(made, b"s" * 32, False, "signed_in")
    value = made.headers.getlist("set-cookie")[0].split(";")[0].split("=", 1)[1].strip('"')
    body = value.split(".")[0]
    payload = json.loads(session._b64d(body))
    assert set(payload) == {"flash", "iat"} and payload["flash"] == "signed_in"


def test_only_the_two_codes_can_be_set():
    assert session.FLASH_CODES == frozenset({"signed_in", "gmail_connected"})
    with pytest.raises(ValueError):
        session.set_flash(Response(), b"s" * 32, False, "welcome")


@pytest.mark.parametrize("token,want", [
    ("good", "signed_in"),
    ("unknown", None),
    ("forged", None),
    ("expired", None),
    ("future", None),
    ("not-a-string", None),
    ("garbage", None),
    ("session-token", None),
    ("non-ascii-body", None),
    ("non-ascii-sig", None),
])
def test_read_flash_honours_only_a_fresh_signed_whitelisted_code(saas_cfg, token, want):
    secret, now = saas_cfg.session_secret, int(time.time())
    value = {
        "good": session.sign(secret, {"flash": "signed_in"}),
        "unknown": session.sign(secret, {"flash": "welcome"}),
        "forged": session.sign(b"another-secret-entirely-32-bytes", {"flash": "signed_in"}),
        "expired": session.sign(secret, {"flash": "signed_in", "iat": now - 600}),
        "future": session.sign(secret, {"flash": "signed_in", "iat": now + 3600}),
        "not-a-string": session.sign(secret, {"flash": ["signed_in"]}),
        "garbage": "not.a-token",
        "session-token": session.sign(secret, {"uid": "u1"}),
        "non-ascii-body": "é.x",
        "non-ascii-sig": "abc.é",
    }[token]
    request = Request({"type": "http", "headers": [
        (b"cookie", f"applyfirst_flash={value}".encode("utf-8"))]})
    assert session.read_flash(request, secret, False) == want


# --- the two callbacks set it, on success only ----------------------------------------------------

@pytest.mark.parametrize("secure", [True, False], ids=["secure", "http"])
def test_google_sign_in_sets_signed_in_and_the_landing_page_deletes_it_alike(saas_cfg,
                                                                              monkeypatch, secure):
    cfg = dataclasses.replace(saas_cfg, secure_cookies=secure)
    db.init_db(cfg.db_path).close()
    c = _client(cfg)
    cb = _sign_in(c, monkeypatch)
    assert (cb.status_code, cb.headers["location"]) == (302, "/dashboard")
    [made] = _sets(cb, _name(secure))
    pages = _follow(c, cb.headers["location"])
    *hops, landed = pages
    assert [r.headers["location"] for r in hops] == ["/onboarding", "/onboarding/connect_gmail"]
    for r in hops:
        assert _headers(r, _name(secure)) == [], "a redirect must never read or spend the flash"
    [delete] = _deletes(landed, _name(secure))
    assert _rules(made) == _rules(delete) == (HOST_RULES if secure else HTTP_RULES)
    assert _banner_text(landed.text) == SIGNED_IN


@pytest.mark.parametrize("secure", [True, False], ids=["secure", "http"])
def test_connecting_gmail_sets_gmail_connected_and_step_two_deletes_it_alike(saas_cfg, master_key,
                                                                            monkeypatch, secure):
    cfg = dataclasses.replace(saas_cfg, secure_cookies=secure)
    user = seed_user(cfg, email=EMAIL)
    c = _client(cfg, user)
    cb = _connect_gmail(c, monkeypatch)
    assert (cb.status_code, cb.headers["location"]) == (302, "/onboarding")
    [made] = _sets(cb, _name(secure))
    *hops, landed = _follow(c, "/onboarding")
    assert [r.headers["location"] for r in hops] == ["/onboarding/profile"]
    assert all(_headers(r, _name(secure)) == [] for r in hops)
    [delete] = _deletes(landed, _name(secure))
    assert _rules(made) == _rules(delete) == (HOST_RULES if secure else HTTP_RULES)
    assert _banner_text(landed.text) == GMAIL_ON


def test_every_failed_callback_sets_no_flash(saas_cfg, master_key, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    anon = _client(saas_cfg)
    _start_login(anon)
    assert _headers(anon.get("/auth/callback", params={"error": "access_denied"}),
                    "applyfirst_flash") == []

    def boom(cfg, **kw):
        raise google_oauth.OAuthError("bad nonce")

    state = _start_login(anon)
    monkeypatch.setattr(google_oauth, "fetch_identity", boom)
    assert _headers(anon.get("/auth/callback", params={"code": "c", "state": state}),
                    "applyfirst_flash") == []

    user = seed_user(saas_cfg, email=EMAIL)
    c = _client(saas_cfg, user)
    c.get("/auth/connect-gmail")
    cancelled = c.get("/auth/gmail-callback", params={"error": "access_denied"})
    assert cancelled.status_code == 400 and _headers(cancelled, "applyfirst_flash") == []

    loc = c.get("/auth/connect-gmail").headers["location"]
    state = parse_qs(urlparse(loc).query)["state"][0]

    def unticked(cfg, **kw):
        raise google_oauth.GmailScopeError("gmail.send not granted")

    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail", unticked)
    scope = c.get("/auth/gmail-callback", params={"code": "c", "state": state})
    assert scope.headers["location"] == "/onboarding/connect_gmail?gmail_error=scope"
    assert _headers(scope, "applyfirst_flash") == []


def test_the_gmail_retry_page_neither_shows_nor_spends_a_pending_flash(saas_cfg, master_key):
    user = seed_user(saas_cfg, email=EMAIL)
    c = _hand_flash(_client(saas_cfg, user), saas_cfg)
    c.get("/auth/connect-gmail")
    page = c.get("/auth/gmail-callback", params={"error": "access_denied"})
    assert page.status_code == 400
    assert _banners(page.text) == [] and _deletes(page, "applyfirst_flash") == []


def test_a_new_sign_in_replaces_a_pending_flash(saas_cfg, monkeypatch):
    db.init_db(saas_cfg.db_path).close()
    c = _hand_flash(_client(saas_cfg), saas_cfg, "gmail_connected")
    cb = _sign_in(c, monkeypatch)
    [made] = _sets(cb, "applyfirst_flash")
    value = made.split(";")[0].split("=", 1)[1].strip('"')
    assert session.unsign(saas_cfg.session_secret, value, 120)["flash"] == "signed_in"


def test_the_real_journey_shows_it_once_then_never_again(saas_cfg, monkeypatch):
    """Refresh, and Back (which re-asks the server, see the no-store test), show nothing."""
    db.init_db(saas_cfg.db_path).close()
    c = _client(saas_cfg)
    cb = _sign_in(c, monkeypatch)
    landed = _follow(c, cb.headers["location"])[-1]
    assert _banner_text(landed.text) == SIGNED_IN
    again = c.get("/onboarding/connect_gmail")
    assert _banners(again.text) == [] and _headers(again, "applyfirst_flash") == []
    assert _banners(c.get("/dashboard", follow_redirects=True).text) == []


# --- where it shows ---------------------------------------------------------------------------------

@pytest.mark.parametrize("state", list(LANDINGS))
def test_signed_in_shows_on_every_page_a_sign_in_can_land_on(saas_cfg, master_key, state):
    spec, where = LANDINGS[state]
    user = _seed(saas_cfg, master_key, spec)
    c = _hand_flash(_client(saas_cfg, user), saas_cfg)
    *hops, landed = _follow(c, "/dashboard")
    assert (landed.status_code, landed.url.path) == (200, where)
    assert all(_deletes(r, "applyfirst_flash") == [] for r in hops)
    assert len(_deletes(landed, "applyfirst_flash")) == 1
    assert len(_banners(landed.text)) == 1
    assert _banner_text(landed.text) == SIGNED_IN


@pytest.mark.parametrize("state,greens", [
    ("gmail-no-details", 1),          # Step 2: the gconf picture is a status block, not a green box
    ("activated", 1),                 # dashboard: the Gmail group is a status block too
    ("ready-with-gmail", 2),          # Step 4: its own green box sits at the foot, past the letter
])
def test_gmail_connected_shows_at_the_top_of_every_page_connect_gmail_lands_on(
        saas_cfg, master_key, state, greens):
    """Step 4's own "Gmail connected" box is about 1,300px down on a 360px phone, so without the
    banner the first screen of the page Step 4's Connect Gmail returns to said nothing about it
    (Simplicity QA round 1, P1)."""
    spec, where = LANDINGS[state]
    user = _seed(saas_cfg, master_key, spec)
    c = _hand_flash(_client(saas_cfg, user), saas_cfg, "gmail_connected")
    landed = _follow(c, "/onboarding")[-1]
    assert (landed.status_code, landed.url.path) == (200, where)
    assert len(_deletes(landed, "applyfirst_flash")) == 1
    assert _banner_text(landed.text) == GMAIL_ON
    assert count_class(landed.text, "alert--success") == greens


def test_step_four_never_stacks_its_two_green_boxes(saas_cfg, master_key):
    """The banner opens the page and Step 4's own box closes it. The heading, the sample post, the
    letter and both Change links always sit between them, so the two are never side by side."""
    user = _seed(saas_cfg, master_key, LANDINGS["ready-with-gmail"][0])
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg, "gmail_connected").get(
        "/onboarding/preview").text
    found = elements(markup)
    first, second = [i for i, e in enumerate(found) if has_class(e, "alert--success")]
    assert first == _index(markup, lambda e: has_class(e, "flash")) + 1, "the banner comes first"
    between = found[first:second]
    assert any(e.tag == "h1" for e in between)
    assert all(any(has_class(e, cls) for e in between)
               for cls in ("preview", "mailcard", "link-row"))


def test_step_one_when_connected_keeps_its_own_green_box_only(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, {"gmail": True})
    c = _hand_flash(_client(saas_cfg, user), saas_cfg, "gmail_connected")
    page = c.get("/onboarding/connect_gmail")
    assert _banners(page.text) == [] and len(_deletes(page, "applyfirst_flash")) == 1
    assert count_class(page.text, "alert--success") == 1
    assert "Gmail is connected" in page_text(page.text)


@pytest.mark.parametrize("spec,path", [
    ({}, "/onboarding/profile"),
    ({"profile": True}, "/onboarding/keywords"),
    ({"activated": True, "keywords": ("virtual assistant",)}, "/dashboard"),
], ids=["step2", "step3", "dashboard"])
def test_gmail_connected_is_never_said_without_a_grant(saas_cfg, master_key, spec, path):
    """The grant can end between the callback and the page (a disconnect in another tab)."""
    user = _seed(saas_cfg, master_key, spec)
    page = _hand_flash(_client(saas_cfg, user), saas_cfg, "gmail_connected").get(path)
    assert page.status_code == 200
    assert _banners(page.text) == [] and len(_deletes(page, "applyfirst_flash")) == 1


@pytest.mark.parametrize("state,path", [
    ("new", "/onboarding/connect_gmail?gmail_error=scope"),       # where the callback sends it
    ("activated", "/dashboard?gmail_error=scope"),                 # and for an activated user
    ("gmail-no-details", "/onboarding/profile?gmail_error=scope"),  # the two other steps that
    ("ready-with-gmail", "/onboarding/preview?gmail_error=scope"),  # read the flag, by hand
])
@pytest.mark.parametrize("code", ["signed_in", "gmail_connected"])
def test_the_scope_error_path_never_shows_a_success_banner(saas_cfg, master_key, state, path,
                                                           code):
    user = _seed(saas_cfg, master_key, LANDINGS[state][0])
    page = _hand_flash(_client(saas_cfg, user), saas_cfg, code).get(path)
    assert page.status_code == 200
    assert _banners(page.text) == []
    if path.startswith(("/onboarding/connect_gmail", "/dashboard")):
        assert "tick the box" in page_text(page.text)


@pytest.mark.parametrize("token", ["forged", "unknown", "expired", "garbage"])
def test_a_bad_flash_is_ignored_and_deleted(saas_cfg, master_key, token):
    user = _seed(saas_cfg, master_key, {})
    c = _client(saas_cfg, user)
    now, secret = int(time.time()), saas_cfg.session_secret
    c.cookies.set("applyfirst_flash", {
        "forged": session.sign(b"another-secret-entirely-32-bytes", {"flash": "signed_in"}),
        "unknown": session.sign(secret, {"flash": "welcome"}),
        "expired": session.sign(secret, {"flash": "signed_in", "iat": now - 600}),
        "garbage": "x",
    }[token])
    page = c.get("/onboarding/connect_gmail")
    assert page.status_code == 200 and _banners(page.text) == []
    [delete] = _deletes(page, "applyfirst_flash")
    assert _rules(delete) == HTTP_RULES


@pytest.mark.parametrize("raw", [b"\xc3\xa9.x", b"abc.\xc3\xa9"], ids=["body", "sig"])
def test_a_non_ascii_flash_is_ignored_and_deleted(saas_cfg, master_key, raw):
    """Sent as a raw header, because the test client's cookie jar refuses non-ASCII values."""
    user = _seed(saas_cfg, master_key, {})
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    good = session.sign(saas_cfg.session_secret, {"uid": user.id}).encode("ascii")
    page = c.get("/onboarding/connect_gmail",
                 headers={"cookie": b"applyfirst_session=" + good + b"; applyfirst_flash=" + raw})
    assert page.status_code == 200 and _banners(page.text) == []
    [delete] = _deletes(page, "applyfirst_flash")
    assert _rules(delete) == HTTP_RULES


@pytest.mark.parametrize("path,want", [("/", (200, None)),
                                       ("/onboarding/connect_gmail", (302, "/login"))])
def test_a_non_ascii_session_cookie_is_a_signed_out_visitor(saas_cfg, path, want):
    db.init_db(saas_cfg.db_path).close()
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    r = c.get(path, headers={"cookie": b"applyfirst_session=abc.\xc3\xa9"})
    assert (r.status_code, r.headers.get("location")) == want


def test_a_page_without_a_flash_is_unchanged(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, LANDINGS["activated"][0])
    page = _client(saas_cfg, user).get("/dashboard")
    assert _banners(page.text) == []
    assert _headers(page, "applyfirst_flash") == []
    assert "no-store" not in page.headers.get("cache-control", "")


@pytest.mark.parametrize("path", FIVE_PAGES + ("/onboarding",))
def test_a_signed_out_visitor_never_sees_a_banner(saas_cfg, path):
    db.init_db(saas_cfg.db_path).close()
    c = _hand_flash(_client(saas_cfg), saas_cfg)
    r = c.get(path)
    assert (r.status_code, r.headers["location"]) == (302, "/login")
    assert _headers(r, "applyfirst_flash") == []
    login = c.get("/login")
    assert _banners(login.text) == [] and _headers(login, "applyfirst_flash") == []


@pytest.mark.parametrize("path", ["/", "/login", "/privacy", "/terms"])
def test_other_pages_ignore_the_flash(saas_cfg, master_key, path):
    user = _seed(saas_cfg, master_key, LANDINGS["activated"][0])
    c = _hand_flash(_client(saas_cfg, user), saas_cfg)
    r = c.get(path)
    assert _banners(r.text) == [] and _headers(r, "applyfirst_flash") == []


@pytest.mark.parametrize("state,path", [
    ("new", "/onboarding/keywords"),               # Step 3 without details bounces to Step 2
    ("details-no-keywords", "/onboarding/preview"),  # Step 4 without keywords bounces to Step 3
])
def test_a_step_that_bounces_never_spends_the_flash(saas_cfg, master_key, state, path):
    user = _seed(saas_cfg, master_key, LANDINGS[state][0])
    c = _hand_flash(_client(saas_cfg, user), saas_cfg)
    *hops, landed = _follow(c, path)
    assert hops and all(_headers(r, "applyfirst_flash") == [] for r in hops)
    assert _banner_text(landed.text) == SIGNED_IN


def test_the_page_that_spends_it_is_never_cached(saas_cfg, master_key):
    """Back must re-ask the server (which no longer has a flash), not replay a stored copy."""
    user = _seed(saas_cfg, master_key, LANDINGS["activated"][0])
    page = _hand_flash(_client(saas_cfg, user), saas_cfg).get("/dashboard")
    assert "no-store" in page.headers["cache-control"]


# --- how it reads -----------------------------------------------------------------------------------

def test_the_banner_is_the_calm_green_status_box(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, {})
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg).get("/onboarding/connect_gmail").text
    [banner] = _banners(markup)
    [box] = [e for e in banner.children if has_class(e, "alert")]
    assert has_class(box, "alert--success") and box.attrs.get("role") == "status"
    assert "tabindex" not in box.attrs, "a status line is read, never focused on load"
    assert "data-arrive-gmail" not in banner.attrs
    assert all("data-arrive-gmail" not in e.attrs for e in banner.children)
    assert [e.attrs.get("class") for e in banner.children if e.tag == "strong"] == ["addr-inline"]
    assert not any(has_class(e, "btn--primary") or has_class(e, "btn") for e in banner.children)


def test_the_close_button_is_a_real_hidden_button_outside_the_status_box(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, {})
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg).get("/onboarding/connect_gmail").text
    [banner] = _banners(markup)
    [button] = [e for e in banner.children if e.tag == "button"]
    assert button.attrs.get("type") == "button"
    assert "hidden" in button.attrs, "no JavaScript, no close button"
    assert "data-dismiss" in button.attrs
    assert clean(button.text) == "Dismiss this message"
    [box] = [e for e in banner.children if e.attrs.get("role") == "status"]
    assert button not in box.children, "showing the button must not be announced as news"


def test_a_long_address_breaks_only_after_the_at_or_a_dot(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, LANDINGS["activated"][0], email=LONG_EMAIL)
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg).get("/dashboard").text
    seg = '<span class="addr-seg">{}</span>'.format
    assert "<wbr>".join(map(seg, ("maria.", "clara.", "santos.", "dlcruz@", "gmail.com"))) in markup
    assert _banner_text(markup) == f"Signed in as {LONG_EMAIL}."


def test_a_hyphen_in_the_address_is_never_a_break_point(saas_cfg, master_key):
    """A browser may break after any hyphen. Each piece is an inline-block, so it may not."""
    user = _seed(saas_cfg, master_key, {}, email="maria.no-keywords@my-co.example.com")
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg).get("/onboarding/connect_gmail").text
    seg = '<span class="addr-seg">{}</span>'.format
    assert "<wbr>".join(map(seg, ("maria.", "no-keywords@", "my-co.example.com"))) in markup
    assert _banner_text(markup) == "Signed in as maria.no-keywords@my-co.example.com."
    [rule] = [decls(body) for sel, body, _ in iter_rules(read_css(STATIC / "css" / "app.css"))
              if sel == ".addr-seg"]
    assert rule["display"] == "inline-block" and rule["max-width"] == "100%"
    assert rule["overflow-wrap"] == "anywhere", "a 30-letter Gmail name must still fit a 320px screen"
    assert "white-space" not in rule, "nowrap would push a long piece out of the green box"


def test_the_email_is_escaped_like_any_user_text(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, {}, email="<b>x</b>@example.com")
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg).get("/onboarding/connect_gmail").text
    assert "<b>x</b>" not in markup and "&lt;b&gt;x&lt;/b&gt;@" in markup


@pytest.mark.parametrize("state", ["new", "gmail-no-details", "details-no-keywords",
                                   "ready-no-gmail"])
def test_on_a_step_it_sits_below_the_stepper_and_above_the_heading(saas_cfg, master_key, state):
    spec, where = LANDINGS[state]
    user = _seed(saas_cfg, master_key, spec)
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg).get(where).text
    stepper = _index(markup, lambda e: has_class(e, "stepper"))
    banner = _index(markup, lambda e: has_class(e, "flash"))
    heading = _index(markup, lambda e: e.tag == "h1")
    assert stepper < banner < heading
    main = next(e for e in elements(markup) if has_class(e, "ob-main"))
    assert any(has_class(e, "flash") for e in main.children)


def test_on_the_dashboard_it_sits_above_the_panel_and_outside_the_grid(saas_cfg, master_key):
    user = _seed(saas_cfg, master_key, LANDINGS["activated"][0])
    markup = _hand_flash(_client(saas_cfg, user), saas_cfg, "gmail_connected").get(
        "/dashboard").text
    banner = _index(markup, lambda e: has_class(e, "flash"))
    panel = _index(markup, lambda e: "data-panel" in e.attrs)
    assert banner < panel
    grid = next(e for e in elements(markup) if has_class(e, "dash__grid"))
    assert not any(has_class(e, "flash") for e in grid.children)
    stack = next(e for e in elements(markup) if has_class(e, "dash__stack"))
    assert any(has_class(e, "flash") for e in stack.children)


def test_the_frozen_arrival_counts_hold_with_a_banner(saas_cfg, master_key):
    step2 = _seed(saas_cfg, master_key, LANDINGS["gmail-no-details"][0], sub="a")
    dash = _seed(saas_cfg, master_key, LANDINGS["activated"][0], sub="b",
                 email="dash@example.com")
    s2 = _hand_flash(_client(saas_cfg, step2), saas_cfg, "gmail_connected").get(
        "/onboarding/profile").text
    d = _hand_flash(_client(saas_cfg, dash), saas_cfg, "gmail_connected").get("/dashboard").text
    assert _banners(s2) and _banners(d)
    assert len([e for e in elements(s2) if "data-arrive-gmail" in e.attrs]) == 1
    assert len([e for e in elements(d) if "data-arrive-gmail" in e.attrs]) == 2


def _without_banner(markup: str) -> str:
    """The page with the banner cut out, CSRF values blanked (their iat may tick) and spaces
    collapsed, so two renders compare equal only if the banner is the one difference."""
    markup = re.sub(r'<div class="flash">.*?</button>\s*</div>', "", markup, count=1, flags=re.S)
    markup = re.sub(r'(name="csrf" value=")[^"]*', r"\1", markup)
    return re.sub(r"\s+", " ", markup)


@pytest.mark.parametrize("state", list(LANDINGS))
@pytest.mark.parametrize("code", ["signed_in", "gmail_connected"])
def test_the_banner_adds_itself_and_nothing_else(saas_cfg, master_key, state, code):
    """Every heading, primary button, hook and count on the page stays exactly as it was."""
    spec, where = LANDINGS[state]
    user = _seed(saas_cfg, master_key, spec)
    plain = _client(saas_cfg, user).get(where).text
    flashed = _hand_flash(_client(saas_cfg, user), saas_cfg, code).get(where).text
    assert len(_banners(flashed)) <= 1
    assert _without_banner(flashed) == _without_banner(plain)
    assert count_class(flashed, "btn--primary") == count_class(plain, "btn--primary")


# --- the close button (app.js) and the look (journey.css) ------------------------------------------

APP_JS = STATIC / "js" / "app.js"


def test_app_js_shows_the_close_button_and_hands_focus_to_the_page():
    source = APP_JS.read_text(encoding="utf-8")
    block = source[source.index("[data-dismiss]"):]
    assert re.search(r"\.hidden\s*=\s*false", block), "JS reveals the hidden close button"
    assert re.search(r'getElementById\("main"\)', block) and ".focus(" in block
    assert re.search(r"\.remove\(\)", block)


def test_a_page_restored_by_back_drops_the_banner():
    source = APP_JS.read_text(encoding="utf-8")
    show = source.index('addEventListener("pageshow"')
    handler = source[show:source.index("});", show)]
    assert ".flash" in handler and ".remove()" in handler


def _flash_rules():
    return [(sel, decls(body), chain) for sel, body, chain in iter_rules(read_css(JOURNEY_CSS))
            if "flash" in sel]


def test_the_close_button_has_a_whole_44px_tap_area_that_can_grow():
    rules = [(sel, d) for sel, d, chain in _flash_rules() if chain == ("@layer journey",)]
    close = {k: v for sel, d in rules if sel.strip() == ".flash__close" for k, v in d.items()}
    assert close.get("min-width") == "44px" and close.get("min-height") == "44px"
    assert all(close.get(p, "auto") == "auto" for p in ("width", "height"))
    pad = {k: v for sel, d in rules if sel.strip() == ".flash>.alert" for k, v in d.items()}
    assert int(pad["padding-right"].removesuffix("px")) >= 48, "text never runs under the button"


def test_the_banner_never_moves_fades_or_hides():
    """Static in every motion setting, so nothing to reduce: no transition, animation, opacity or
    transform on it, and it is never a reveal target."""
    moving = [(sel, p) for sel, d, _chain in _flash_rules() for p in d
              if re.match(r"(?:transition|animation|opacity|transform|translate|visibility)", p)]
    assert moving == []
    reveal = (STATIC / "js" / "reveal.js").read_text(encoding="utf-8")
    assert "flash" not in reveal


def test_the_banner_rules_live_in_the_components_section():
    raw = JOURNEY_CSS.read_bytes().decode("utf-8")
    start, end = raw.index("/* ---- 5 components */"), raw.index("/* ---- 6 chrome */")
    assert raw.count(".flash") == raw[start:end].count(".flash") > 0
