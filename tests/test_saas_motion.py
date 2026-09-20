"""Static guards for the onboarding motion layer (spec onboarding-motion.md 11.1, M-1 to M-20).

The motion layer is a contract, not a look. It may only load on the five signed-in app pages,
only in the one locked head order, only inside a ``prefers-reduced-motion: no-preference``
block, and only within a byte budget — and the one vendored library is pinned by sha256
because its bytes ship to every user who celebrates. None of that shows up in an ordinary page
test, so every frozen rule is asserted here: head order and page weight, the reversible brand
patch on canvas-confetti, a small CSS parser over motion.css, the server-printed ``data-fresh``,
``data-arrive-gmail``, ``data-burst-src`` and ``data-step`` hooks, the "Watching since" line,
and cheap string guards over vt.js.

Nothing here touches a route, a redirect, a CSRF field or the Content-Security-Policy.
"""

from __future__ import annotations

import gzip
import hashlib
import math
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pytest
from jinja2 import ChoiceLoader, DictLoader

from applyfirst.saas import app as app_module
from applyfirst.saas import static_assets
from _saas_client import (
    EXPECTED_CSP, clean, client_for, count_class, db_conn, elements, has_class, page_text,
    post_forms, seed_user,
)

SAAS = Path(static_assets.__file__).parent
REPO = SAAS.parents[1]
STATIC = SAAS / "static"
TEMPLATES = SAAS / "templates"

MOTION_CSS = STATIC / "css" / "motion.css"
APP_CSS = STATIC / "css" / "app.css"
VT_JS = STATIC / "js" / "vt.js"
MOTION_JS = STATIC / "js" / "motion.js"
VENDOR_JS = STATIC / "vendor" / "canvas-confetti-1.9.4.js"
VENDOR_LICENCE = STATIC / "licenses" / "canvas-confetti-ISC.txt"
# app.js is an own file for the pattern scans (M-5); only these two are "own JS" for the
# byte budget (spec 4.1: app.js gains nothing from this spec).
OWN_JS = sorted(STATIC.glob("js/*.js"))
MOTION_JS_FILES = [VT_JS, MOTION_JS]

ONBOARDING_PAGES = ("/onboarding/connect_gmail", "/onboarding/profile", "/onboarding/keywords",
                    "/onboarding/preview")
APP_PAGES = ONBOARDING_PAGES + ("/dashboard",)
NON_APP_PAGES = ("/", "/login", "/privacy", "/terms")
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")

MASTER_KEY = b"0123456789abcdef0123456789abcdef"
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


# --- shared helpers -----------------------------------------------------------------------

def _lf_bytes(path: Path) -> bytes:
    """The file's bytes with CRLF normalised to LF, so a Windows checkout hashes the same."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _gz(path: Path) -> int:
    return len(gzip.compress(_lf_bytes(path), 9, mtime=0))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _matching(text: str, open_paren: int) -> str:
    """The text between ``text[open_paren]`` ('(') and its matching ')'."""
    assert text[open_paren] == "("
    depth, i = 0, open_paren
    while i < len(text):
        depth += (text[i] == "(") - (text[i] == ")")
        if depth == 0:
            return text[open_paren + 1:i]
        i += 1
    raise AssertionError("unbalanced parentheses")


def _onboarding_client(cfg, *, gmail: bool = True, activated: bool = False, sub: str = "ob",
                       keywords: tuple[str, ...] = ("virtual assistant",)):
    """A signed-in client whose user can render all four onboarding steps."""
    user = seed_user(cfg, sub=sub, email=f"{sub}@example.com", profile=True, keywords=keywords,
                     activated=activated, gmail_key=MASTER_KEY if gmail else None)
    return client_for(cfg, user), user


def _dashboard_client(cfg, *, gmail: bool = True, sub: str = "dash",
                      keywords: tuple[str, ...] = ("virtual assistant",)):
    user = seed_user(cfg, sub=sub, email=f"{sub}@example.com", activated=True, keywords=keywords,
                     gmail_key=MASTER_KEY if gmail else None)
    return client_for(cfg, user), user


def _five_pages(cfg) -> dict[str, str]:
    """The five app pages, each rendered in the state that shows its motion hooks."""
    ob, _ = _onboarding_client(cfg)
    dash, _ = _dashboard_client(cfg)
    pages = {path: ob.get(path).text for path in ONBOARDING_PAGES}
    pages["/dashboard"] = dash.get("/dashboard").text
    return pages


def _set_times(cfg, user, *, activated_at: str | None = None, gmail_at: str | None = None):
    """Rewrite the two timestamps "Watching since" reads (4.4)."""
    with db_conn(cfg) as conn:
        if activated_at is not None:
            conn.execute("UPDATE user_profiles SET activated_at=? WHERE user_id=?",
                         (activated_at, user.id))
        if gmail_at is not None:
            conn.execute("UPDATE oauth_credentials SET updated_at=? WHERE user_id=?",
                         (gmail_at, user.id))
        conn.commit()


def _freeze(monkeypatch, iso: str) -> datetime:
    """Freeze the server clock seam (app._utcnow) that the dashboard route reads."""
    now = datetime.strptime(iso, TS_FMT).replace(tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "_utcnow", lambda: now)
    return now


def _shift(iso: str, seconds: int) -> str:
    return (datetime.strptime(iso, TS_FMT) + timedelta(seconds=seconds)).strftime(TS_FMT)


@contextmanager
def _celebrate_off():
    """Render with the owner switch ``CELEBRATE`` set to false, then put _ui.html back."""
    env = app_module._TEMPLATES.env
    source = _text(TEMPLATES / "_ui.html")
    patched = source.replace("{% set CELEBRATE = true %}", "{% set CELEBRATE = false %}", 1)
    assert patched != source, "_ui.html no longer carries the CELEBRATE switch"
    original = env.loader
    env.loader = ChoiceLoader([DictLoader({"_ui.html": patched}), original])
    if env.cache is not None:
        env.cache.clear()
    try:
        yield
    finally:
        env.loader = original
        if env.cache is not None:
            env.cache.clear()


def _attr_elements(markup: str, attr: str):
    return [e for e in elements(markup) if attr in e.attrs]


# --- a very small CSS reader (used by M-6, M-14, M-16, M-17, M-18) -------------------------

_CONTAINERS = ("@media", "@supports", "@layer", "@container", "@scope", "@starting-style")
_TIME = re.compile(r"-?\d*\.?\d+m?s", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_IDENT = re.compile(r"-?[A-Za-z_][\w-]*")
_ANIM_KEYWORDS = {
    "normal", "reverse", "alternate", "alternate-reverse", "none", "forwards", "backwards",
    "both", "running", "paused", "infinite", "ease", "ease-in", "ease-out", "ease-in-out",
    "linear", "step-start", "step-end", "inherit", "initial", "unset", "revert",
}


class Rule(NamedTuple):
    kind: str            # "style" or "keyframes"
    chain: tuple         # the at-rule preludes wrapping it, outermost first
    prelude: str         # the selector, or "@keyframes af-dot"
    body: str


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _split_blocks(css: str) -> list[tuple[str, str]]:
    """(prelude, body) for every brace-matched block at this level. Bare statements skipped."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(css)
    while i < n:
        brace, semi = css.find("{", i), css.find(";", i)
        if brace < 0:
            break
        if 0 <= semi < brace:                      # e.g. "@layer reset, tokens, ...;"
            i = semi + 1
            continue
        depth, k = 1, brace + 1
        while k < n and depth:
            depth += (css[k] == "{") - (css[k] == "}")
            k += 1
        out.append((css[i:brace].strip(), css[brace + 1:k - 1]))
        i = k
    return out


