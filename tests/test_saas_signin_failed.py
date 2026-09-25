"""D8 and D9 of the sign-up redesign (spec 6.4, 6.5 and 7).

D8: every /auth/callback failure shows ONE styled page, "Sign-in didn't finish": status 400,
text/html, the frozen CSP, the oauth transaction cookie cleared, nothing stored and no session
set. The page is the same bytes whatever went wrong, so it is no oracle, and the reason goes to
the server log only.

D9: a signed-out GET of an onboarding page, Connect Gmail or its callback gets a 302 to /login
instead of a 401 JSON reply. POST routes and the JSON API keep today's 401 and 403.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.routing import APIRoute

from applyfirst.saas import app as app_module
from applyfirst.saas import google_oauth, session, static_assets
from applyfirst.saas.app import create_app
from _journey_css import JOURNEY_CSS, JOURNEY_TEMPLATES, TEMPLATES, decls, iter_rules
from _saas_client import (
    EXPECTED_CSP, clean, client_for, count_class, db_conn, elements, page_text, seed_user,
    txn_cookie_cleared,
)

TITLE = "Sign-in didn't finish"
LINE = "You can try again, it only takes a moment."
HOME_LINK = "Back to the homepage"
OLD_JSON = "sign-in failed; please try again"
PROBE = "<script>alert(9)</script>"
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")     # test M-2
REASONS = ("google_error", "state", "no_code", "exchange")


# --- D8: how a sign-in can fail ---------------------------------------------------------------

def _boom(exc):
    def raise_it(*a, **kw):
        raise exc
    return raise_it


def _start(c) -> str:
    """Begin a real sign-in (sets the oauth txn cookie) and return its state."""
    loc = c.get("/auth/login").headers["location"]
    return parse_qs(urlparse(loc).query)["state"][0]


def _cancel(c, cfg, mp):
    _start(c)
    return c.get("/auth/callback", params={"error": "access_denied", "error_description": PROBE})


def _no_txn(c, cfg, mp):
    return c.get("/auth/callback", params={"code": "c", "state": "s"})


def _no_state(c, cfg, mp):
    _start(c)
    return c.get("/auth/callback", params={"code": "c"})


def _wrong_state(c, cfg, mp):
    _start(c)
    return c.get("/auth/callback", params={"code": "c", "state": "WRONG"})


def _expired_txn(c, cfg, mp):
    c.cookies.set("applyfirst_oauth", session.sign(cfg.session_secret, {
        "state": "s", "nonce": "n", "verifier": "v", "iat": int(time.time()) - 1200}))
    return c.get("/auth/callback", params={"code": "c", "state": "s"})


def _forged_txn(c, cfg, mp):
    c.cookies.set("applyfirst_oauth", session.sign(b"not-the-server-secret-32-bytes!!!", {
        "state": "s", "nonce": "n", "verifier": "v"}))
    return c.get("/auth/callback", params={"code": "c", "state": "s"})


def _no_code(c, cfg, mp):
    return c.get("/auth/callback", params={"state": _start(c)})


def _exchange(c, cfg, mp):
    mp.setattr(google_oauth, "fetch_identity", _boom(google_oauth.OAuthError("nonce mismatch")))
    return c.get("/auth/callback", params={"code": "c", "state": _start(c)})


# Every branch of auth_callback that fails, with the reason the server logs for it.
FAILURES = {"cancel": (_cancel, "google_error"), "no_txn": (_no_txn, "state"),
            "no_state": (_no_state, "state"), "wrong_state": (_wrong_state, "state"),
            "expired_txn": (_expired_txn, "state"), "forged_txn": (_forged_txn, "state"),
            "no_code": (_no_code, "no_code"), "exchange": (_exchange, "exchange")}


def _fail(cfg, mp, kind: str, user=None):
    """Run one failure with the Google exchange armed to explode: only the exchange case may
    reach it, so every other case proves the check happens before any call to Google."""
    mp.setattr(google_oauth, "fetch_identity",
               _boom(AssertionError("the callback called Google after a failed check")))
    return FAILURES[kind][0](client_for(cfg, user), cfg, mp)


def _no_rate_limit(cfg):
    return dataclasses.replace(cfg, auth_rate_limit=0)


def _users(cfg) -> int:
    with db_conn(cfg) as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


@pytest.mark.parametrize("kind", FAILURES)
def test_every_callback_failure_is_the_400_page(saas_cfg, monkeypatch, caplog, kind):
    with caplog.at_level(logging.WARNING, logger="applyfirst.saas.app"):
        r = _fail(saas_cfg, monkeypatch, kind)
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert txn_cookie_cleared(r)
    assert not [h for h in r.headers.get_list("set-cookie") if h.startswith("applyfirst_session=")]
    assert _users(saas_cfg) == 0, "a failed sign-in stores nobody"
    assert [clean(e.text) for e in elements(r.text) if e.tag == "h1"] == [TITLE]
    assert OLD_JSON not in r.text and not r.text.lstrip().startswith("{")
    # The reason goes to the server log only, once, and never reaches the page.
    logged = [rec for rec in caplog.records if rec.getMessage() == "signin_failed"]
    assert [rec.fields for rec in logged] == [{"reason": FAILURES[kind][1]}]
    text = page_text(r.text).lower()
    for word in REASONS + ("access_denied", "nonce", "token", "error"):
        assert word not in text, f"the page says {word!r}"


def test_the_page_is_the_same_bytes_whatever_went_wrong(saas_cfg, monkeypatch):
    cfg = _no_rate_limit(saas_cfg)
    bodies = {}
    for kind in FAILURES:
        with monkeypatch.context() as mp:
            bodies[kind] = _fail(cfg, mp, kind).text
    assert len(set(bodies.values())) == 1, sorted(bodies)


def test_a_signed_in_visitor_gets_the_same_page(saas_cfg, monkeypatch):
    """The page never reads the session, so it cannot differ for someone already signed in."""
    cfg = _no_rate_limit(saas_cfg)
    anon = _fail(cfg, monkeypatch, "wrong_state").text
    signed = _fail(cfg, monkeypatch, "wrong_state", user=seed_user(cfg)).text
    assert signed == anon
    assert 'name="csrf"' not in signed and "Log out" not in signed


def test_nothing_google_sends_back_is_reflected(saas_cfg, monkeypatch):
    r = _fail(saas_cfg, monkeypatch, "cancel")
    assert PROBE not in r.text and "alert(9)" not in r.text


# --- D8: the page itself (spec 6.4) -------------------------------------------------------------

def _page(cfg, mp) -> str:
    return _fail(cfg, mp, "cancel").text


def test_the_page_says_what_happened_and_offers_one_way_back_in(saas_cfg, monkeypatch):
    markup = _page(saas_cfg, monkeypatch)
    text = page_text(markup)
    where = [text.find(s) for s in (TITLE, LINE, "Continue with Google", HOME_LINK)]
    assert -1 not in where and where == sorted(where), where
    ui = app_module._TEMPLATES.env.get_template("_ui.html").module
    assert markup.count(str(ui.google_button(block=True))) == 1, "the macro, untouched"
    assert markup.count('class="gsi-btn') == 1
    home = [e for e in elements(markup) if e.tag == "a" and clean(e.text) == HOME_LINK]
    assert len(home) == 1 and home[0].attrs.get("href") == "/"
    assert "<form" not in markup, "a signed-out page has no form"
    assert "Agad" in re.search(r"<title>(.*?)</title>", markup, re.S).group(1)


def test_the_page_wears_the_journey_look(saas_cfg, monkeypatch):
    assert "signin_failed.html" in JOURNEY_TEMPLATES
    markup = _page(saas_cfg, monkeypatch)
    sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)">', markup)
    assert sheets == [static_assets.static_url(p) for p in (
        "css/app.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css")]
    assert markup.index(sheets[-1]) < markup.index(static_assets.static_url("js/reveal.js"))
    metas = {e.attrs.get("name"): e.attrs for e in elements(markup) if e.tag == "meta"}
    assert metas["color-scheme"]["content"] == "light dark"
    themes = [e.attrs.get("media") for e in elements(markup)
              if e.tag == "meta" and e.attrs.get("name") == "theme-color"]
    assert themes == ["(prefers-color-scheme: light)", "(prefers-color-scheme: dark)"]
    assert re.search(r'<body class="is-auth">', markup), "the login card layout"
    assert count_class(markup, "site-header") == 1


def test_the_page_stays_a_public_page(saas_cfg, monkeypatch):
    """No motion head (M-2), no step on <html> (M-9), no preload of Inter (spec 4.5)."""
    markup = _page(saas_cfg, monkeypatch)
    assert [a for a in MOTION_ASSETS if a in markup] == []
    assert "data-step" not in re.search(r"<html\b[^>]*>", markup).group(0)
    assert [t for t in re.findall(r"<link\b[^>]*>", markup) if "inter" in t.lower()] == []


# --- D8: journey.css section 10 -----------------------------------------------------------------

def _section(number: int) -> str:
    raw = JOURNEY_CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = raw.index(f"/* ---- {number} ")
    end = raw.index("/* ---- ", start + 1)
    return re.sub(r"/\*.*?\*/", "", raw[start:end], flags=re.S)


def test_section_10_styles_only_this_page_and_moves_nothing():
    rules = list(iter_rules(_section(10)))
    assert rules, "section 10 holds the page's own rules"
    for selectors, body, _chain in rules:
        assert all(s.strip().startswith(".auth__icon") for s in selectors.split(",")), selectors
        assert not [p for p in decls(body) if p.startswith(("transition", "animation"))], (
            f"{selectors}: motion belongs in section 11")
    others = [p.name for p in TEMPLATES.glob("*.html")
              if p.name != "signin_failed.html" and "auth__icon" in p.read_text(encoding="utf-8")]
    assert others == []


def test_the_icon_well_uses_the_calm_attention_tokens():
    props = {}
    for selectors, body, _chain in iter_rules(_section(10)):
        if selectors.strip() == ".auth__icon":
            props.update(decls(body))
    assert props.get("background") == "var(--j-attn-bg)"
    assert props.get("color") == "var(--j-attn-fg)"


# --- D9: signed-out visits (spec 6.5) -----------------------------------------------------------

SPEC_PAGES = ("/onboarding", "/onboarding/connect_gmail", "/onboarding/profile",
              "/onboarding/keywords", "/onboarding/preview", "/auth/connect-gmail",
              "/auth/gmail-callback")


def _dependency_names(dependant) -> set[str]:
    names: set[str] = set()
    for dep in dependant.dependencies:
        names.add(getattr(dep.call, "__name__", ""))
        names |= _dependency_names(dep)
    return names


def _routes_using(app, name: str) -> set[tuple[str, str]]:
    return {(method, route.path) for route in app.routes if isinstance(route, APIRoute)
            for method in route.methods if name in _dependency_names(route.dependant)}


def test_the_login_redirect_guards_exactly_the_spec_pages(saas_cfg):
    app = create_app(saas_cfg)
    assert _routes_using(app, "require_user_or_login") == {("GET", p) for p in SPEC_PAGES}
    assert _routes_using(app, "require_user") == {
        ("GET", "/me"), ("GET", "/api/oauth-credentials/{cred_id}"),
        ("POST", "/auth/logout"), ("POST", "/onboarding/profile"),
        ("POST", "/onboarding/keywords"), ("POST", "/onboarding/keywords/{keyword_id}/delete"),
        ("POST", "/onboarding/activate"), ("POST", "/auth/disconnect-gmail")}


@pytest.mark.parametrize("path", SPEC_PAGES + (
    "/onboarding/profile?error=1", "/onboarding/connect_gmail?gmail_error=scope",
    "/auth/gmail-callback?error=access_denied", "/auth/gmail-callback?code=c&state=s"))
def test_a_signed_out_visit_goes_to_login(saas_cfg, monkeypatch, path):
    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail",
                        _boom(AssertionError("a signed-out callback reached Google")))
    r = client_for(saas_cfg).get(path)
    assert r.status_code == 302
    assert r.headers["location"] == "/login", "no next= parameter (spec 6.5)"
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert "json" not in r.headers.get("content-type", "")
    assert not [h for h in r.headers.get_list("set-cookie") if h.startswith("applyfirst_oauth=")]


@pytest.mark.parametrize("cookie", ["forged", "expired", "deleted_user"])
def test_a_session_that_names_nobody_also_goes_to_login(saas_cfg, cookie):
    user = seed_user(saas_cfg)
    secret, payload = saas_cfg.session_secret, {"uid": user.id}
    if cookie == "forged":
        secret = b"not-the-server-secret-32-bytes!!!"
    elif cookie == "expired":
        payload["iat"] = int(time.time()) - 8 * 24 * 3600
    else:
        with db_conn(saas_cfg) as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user.id,))
            conn.commit()
    c = client_for(saas_cfg)
    c.cookies.set("applyfirst_session", session.sign(secret, payload))
    for path in SPEC_PAGES:
        r = c.get(path)
        assert (r.status_code, r.headers.get("location")) == (302, "/login"), path


def test_the_redirect_lands_on_a_page_that_renders(saas_cfg):
    c = client_for(saas_cfg)
    assert c.get("/onboarding").headers["location"] == "/login"
    assert c.get("/login").status_code == 200


SIGNED_OUT_POSTS = [("/onboarding/profile", {"full_name": "A", "job_type": "B",
                                             "standard_subject": "C", "standard_message": "D"}),
                    ("/onboarding/keywords", {"keyword": "va"}),
                    ("/onboarding/keywords/k1/delete", {}), ("/onboarding/activate", {}),
                    ("/auth/logout", {}), ("/auth/disconnect-gmail", {})]


@pytest.mark.parametrize("path,data", SIGNED_OUT_POSTS, ids=[p for p, _ in SIGNED_OUT_POSTS])
def test_signed_out_posts_keep_their_401(saas_cfg, path, data):
    r = client_for(saas_cfg).post(path, data={**data, "csrf": "x"})
    assert r.status_code == 401
    assert r.json() == {"detail": "authentication required"}


@pytest.mark.parametrize("path,data", SIGNED_OUT_POSTS, ids=[p for p, _ in SIGNED_OUT_POSTS])
def test_signed_in_posts_without_a_token_keep_their_403(saas_cfg, path, data):
    r = client_for(saas_cfg, seed_user(saas_cfg)).post(path, data=data)
    assert r.status_code == 403
    assert r.json() == {"detail": "invalid or missing CSRF token"}


@pytest.mark.parametrize("path", ["/me", "/api/oauth-credentials/x"])
def test_the_json_api_keeps_its_401(saas_cfg, path):
    r = client_for(saas_cfg).get(path)
    assert r.status_code == 401
    assert r.json() == {"detail": "authentication required"}


# (who, path, status, location): what a signed-in visitor gets today, unchanged by D9.
SIGNED_IN = [
    ("fresh", "/onboarding", 302, "/onboarding/connect_gmail"),
    ("fresh", "/onboarding/connect_gmail", 200, None),
    ("fresh", "/onboarding/profile", 200, None),
    ("fresh", "/onboarding/keywords", 302, "/onboarding/profile"),
    ("fresh", "/onboarding/preview", 302, "/onboarding/profile"),
    ("fresh", "/auth/connect-gmail", 302, google_oauth.AUTH_URI),
    ("fresh", "/auth/gmail-callback?error=access_denied", 400, None),
    ("done", "/onboarding", 302, "/dashboard"),
    ("done", "/onboarding/keywords", 200, None),
    ("done", "/onboarding/preview", 200, None),
]


@pytest.mark.parametrize("who,path,status,where", SIGNED_IN,
                         ids=[f"{w}:{p}" for w, p, _, _ in SIGNED_IN])
def test_signed_in_visits_are_unchanged(saas_cfg, who, path, status, where):
    user = (seed_user(saas_cfg) if who == "fresh"
            else seed_user(saas_cfg, activated=True, keywords=("va",)))
    r = client_for(saas_cfg, user).get(path)
    assert r.status_code == status
    if where is None:
        assert "location" not in r.headers
    else:
        assert r.headers["location"].startswith(where)
