"""Static guards over the SaaS templates: autoescape, CSP-safe markup, contiguous strings the
other tests and Google's reviewers rely on, per-template macro imports, no build folders."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from applyfirst.saas import static_assets
from _saas_client import client_for, seed_user

SAAS = Path(static_assets.__file__).parent
TEMPLATES = SAAS / "templates"
STATIC = SAAS / "static"
TEMPLATE_FILES = sorted(TEMPLATES.glob("*.html"))
_TAG = re.compile(r"<[a-zA-Z][^>]*>", re.S)


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _markup_only(src: str) -> str:
    """Drop Jinja comments so a documented example never trips a guard."""
    return re.sub(r"\{#.*?#\}", "", src, flags=re.S)


def test_every_page_template_exists():
    names = {p.name for p in TEMPLATE_FILES}
    assert {"base.html", "home.html", "login.html", "onboarding_connect_gmail.html",
            "onboarding_profile.html", "onboarding_keywords.html", "onboarding_preview.html",
            "dashboard.html", "privacy.html", "terms.html"} <= names


# --- T40 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_autoescape_stays_on(path):
    src = _markup_only(_src(path))
    assert "url_for" not in src
    assert "ui.icon(" not in src
    assert not re.search(r"autoescape\s+false", src, re.I)
    assert "Markup" not in src
    if path.name != "_icons.html":
        assert not re.search(r"\|\s*safe\b", src), "| safe is allowed only in _icons.html"


# --- T41 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_markup_is_csp_safe(path):
    src = _markup_only(_src(path))
    tags = _TAG.findall(src)
    assert not re.search(r"<style\b", src, re.I), "no <style> blocks (use static/css/app.css)"
    assert not any(re.search(r"\sstyle\s*=", t, re.I) for t in tags), "no style= attributes"
    scripts = [t for t in tags if re.match(r"<script\b", t, re.I)]
    assert all(re.search(r"\ssrc\s*=", t) for t in scripts), "no inline <script>"
    assert not any(re.search(r"\son[a-z]+\s*=", t, re.I) for t in tags), "no on*= handlers"
    assert "javascript:" not in src.lower()
    for t in tags:
        if re.match(r"<(script|link|img|source|iframe|embed|object|video|audio)\b", t, re.I):
            assert not re.search(r"""(?:src|href|srcset)\s*=\s*["']?\s*(?:https?:)?//""", t,
                                 re.I), f"external asset in {t}"
    assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", src, re.I)
    assert "sparkles" not in src


def test_no_sparkles_icon_anywhere_in_static():
    for path in STATIC.rglob("*"):
        if path.suffix in (".css", ".js", ".svg", ".html"):
            assert "sparkles" not in path.read_text(encoding="utf-8"), path.name


# --- T42 ----------------------------------------------------------------------------------

def _page(cfg, page: str) -> str:
    """One rendered page: a public path, or "scope" for the signed-in Step 1 retry note."""
    if page == "scope":
        return client_for(cfg, seed_user(cfg)).get(
            "/onboarding/connect_gmail?gmail_error=scope").text
    return client_for(cfg).get(page).text


@pytest.mark.parametrize("page,needle", [
    ("/", "Continue with Google"), ("/login", "Continue with Google"), ("/", "gmail.send"),
    ("/", 'href="/privacy"'), ("/login", 'href="/privacy"'), ("/privacy", "gmail.send"),
    ("/privacy", "Limited Use"), ("/privacy", "Google API Services User Data Policy"),
    ("/terms", "Terms of Service"), ("scope", "tick the box"),
])
def test_asserted_strings_render_contiguously(saas_cfg, page, needle):
    assert needle in _page(saas_cfg, page)


def test_never_read_renders_contiguously_on_privacy(saas_cfg):
    assert "never read" in _page(saas_cfg, "/privacy").lower()


def test_daily_limit_phrase_lives_only_in_the_dashboard_today_branch():
    for path in TEMPLATE_FILES:
        count = _markup_only(_src(path)).count("daily limit reached")
        assert count == (1 if path.name == "dashboard.html" else 0), path.name


# --- T43 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_each_template_imports_the_macros_it_uses(path):
    src = _markup_only(_src(path))
    if path.name != "_icons.html" and re.search(r"(?<![\w.])icon\(", src):
        assert re.search(r"""\{%-?\s*from\s+["']_icons\.html["']\s+import\s+[^%]*\bicon\b""",
                         src), f"{path.name} calls icon( without importing it"
    if re.search(r"(?<![\w.])ui\.", src):
        assert re.search(r"""\{%-?\s*import\s+["']_ui\.html["']\s+as\s+ui\b""", src), (
            f"{path.name} uses ui. without importing _ui.html")


def test_static_has_no_build_output_or_mjs():
    for path in STATIC.rglob("*"):
        assert path.name not in ("dist", "build"), path
        assert path.suffix != ".mjs", path