def _rules(css: str, chain: tuple = ()) -> list[Rule]:
    """Every style rule and @keyframes block, each with the at-rules wrapping it."""
    found: list[Rule] = []
    for prelude, body in _split_blocks(css):
        if prelude.startswith("@keyframes"):
            found.append(Rule("keyframes", chain, prelude, body))
        elif prelude.startswith(_CONTAINERS):
            found.extend(_rules(body, chain + (prelude,)))
        else:
            found.append(Rule("style", chain, prelude, body))
    return found


def _decls(body: str) -> list[tuple[str, str]]:
    """(property, value) pairs of one declaration block, nested blocks dropped."""
    body = re.sub(r"[^{}]*\{[^{}]*\}", " ", body)
    out = []
    for part in body.split(";"):
        prop, sep, value = part.partition(":")
        if sep and prop.strip():
            out.append((prop.strip().lower(), value.strip()))
    return out


def _tokens(value: str) -> list[str]:
    """Whitespace-split, but keeping var(...) / cubic-bezier(...) / linear(...) whole."""
    out, depth, current = [], 0, ""
    for ch in value:
        depth += (ch == "(") - (ch == ")")
        if ch.isspace() and depth == 0:
            if current:
                out.append(current)
            current = ""
        else:
            current += ch
    if current:
        out.append(current)
    return out


def _ms(value: str) -> float | None:
    token = value.strip()
    if not _TIME.fullmatch(token):
        return None
    return float(token[:-2]) if token.lower().endswith("ms") else float(token[:-1]) * 1000


class Anim(NamedTuple):
    name: str | None
    duration: float | None
    delay: float
    iterations: float


def _animation(decls: list[tuple[str, str]]) -> Anim | None:
    """The animation one rule declares, shorthand and longhands together. None when it has no
    animation, or sets it to ``none``."""
    name, duration, delay, iterations, seen = None, None, None, None, False
    for prop, value in decls:
        if prop == "animation":
            seen = True
            if value.strip() == "none":
                return None
            toks = _tokens(value)
            times = [t for t in toks if _TIME.fullmatch(t)]
            if times:
                duration = _ms(times[0])
            if len(times) > 1:
                delay = _ms(times[1])
            for tok in toks:
                if tok == "infinite":
                    iterations = math.inf
                elif _NUMBER.fullmatch(tok):
                    iterations = float(tok)
            names = [t for t in toks if _IDENT.fullmatch(t) and t.lower() not in _ANIM_KEYWORDS]
            if names:
                name = names[-1]
        elif prop == "animation-name":
            seen = True
            if value.strip() == "none":
                return None
            name = value.strip()
        elif prop == "animation-duration":
            seen, duration = True, _ms(value)
        elif prop == "animation-delay":
            seen, delay = True, _ms(value)
        elif prop == "animation-iteration-count":
            seen = True
            iterations = math.inf if value.strip() == "infinite" else float(value.strip())
    if not seen:
        return None
    return Anim(name, duration, delay or 0.0, iterations if iterations is not None else 1.0)


def _no_preference(chain: tuple) -> bool:
    return any(re.search(r"prefers-reduced-motion\s*:\s*no-preference", link) for link in chain)


MOTION_RULES = _rules(_strip_comments(_text(MOTION_CSS)))
APP_RULES = _rules(_strip_comments(_text(APP_CSS)))
# The one animation the spec lets run forever: the busy spinner on a link or button (6.11).
_SPINNER = ("btn__spin", 'data-state="busy"')


def _is_spinner(selector: str) -> bool:
    return any(marker in selector for marker in _SPINNER)


# --- M-1 -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", APP_PAGES)
def test_the_motion_head_keeps_its_locked_order_on_every_app_page(saas_cfg, path):
    markup = _five_pages(saas_cfg)[path]
    tags = re.findall(r"<(?:link|script)\b[^>]*>", markup)
    at = {}
    for index, tag in enumerate(tags):
        for asset in ("css/app.css", "css/motion.css", "js/vt.js", "js/motion.js"):
            if asset in tag:
                at[asset] = (index, tag)
    assert set(at) == {"css/app.css", "css/motion.css", "js/vt.js", "js/motion.js"}, path
    assert at["css/app.css"][0] < at["css/motion.css"][0] < at["js/vt.js"][0] < \
        at["js/motion.js"][0], f"{path}: head order is locked (4.2, MG-31)"
    vt_tag = at["js/vt.js"][1]
    assert not re.search(r"\s(?:async|defer|type)\b", vt_tag), (
        f"{path}: vt.js must be classic and parser-blocking, got {vt_tag}")
    assert re.search(r"\sdefer\b", at["js/motion.js"][1]), f"{path}: motion.js must be deferred"
    first_script = next(i for i, tag in enumerate(tags) if tag.lower().startswith("<script"))
    assert first_script > at["css/motion.css"][0], f"{path}: no <script> may precede motion.css"


