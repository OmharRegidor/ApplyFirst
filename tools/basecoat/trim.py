"""Rebuild Agad's trimmed Basecoat stylesheet from the pinned upstream file (spec 4.3).

Run it by hand, and only when Basecoat is upgraded:

    .venv/Scripts/python.exe tools/basecoat/trim.py

Input:  tools/basecoat/basecoat-1.0.2.cdn.min.css, byte for byte the file
        package/dist/basecoat.cdn.min.css in the basecoat-css 1.0.2 npm tarball.
Output: applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css, LF line endings.

The output depends only on the input bytes and the constants below, so
tests/test_saas_basecoat.py calls trim() again and requires the committed file byte for byte.
Anything in the input this script does not recognise stops it with TrimError instead of being
copied through, so an upgrade cannot quietly bring back a reset, a colour block or a new layer.
Standard library only. No Node, no Tailwind, nothing to install.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.0.2"
SOURCE = ROOT / "tools" / "basecoat" / f"basecoat-{VERSION}.cdn.min.css"
OUTPUT = ROOT / "applyfirst" / "saas" / "static" / "vendor" / f"basecoat-{VERSION}-agad.css"
SOURCE_SHA256 = "8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0"
SOURCE_URL = "https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz"
SOURCE_IN_PACKAGE = "package/dist/basecoat.cdn.min.css"
TRIMMED_ON = "2026-09-25"           # printed in the header; change it by hand when you re-trim
GZIP_CAP = 7000                     # spec 8

# Step 4: the only Basecoat component classes the sign-up pages use.
ALLOWED = frozenset({"btn", "card", "card-title", "card-description", "card-action", "field",
                     "input", "label", "textarea", "alert", "badge"})
# Step 4b: markup the journey pages never write (they use BEM classes such as btn--primary and
# badge--ok, mark errors with aria-invalid, and every input is a text box or a textarea). A
# selector that can only match through one of these is dropped from its list, and a rule left
# with no selector is dropped. tests/test_saas_basecoat.py fails if a template starts writing one.
NEVER_IN_OUR_MARKUP = re.compile(
    r"\[data-(?:variant|size|orientation)=|\[data-(?:invalid|disabled)\b"
    r"|\[type=(?:checkbox|radio|range)\]|\[role=switch\]|:checked")
# Step 4c: a rule with !important is dropped. An important declaration in the lowest layer beats
# every declaration in the layers above it, so journey.css could never override it.
# Step 5: the two dark forms Tailwind writes for Basecoat.
DARK_IS = ":is(html.dark *)"
DARK_PREFIX = "html.dark "
DARK_MEDIA = "@media (prefers-color-scheme:dark)"
# Step 3: theme variables never copied. --color-* carry colour, and journey.css supplies the ones
# the kept rules read (spec 4.4). The others collide with app.css (--font-sans, the frozen
# --ease-out) or serve dropped parts, so a kept rule that reads one of them stops the script.
COLOUR_THEME = re.compile(r"--color-")
COLLIDING_THEME = re.compile(r"--(?:font-(?!weight-)|ease-|animate-|default-(?:mono-)?font)")
# Step 2: top-level statements dropped whole.
DROPPED_TOP = frozenset({"@layer properties", "@layer base", "@layer utilities", ":root", ".dark",
                         "@keyframes pulse", "@keyframes toast-up"})
GROUPING = ("@layer", "@media", "@supports", "@container", "@starting-style")
_VAR_READ = re.compile(r"var\((--[\w-]+)")
_CLASS = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")


class TrimError(ValueError):
    """The input is not shaped the way this script expects. Read it before changing the rules."""


class Node:
    """One statement. A style rule has a body, a grouping rule (@layer, @media, @supports,
    @container, @starting-style) has children, and a comment or a ';' statement has neither."""

    __slots__ = ("prelude", "body", "children")

    def __init__(self, prelude: str, body: str | None = None,
                 children: list[Node] | None = None) -> None:
        self.prelude, self.body, self.children = prelude, body, children

    @property
    def is_rule(self) -> bool:
        return self.children is None and not self.prelude.startswith(("@", "/*"))


# --- reading --------------------------------------------------------------------------------

def _skip_string(text: str, i: int) -> int:
    """The index just past the quoted string that starts at text[i]."""
    quote, i = text[i], i + 1
    while text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def _block_end(text: str, i: int) -> int:
    """text[i] is '{'. The index of the '}' that closes it."""
    depth = 0
    while True:
        if text[i] in "\"'":
            i = _skip_string(text, i)
            continue
        if text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1


def parse(text: str) -> list[Node]:
    """Split a stylesheet, or the inside of a grouping rule, into statements."""
    nodes: list[Node] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text.startswith("/*", i):
            end = text.index("*/", i) + 2
            nodes.append(Node(text[i:end]))
            i = end
            continue
        j = i
        while j < n and text[j] not in "{;}":
            j = _skip_string(text, j) if text[j] in "\"'" else j + 1
        prelude = text[i:j].strip()
        if j == n or text[j] == "}":
            raise TrimError(f"declarations outside a rule: {prelude[:60]!r}")
        if text[j] == ";":
            nodes.append(Node(prelude))
            i = j + 1
            continue
        end = _block_end(text, j)
        inner = text[j + 1:end]
        if prelude.startswith(GROUPING):
            nodes.append(Node(prelude, children=parse(inner)))
        elif prelude.startswith("@") or "{" not in inner:
            nodes.append(Node(prelude, body=inner))
        else:
            raise TrimError(f"a rule nested inside {prelude[:60]!r}")
        i = end + 1
    return nodes


def split_top(text: str, sep: str) -> list[str]:
    """Split text on sep wherever sep is outside brackets, parentheses and strings."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            i = _skip_string(text, i)
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _close(text: str, start: int) -> int:
    """text[start - 1] is '('. The index just past its matching ')'."""
    depth, i = 1, start
    while depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return i


