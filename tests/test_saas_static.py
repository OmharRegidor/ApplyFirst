"""The /static mount: MIME types, cache headers, security headers, hashed URLs."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from applyfirst.saas import app as app_module
from applyfirst.saas import static_assets
from applyfirst.saas.app import create_app
from _saas_client import EXPECTED_CSP, client_for

TEMPLATES = Path(app_module.__file__).parent / "templates"
REAL_STATIC = static_assets.STATIC_DIR


@pytest.fixture
def static_dir(tmp_path, monkeypatch):
    """A throwaway static folder, so these tests never depend on which assets ship."""
    root = tmp_path / "static"
    for rel, body in {"css/app.css": b"body{margin:0}", "js/app.js": b"void 0;",
                      "fonts/f.woff2": b"wOF2\x00\x01", "brand/i.svg": b"<svg/>",
                      "brand/i.png": b"\x89PNG\r\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(body)
    (tmp_path / "secret.py").write_text("x = 1", encoding="utf-8")      # outside the mount
    monkeypatch.setattr(static_assets, "STATIC_DIR", root)   # what create_app mounts and hashes
    return root


@pytest.fixture
def client(saas_cfg, static_dir):
    return client_for(saas_cfg)


# --- T25 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path,ctype", [
    ("css/app.css", "text/css; charset=utf-8"), ("js/app.js", "text/javascript; charset=utf-8"),
    ("fonts/f.woff2", "font/woff2"), ("brand/i.svg", "image/svg+xml"),
    ("brand/i.png", "image/png"),
])
def test_served_with_pinned_mime_type(client, path, ctype):
    r = client.get(f"/static/{path}")
    assert r.status_code == 200
    assert r.headers["content-type"] == ctype


# --- T26 ----------------------------------------------------------------------------------

def test_cache_headers_one_day_plain_one_year_hashed(client):
    assert client.get("/static/css/app.css").headers["cache-control"] == "public, max-age=86400"
    assert (client.get("/static/css/app.css?v=abc123").headers["cache-control"]
            == "public, max-age=31536000, immutable")


@pytest.mark.parametrize("query,cache", [("", "public, max-age=86400"),
                                         ("?v=abc123", "public, max-age=31536000, immutable")])
def test_revalidation_returns_304_with_the_same_cache_header(client, query, cache):
    etag = client.get(f"/static/css/app.css{query}").headers["etag"]
    r = client.get(f"/static/css/app.css{query}", headers={"if-none-match": etag})
    assert r.status_code == 304
    assert r.headers["cache-control"] == cache


# --- F-001: no byte ranges (Starlette has no cap on the range count) ------------------------

def test_many_ranges_get_the_full_file_not_a_multipart_206(client):
    ranges = ",".join(f"{i}-{i}" for i in range(0, 14, 2))       # 7 ranges in "body{margin:0}"
    r = client.get("/static/css/app.css", headers={"range": f"bytes={ranges}"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/css; charset=utf-8"
    assert r.content == b"body{margin:0}"
    assert r.headers["accept-ranges"] == "none"
    assert "content-range" not in r.headers


@pytest.mark.parametrize("extra", [{}, {"if-range": "anything"}])
def test_a_single_range_also_gets_the_full_file(client, extra):
    r = client.get("/static/css/app.css", headers={"range": "bytes=0-3", **extra})
    assert r.status_code == 200
    assert r.content == b"body{margin:0}"
    assert r.headers["accept-ranges"] == "none"


def test_revalidation_with_a_range_still_returns_304_and_cache_control(client):
    etag = client.get("/static/css/app.css?v=abc123").headers["etag"]
    r = client.get("/static/css/app.css?v=abc123",
                   headers={"if-none-match": etag, "range": "bytes=0-3,5-7"})
    assert r.status_code == 304
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


# --- T27 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/static/%2e%2e/secret.py", "/static/..%2fsecret.py",
                                  "/static/css/..%2f..%2fsecret.py", "/static/nope.css",
                                  "/static/css/", "/static/css"])
def test_no_escape_and_no_listing(client, path):
    assert client.get(path).status_code == 404


def test_static_is_read_only(client):
    assert client.post("/static/css/app.css").status_code == 405


def test_static_responses_carry_the_unchanged_security_headers(client):
    r = client.get("/static/css/app.css")
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_rate_limiter_never_counts_static(saas_cfg, static_dir):
    c = client_for(dataclasses.replace(saas_cfg, auth_rate_limit=1))
    for _ in range(5):
        assert c.get("/static/css/app.css").status_code == 200
    assert c.get("/auth/login").status_code == 302          # the first /auth/ hit is still free
    assert c.get("/auth/login").status_code == 429          # ... and the limiter is really on


# --- T28 ----------------------------------------------------------------------------------

def test_static_url_is_root_relative_and_content_hashed(static_dir):
    first = static_assets.static_url("css/app.css")
    assert re.fullmatch(r"/static/css/app\.css\?v=[0-9a-f]{12}", first)
    assert static_assets.static_url("css/app.css") == first                # stable
    (static_dir / "css/app.css").write_bytes(b"body{margin:1px;padding:0}")
    assert static_assets.static_url("css/app.css") != first                # new content, new URL
    assert static_assets.static_url("missing.css") == "/static/missing.css"


def test_templates_see_static_url_as_a_global():
    assert app_module._TEMPLATES.env.globals["static_url"] is static_assets.static_url


# --- T29 (the REAL folder, no monkeypatch) ------------------------------------------------

def test_real_static_folder_is_committed_with_the_stylesheet():
    # StaticFiles refuses to start without the folder, which would fail every test.
    assert (REAL_STATIC / "css" / "app.css").is_file()


def _template_refs() -> set[str]:
    refs: set[str] = set()
    for tpl in TEMPLATES.glob("*.html"):
        src = tpl.read_text("utf-8")
        refs |= set(re.findall(r"static_url\(\s*['\"]([^'\"]+)['\"]", src))
        refs |= set(re.findall(r"""["'(]/static/([^"'?)#\s]+)""", src))
    return refs


def test_every_static_reference_in_templates_points_at_a_real_file():
    missing = [r for r in sorted(_template_refs()) if not (REAL_STATIC / r).is_file()]
    assert missing == []


def test_every_url_in_the_stylesheet_points_at_a_real_file():
    css_dir = REAL_STATIC / "css"
    missing = []
    for css in css_dir.glob("*.css"):
        for ref in re.findall(r"url\(\s*['\"]?([^'\")]+)", css.read_text("utf-8")):
            if ref.startswith("data:"):
                continue
            target = (REAL_STATIC / ref[len("/static/"):] if ref.startswith("/static/")
                      else (css_dir / ref.split("?")[0]).resolve())
            if not target.is_file():
                missing.append(ref)
    assert missing == []


# --- T30 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("seconds,minutes", [(600, 10), (330, 6), (450, 8), (20, 1), (0, 1),
                                             (89, 1), (90, 2), (3000, 50)])
def test_check_every_min(seconds, minutes):
    assert app_module.check_every_min(seconds) == minutes


def test_page_context_reads_the_serving_apps_config(saas_cfg):
    cfg = dataclasses.replace(saas_cfg, worker_interval=330, daily_tailor_cap=7)
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cfg=cfg)))
    assert app_module._page_context(req) == {"check_every_min": 6, "apps_per_day": 7}


def test_create_app_fails_loudly_without_the_static_folder(saas_cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(static_assets, "STATIC_DIR", tmp_path / "missing")
    with pytest.raises(RuntimeError):
        create_app(saas_cfg)