# --- M-2 -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", NON_APP_PAGES)
def test_the_public_pages_gain_no_motion_bytes(saas_cfg, path):
    markup = client_for(saas_cfg).get(path).text
    found = [asset for asset in MOTION_ASSETS if asset in markup]
    assert found == [], f"{path} loads {found} (MG-01, MG-32)"


@pytest.mark.parametrize("method,path", [("GET", "/nope"), ("POST", "/"), ("POST", "/privacy")])
def test_the_json_error_bodies_name_no_motion_file(saas_cfg, method, path):
    resp = client_for(saas_cfg).request(method, path)
    assert resp.headers["content-type"].startswith("application/json")
    found = [asset for asset in MOTION_ASSETS if asset in resp.text]
    assert found == [], f"{method} {path} JSON body names {found}"


def test_app_js_stays_out_of_the_motion_layer():
    source = _text(STATIC / "js" / "app.js")
    found = [word for word in ("pagereveal", "view-transition", "confetti") if word in source]
    assert found == [], f"app.js must not do motion work, found {found}"


# --- M-3 -----------------------------------------------------------------------------------

def test_every_motion_file_stays_inside_its_gzip_cap():
    motion_css, vt_js, motion_js = _gz(MOTION_CSS), _gz(VT_JS), _gz(MOTION_JS)
    own = vt_js + motion_js
    assert motion_css <= 2850, f"motion.css gzip {motion_css} B"
    assert vt_js <= 1900, f"vt.js gzip {vt_js} B"
    assert motion_css + vt_js <= 4700, f"render-blocking pair gzip {motion_css + vt_js} B"
    assert motion_js <= 3000, f"motion.js gzip {motion_js} B"
    assert own <= 4500, f"own motion JS gzip {own} B"
    assert own + _gz(VENDOR_JS) <= 11500, f"own JS plus the vendored file {own + _gz(VENDOR_JS)} B"


# --- M-4 -----------------------------------------------------------------------------------

UPSTREAM_SHA = "49f4bcbc56e7ceb5c3d25d13db1d0da965b6cd1c8a54a707bb055be0685b0a95"
PATCHED_SHA = "26f0bb1c55f14db7d1782d243af60a3d090e103ddf5526ffd4a689088cc0e98e"
# Spec 10.1, verbatim, LF line endings. The brand block is the only change we vendor.
UPSTREAM_COLOURS = b"""    colors: [
      '#26ccff',
      '#a25afd',
      '#ff5e7e',
      '#88ff5a',
      '#fcff42',
      '#ffa62d',
      '#ff36ff'
    ],"""
BRAND_COLOURS = b"""    colors: [
      '#38AEEA',
      '#86CBF2',
      '#0B6BC7'
    ],"""


def test_the_vendored_library_is_the_pinned_brand_patched_build():
    data = _lf_bytes(VENDOR_JS)
    assert hashlib.sha256(data).hexdigest() == PATCHED_SHA
    assert data.count(BRAND_COLOURS) == 1, "the brand colours block must appear exactly once"
    assert UPSTREAM_COLOURS not in data


def test_undoing_the_colour_patch_gives_back_the_upstream_file():
    data = _lf_bytes(VENDOR_JS)
    restored = data.replace(BRAND_COLOURS, UPSTREAM_COLOURS, 1)
    assert hashlib.sha256(restored).hexdigest() == UPSTREAM_SHA, (
        "the colours must be the only difference from upstream canvas-confetti 1.9.4")


def test_the_vendored_library_stays_inside_its_gzip_cap():
    assert _gz(VENDOR_JS) <= 7000, f"vendored canvas-confetti gzip {_gz(VENDOR_JS)} B"


def test_the_vendored_licence_names_the_author_and_our_modification():
    licence = _text(VENDOR_LICENCE)
    assert "Kiril Vatev" in licence
    assert "Modified by Agad" in licence


def test_gitattributes_keeps_the_vendor_folder_byte_for_byte():
    assert "applyfirst/saas/static/vendor/** -text" in _text(REPO / ".gitattributes")


# --- M-5 -----------------------------------------------------------------------------------

BANNED_JS = ("eval(", "new Function", "Function(", "innerHTML", "outerHTML",
             "insertAdjacentHTML", "document.write", "fetch(", "XMLHttpRequest", "new Worker",
             "Blob(", "importScripts")
_STRING_TIMER = re.compile(r"set(?:Timeout|Interval)\s*\(\s*[\"'`]")


@pytest.mark.parametrize("path", OWN_JS, ids=lambda p: p.name)
def test_our_own_javascript_needs_nothing_the_csp_forbids(path):
    source = _text(path)
    found = [pattern for pattern in BANNED_JS if pattern in source]
    assert found == [], f"{path.name}: {found}"
    assert not _STRING_TIMER.search(source), f"{path.name}: no string timers"


@pytest.mark.parametrize("path", OWN_JS, ids=lambda p: p.name)
def test_our_own_javascript_never_uses_the_confetti_default_call(path):
    source = _text(path)
    assert "confetti(" not in source, f"{path.name}: the default call needs a blob: Worker"
    assert "confetti.reset(" not in source, f"{path.name}: the global reset needs one too"


def test_every_confetti_create_call_turns_the_worker_off():
    source = _text(MOTION_JS)
    sites = list(re.finditer(r"confetti\.create\(", source))
    assert sites, "motion.js must build its own confetti instance"
    for site in sites:
        args = _matching(source, site.end() - 1)
        assert re.search(r"useWorker\s*:\s*false", args), f"create() without useWorker: false"


