"""Self-hosted static files for the SaaS pages: MIME pins, hashed URLs, cache headers.

Everything the pages load (CSS, fonts, icons, the small JS file) is served from our own
origin under /static, because the CSP (``default-src 'self'``) blocks every CDN.
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs

from fastapi.staticfiles import StaticFiles

# Python 3.12 (the Docker image) has no .woff2 entry in its built-in table, and
# python:3.12-slim ships no /etc/mime.types. On Windows the registry can map .js or .mjs
# to text/plain, which X-Content-Type-Options: nosniff then refuses to run. Pin them all.
for _ext, _type in {".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2",
                    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
                    ".webmanifest": "application/manifest+json"}.items():
    mimetypes.add_type(_type, _ext)

STATIC_DIR = Path(__file__).resolve().parent / "static"
# (absolute path, mtime_ns, size) -> 12-hex content hash. Keyed by the full path so a test
# that points STATIC_DIR at a temp folder never reuses a hash from the real one.
_ASSET_HASHES: dict[tuple[str, int, int], str] = {}


def static_url(rel: str) -> str:
    """Root-relative, content-hashed URL for a file under static/ (e.g. 'css/app.css').

    Root-relative on purpose. Starlette's url_for() builds an absolute URL from the request,
    and on Fly uvicorn only trusts X-Forwarded-Proto from 127.0.0.1, so it would emit http://
    asset links that an https:// page blocks as mixed content.
    The hash is re-read only when the file's mtime or size changes, so CSS edits show up in
    dev without restarting uvicorn, and production pays one stat() per call. A missing file
    gets the plain unhashed URL (it then 404s visibly instead of crashing the page).
    """
    path = STATIC_DIR / rel
    try:
        st = path.stat()
    except OSError:
        return f"/static/{rel}"
    key = (str(path), st.st_mtime_ns, st.st_size)
    digest = _ASSET_HASHES.get(key)
    if digest is None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        _ASSET_HASHES[key] = digest
    return f"/static/{rel}?v={digest}"


# Request headers that turn a static GET into a 206 partial response.
_RANGE_HEADERS = frozenset({b"range", b"if-range"})


class CachedStaticFiles(StaticFiles):
    """StaticFiles plus Cache-Control, without byte ranges.

    Hashed URLs (?v=...) never change, so browsers keep them a year. Anything requested
    without ?v (fonts referenced from CSS, the preload link) is kept a day and then
    revalidated cheaply with the ETag StaticFiles already sends. Rename a font file if its
    content ever changes. A 304 revalidation carries the same header.

    Range requests are ignored (always the full 200) and Accept-Ranges says "none". Starlette
    puts no cap on how many ranges one request may ask for, so a single anonymous request
    with thousands of them could pin the only uvicorn worker's CPU for seconds. Every file
    here is small, so partial downloads buy nothing.
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "headers": [(k, v) for k, v in scope["headers"]
                                          if k.lower() not in _RANGE_HEADERS]}
        await super().__call__(scope, receive, send)

    def file_response(self, full_path, stat_result, scope, status_code=200):
        resp = super().file_response(full_path, stat_result, scope, status_code)
        hashed = "v" in parse_qs(scope.get("query_string", b"").decode("latin-1"))
        resp.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if hashed else "public, max-age=86400"
        )
        resp.headers["Accept-Ranges"] = "none"
        return resp