def without(selector: str, groups: tuple[str, ...]) -> str:
    """The selector with the argument of every listed pseudo-class (":not(" and so on) removed."""
    out, i = [], 0
    while i < len(selector):
        hit = next((g for g in groups if selector.startswith(g, i)), None)
        if hit is None:
            out.append(selector[i])
            i += 1
        else:
            i = _close(selector, i + len(hit))
    return "".join(out)


def classes(selector: str) -> set[str]:
    """The classes a selector styles. Attribute values are ignored, and so are the arguments of
    :not(), which names what must be absent, and :has(), which names what sits inside."""
    styled = without(selector, (":not(", ":has("))
    return set(_CLASS.findall(re.sub(r"\[[^\]]*\]", "", styled)))


def _alternatives(selector: str) -> list[str]:
    """Every way the selector can match: :not() arguments removed (they are never required),
    and each :is(), :where() and :has() list expanded into its choices."""
    selector = without(selector, (":not(",))
    m = re.search(r":(?:is|where|has)\(", selector)
    if m is None:
        return [selector]
    end = _close(selector, m.end())
    head, tail = selector[:m.start()], selector[end:]
    return [alt for arg in split_top(selector[m.end():end - 1], ",")
            for alt in _alternatives(head + arg + tail)]


def can_match_our_markup(selector: str) -> bool:
    """False when every way the selector can match needs markup the journey pages never write."""
    return any(not NEVER_IN_OUR_MARKUP.search(alt) for alt in _alternatives(selector))


# --- deciding -------------------------------------------------------------------------------

def _undark(selector: str) -> str:
    """Step 5: the selector without its dark marker, which must sit outside every bracket."""
    at = selector.find(DARK_IS)
    if at < 0:
        at, selector = 0, selector.removeprefix(DARK_PREFIX)
    else:
        selector = selector[:at] + selector[at + len(DARK_IS):]
    if selector[:at].count("(") != selector[:at].count(")") or "dark" in selector:
        raise TrimError(f"a dark form this script does not know: {selector[:80]!r}")
    return selector


def _keep_rule(rule: Node) -> Node | None:
    selectors = split_top(rule.prelude, ",")
    dark = [DARK_IS in s or s.startswith(DARK_PREFIX) for s in selectors]
    if any(dark) and not all(dark):
        raise TrimError(f"a selector list mixes light and dark: {rule.prelude[:80]!r}")
    if all(dark):
        selectors = [_undark(s) for s in selectors]
    elif "dark" in rule.prelude:
        raise TrimError(f"a dark form this script does not know: {rule.prelude[:80]!r}")
    if not all(classes(s) and classes(s) <= ALLOWED for s in selectors):
        return None                                                         # step 4
    selectors = [s for s in selectors if can_match_our_markup(s)]            # step 4b
    if not selectors or "!important" in rule.body:                          # step 4c
        return None
    kept = Node(",".join(selectors), body=rule.body)
    return Node(DARK_MEDIA, children=[kept]) if all(dark) else kept