def test_every_burst_call_passes_the_brand_colours():
    source = _text(MOTION_JS)
    made = re.search(r"const\s+(\w+)\s*=\s*window\.confetti\.create\(", source)
    assert made, "expected `const X = window.confetti.create(` in motion.js"
    calls = [_matching(source, m.end() - 1)
             for m in re.finditer(rf"\b{made.group(1)}\s*\(", source)]
    assert calls, f"{made.group(1)} is created but never fired"
    for args in calls:
        assert "colors:" in args, "every burst must name its colours explicitly (R5)"


# --- M-6 -----------------------------------------------------------------------------------

KEYFRAME_PROPERTIES = {"opacity", "transform", "translate", "scale", "background-color"}


def test_motion_css_parses_into_rules():
    assert len(MOTION_RULES) > 40, "the CSS reader found almost nothing to check"
    assert any(r.kind == "keyframes" for r in MOTION_RULES)


def test_every_motion_css_animation_is_opt_in():
    outside = []
    for rule in MOTION_RULES:
        if rule.kind == "keyframes" and not _no_preference(rule.chain):
            outside.append(rule.prelude)
        if rule.kind == "style" and not _no_preference(rule.chain):
            if rule.prelude.startswith("@view-transition"):
                outside.append(rule.prelude)
            for prop, value in _decls(rule.body):
                if prop in ("animation", "animation-name") and value.strip() != "none":
                    outside.append(f"{rule.prelude} {{ {prop}: {value} }}")
                if prop == "transition":
                    outside.append(f"{rule.prelude} {{ {prop}: {value} }}")
    assert outside == [], f"outside prefers-reduced-motion: no-preference: {outside} (MG-22)"


def test_motion_css_never_asks_for_a_will_change_layer():
    assert "will-change" not in _text(MOTION_CSS), "MG-12"


def test_keyframes_animate_only_compositor_safe_properties():
    bad = []
    for rule in MOTION_RULES:
        if rule.kind != "keyframes":
            continue
        name = rule.prelude.split()[-1]
        allowed = KEYFRAME_PROPERTIES | ({"border-radius"} if name == "af-fill" else set())
        for _selector, body in _split_blocks(rule.body):
            for prop, _value in _decls(body):
                if prop not in allowed:
                    bad.append(f"{name}: {prop}")
    assert bad == [], f"MG-11 allows only {sorted(KEYFRAME_PROPERTIES)} (+ border-radius in af-fill): {bad}"


def test_only_the_busy_spinner_runs_forever():
    forever = [r.prelude for r in MOTION_RULES if r.kind == "style"
               and (_animation(_decls(r.body)) or Anim(None, None, 0, 1)).iterations == math.inf]
    assert forever, "the busy spinner should be the one looping animation the parser sees"
    assert all(_is_spinner(selector) for selector in forever), \
        f"only a busy spinner may loop: {forever}"


def test_no_motion_css_animation_outlasts_the_five_second_budget():
    animations = [(r.prelude, _animation(_decls(r.body))) for r in MOTION_RULES
                  if r.kind == "style"]
    animations = [(sel, a) for sel, a in animations if a is not None and not _is_spinner(sel)]
    assert animations, "expected motion.css to declare animations"
    # A rule that only overrides the delay inherits its duration from the rule it overrides, so
    # it is measured against the longest finite run in the file. Conservative on purpose.
    longest = max(a.duration * a.iterations for _sel, a in animations
                  if a.duration is not None and a.iterations != math.inf)
    over = []
    for selector, anim in animations:
        span = anim.duration * anim.iterations if anim.duration is not None else longest
        if anim.delay + span > 5000:
            over.append(f"{selector} ({anim.delay + span:.0f} ms)")
    assert over == [], f"MG-16 caps a moment at 5,000 ms: {over}"


@pytest.mark.parametrize("quiet", [".since", ".meter", "h1"])
def test_no_text_and_no_meter_animates(quiet):
    animated = [r.prelude for r in MOTION_RULES if r.kind == "style" and quiet in r.prelude
                and _animation(_decls(r.body)) is not None]
    assert animated == [], f"R3, R12: {quiet} must not animate, found {animated}"


# --- M-7 -----------------------------------------------------------------------------------

def test_the_palette_guard_scans_the_javascript_files_too():
    import test_saas_palette

    scanned = {Path(p).resolve() for p in test_saas_palette.SCANNED}
    missing = [p.name for p in OWN_JS + [VENDOR_JS] if p.resolve() not in scanned]
    assert missing == [], f"the palette guard must scan {missing} as well (MG-30, R5)"


def test_the_palette_guard_already_covers_motion_css():
    import test_saas_palette

    scanned = {Path(p).resolve() for p in test_saas_palette.CSS_FILES}
    assert MOTION_CSS.resolve() in scanned


def test_no_banned_hue_in_any_javascript_file():
    import test_saas_palette

    bad = {}
    for path in OWN_JS + [VENDOR_JS]:
        found = sorted({raw for raw, rgb in test_saas_palette._colours(_text(path))
                        if test_saas_palette._is_purple(rgb)})
        if found:
            bad[path.name] = found
    assert bad == {}, f"hue 230-345 colours in JavaScript: {bad}"


# --- M-8 -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path,step", list(zip(ONBOARDING_PAGES, (1, 2, 3, 4))))
def test_onboarding_mode_marks_the_current_step_once(saas_cfg, path, step):
    client, _ = _onboarding_client(saas_cfg)
    markup = client.get(path).text
    assert count_class(markup, "stepper__marker") == 1, path
    current = [e for e in elements(markup) if e.attrs.get("aria-current") == "step"]
    assert len(current) == 1, path
    markers = [c for c in current[0].children if has_class(c, "stepper__marker")]
    assert len(markers) == 1, f"{path}: the marker belongs inside the current step"
    assert markers[0].attrs.get("aria-hidden") == "true"


@pytest.mark.parametrize("path", ONBOARDING_PAGES)
def test_editing_mode_shows_no_step_marker(saas_cfg, path):
    client, _ = _onboarding_client(saas_cfg, activated=True, sub="edit")
    assert count_class(client.get(path).text, "stepper__marker") == 0, path


