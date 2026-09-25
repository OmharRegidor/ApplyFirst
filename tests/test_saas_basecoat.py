"""Basecoat, vendored and trimmed (sign-up redesign spec 4.1, 4.3 and 8).

The sign-up pages use eight of Basecoat's parts. tools/basecoat/trim.py cuts them out of the
pinned upstream file, so these tests pin both files by sha256, run the trim again and require the
same bytes, and read the trimmed file for anything that must never reach a phone: Tailwind's
reset, the class-based dark mode, a colour block, a component we do not use, an endless
animation, or an !important that no layer above Basecoat could override.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from applyfirst.saas import static_assets

SAAS = Path(static_assets.__file__).parent
REPO = SAAS.parents[1]
STATIC = SAAS / "static"
TEMPLATES = SAAS / "templates"
TOOLS = REPO / "tools" / "basecoat"
UPSTREAM = TOOLS / "basecoat-1.0.2.cdn.min.css"
TRIM_PY = TOOLS / "trim.py"
TRIMMED = STATIC / "vendor" / "basecoat-1.0.2-agad.css"
BASECOAT_LICENCE = STATIC / "licenses" / "basecoat-MIT.txt"
TAILWIND_LICENCE = STATIC / "licenses" / "tailwindcss-MIT.txt"
NEW_FILES = (UPSTREAM, TRIM_PY, TRIMMED, BASECOAT_LICENCE, TAILWIND_LICENCE)

# package/dist/basecoat.cdn.min.css in the npm tarball
# https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz
UPSTREAM_SHA = "8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0"
TRIMMED_SHA = "4aae6ed8773c27938e12e6c87139f99305fb680a4cd5298c7864034119325157"
GZIP_CAP = 7000                                                              # spec 8
ALLOWED = {"btn", "card", "card-title", "card-description", "card-action", "field", "input",
           "label", "textarea", "alert", "badge"}                              # spec 4.3 step 4
UNUSED_PARTS = ("dialog", "alert-dialog", "menu", "dropdown-menu", "popover", "select", "tabs",
                "toast", "sidebar", "table", "command", "combobox", "accordion", "avatar")
PREFLIGHT = {"*", "html", "body", "a", "h1", "h2", "h3", "h4", "h5", "h6", "img", "details",
             "summary", "button", "input", "textarea", "select", "ol", "ul", "hr", "table",
             ":root", ":host", "::backdrop", "::placeholder", "::file-selector-button"}
# What the trimmed file reads but leaves to journey.css (spec 4.4). journey.css defines each one.
SUPPLIED_BY_JOURNEY = ("--color-card", "--color-card-foreground", "--color-destructive",
                       "--color-foreground", "--color-input", "--color-muted-foreground",
                       "--color-primary", "--color-primary-foreground", "--color-ring", "--radius")
# The only custom properties the trimmed file may define: sizes, radius, spacing, text sizes,
# weights, leading and Tailwind's internal --tw-* plumbing (spec 4.3 step 3).
OWN_VARIABLE = re.compile(r"--(?:spacing|text-(?:xs|sm|base|lg)|font-weight-|leading-|radius-"
                          r"|default-transition-|tw-)")
# Markup whose Basecoat rules trim.py drops (its step 4b). A page that writes one gets no styling.
TRIMMED_MARKUP = re.compile(r"""data-(?:variant|size|orientation|invalid|disabled)\b"""
                            r"""|type=["']?(?:checkbox|radio|range)\b|role=["']?switch\b""")
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")      # test M-2


def _lf_bytes(path: Path) -> bytes:
    """The file's bytes with CRLF normalised to LF, so a Windows checkout hashes the same."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _gz(path: Path) -> int:
    return len(gzip.compress(_lf_bytes(path), 9, mtime=0))


def _css(path: Path) -> str:
    return re.sub(r"/\*.*?\*/", "", _lf_bytes(path).decode("utf-8"), flags=re.S)


def _without_not_and_has(selector: str) -> str:
    """The selector with the arguments of :not() and :has() removed: what is left is what it
    styles."""
    out, i = [], 0
    while i < len(selector):
        if selector.startswith((":not(", ":has("), i):
            depth, i = 1, i + 5
            while depth:
                depth += {"(": 1, ")": -1}.get(selector[i], 0)
                i += 1
        else:
            out.append(selector[i])
            i += 1
    return "".join(out)


def _selectors(selector_list: str) -> list[str]:
    """The selectors of a list, split on the commas that sit outside brackets."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(selector_list):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            out.append(selector_list[start:i])
            start = i + 1
    return out + [selector_list[start:]]


def _styled_classes(selector: str) -> set[str]:
    styled = re.sub(r"\[[^\]]*\]", "", _without_not_and_has(selector))
    return set(re.findall(r"\.(-?[_a-zA-Z][\w-]*)", styled))


@pytest.fixture(scope="module")
def trim():
    """tools/basecoat/trim.py, imported by path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("basecoat_trim", TRIM_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rules(nodes, chain=()):
    """(selector list, body, enclosing at-rules) for every style rule, depth first."""
    for node in nodes:
        if node.children is not None:
            yield from _rules(node.children, chain + (node.prelude,))
        elif node.is_rule:
            yield node.prelude, node.body, chain


@pytest.fixture(scope="module")
def layer(trim):
    """The children of the one @layer basecoat block."""
    top = trim.parse(_css(TRIMMED))
    assert top[0].prelude == "@layer basecoat"
    return top[0].children


# --- vendor pins (spec 8) ---------------------------------------------------------------------

def test_the_upstream_file_is_the_pinned_basecoat_release():
    assert hashlib.sha256(_lf_bytes(UPSTREAM)).hexdigest() == UPSTREAM_SHA


def test_the_trimmed_file_is_the_pinned_build():
    assert hashlib.sha256(_lf_bytes(TRIMMED)).hexdigest() == TRIMMED_SHA


def test_running_trim_again_gives_the_committed_file_byte_for_byte(trim):
    assert trim.trim(_lf_bytes(UPSTREAM)) == _lf_bytes(TRIMMED), (
        "the trimmed file was edited by hand, or trim.py changed without re-running it")


def test_trim_reads_and_writes_the_pinned_paths(trim):
    assert (trim.SOURCE, trim.OUTPUT) == (UPSTREAM, TRIMMED)
    assert trim.SOURCE_SHA256 == UPSTREAM_SHA
    assert trim.GZIP_CAP == GZIP_CAP


@pytest.mark.parametrize("change", [
    (b"", b"@layer reset{a{color:red}}"),                         # a new top-level statement
    (b"@layer components{", b"@layer components{.btn:where(.dark *){color:red}"),  # new dark form
    (b"@layer components{", b"@layer components{@font-feature-values X{@swash{a:1}}"),
])
def test_trim_stops_on_input_it_does_not_recognise(trim, change):
    old, new = change
    source = _lf_bytes(UPSTREAM)
    changed = source + new if old == b"" else source.replace(old, new, 1)
    with pytest.raises(trim.TrimError):
        trim.trim(changed)


def test_gitattributes_keeps_both_basecoat_files_byte_for_byte():
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "applyfirst/saas/static/vendor/** -text" in attributes
    assert "tools/basecoat/*.css -text" in attributes


def test_both_files_have_lf_endings_only():
    assert b"\r" not in UPSTREAM.read_bytes()
    assert b"\r" not in TRIMMED.read_bytes()


def test_the_trimmed_file_stays_inside_its_gzip_cap():
    assert _gz(TRIMMED) <= GZIP_CAP, f"trimmed Basecoat gzip {_gz(TRIMMED)} B"


def test_the_header_names_the_source_its_sha256_the_script_the_date_and_the_licences():
    head = _lf_bytes(TRIMMED).decode("utf-8").split("@layer basecoat{", 1)[0]
    for needle in ("/*! tailwindcss v4.3.1 | MIT License", "/*! basecoat-css 1.0.2 | MIT License",
                   "tools/basecoat/basecoat-1.0.2.cdn.min.css", UPSTREAM_SHA,
                   "tools/basecoat/trim.py", "basecoat-MIT.txt", "tailwindcss-MIT.txt"):
        assert needle in head, needle
    assert re.search(r"trim\.py on \d{4}-\d{2}-\d{2}\.", head)


def test_the_licences_name_their_authors():
    basecoat = BASECOAT_LICENCE.read_text(encoding="utf-8")
    tailwind = TAILWIND_LICENCE.read_text(encoding="utf-8")
    for licence in (basecoat, tailwind):
        assert licence.startswith("MIT License")
        assert "Permission is hereby granted, free of charge" in licence
    assert "Copyright (c) 2025 Ronan Berder" in basecoat
    assert "Copyright (c) Tailwind Labs, Inc." in tailwind


def test_no_new_file_name_contains_a_motion_asset_name():
    for path in NEW_FILES:
        assert path.is_file(), path
        assert not any(name in path.name for name in MOTION_ASSETS), path.name


# --- trimmed content (spec 8) -----------------------------------------------------------------

def test_everything_sits_in_the_basecoat_layer_except_property_registrations(trim):
    top = trim.parse(_css(TRIMMED))
    assert top[0].prelude == "@layer basecoat" and top[0].children
    rest = [node.prelude for node in top[1:]]
    assert rest and all(re.fullmatch(r"@property --tw-[\w-]+", p) for p in rest), rest


def test_no_preflight_or_bare_element_selector(layer):
    rules = list(_rules(layer))
    theme = [r for r in rules if r[0] == ":root,:host"]
    assert len(theme) == 1 and theme[0][2] == (), "one theme rule, at the top of the layer"
    assert all(d.split(":", 1)[0].startswith("--") for d in theme[0][1].split(";"))
    for selectors, _body, _chain in rules:
        if selectors == ":root,:host":
            continue
        for selector in _selectors(selectors):
            assert selector.strip() not in PREFLIGHT, selectors
            assert _styled_classes(selector), f"a selector with no class: {selector}"


def test_only_the_parts_the_sign_up_pages_use_are_styled(layer):
    styled = set()
    for selectors, _body, _chain in _rules(layer):
        if selectors != ":root,:host":
            styled |= {c for s in _selectors(selectors) for c in _styled_classes(s)}
    assert styled <= ALLOWED, sorted(styled - ALLOWED)
    assert not styled & set(UNUSED_PARTS)


def test_dark_mode_follows_the_phone_setting_not_a_class(layer):
    css = _css(TRIMMED)
    assert ".dark" not in css and "html.dark" not in css
    chains = [chain for _s, _b, chain in _rules(layer)]
    assert any("@media (prefers-color-scheme:dark)" in chain for chain in chains)
    assert not re.search(r"prefers-color-scheme:\s*light", css)


def test_no_colour_block_font_or_easing_variable_is_defined(layer):
    css = _css(TRIMMED)
    assert "oklch(" not in css
    defined = set()
    for _selectors, body, _chain in _rules(layer):
        defined |= set(re.findall(r"(?:^|;)\s*(--[\w-]+)\s*:", body))
    assert defined and all(OWN_VARIABLE.match(name) for name in defined), sorted(
        n for n in defined if not OWN_VARIABLE.match(n))


def test_nothing_animates_and_nothing_is_important():
    css = _css(TRIMMED)
    assert "@keyframes" not in css
    assert not re.search(r"(?<![\w-])animation(?:-name)?\s*:", css)
    assert "infinite" not in css
    assert "!important" not in css


def test_every_variable_read_is_defined_registered_or_supplied_by_journey():
    css = _css(TRIMMED)
    read = set(re.findall(r"var\((--[\w-]+)", css))
    defined = set(re.findall(r"(?<![\w-])(--[\w-]+)\s*:", css))
    registered = set(re.findall(r"@property (--[\w-]+)", css))
    assert read - defined - registered == set(SUPPLIED_BY_JOURNEY)
    assert registered <= read, sorted(registered - read)                 # step 6: only what is read


def test_no_template_writes_markup_whose_basecoat_rules_were_trimmed():
    for path in sorted(TEMPLATES.glob("*.html")):
        src = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        found = sorted({m.group(0) for m in TRIMMED_MARKUP.finditer(src)})
        assert found == [], f"{path.name}: trim.py drops Basecoat's rules for {found}"
