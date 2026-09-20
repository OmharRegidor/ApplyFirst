"""Shared helpers for the SaaS redesign tests: seeded users, signed-in clients, DB reads, page
parsing, a recording AI provider, and the owner-string markers the prompt tests look for.

Not a test module (no ``test_`` prefix). Imported by the redesign test files only; the older
test files keep their own small helpers unchanged.
"""

from __future__ import annotations

import html as _html
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from applyfirst.saas import db, session
from applyfirst.saas.app import create_app

EXPECTED_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
PROFILE = {"full_name": "Maria Santos", "job_type": "Virtual Assistant",
           "standard_subject": "VA – Maria Santos",
           "standard_message": "Hi! I'm Maria, a VA with 3 years in customer support."}

# Owner-specific strings that must never reach a SaaS user's prompt or letter, plus the resume and
# availability claims the owner decisions (2026-09-19) forbid when the profile does not back them.
OWNER_MARKERS = ("omhar", "regidor", "n8n", "tech stack", "live projects", "ai agent team")
RESUME_CLAIMS = ("resume attached", "resume is attached", "tailored resume")
INVENTED_AVAILABILITY = ("available to start immediately", "start immediately", "flexible hours")


def hits(text: str, markers) -> list[str]:
    """The markers found in ``text``, case-insensitively."""
    low = text.lower()
    return [m for m in markers if m in low]


class RecordingProvider:
    """A fake AI provider: records every (system, user) prompt pair and answers ``response``."""

    name = "gemini"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


def seed_user(cfg, *, sub: str = "g", email: str = "maria@example.com", name: str | None = "Maria",
              profile: bool = False, keywords: tuple[str, ...] = (), activated: bool = False,
              gmail_key: bytes | None = None, usage: int = 0) -> db.User:
    """Create one user in the requested state. ``gmail_key`` stores a working Gmail grant."""
    conn = db.init_db(cfg.db_path)
    try:
        user = db.upsert_user_by_google(conn, google_sub=sub, email=email, display_name=name)
        if profile or activated:
            db.upsert_profile(conn, user.id, **PROFILE)
        for kw in keywords:
            db.add_keyword(conn, user.id, kw)
        if activated:
            db.set_activated(conn, user.id)
        if gmail_key is not None:
            db.store_gmail_credential(conn, user.id, refresh_token="rt-old", master_key=gmail_key)
        for _ in range(usage):
            db.try_increment_ai_usage(conn, user.id, 10_000)
        return user
    finally:
        conn.close()


def client_for(cfg, user: db.User | None = None, *, app=None, csrf_header: bool = False,
               user_agent: str | None = None) -> TestClient:
    """A TestClient (no redirects followed), signed in as ``user`` when given."""
    c = TestClient(app or create_app(cfg), follow_redirects=False)
    if user is not None:
        c.cookies.set("applyfirst_session", session.sign(cfg.session_secret, {"uid": user.id}))
        if csrf_header:
            c.headers["X-CSRF-Token"] = session.issue_csrf(cfg.session_secret, user.id)
    if user_agent is not None:
        c.headers["User-Agent"] = user_agent
    return c


def gmail_callback(c: TestClient, **params):
    """Start Connect Gmail (sets the txn cookie), then hit the callback with its real state."""
    loc = c.get("/auth/connect-gmail").headers["location"]
    state = parse_qs(urlparse(loc).query)["state"][0]
    return c.get("/auth/gmail-callback", params={"code": "c", "state": state, **params})


@contextmanager
def db_conn(cfg):
    """A short-lived connection to the test database, always closed."""
    conn = db.connect(cfg.db_path)
    try:
        yield conn
    finally:
        conn.close()


def is_connected(cfg, user: db.User) -> bool:
    with db_conn(cfg) as conn:
        return db.gmail_connected(conn, user.id)


def saved_profile(cfg, user: db.User) -> db.Profile | None:
    with db_conn(cfg) as conn:
        return db.get_profile(conn, user.id)


def txn_cookie_cleared(resp) -> bool:
    """The response deletes the oauth txn cookie (an empty value with an expiry in the past)."""
    return any(h.startswith("applyfirst_oauth=") and ("Max-Age=0" in h or "expires=" in h.lower())
               for h in resp.headers.get_list("set-cookie"))


_BLOCK = re.compile(r"</?(?:p|li|h[1-6]|ul|ol|div|section|nav|header|footer|main|article|table|"
                    r"tr|td|th|dt|dd|dl|pre|figure|figcaption|summary|details|br)\b[^>]*>", re.I)


def page_text(markup: str) -> str:
    """Visible-ish text: scripts/styles dropped, tags stripped, entities decoded, spaces collapsed."""
    markup = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    markup = _BLOCK.sub(" ", markup)
    return clean(_html.unescape(re.sub(r"<[^>]+>", "", markup)))


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    text: str = ""
    children: list["Element"] = field(default_factory=list)


class _Tree(HTMLParser):
    """A forgiving element list: every start tag with its attrs and its inner text."""

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._open: list[Element] = []

    def handle_starttag(self, tag, attrs):
        el = Element(tag, {k.lower(): (v if v is not None else "") for k, v in attrs})
        self.elements.append(el)
        for parent in self._open:
            parent.children.append(el)
        if tag not in self._VOID:
            self._open.append(el)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID and self._open and self._open[-1].tag == tag:
            self._open.pop()

    def handle_endtag(self, tag):
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i].tag == tag:
                del self._open[i:]
                break

    def handle_data(self, data):
        for el in self._open:
            el.text += data


def elements(markup: str) -> list[Element]:
    tree = _Tree()
    tree.feed(markup)
    tree.close()
    return tree.elements


def by_id(markup: str, element_id: str) -> Element | None:
    return next((e for e in elements(markup) if e.attrs.get("id") == element_id), None)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def post_forms(markup: str, action_rx: str) -> list[Element]:
    """POST forms whose action fully matches ``action_rx``, in document order."""
    return [e for e in elements(markup) if e.tag == "form"
            and (e.attrs.get("method") or "").lower() == "post"
            and re.fullmatch(action_rx, e.attrs.get("action", ""))]


def form_inputs(form: Element) -> list[Element]:
    return [c for c in form.children if c.tag in ("input", "textarea", "select")]


def has_class(el: Element, cls: str) -> bool:
    return cls in el.attrs.get("class", "").split()


def count_class(markup: str, cls: str) -> int:
    return sum(1 for e in elements(markup) if has_class(e, cls))