# --- M-9 -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path,step", list(zip(APP_PAGES, ("1", "2", "3", "4", "0"))))
def test_the_server_stamps_the_step_on_the_html_element(saas_cfg, path, step):
    markup = _five_pages(saas_cfg)[path]
    html_tag = re.search(r"<html[^>]*>", markup).group(0)
    assert f'data-step="{step}"' in html_tag, f"{path}: {html_tag}"


@pytest.mark.parametrize("path", NON_APP_PAGES)
def test_no_other_page_carries_a_step(saas_cfg, path):
    html_tag = re.search(r"<html[^>]*>", client_for(saas_cfg).get(path).text).group(0)
    assert "data-step" not in html_tag, f"{path}: {html_tag}"


# --- M-10 ----------------------------------------------------------------------------------

def test_every_keyword_chip_and_suggestion_names_its_own_keyword(saas_cfg):
    saved = ("virtual assistant", "data entry")
    client, _ = _onboarding_client(saas_cfg, keywords=saved, sub="kws")
    markup = client.get("/onboarding/keywords").text
    quick = app_module._TEMPLATES.env.get_template("_ui.html").module.QUICK_KEYWORDS
    chips, quicks = {}, {}
    for el in elements(markup):
        if el.tag == "li" and has_class(el, "kw"):
            label = next(c for c in el.children if has_class(c, "kw__text"))
            chips[clean(label.text)] = el.attrs.get("data-vt-kw")
        if el.tag == "button" and has_class(el, "quick"):
            word = [c for c in el.children if c.tag == "span"][-1]
            quicks[clean(word.text)] = el.attrs.get("data-vt-kw")
    assert set(chips) == set(saved)
    assert all(label == value for label, value in chips.items()), chips
    # The page offers only the suggestions the user has not saved yet.
    assert set(quicks) == set(quick) - set(saved) and quicks
    assert all(label == value for label, value in quicks.items()), quicks


def test_a_keyword_with_markup_characters_is_escaped_in_the_attribute(saas_cfg):
    nasty = 'a"b<c'
    client, _ = _onboarding_client(saas_cfg, keywords=(nasty,), sub="esc")
    markup = client.get("/onboarding/keywords").text
    assert 'data-vt-kw="a&#34;b&lt;c"' in markup
    chip = next(e for e in elements(markup) if e.tag == "li" and has_class(e, "kw"))
    assert chip.attrs["data-vt-kw"] == nasty


# --- M-11 ----------------------------------------------------------------------------------

def test_step_two_confirms_a_connected_gmail_in_onboarding_mode(saas_cfg):
    client, _ = _onboarding_client(saas_cfg, sub="s2on")
    markup = client.get("/onboarding/profile").text
    assert markup.count('class="gconf"') == 1, "the route must pass gmail_connected to Step 2"
    assert len(_attr_elements(markup, "data-arrive-gmail")) == 1


def test_step_two_says_nothing_when_gmail_is_not_connected(saas_cfg):
    client, _ = _onboarding_client(saas_cfg, gmail=False, sub="s2off")
    markup = client.get("/onboarding/profile").text
    assert 'class="gconf"' not in markup
    assert _attr_elements(markup, "data-arrive-gmail") == []


def test_step_two_stays_still_behind_a_retry_note(saas_cfg):
    client, _ = _onboarding_client(saas_cfg, sub="s2retry")
    markup = client.get("/onboarding/profile?gmail_error=scope").text
    assert 'class="gconf"' not in markup
    assert _attr_elements(markup, "data-arrive-gmail") == []


def test_the_step_four_success_alert_carries_the_arrival_flag(saas_cfg):
    client, _ = _onboarding_client(saas_cfg, sub="s4on")
    flagged = _attr_elements(client.get("/onboarding/preview").text, "data-arrive-gmail")
    assert len(flagged) == 1
    assert has_class(flagged[0], "alert--success")


@pytest.mark.parametrize("query,gmail", [("?gmail_error=scope", True), ("", False)])
def test_step_four_drops_the_arrival_flag_on_a_retry_or_no_grant(saas_cfg, query, gmail):
    client, _ = _onboarding_client(saas_cfg, gmail=gmail, sub=f"s4{int(gmail)}")
    markup = client.get(f"/onboarding/preview{query}").text
    assert _attr_elements(markup, "data-arrive-gmail") == []


def test_the_dashboard_flags_the_gmail_sheet_and_the_live_panel(saas_cfg):
    client, _ = _dashboard_client(saas_cfg, sub="dashon")
    flagged = _attr_elements(client.get("/dashboard").text, "data-arrive-gmail")
    assert len(flagged) == 2
    assert {"sheet", "status"} <= {c for e in flagged for c in e.attrs["class"].split()}


def test_an_older_grant_with_a_retry_note_moves_nothing(saas_cfg):
    """R11: the live panel still shows, and the note still shows, but nothing lands."""
    client, _ = _dashboard_client(saas_cfg, sub="dashretry")
    markup = client.get("/dashboard?gmail_error=scope").text
    assert 'data-panel="live"' in markup
    assert "tick the box" in page_text(markup)
    assert _attr_elements(markup, "data-arrive-gmail") == []


def test_a_dashboard_without_gmail_flags_nothing(saas_cfg):
    client, _ = _dashboard_client(saas_cfg, gmail=False, sub="dashoff")
    assert _attr_elements(client.get("/dashboard").text, "data-arrive-gmail") == []


# --- M-12 ----------------------------------------------------------------------------------

FROZEN = "2026-09-19T03:00:00Z"


@pytest.mark.parametrize("age,fresh", [(0, True), (60, True), (120, True), (121, False),
                                       (3600, False)])
def test_data_fresh_lives_only_inside_the_switch_on_window(saas_cfg, monkeypatch, age, fresh):
    client, user = _dashboard_client(saas_cfg, sub=f"fresh{age}")
    _set_times(saas_cfg, user, activated_at=_shift(FROZEN, -age))
    _freeze(monkeypatch, FROZEN)
    markup = client.get("/dashboard").text
    panels = _attr_elements(markup, "data-fresh")
    assert len(panels) == (1 if fresh else 0), f"{age} s after activation"
    if fresh:
        assert panels[0].attrs.get("data-panel") == "live"


