"""Shared readers for the sign-up journey stylesheets (signup redesign spec 4.1, 4.2 and 8).

Not a test module (no ``test_`` prefix). Imported by ``tests/test_saas_journey.py`` and
``tests/test_saas_signin_failed.py``. Standard library only, so it imports on a bare checkout.

``JOURNEY_TEMPLATES`` is the one list of templates allowed to load the journey look. It starts
empty; each page task appends its template in the same change that links the two stylesheets,
and the scope test in ``test_saas_journey.py`` fails if a template links them without being
listed, or is listed without linking them.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Iterator

ROOT: Path = Path(__file__).resolve().parents[1]
STATIC: Path = ROOT / "applyfirst" / "saas" / "static"
TEMPLATES: Path = ROOT / "applyfirst" / "saas" / "templates"
JOURNEY_CSS: Path = STATIC / "css" / "journey.css"
BASECOAT_CSS: Path = STATIC / "vendor" / "basecoat-1.0.2-agad.css"

JOURNEY_TEMPLATES: list[str] = ["login.html", "onboarding_connect_gmail.html",
                                "onboarding_profile.html", "onboarding_keywords.html",
                                "onboarding_preview.html", "dashboard.html",
                                "signin_failed.html"]

# At-rules whose block holds more rules. Every other at-rule with a block (@font-face, @property,
# @keyframes, @view-transition) is yielded whole, like a style rule.
_CONTAINERS = ("@media", "@supports", "@layer", "@container", "@scope", "@starting-style")


def read_css(path: Path) -> str:
    """The file as text with CRLF normalised to LF and every /* comment */ removed."""
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _blocks(css: str) -> Iterator[tuple[str, str]]:
    """(prelude, body) for every brace-matched block at this level. Strings are respected, and a
    bare statement such as ``@layer a, b;`` is skipped."""
    depth, quote, start, open_at, i, n = 0, "", 0, -1, 0, len(css)
    while i < n:
        ch = css[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == ";" and depth == 0:
            start = i + 1
        elif ch == "{":
            if depth == 0:
                open_at = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise ValueError(f"unbalanced '}}' at offset {i}")
            if depth == 0:
                yield css[start:open_at], css[open_at + 1:i]
                start = i + 1
        i += 1
    if depth or quote:
        raise ValueError("unbalanced braces or an open string at the end of the stylesheet")


def iter_rules(css: str, _chain: tuple[str, ...] = ()) -> Iterator[tuple[str, str, tuple[str, ...]]]:
    """(selector_list, declarations_body, enclosing_at_rules) for every rule, outermost at-rule
    first. Pass comment-free text (``read_css``). Preludes are whitespace-collapsed, so a chain
    reads like ``("@layer journey", "@media (prefers-color-scheme:dark)")``. A rule that nests
    rules (Basecoat's ``&:hover``) is yielded once, nested blocks inside its body."""
    for prelude, body in _blocks(css):
        prelude = _squash(prelude)
        if prelude.startswith(_CONTAINERS):
            yield from iter_rules(body, _chain + (prelude,))
        else:
            yield prelude, body, _chain


def _split_top(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside quotes, parentheses and brackets."""
    out, depth, quote, cur = [], 0, "", ""
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return out


def decls(body: str) -> dict[str, str]:
    """{property: value} for one declaration block, the last one winning. Nested rules are dropped,
    properties are lower-cased, values keep their case and ``!important``, whitespace collapsed."""
    flat, prev = body, None
    while prev != flat:
        prev, flat = flat, re.sub(r"[^{};]*\{[^{}]*\}", ";", flat)
    out: dict[str, str] = {}
    for part in _split_top(flat, ";"):
        prop, sep, value = part.partition(":")
        if sep and prop.strip():
            out[prop.strip().lower()] = _squash(value)
    return out


def _channel(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    h = hex_colour.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"not an opaque hex colour: {hex_colour!r}")
    r, g, b = (_channel(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg_hex: str, bg_hex: str) -> float:
    """The WCAG 2 contrast ratio of two opaque hex colours, from 1.0 to 21.0."""
    a, b = _luminance(fg_hex), _luminance(bg_hex)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def gzip_size(path: Path) -> int:
    """Bytes after gzip level 9 of the file with CRLF normalised to LF (a Windows checkout
    measures the same as the Linux image)."""
    return len(gzip.compress(path.read_bytes().replace(b"\r\n", b"\n"), 9, mtime=0))


_DARK = re.compile(r"^@media \(prefers-color-scheme:\s*dark\)$")


def tokens(css: str, scheme: str) -> dict[str, str]:
    """The ``--j-*`` values journey.css gives ``:root`` in ``"light"`` or ``"dark"``. Light is every
    ``:root`` rule directly in ``@layer journey``; dark is light overlaid with the ``:root`` rules
    inside ``@media (prefers-color-scheme: dark)`` in that layer. Pass ``read_css`` text."""
    if scheme not in ("light", "dark"):
        raise ValueError(f"scheme must be 'light' or 'dark', not {scheme!r}")
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    for selectors, body, chain in iter_rules(css):
        if not chain or chain[0] != "@layer journey":
            continue
        if ":root" not in [s.strip() for s in _split_top(selectors, ",")]:
            continue
        found = {k: v for k, v in decls(body).items() if k.startswith("--j-")}
        if len(chain) == 1:
            light.update(found)
        elif len(chain) == 2 and _DARK.match(chain[1]):
            dark.update(found)
    return dict(light) if scheme == "light" else {**light, **dark}