def _filter(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    for node in nodes:
        if node.is_rule:
            kept = _keep_rule(node)
        elif node.children is not None and node.prelude.startswith(GROUPING[1:]):
            kids = _filter(node.children)
            kept = Node(node.prelude, children=kids) if kids else None
        else:
            raise TrimError(f"unexpected statement in @layer components: {node.prelude[:60]!r}")
        if kept is not None:
            out.append(kept)
    return _merge(out)


def _merge(nodes: list[Node]) -> list[Node]:
    """Join neighbouring grouping rules with the same prelude. Order and meaning are unchanged."""
    out: list[Node] = []
    for node in nodes:
        if (node.children is not None and out and out[-1].children is not None
                and out[-1].prelude == node.prelude):
            out[-1] = Node(node.prelude, children=_merge(out[-1].children + node.children))
        else:
            out.append(node)
    return out


def reads(nodes: list[Node]) -> set[str]:
    """Every custom property the rules read with var()."""
    names: set[str] = set()
    for node in nodes:
        if node.children is not None:
            names |= reads(node.children)
        else:
            names |= set(_VAR_READ.findall(node.body or ""))
    return names


def _theme(layer: Node, wanted_by_rules: set[str]) -> Node:
    """Step 3: the theme variables the kept rules read, and the ones those read in turn."""
    if [c.prelude for c in layer.children] != [":root,:host"]:
        raise TrimError("@layer theme should hold exactly one :root,:host rule")
    root = layer.children[0]
    decls = [d.split(":", 1) for d in split_top(root.body, ";") if d.strip()]
    values = {name.strip(): value for name, value in decls}
    wanted: set[str] = set()
    frontier = {r for r in wanted_by_rules if r in values}
    while frontier:
        name = frontier.pop()
        if COLLIDING_THEME.match(name):
            raise TrimError(f"a kept rule reads {name}, which app.css owns or which was dropped")
        if COLOUR_THEME.match(name):
            continue
        wanted.add(name)
        frontier |= {r for r in _VAR_READ.findall(values[name]) if r in values} - wanted
    body = ";".join(f"{name.strip()}:{value}" for name, value in decls if name.strip() in wanted)
    return Node(":root,:host", body=body)


# --- writing --------------------------------------------------------------------------------

def _emit(nodes: list[Node], lines: list[str]) -> None:
    for node in nodes:
        if node.children is None:
            lines.append(f"{node.prelude}{{{node.body}}}")
        else:
            lines.append(node.prelude + "{")
            _emit(node.children, lines)
            lines.append("}")


def header(source_sha256: str) -> list[str]:
    return [
        f"/*! basecoat-css {VERSION} | MIT License | https://basecoatui.com */",
        f"/* Trimmed for Agad by tools/basecoat/trim.py on {TRIMMED_ON}. Do not edit this file:",
        "   change trim.py and run it again.",
        f"   Source: tools/basecoat/basecoat-{VERSION}.cdn.min.css, which is {SOURCE_IN_PACKAGE}",
        f"   from {SOURCE_URL}",
        f"   sha256 {source_sha256}",
        "   Licences: /static/licenses/basecoat-MIT.txt, /static/licenses/tailwindcss-MIT.txt */",
    ]


def lf(data: bytes) -> bytes:
    """The bytes with CRLF turned into LF, so a Windows checkout hashes and trims the same."""
    return data.replace(b"\r\n", b"\n")


def trim(source: bytes) -> bytes:
    """The trimmed stylesheet for these upstream bytes (spec 4.3 steps 1 to 7)."""
    source = lf(source)
    licence = theme = components = None
    properties: list[Node] = []
    for node in parse(source.decode("utf-8")):
        head = node.prelude
        if head.startswith("/*! tailwindcss v"):
            licence = head                                                  # step 1
        elif head in DROPPED_TOP:
            continue                                                        # step 2
        elif head == "@layer theme":
            theme = node
        elif head == "@layer components":
            components = _filter(node.children)                             # steps 4, 4b, 5
        elif head.startswith("@property --tw-"):
            properties.append(node)
        else:
            raise TrimError(f"unexpected top-level statement: {head[:60]!r}")
    if licence is None or theme is None or components is None:
        raise TrimError("the Tailwind licence, @layer theme or @layer components is missing")
    read = reads(components)
    kept_props = [p for p in properties if p.prelude.split()[1] in read]  # step 6
    lines = [licence, *header(hashlib.sha256(source).hexdigest()), "@layer basecoat{"]
    _emit([_theme(theme, read), *components], lines)                        # steps 3 and 7
    lines.append("}")
    _emit(kept_props, lines)
    return ("\n".join(lines) + "\n").encode("utf-8")


def main() -> int:
    source = lf(SOURCE.read_bytes())
    digest = hashlib.sha256(source).hexdigest()
    if digest != SOURCE_SHA256:
        print(f"{SOURCE.name}: sha256 {digest}, expected {SOURCE_SHA256}", file=sys.stderr)
        return 1
    out = trim(source)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(out)
    size = len(gzip.compress(out, 9, mtime=0))
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}: {len(out)} B, {size} B gzip "
          f"(cap {GZIP_CAP}), sha256 {hashlib.sha256(out).hexdigest()}")
    return 0 if size <= GZIP_CAP else 1


if __name__ == "__main__":
    sys.exit(main())