@pytest.mark.parametrize("path", ONBOARDING_PAGES)
def test_no_onboarding_page_carries_the_switch_on_hooks(saas_cfg, path):
    markup = _five_pages(saas_cfg)[path]
    assert _attr_elements(markup, "data-fresh") == [], path


def test_the_burst_source_sits_on_the_live_panel_when_it_is_fresh(saas_cfg, monkeypatch):
    client, user = _dashboard_client(saas_cfg, sub="burst")
    _set_times(saas_cfg, user, activated_at=_shift(FROZEN, -30))
    _freeze(monkeypatch, FROZEN)
    sources = _attr_elements(client.get("/dashboard").text, "data-burst-src")
    assert len(sources) == 1 and sources[0].attrs.get("data-panel") == "live"
    assert sources[0].attrs["data-burst-src"].startswith("/static/vendor/canvas-confetti-1.9.4.js")


def test_a_returning_dashboard_downloads_nothing(saas_cfg, monkeypatch):
    client, user = _dashboard_client(saas_cfg, sub="return")
    _set_times(saas_cfg, user, activated_at=_shift(FROZEN, -3600))
    _freeze(monkeypatch, FROZEN)
    assert _attr_elements(client.get("/dashboard").text, "data-burst-src") == []


def test_the_burst_source_sits_on_the_step_four_primary_form(saas_cfg):
    client, _ = _onboarding_client(saas_cfg, sub="s4burst")
    markup = client.get("/onboarding/preview").text
    sources = _attr_elements(markup, "data-burst-src")
    assert len(sources) == 1
    forms = post_forms(markup, "/onboarding/activate")
    assert len(forms) == 1 and "data-burst-src" in forms[0].attrs
    assert "Start watching for jobs" in clean(forms[0].text)


def test_the_without_gmail_form_never_celebrates(saas_cfg):
    client, _ = _onboarding_client(saas_cfg, gmail=False, sub="s4nog")
    markup = client.get("/onboarding/preview").text
    assert _attr_elements(markup, "data-burst-src") == []
    assert "Start watching without Gmail" in page_text(markup)


@pytest.mark.parametrize("path", ONBOARDING_PAGES)
def test_editing_mode_never_celebrates(saas_cfg, path):
    client, _ = _onboarding_client(saas_cfg, activated=True, sub="editburst")
    assert _attr_elements(client.get(path).text, "data-burst-src") == [], path


def test_the_celebrate_switch_removes_every_burst_source(saas_cfg, monkeypatch):
    dash, user = _dashboard_client(saas_cfg, sub="nocel")
    step4, _ = _onboarding_client(saas_cfg, sub="nocel4")
    _set_times(saas_cfg, user, activated_at=_shift(FROZEN, -30))
    _freeze(monkeypatch, FROZEN)
    with _celebrate_off():
        assert _attr_elements(dash.get("/dashboard").text, "data-burst-src") == []
        assert _attr_elements(step4.get("/onboarding/preview").text, "data-burst-src") == []
    assert _attr_elements(step4.get("/onboarding/preview").text, "data-burst-src") != []


# --- M-13 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("now,activated_at,gmail_at,expected", [
    # Same Manila day: the clock time.
    (FROZEN, "2026-09-19T01:14:00Z", "2026-09-18T00:00:00Z", "9:14 AM"),
    # A later day: the date, never a bare clock time.
    (FROZEN, "2026-09-14T01:14:00Z", "2026-09-13T00:00:00Z", "14 Sep"),
    # A reconnect restarts the watch, and today's reconnect reads as a time again.
    (FROZEN, "2026-09-14T01:14:00Z", "2026-09-19T02:30:00Z", "10:30 AM"),
    (FROZEN, "2026-09-10T01:00:00Z", "2026-09-17T05:00:00Z", "17 Sep"),
    # Manila midnight, both sides. 15:00 UTC is already the 20th in Manila.
    ("2026-09-19T16:30:00Z", "2026-09-19T15:00:00Z", None, "19 Sep"),
    ("2026-09-19T15:59:00Z", "2026-09-18T16:30:00Z", None, "12:30 AM"),
    # Another year keeps the year.
    (FROZEN, "2025-09-14T01:14:00Z", None, "14 Sep 2025"),
    # Midnight and noon read as 12, not 0.
    ("2026-09-19T15:00:00Z", "2026-09-18T16:05:00Z", None, "12:05 AM"),
    ("2026-09-19T08:00:00Z", "2026-09-19T04:05:00Z", None, "12:05 PM"),
])
def test_watching_since_reads_the_start_of_the_current_watch(now, activated_at, gmail_at,
                                                             expected):
    when = datetime.strptime(now, TS_FMT).replace(tzinfo=timezone.utc)
    assert app_module.watching_since_text(activated_at, gmail_at, when) == expected


def test_a_user_who_never_activated_has_no_watching_since_line():
    when = datetime.strptime(FROZEN, TS_FMT).replace(tzinfo=timezone.utc)
    assert app_module.watching_since_text(None, "2026-09-01T00:00:00Z", when) is None


@pytest.mark.parametrize("activated_at,gmail_at,expected", [
    ("2026-09-19T01:14:00Z", "2026-09-18T00:00:00Z", "Watching since 9:14 AM"),
    ("2026-09-14T01:14:00Z", "2026-09-13T00:00:00Z", "Watching since 14 Sep"),
    # The reconnect is the LATER of the two, so this row fails if the route ever stops passing
    # db.gmail_connected_at (it would read "14 Sep", the activation date, instead).
    ("2026-09-14T01:14:00Z", "2026-09-19T02:30:00Z", "Watching since 10:30 AM"),
])
def test_the_dashboard_prints_the_watching_since_line(saas_cfg, monkeypatch, activated_at,
                                                      gmail_at, expected):
    client, user = _dashboard_client(saas_cfg, sub="since")
    _set_times(saas_cfg, user, activated_at=activated_at, gmail_at=gmail_at)
    _freeze(monkeypatch, FROZEN)
    markup = client.get("/dashboard").text
    lines = [clean(e.text) for e in elements(markup) if has_class(e, "since")]
    assert lines == [expected]


# --- M-14 ----------------------------------------------------------------------------------

def test_the_live_dot_pulse_stops_after_two_cycles():
    pulses = [_animation(_decls(r.body)) for r in APP_RULES
              if r.kind == "style" and ".live i::after" in r.prelude]
    pulses = [a for a in pulses if a is not None]
    assert len(pulses) == 1, "expected exactly one .live i::after animation in app.css"
    assert pulses[0].iterations == 2, "WCAG 2.2.2: the pulse must stop (spec 4.5)"


def test_only_the_button_spinner_runs_forever_in_app_css():
    forever = [r.prelude for r in APP_RULES if r.kind == "style"
               and (_animation(_decls(r.body)) or Anim(None, None, 0, 1)).iterations == math.inf]
    assert forever and all("btn__spin" in selector for selector in forever), forever


# --- M-15 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", APP_PAGES)
def test_the_app_pages_stay_csp_clean_with_motion_on(saas_cfg, path):
    markup = _five_pages(saas_cfg)[path]
    tags = re.findall(r"<[a-zA-Z][^>]*>", markup, re.S)
    scripts = [t for t in tags if re.match(r"<script\b", t, re.I)]
    assert scripts and all(re.search(r"\ssrc\s*=", t) for t in scripts), f"{path}: inline script"
    assert not any(re.search(r"\sstyle\s*=", t, re.I) for t in tags), f"{path}: style= attribute"
    assert not any(re.search(r"\son[a-z]+\s*=", t, re.I) for t in tags), f"{path}: on*= handler"


def test_the_content_security_policy_is_unchanged_on_an_app_page(saas_cfg):
    client, _ = _dashboard_client(saas_cfg, sub="csp")
    assert client.get("/dashboard").headers["content-security-policy"] == EXPECTED_CSP


def test_no_sparkles_reached_static_including_the_vendor_folder():
    for path in STATIC.rglob("*"):
        if path.suffix in (".css", ".js", ".svg", ".html", ".txt"):
            assert "sparkles" not in _text(path), path.name


def test_the_motion_files_added_no_build_folder_or_module_script():
    for path in STATIC.rglob("*"):
        assert path.name not in ("dist", "build"), path
        assert path.suffix != ".mjs", path


# --- M-16 ----------------------------------------------------------------------------------

def test_a_new_keyword_gets_its_ring_in_every_motion_mode():
    rings = [r for r in MOTION_RULES if r.kind == "style" and r.prelude == ".kw[data-new]"
             and not any("forced-colors" in link for link in r.chain)]
    assert len(rings) == 1, "expected one unconditional .kw[data-new] rule"
    assert not _no_preference(rings[0].chain), "R2: the static cue must not be motion-only"
    assert ("box-shadow", "0 0 0 2px #38AEEA") in _decls(rings[0].body)


def test_forced_colours_give_the_new_keyword_a_highlight_outline():
    rules = [r for r in MOTION_RULES if r.kind == "style" and ".kw[data-new]" in r.prelude
             and any(re.search(r"forced-colors\s*:\s*active", link) for link in r.chain)]
    assert len(rules) == 1
    outlines = [v for p, v in _decls(rules[0].body) if p == "outline"]
    assert outlines and "Highlight" in outlines[0], outlines


def test_the_sonar_ring_stays_behind_the_motion_switch():
    sonar = [r for r in MOTION_RULES if r.kind == "style" and r.prelude == ".kw[data-new]::after"]
    assert len(sonar) == 1
    assert _no_preference(sonar[0].chain)
    assert _animation(_decls(sonar[0].body)) is not None


# --- M-17 ----------------------------------------------------------------------------------

def _app_decls(selector: str, *, inside: str | None = None) -> dict[str, str]:
    """What app.css ends up declaring for ``selector``, either unconditionally or inside
    ``inside``. Rules from every layer are merged in source order, the last one winning, the
    way a browser resolves them. Forced-colours overrides are a separate contract (M-18)."""
    merged: dict[str, str] = {}
    for rule in APP_RULES:
        if (rule.kind == "style" and rule.prelude == selector
                and not any("forced-colors" in link for link in rule.chain)
                and (any(inside in link for link in rule.chain) if inside is not None
                     else not any(link.startswith("@media") for link in rule.chain))):
            merged.update(_decls(rule.body))
    assert merged, f"app.css declares nothing for `{selector}` (inside {inside})"
    return merged


def test_the_stepper_marker_is_drawn_by_app_css_alone():
    marker = _app_decls(".stepper__marker")
    assert marker["position"] == "absolute"
    assert marker["forced-color-adjust"] == "none"
    row = _app_decls(".stepper__marker", inside="min-width: 960px")
    assert row["inset"] == "0" and row["height"] == "auto"
    assert _app_decls(".stepper__item")["position"] == "relative"
    current = _app_decls('.stepper__item[aria-current="step"]::before')
    assert current["background"] == "var(--line)", "the current segment goes grey under the marker"


def test_motion_css_only_names_the_stepper_marker():
    mentions = [r for r in MOTION_RULES if ".stepper__marker" in r.prelude]
    assert len(mentions) == 1, mentions
    assert [p for p, _v in _decls(mentions[0].body)] == ["view-transition-name"]
    assert _text(MOTION_CSS).count(".stepper__marker") == 1


# --- M-18 ----------------------------------------------------------------------------------

def test_the_rail_marker_uses_the_system_colours_in_forced_colours():
    forced = [r for r in APP_RULES if r.kind == "style"
              and any("forced-colors: active" in link and "min-width: 960px" in link
                      for link in r.chain)]
    by_selector = {r.prelude: dict(_decls(r.body)) for r in forced}
    assert by_selector.get(".stepper__marker", {}).get("forced-color-adjust") == "auto"
    assert by_selector.get(".stepper__marker", {}).get("background") == "Highlight"
    assert by_selector.get('.stepper__item[aria-current="step"]', {}).get("color") == "HighlightText"


def test_the_phone_bar_keeps_its_own_colour_in_forced_colours():
    assert _app_decls(".stepper__marker")["forced-color-adjust"] == "none"


# --- M-19 ----------------------------------------------------------------------------------

def test_editing_your_details_stays_quiet(saas_cfg):
    editing, _ = _onboarding_client(saas_cfg, activated=True, sub="quiet")
    onboarding, _ = _onboarding_client(saas_cfg, sub="loud")
    quiet = editing.get("/onboarding/profile").text
    loud = onboarding.get("/onboarding/profile").text
    assert 'class="gconf"' not in quiet
    assert _attr_elements(quiet, "data-arrive-gmail") == []
    assert loud.count('class="gconf"') == 1
    assert len(_attr_elements(loud, "data-arrive-gmail")) == 1


# --- M-20 ----------------------------------------------------------------------------------

def test_the_morph_is_named_only_in_the_full_tier():
    source = _text(VT_JS)
    pushes = list(re.finditer(r'push\(\s*"act"\s*\)', source))
    assert len(pushes) == 1, "expected one place that adds the act token"
    line = source[source.rfind("\n", 0, pushes[0].start()) + 1:pushes[0].end()]
    assert 'tier === "full"' in line, f"R8: the morph is full-tier only, got {line.strip()}"


def test_saved_chips_are_named_only_near_the_top_of_the_page():
    source = _text(VT_JS)
    cap = re.search(r"cap\s*=\s*([^;,]+)", source)
    assert cap, "expected a saved-chip cap in vt.js"
    # \b after the number, so widening the threshold (scrollY <= 1200) cannot pass as a substring.
    assert re.search(r"scrollY\s*<=\s*120\b", cap.group(1)), f"R9: got {cap.group(1).strip()}"


@pytest.mark.parametrize("handler", ["pageswap", "pagereveal"])
def test_both_handlers_clear_the_old_names_first(handler):
    source = _text(VT_JS)
    start = source.index(f'addEventListener("{handler}"')
    body = source[source.index("{", source.index("=>", start)) + 1:]
    first = next(line.strip() for line in body.splitlines() if line.strip())
    assert first == "unname();", f"R10: {handler} must clear names first, got {first}"


def test_pageswap_names_nothing_on_a_back_or_forward_navigation():
    source = _text(VT_JS)
    assert re.search(r'navigationType\s*===\s*"traverse"', source), "R10"
    assert "trav(e.activation)" in source, "R10: pageswap must test e.activation"


# --- review fixes (2026-09-20) --------------------------------------------------------------
#
# Three rules the 11.1 table does not name, each found by the post-build review and each proven
# before it was fixed: the desktop rail paint order (watched in Chrome 153), the switch-on peak
# when Web Storage is unavailable (spec 4.3 promises it still plays), and a stored timestamp
# that is not the shape db.py writes (it used to 500 the whole dashboard).

def test_the_desktop_rail_paints_above_the_marker_snapshot():
    """From 960 px the marker is the row-sized tint and belongs BEHIND the row (app.css gives it
    z-index -1). A named descendant leaves its ancestor's snapshot and paints above it, so the
    rail is lifted instead — otherwise the marker blanks the current step's number and label for
    the whole 520 ms glide. Phones must keep the default order: there the marker is the 6 px bar
    and has to stay above the rail's own grey segment."""
    lifts = [r for r in MOTION_RULES if r.kind == "style"
             and "::view-transition-group(af-rail)" in r.prelude
             and any(prop == "z-index" for prop, _ in _decls(r.body))]
    assert len(lifts) == 1, "expected exactly one z-index on the af-rail group"
    chain = " ".join(lifts[0].chain)
    assert "min-width: 960px" in chain, f"the lift must be desktop-only, got {lifts[0].chain}"
    assert "prefers-reduced-motion: no-preference" in chain, "MG-22"
    assert [v for prop, v in _decls(lifts[0].body) if prop == "z-index"] == ["1"]


def test_a_dashboard_is_marked_still_only_when_storage_actually_works():
    """Spec 4.3: if storage is blocked every page is still complete and "the server-side
    data-fresh still plays the CSS peak". Writing data-still whenever the tap flag is missing
    would suppress the switch-on for anyone whose browser refuses sessionStorage."""
    source = _text(VT_JS)
    still = re.search(r"root\.dataset\.still\s*=", source)
    assert still, "expected vt.js to write data-still"
    line = source[source.rfind("\n", 0, still.start()) + 1:source.find("\n", still.start())]
    assert re.search(r"step === 0 && S\b", line), f"4.3: got {line.strip()}"


@pytest.mark.parametrize("stored", [
    "2026-09-19 01:14:00",              # SQLite CURRENT_TIMESTAMP shape: no T, no Z
    "2026-09-19T01:14:00",              # no trailing Z
    "2026-09-19T01:14:00.500000Z",      # sub-second precision
    "2026-09-19T01:14:00+00:00",        # an offset instead of Z
    "not a date",
])
def test_a_timestamp_the_server_cannot_read_drops_the_line_instead_of_raising(stored):
    when = datetime.strptime(FROZEN, TS_FMT).replace(tzinfo=timezone.utc)
    assert app_module.watching_since_text(stored, None, when) is None
    assert app_module._activated_fresh(stored, when) is False
    # An unreadable Gmail time falls back to the activation; it must not lose the line.
    assert app_module.watching_since_text("2026-09-19T01:14:00Z", stored, when) == "9:14 AM"


@pytest.mark.parametrize("activated_at,gmail_at,since", [
    ("2026-09-19 01:14:00", "2026-09-18T00:00:00Z", []),
    ("2026-09-19T01:14:00Z", "2026-09-19 02:30:00", ["Watching since 9:14 AM"]),
])
def test_the_dashboard_survives_a_stored_timestamp_it_cannot_read(saas_cfg, monkeypatch,
                                                                  activated_at, gmail_at, since):
    """A decorative line must never cost a user their whole page (the TestClient re-raises, so
    before the fix this call raised ValueError instead of returning the dashboard)."""
    client, user = _dashboard_client(saas_cfg, sub="badts")
    _set_times(saas_cfg, user, activated_at=activated_at, gmail_at=gmail_at)
    _freeze(monkeypatch, FROZEN)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert [clean(e.text) for e in elements(resp.text) if has_class(e, "since")] == since
