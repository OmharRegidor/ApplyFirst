"""The sign-up journey's look: journey.css, its cascade layer and where it may load (signup
redesign spec 4.2, 4.4, 5 and 8).

journey.css lives in its own layer, above Basecoat and every app.css layer and below the frozen
motion layer. So any rule in it beats Basecoat and app.css whatever the specificity, and none can
outrank motion.css. That power is also the risk: one careless rule would repaint the Activate
button in the middle of its frozen morph, clip a keyword chip, bring the gradient back, or drop a
colour under AA in dark mode, and no page test would notice. So these tests read the frozen
values straight out of the file, compute the contrast from the real tokens in both schemes, pin
every Basecoat leak spec 5.2 names, and allow the two new stylesheets only on the templates
listed in ``_journey_css.JOURNEY_TEMPLATES``.

Page tasks add their own structure checks at the end of this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _journey_css import (
    BASECOAT_CSS, JOURNEY_CSS, JOURNEY_TEMPLATES, ROOT, STATIC, TEMPLATES, contrast, decls,
    gzip_size, iter_rules, read_css, tokens,
)
from _saas_client import client_for

APP_CSS = STATIC / "css" / "app.css"
MOTION_CSS = STATIC / "css" / "motion.css"
BASE_HTML = TEMPLATES / "base.html"
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")      # test M-2
SECTIONS = ("fonts", "tokens", "basecoat-map", "base", "components", "chrome", "login",
            "onboarding", "dashboard", "signin-failed", "motion")
# Spec 4.2: the seven templates that may ever load the look.
SPEC_JOURNEY = {"login.html", "onboarding_connect_gmail.html", "onboarding_profile.html",
                "onboarding_keywords.html", "onboarding_preview.html", "dashboard.html",
                "signin_failed.html"}
PAGE_TEMPLATES = sorted(p.name for p in TEMPLATES.glob("*.html")
                        if not p.name.startswith("_") and p.name != "base.html")
KEEP_TODAY = ("/", "/privacy", "/terms")                                     # spec D1
J_TOKENS = {"--j-ground", "--j-surface", "--j-text", "--j-muted", "--j-edge", "--j-link",
            "--j-primary", "--j-primary-hover", "--j-hairline", "--j-attn-fg", "--j-attn-bg",
            "--j-ok-fg", "--j-ok-bg", "--j-danger-fg", "--j-shadow"}
SCHEME_FREE = {"--j-primary", "--j-primary-hover"}      # the frozen blue and its hover, both modes
JOURNEY_STACK = ('-apple-system, BlinkMacSystemFont, "Inter Agad", "Inter Agad Fallback", '
                 'system-ui, "Segoe UI", Roboto, sans-serif')

JOURNEY = read_css(JOURNEY_CSS)
RULES = [(sel, body, chain) for sel, body, chain in iter_rules(JOURNEY)
         if chain and chain[0] == "@layer journey"]


# --- small selector readers ------------------------------------------------------------------

def _split(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside parentheses, brackets and quotes."""
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
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    out.append(cur.strip())
    return out


def _norm(part: str) -> str:
    """One selector, combinators without spaces around them: ``.alert > svg`` -> ``.alert>svg``."""
    return re.sub(r"\s*([>+~])\s*", r"\1", " ".join(part.split()))


def _subject(part: str) -> str:
    """The last compound selector of one complex selector (the element the rule styles)."""
    depth, last = 0, 0
    for i, ch in enumerate(_norm(part)):
        depth += (ch in "([") - (ch in ")]")
        if depth == 0 and ch in " >+~":
            last = i + 1
    return _norm(part)[last:]


def _positive(subject: str) -> str:
    """The subject without its :not(...) parts, which name what it does NOT style."""
    return re.sub(r":not\([^)]*\)", "", subject)


def _parts(sel: str) -> list[str]:
    return [_norm(p) for p in _split(sel)]


def _plain(chain: tuple) -> bool:
    """Directly in @layer journey, under no media or other condition."""
    return chain == ("@layer journey",)


def _declared(part: str, prop: str, *, chain_ok=_plain) -> str | None:
    """What the last journey rule listing exactly ``part`` sets ``prop`` to, or None."""
    value = None
    for sel, body, chain in RULES:
        if chain_ok(chain) and part in _parts(sel):
            value = decls(body).get(prop, value)
    return value


def _in(chain: tuple, pattern: str) -> bool:
    return any(re.search(pattern, link) for link in chain)


# --- layers (spec 4.2, 8) -------------------------------------------------------------------

def _layer_statement(path: Path) -> list[str]:
    m = re.search(r"@layer\s+([^;{]+);", read_css(path))
    assert m, f"{path.name} opens without a layer order statement"
    return [name.strip() for name in m.group(1).split(",")]


def test_app_css_puts_basecoat_first_and_journey_last():
    assert _layer_statement(APP_CSS) == ["basecoat", "reset", "tokens", "base", "components",
                                         "screens", "journey"]


def test_the_frozen_motion_layer_still_lands_above_journey():
    """The first appearance of a name fixes its place: app.css loads first, then motion.css
    (M-1), whose own statement at motion.css:2 appends motion after journey."""
    order: list[str] = []
    for path in (APP_CSS, MOTION_CSS):
        for name in _layer_statement(path):
            if name not in order:
                order.append(name)
    assert order == ["basecoat", "reset", "tokens", "base", "components", "screens", "journey",
                     "motion"]


@pytest.mark.parametrize("path,layer", [(JOURNEY_CSS, "journey"), (BASECOAT_CSS, "basecoat")],
                         ids=["journey.css", "basecoat"])
def test_every_rule_in_the_new_stylesheets_sits_in_its_own_layer(path, layer):
    """An unlayered rule beats every layer (Basecoat's own :root block did exactly that), so
    only @font-face and @property may stay outside, and nothing may open a sub-layer."""
    loose = []
    for sel, _body, chain in iter_rules(read_css(path)):
        if not chain:
            if not sel.startswith(("@font-face", "@property")):
                loose.append(sel)
        elif chain[0] != f"@layer {layer}" or any(c.startswith("@layer") for c in chain[1:]):
            loose.append(f"{sel} in {chain}")
    assert loose == [], f"{path.name}: rules outside @layer {layer}: {loose[:5]}"


def test_journey_css_keeps_its_eleven_sections_in_one_layer_block():
    raw = JOURNEY_CSS.read_bytes().decode("utf-8").replace("\r\n", "\n")
    found = re.findall(r"/\* ---- (\d+) ([\w-]+) \*/", raw)
    assert found == [(str(i), name) for i, name in enumerate(SECTIONS, 1)], found
    opens = [m.start() for m in re.finditer(r"@layer\s+journey\s*\{", raw)]
    assert len(opens) == 1, "exactly one @layer journey { ... } block"
    assert raw.index("/* ---- 1 fonts */") < opens[0] < raw.index("/* ---- 2 tokens */")
    assert raw.rstrip().endswith("}") and read_css(JOURNEY_CSS).rstrip().endswith("}")
    assert "\r" not in raw, "journey.css is written with LF endings"


# --- frozen values, statically (spec 8, 9) -----------------------------------------------------

_BTN = re.compile(r"\.(btn(?:--[\w-]+)?)(?![\w-])")


def _styles_the_primary(part: str) -> bool:
    """True when ``part`` can style a .btn--primary element itself: its subject names
    .btn--primary, or names .btn with no other variant. Pseudo-elements are not the button."""
    subject = _subject(part)
    if "::" in subject or re.search(r":(?:before|after)\b", subject):
        return False
    names = set(_BTN.findall(_positive(subject)))
    return "btn--primary" in names or (names == {"btn"})


def test_no_journey_rule_gives_the_primary_an_image_a_fade_or_other_corners():
    """motion.css's af-fill morph starts from a flat #0B6BC7 at 12px and opacity 1 (spec 5.2).
    background-image may only be none, which is how journey removes app.css's gradient."""
    bad = []
    for sel, body, _chain in RULES:
        if not any(_styles_the_primary(p) for p in _parts(sel)):
            continue
        d = decls(body)
        if d.get("background-image", "none").replace("!important", "").strip() != "none":
            bad.append((sel, "background-image", d["background-image"]))
        shorthand = d.get("background", "")
        if re.search(r"gradient|url\(|--grad|image-set", shorthand):
            bad.append((sel, "background", shorthand))
        if "opacity" in d and float(d["opacity"].replace("!important", "")) < 1:
            bad.append((sel, "opacity", d["opacity"]))
        if "border-radius" in d and d["border-radius"] != "var(--r-md)":
            bad.append((sel, "border-radius", d["border-radius"]))
    assert bad == []


def test_the_journey_primary_is_flat_blue_and_disabled_or_busy_wins_over_hover():
    assert _declared(".btn--primary", "background-image") == "none"
    assert _declared(".btn--primary", "background-color") == "var(--j-primary)"
    hover = [i for i, (sel, _b, _c) in enumerate(RULES) if ".btn--primary:hover" in _parts(sel)]
    held = [i for i, (sel, body, _c) in enumerate(RULES)
            if any(_styles_the_primary(p) and "disabled" in p and "busy" in p for p in _parts(sel))]
    assert hover and len(held) == 1, "one rule holds the disabled and the busy primary"
    d = decls(RULES[held[0]][1])
    assert (d.get("background-color"), d.get("opacity"), d.get("border-radius")) == (
        "var(--j-primary)", "1", "var(--r-md)")
    assert held[0] > max(hover), "the held rule must come after every hover rule to win"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_primary_is_the_frozen_blue_in_both_schemes(scheme):
    t = tokens(JOURNEY, scheme)
    assert t["--j-primary"].upper() == "#0B6BC7"
    assert t["--j-primary-hover"].upper() == "#0A5AA8"


def test_journey_css_leaves_the_live_panel_frame_alone():
    """.status--live is the af-fill end state: navy, 24px, position relative, isolated, opaque."""
    frozen = {"background", "background-color", "background-image", "color", "border-radius",
              "position", "isolation", "opacity"}
    bad = [(sel, sorted(frozen & set(decls(body))))
           for sel, body, _c in RULES
           if any(re.search(r"\.status(?:--live)?(?![\w-])", _subject(p)) for p in _parts(sel))
           and frozen & set(decls(body))]
    assert bad == []


def test_journey_css_never_rings_or_clips_a_keyword_chip():
    """motion.css draws the new-chip ring with box-shadow on .kw, and a clipped parent cuts it."""
    bad = []
    for sel, body, _c in RULES:
        d = decls(body)
        for p in _parts(sel):
            subject = _subject(p)
            if re.search(r"\.kw(?![\w-])", subject) and {"box-shadow", "overflow", "overflow-x",
                                                        "overflow-y", "clip-path"} & set(d):
                bad.append(sel)
            if re.search(r"\.(?:kw|chip-list)(?![\w-])", subject) and re.search(
                    r"hidden|clip", d.get("overflow", "")):
                bad.append(sel)
    assert bad == []


def test_journey_css_never_draws_on_a_button_pseudo_element():
    """motion.css owns a.btn[data-state=busy]::before (the spinner); a ::after on a button is
    the tap-extender trap spec 5.2 forbids. Quiet links carry their own ::after instead."""
    bad = [sel for sel, _b, _c in RULES for p in _parts(sel)
           if _BTN.search(p) and re.search(r"::?(?:before|after)\b", p)]
    assert bad == []


def test_journey_css_only_reads_the_existing_easing_and_defines_none():
    """--ease-out, --ease-settle, --ease-exit and --ease-spring are frozen motion names."""
    assert not re.search(r"--ease-[\w-]*\s*:", JOURNEY), "journey.css defines an --ease-* name"
    used = set(re.findall(r"var\(\s*(--ease-[\w-]+)", JOURNEY))
    assert used <= {"--ease-land"}, f"only the existing --ease-land curve (spec 5.4), got {used}"


# --- tokens and contrast (spec 5.3) ----------------------------------------------------------

def test_both_schemes_define_every_journey_token():
    light, dark = tokens(JOURNEY, "light"), tokens(JOURNEY, "dark")
    assert set(light) == J_TOKENS
    unchanged = sorted(k for k in J_TOKENS - SCHEME_FREE if dark[k] == light[k])
    assert unchanged == [], f"dark mode must redefine {unchanged}"


# (scheme, foreground, background, the ratio spec 5.3 records). A token name or a literal hex.
CONTRAST = [
    ("light", "--j-text", "--j-ground", 14.20), ("light", "--j-text", "--j-surface", 15.39),
    ("light", "--j-muted", "--j-ground", 6.08), ("light", "--j-muted", "--j-surface", 6.59),
    ("light", "--j-edge", "--j-ground", 3.47), ("light", "--j-edge", "--j-surface", 3.76),
    ("light", "--j-link", "--j-ground", 4.91), ("light", "--j-link", "--j-surface", 5.33),
    ("light", "#FFFFFF", "--j-primary", 5.33), ("light", "--j-attn-fg", "--j-attn-bg", 6.9),
    ("light", "--j-ok-fg", "--j-ok-bg", 6.38), ("light", "--j-danger-fg", "--j-surface", 6.5),
    ("light", "--j-link", "--j-attn-bg", 4.5),          # the links inside the amber #form-error box
    ("dark", "--j-text", "--j-ground", 16.04), ("dark", "--j-text", "--j-surface", 14.64),
    ("dark", "--j-muted", "--j-ground", 8.20), ("dark", "--j-muted", "--j-surface", 7.48),
    ("dark", "--j-edge", "--j-ground", 4.39), ("dark", "--j-edge", "--j-surface", 4.00),
    ("dark", "--j-link", "--j-ground", 8.62), ("dark", "--j-link", "--j-surface", 7.87),
    ("dark", "#FFFFFF", "--j-primary", 5.33), ("dark", "--j-primary", "--j-ground", 3.55),
    ("dark", "--j-primary", "--j-surface", 3.24), ("dark", "--j-attn-fg", "--j-attn-bg", 9.95),
    ("dark", "--j-ok-fg", "--j-ok-bg", 8.54), ("dark", "--j-danger-fg", "--j-surface", 7.57),
    ("dark", "--j-link", "--j-attn-bg", 4.5),
]
_EDGES = {"--j-edge", "--j-primary"}                # control edges and large shapes: 3 to 1


@pytest.mark.parametrize("scheme,fg,bg,want", CONTRAST,
                         ids=[f"{s}-{f}-on-{b}" for s, f, b, _ in CONTRAST])
def test_contrast_computed_from_the_real_tokens(scheme, fg, bg, want):
    t = tokens(JOURNEY, scheme)
    got = contrast(t.get(fg, fg), t.get(bg, bg))
    floor = 3.0 if fg in _EDGES and bg != "--j-primary" else 4.5
    assert got >= floor, f"{fg} on {bg} in {scheme} is {got:.2f}, under {floor}"
    assert got >= want - 0.01, f"{fg} on {bg} in {scheme} is {got:.2f}, spec 5.3 says {want}"


def test_app_css_tokens_follow_the_journey_tokens():
    """Repointed once in section 2, so every app.css rule that reads them follows dark mode."""
    want = {"--ground": "var(--j-ground)", "--surface": "var(--j-surface)",
            "--sunk": "var(--j-ground)", "--line": "var(--j-hairline)",
            "--line-strong": "var(--j-edge)", "--text-strong": "var(--j-text)",
            "--text": "var(--j-text)", "--text-muted": "var(--j-muted)"}
    rules = [decls(b) for s, b, c in RULES
             if _plain(c) and {":root", ".mailcard", ".gsi-btn"} <= set(_parts(s))]
    got = {k: v for d in rules for k, v in d.items() if k in want}
    assert got == want


def test_the_sample_email_and_the_google_button_stay_light_in_dark_mode():
    """Spec 3 and 5.3. var() resolves where it is declared, so the island must redefine the
    --j-* values itself and be listed on both mapping rules, or it would inherit dark ones."""
    light = tokens(JOURNEY, "light")
    island = {}
    for sel, body, chain in RULES:
        if (len(chain) == 2 and re.search(r"prefers-color-scheme:\s*dark", chain[1])
                and set(_parts(sel)) == {".mailcard", ".gsi-btn"}):
            island.update({k: v for k, v in decls(body).items() if k.startswith("--j-")})
    assert island == {k: v for k, v in light.items() if k not in SCHEME_FREE}
    mapped = [set(decls(b)) for s, b, c in RULES
              if _plain(c) and {":root", ".mailcard", ".gsi-btn"} <= set(_parts(s))]
    assert any("--text" in d for d in mapped) and any("--color-card" in d for d in mapped)
    assert _declared(".mailcard", "color-scheme") == "light"
    assert _declared(".gsi-btn", "color-scheme") == "light"
    assert _declared(".mailcard", "color") == "var(--j-text)"


def test_the_google_button_is_never_restyled():
    """Spec 3: 40px, #747775 edge, Google Sans Button. journey may only set its scheme."""
    bad = [(sel, prop) for sel, body, _c in RULES
           if any(".gsi-btn" in _positive(_subject(p)) for p in _parts(sel))
           for prop in decls(body) if not prop.startswith("--") and prop != "color-scheme"]
    assert bad == []


SPEC_44 = ("--background", "--foreground", "--card", "--card-foreground", "--primary",
           "--primary-foreground", "--secondary", "--muted", "--muted-foreground", "--border",
           "--input", "--ring", "--destructive", "--radius")


def test_journey_supplies_every_variable_the_trimmed_basecoat_reads():
    """Spec 4.4. The trim drops Basecoat's colours and its --color-* aliases, so whatever the
    kept rules read and nothing in the file defines or registers must come from journey.css."""
    root: dict[str, str] = {}
    for sel, body, chain in RULES:
        if _plain(chain) and ":root" in _parts(sel):
            root.update(decls(body))
    missing = [name for name in SPEC_44 if name not in root]
    assert missing == [], f"spec 4.4 names missing: {missing}"
    assert (root["--primary"].upper(), root["--primary-foreground"].upper()) == ("#0B6BC7",
                                                                                 "#FFFFFF")
    bc = read_css(BASECOAT_CSS)
    reads = set(re.findall(r"var\(\s*(--[\w-]+)", bc))
    defined = set(re.findall(r"(--[\w-]+)\s*:", bc))
    registered = set(re.findall(r"@property\s+(--[\w-]+)", bc))
    need = reads - defined - registered
    assert {"--color-primary", "--radius"} <= need, "sanity: the trimmed file reads these"
    assert sorted(need - set(root)) == []


# --- base (spec 4.5, 5.1) ------------------------------------------------------------------

def test_the_journey_body_uses_the_inter_stack_at_nominal_size():
    """Apple devices match -apple-system first and never fetch Inter. font-size-adjust is none,
    measured in Task 2: .546 also keeps Inter nominal but cancels the fallback's size-adjust."""
    bodies = [decls(b) for s, b, _c in RULES if s == "body"]
    assert len(bodies) == 1, "journey.css styles body exactly once"
    stack = re.sub(r"\s*,\s*", ", ", bodies[0].get("font-family", ""))
    assert stack == JOURNEY_STACK
    assert bodies[0].get("font-size-adjust") == "none"


def test_type_follows_spec_5_1_through_app_css_own_tokens():
    phone = {k: v for s, b, c in RULES if _plain(c) and ":root" in _parts(s)
             for k, v in decls(b).items() if k.startswith("--fs-")}
    assert {k: phone.get(k) for k in ("--fs-body", "--fs-small", "--fs-caption", "--fs-h1",
                                      "--fs-h3")} == {
        "--fs-body": "1rem", "--fs-small": ".9375rem", "--fs-caption": ".75rem",
        "--fs-h1": "1.75rem", "--fs-h3": "1.25rem"}
    pc = {k: v for s, b, c in RULES
          if c[1:] == ("@media (hover:hover) and (pointer:fine)",) and ":root" in _parts(s)
          for k, v in decls(b).items()}
    assert {k: pc.get(k) for k in ("--fs-body", "--fs-small", "--fs-h1")} == {
        "--fs-body": ".9375rem", "--fs-small": ".875rem", "--fs-h1": "1.875rem"}
    assert _declared("h1", "font-weight") == "600" == _declared("h3", "font-weight")


def test_type_never_switches_on_width_alone():
    """Spec 5.1: a phone held sideways keeps phone sizes. Width breakpoints may lay out, never
    resize type."""
    bad = [(sel, chain) for sel, body, chain in RULES
           if any("width" in c for c in chain[1:])
           and any(k == "font-size" or k.startswith("--fs-") for k in decls(body))]
    assert bad == []


# --- components: every Basecoat leak spec 5.2 lists, by name ---------------------------------

LEAKS = [
    (".btn", "height", "auto"),                        # fixed 36px
    (".btn", "transition", "none"),                    # transition-property: all, unconditional
    (".btn", "box-shadow", "none"),                    # the focus ring shadow
    (".btn", "background-clip", "border-box"),         # padding-box shrinks the fill by 1px
    (".btn:active", "translate", "none"),              # the 1px press
    (".btn:active", "transform", "none"),              # app.css translateY(1px)
    (".btn:disabled", "opacity", "1"),                 # opacity .5
    (".btn:focus-visible", "outline-style", "solid"),  # outline-style: none
    (".btn svg", "width", "20px"),                     # .btn svg at 16px
    (".input", "height", "auto"),                      # fixed 36px, and textarea.input too
    (".input", "box-shadow", "none"),                  # drop shadow and focus ring
    (".input", "transition", "none"),
    (".input:focus-visible", "outline-style", "solid"),
    ("textarea.input", "field-sizing", "fixed"),       # field-sizing: content
    (".input[aria-invalid=true]", "border-color", "var(--amber-600)"),  # amber, never red
    (".alert>svg", "grid-row", "auto"),                # the empty strip
    (".alert>svg", "translate", "none"),
    (".badge", "height", "auto"),                      # clips "Connected"
    (".badge", "overflow", "visible"),
    (".badge", "transition", "none"),
    (":focus-visible", "outline-color", "var(--j-link)"),
    (".sheet", "overflow", "visible"),                 # groups never clip focus rings
]


@pytest.mark.parametrize("part,prop,want", LEAKS, ids=[f"{p} {q}" for p, q, _ in LEAKS])
def test_every_basecoat_leak_is_switched_off_by_name(part, prop, want):
    assert _declared(part, prop) == want


def test_every_journey_input_rule_resolves_to_16px_or_more():
    """Spec 3 and 5.1. Anything under 16px makes iOS zoom the page on focus."""
    field = re.compile(r"\.(?:input|textarea)(?![\w-])|(?:^|[^\w.#-])(?:input|textarea|select)"
                       r"(?![\w-])")

    def px(value: str) -> float | None:
        v = value.replace("!important", "").strip()
        m = re.fullmatch(r"max\((.*)\)", v)
        if m:
            known = [x for x in (px(p) for p in _split(m.group(1))) if x is not None]
            return max(known) if known else None
        m = re.fullmatch(r"(\d*\.?\d+)(px|rem)", v)
        return float(m.group(1)) * (16 if m.group(2) == "rem" else 1) if m else None

    sizes = []
    for sel, body, chain in RULES:
        if not any(field.search(_subject(p)) for p in _parts(sel)):
            continue
        d = decls(body)
        assert "font" not in d, f"{sel}: no font shorthand on inputs, write font-size"
        if "font-size" in d:
            sizes.append((sel, chain, px(d["font-size"])))
    assert sizes, "journey.css must size its inputs itself (Basecoat drops them to 14px)"
    small = [(s, c, v) for s, c, v in sizes if v is None or v < 16]
    assert small == []


# --- review focus: zoomed text, high contrast, a laptop with a touch screen -------------------
#
# Three things that bite real users and that no page test reaches. Each reads every journey rule,
# so it keeps guarding sections 7 to 10 as the page tasks fill them.

_CONTROL = re.compile(r"\.(?:btn(?:--[\w-]+)?|input)(?![\w-])|^(?:input|textarea|select|button)"
                      r"(?![\w-])")


def test_no_control_gets_a_fixed_height_so_zoomed_text_never_clips():
    """Text zoomed to 200 percent, or Android's largest font size, makes a label taller than any
    fixed box, and Basecoat fixes buttons and inputs at 36px. A control may only grow: height
    auto over a min-height floor, no fixed or maximum height, no line height in px, nothing
    clipped and no label forced onto one line."""
    bad = []
    for sel, body, _chain in RULES:
        d = decls(body)
        for part in _parts(sel):
            subject = _positive(_subject(part))
            if "::" in subject or ".gsi-btn" in subject or not _CONTROL.search(subject):
                continue
            bad += [(part, p, d[p]) for p in ("height", "max-height", "block-size",
                                              "max-block-size") if d.get(p, "auto") not in
                    ("auto", "none")]
            bad += [(part, p, d[p]) for p in ("overflow", "overflow-x", "overflow-y")
                    if re.search(r"hidden|clip", d.get(p, ""))]
            if d.get("line-height", "").endswith("px") or d.get("white-space") == "nowrap":
                bad.append((part, "line-height or white-space", body))
    assert bad == []
    for part in (".btn", ".input"):
        assert (_declared(part, "height"), _declared(part, "min-height")) == ("auto", "44px")


_SYSTEM_COLOUR = re.compile(r"\b(?:CanvasText|Canvas|Highlight|HighlightText|ButtonText|"
                            r"ButtonFace|ButtonBorder|LinkText|GrayText|Field|FieldText)\b")


def _family(prop: str) -> str | None:
    """The part of a component's look a property draws in high contrast."""
    if prop in ("color", "outline", "outline-color"):
        return "outline" if prop.startswith("outline") else "color"
    if prop in ("background", "background-color"):
        return "background"
    if re.fullmatch(r"border(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?"
                    r"(?:-(?:width|style))?", prop):
        return "border"
    return None


def _keys(part: str) -> set[str]:
    """What one selector names: the classes of its subject, or the bare subject."""
    subject = _positive(_subject(part))
    return set(re.findall(r"\.[\w-]+", subject)) or {subject}


def test_high_contrast_keeps_every_shape_and_system_colour_app_css_gives():
    """Windows high contrast (forced colours) repaints pages with system colours. app.css gives
    buttons, cards, alerts and badges a CanvasText border there, the rail marker Highlight, and
    focus rings Highlight. Every journey rule outranks app.css's forced-colours block, so where
    journey.css redraws one of those, it must put the high-contrast value back itself."""
    wanted = set()
    for sel, body, chain in iter_rules(read_css(APP_CSS)):
        if _in(chain, r"forced-colors"):
            for prop, value in decls(body).items():
                if _family(prop) and _SYSTEM_COLOUR.search(value):
                    wanted |= {(k, _family(prop)) for p in _parts(sel) for k in _keys(p)}
    assert (".btn", "border") in wanted and (":focus-visible", "outline") in wanted, "sanity"
    touched, restored = set(), set()
    for sel, body, chain in RULES:
        for prop, value in decls(body).items():
            if _family(prop) is None:
                continue
            keys = {(k, _family(prop)) for p in _parts(sel) for k in _keys(p)}
            if not _in(chain, r"forced-colors"):
                touched |= keys
            elif _SYSTEM_COLOUR.search(value):
                restored |= keys
    assert sorted((touched & wanted) - restored) == []


_COMPUTER = "(hover:hover) and (pointer:fine)"
_COLOUR_ONLY = {"color", "background", "background-color", "border-color", "outline-color",
                "text-decoration", "text-decoration-line", "text-decoration-color"}


def _touch_hazards(rules) -> list:
    """Rules that size things for a touch screen's stuck hover. Any spelling of a hover query
    counts: (hover:hover), (hover: hover) and the bare (hover) match the same devices."""
    bad = []
    for sel, body, chain in rules:
        media, props = " ".join(chain[1:]), set(decls(body))
        if re.search(r"any-(?:pointer|hover)|pointer:\s*coarse|hover:\s*none", media):
            bad.append((sel, media))
        elif "pointer" in media and _COMPUTER not in media:
            bad.append((sel, media))
        elif "hover" in media and _COMPUTER not in media and props - _COLOUR_ONLY:
            bad.append((sel, sorted(props - _COLOUR_ONLY)))
    return bad


def test_computer_sizes_need_a_fine_pointer_that_hovers():
    """A Windows laptop with a touch screen: its main pointer is the trackpad, so it gets the
    computer sizes, and a finger still taps them. Sizes switch only on (hover:hover) and
    (pointer:fine), never on any-pointer, any-hover or a coarse pointer; a rule under
    (hover:hover) alone changes colours only, so a hover that a tap leaves stuck moves nothing;
    and the quiet links keep their 44px tap band on every device, not only on phones."""
    assert _touch_hazards(RULES) == []
    assert _declared(".btn", "min-height", chain_ok=lambda c: c[1:] == (f"@media {_COMPUTER}",)) \
        == "40px"
    assert _declared(".text-link::after", "height") == "44px"


@pytest.mark.parametrize("query", ["(hover:hover)", "(hover: hover)", "(hover)"])
def test_the_touch_guard_reads_every_spelling_of_hover(query):
    """A browser reads all three the same, so a size change under any of them is the stuck-hover
    bug the test above guards against."""
    planted = f"@layer journey{{@media {query}{{.btn{{min-height:36px}}}}}}"
    assert _touch_hazards(list(iter_rules(planted))) == [(".btn", ["min-height"])]


# --- motion (spec 5.4) -----------------------------------------------------------------------

_NO_PREF = r"prefers-reduced-motion:\s*no-preference"
_STILL = {"none", "0s", "0ms"}
_TIME = re.compile(r"(\d*\.?\d+)(ms|s)")


def _still(value: str) -> bool:
    """transition: none (and friends) switches motion off, so it may sit anywhere."""
    return value.lower().replace("!important", "").strip() in _STILL


def test_everything_that_moves_waits_for_no_preference():
    loose = [(sel, prop) for sel, body, chain in RULES for prop, value in decls(body).items()
             if re.match(r"(?:transition|animation)(?:-|$)", prop)
             and not _still(value) and not _in(chain, _NO_PREF)]
    assert loose == []
    assert "scroll-behavior" not in JOURNEY, "smooth scrolling is banned"


def test_transitions_are_short_on_the_land_curve_and_move_nothing_else():
    """100 to 300ms on --ease-land. Transform and opacity, plus the colour of a hover."""
    allowed = {"transform", "opacity", "background-color", "border-color", "color"}
    bad = []
    for sel, body, chain in RULES:
        value = decls(body).get("transition", "none")
        if _still(value):
            continue
        for item in _split(value):
            words = item.split()
            times = [float(m.group(1)) * (1 if m.group(2) == "ms" else 1000)
                     for w in words for m in [_TIME.fullmatch(w)] if m]
            if words[0] not in allowed or not times or not 100 <= times[0] <= 300 or \
                    "var(--ease-land)" not in words:
                bad.append((sel, item))
    assert bad == []
    for sel, body, _c in iter_rules(JOURNEY):
        if sel.startswith("@keyframes"):
            props = set(re.findall(r"([\w-]+)\s*:", body))
            assert props <= {"transform", "opacity", "translate", "scale"}, (sel, props)


def test_a_pressed_button_scales_and_never_travels():
    pressed = _declared(".btn:active", "transform", chain_ok=lambda c: _in(c, _NO_PREF))
    assert pressed == "scale(.97)"
    assert _declared(".btn:active", "translate", chain_ok=lambda c: _in(c, _NO_PREF)) is None


def test_the_reduced_motion_reset_covers_details_content():
    """app.css's reset is `*, ::before, ::after`, which never reaches ::details-content."""
    hits = [decls(b).get("transition", "") for s, b, c in RULES
            if _in(c, r"prefers-reduced-motion:\s*reduce") and "::details-content" in _parts(s)]
    assert hits and all(h.startswith("none") for h in hits)


# --- budgets (spec 8) --------------------------------------------------------------------------

def test_the_two_new_stylesheets_stay_inside_their_gzip_caps():
    assert gzip_size(JOURNEY_CSS) <= 8000, f"journey.css is {gzip_size(JOURNEY_CSS)} B gzip"
    assert gzip_size(BASECOAT_CSS) <= 7000, f"Basecoat is {gzip_size(BASECOAT_CSS)} B gzip"


def test_the_render_blocking_css_of_the_login_page_stays_under_30000_bytes():
    """app.css, the trimmed Basecoat file and journey.css, the three stylesheets /login blocks
    first paint on. Computed from the files, so it holds before any page links them."""
    total = sum(gzip_size(p) for p in (APP_CSS, BASECOAT_CSS, JOURNEY_CSS))
    assert total <= 30000, f"{total} B gzip"


# --- scope: where the look may load (spec 4.2, 8) ------------------------------------------------

JOURNEY_LINKS = ("{{ static_url('vendor/basecoat-1.0.2-agad.css') }}",
                 "{{ static_url('css/journey.css') }}")


def _block(src: str, name: str) -> str | None:
    m = re.search(r"\{%-?\s*block\s+" + name + r"\s*-?%\}(.*?)\{%-?\s*endblock", src, re.S)
    return m.group(1) if m else None


def test_only_spec_templates_can_join_the_journey():
    assert len(set(JOURNEY_TEMPLATES)) == len(JOURNEY_TEMPLATES)
    assert set(JOURNEY_TEMPLATES) <= SPEC_JOURNEY
    assert set(JOURNEY_TEMPLATES) <= set(PAGE_TEMPLATES)


@pytest.mark.parametrize("name", PAGE_TEMPLATES)
def test_the_journey_look_loads_on_exactly_the_listed_templates(name):
    """Listed: page_css links Basecoat then journey.css (both hashed), the page asks for light
    and dark, and the two theme colours are the header surface of each scheme. Not listed:
    the template names neither file and keeps base.html's light defaults."""
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    if name not in JOURNEY_TEMPLATES:
        assert "basecoat" not in src and "journey.css" not in src, name
        assert _block(src, "color_scheme") is None and _block(src, "theme_color_meta") is None
        return
    links = re.findall(r"<link\b[^>]*>", _block(src, "page_css") or "")
    assert links == [f'<link rel="stylesheet" href="{u}">' for u in JOURNEY_LINKS]
    assert (_block(src, "color_scheme") or "").strip() == "light dark"
    metas = dict((s, c.upper()) for c, s in re.findall(
        r'<meta name="theme-color" content="(#[0-9A-Fa-f]{6})" '
        r'media="\(prefers-color-scheme: (light|dark)\)">', _block(src, "theme_color_meta") or ""))
    assert metas == {s: tokens(JOURNEY, s)["--j-surface"].upper() for s in ("light", "dark")}


@pytest.mark.parametrize("path", KEEP_TODAY)
def test_the_pages_that_keep_todays_look_never_load_the_journey_files(saas_cfg, path):
    resp = client_for(saas_cfg).get(path)
    assert resp.status_code == 200
    assert "basecoat" not in resp.text and "journey.css" not in resp.text


# Rendered by base.html today, byte for byte. The two new blocks must default to exactly this.
TODAY_HEAD = ('\n  <meta name="color-scheme" content="light">\n'
              '  <meta name="theme-color" content="#F3F6FA">\n  <title>')


@pytest.mark.parametrize("path", KEEP_TODAY)
def test_the_new_head_blocks_render_todays_bytes_by_default(saas_cfg, path):
    html = client_for(saas_cfg).get(path).text.replace("\r\n", "\n")
    assert TODAY_HEAD in html
    assert html.count('name="theme-color"') == 1 and html.count('name="color-scheme"') == 1


def test_base_offers_the_blocks_the_journey_pages_fill():
    src = BASE_HTML.read_text(encoding="utf-8")
    assert '<meta name="color-scheme" content="{% block color_scheme %}light{% endblock %}">' in src
    assert ('{% block theme_color_meta %}<meta name="theme-color" content="'
            '{% block theme_color %}#F3F6FA{% endblock %}">{% endblock %}') in src
    assert src.index("{% block motion_head %}") < src.index("{% block page_css %}") < \
        src.index("js/reveal.js"), "page_css stays after the motion head (M-1)"


NEW_FILES = ("tools/basecoat/basecoat-1.0.2.cdn.min.css", "tools/basecoat/trim.py",
             "applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css",
             "applyfirst/saas/static/css/journey.css", "tools/fonts/build_inter.py",
             "applyfirst/saas/static/licenses/basecoat-MIT.txt",
             "applyfirst/saas/static/licenses/tailwindcss-MIT.txt",
             "applyfirst/saas/static/licenses/OFL-inter.txt",
             "applyfirst/saas/templates/signin_failed.html", "tests/_journey_css.py",
             "tests/test_saas_journey.py", "tests/test_saas_basecoat.py",
             "tests/test_saas_signin_failed.py")
FONT_FILES = tuple(str(p.relative_to(ROOT)) for p in (STATIC / "fonts").glob("inter-*.woff2"))


@pytest.mark.parametrize("rel", NEW_FILES + FONT_FILES)
def test_no_new_file_name_contains_a_motion_asset_name(rel):
    """M-2 greps the public pages for these substrings, so a name like journey-motion.css would
    fail it the moment a page linked it."""
    name = Path(rel).name
    assert [b for b in MOTION_ASSETS if b in name] == []


# --- the readers themselves ------------------------------------------------------------------

def test_the_css_reader_sees_through_layers_media_and_strings():
    css = ('@layer a,b;@layer a{@media (x:y){.b>i{content:"}{;";color:red}}}'
           '@font-face{font-family:"q"}')
    got = list(iter_rules(css))
    assert got[0] == (".b>i", 'content:"}{;";color:red', ("@layer a", "@media (x:y)"))
    assert got[1][0] == "@font-face" and got[1][2] == ()
    assert decls(got[0][1]) == {"content": '"}{;"', "color": "red"}
    assert decls("a:1;&:hover{a:2};b:3") == {"a": "1", "b": "3"}


def test_the_contrast_reader_is_wcag():
    assert round(contrast("#FFFFFF", "#000000"), 2) == 21.0
    assert round(contrast("#FFF", "#0B6BC7"), 2) == 5.33
    with pytest.raises(ValueError):
        tokens(JOURNEY, "sepia")


# --- Task 4: the login page (spec 6.1, 4.2) ---------------------------------------------------
#
# The first journey page. These tests read the rendered /login, not the template source, so they
# hold whatever macro or block prints the markup. The Google button checks read journey.css
# against the button's real place in the page: the journey layer outranks app.css's `.gsi-btn`
# rule whatever the specificity, so a bare `a { color: ... }` in journey.css would repaint the
# button just as surely as a rule that names it.

import re
from html.parser import HTMLParser

import pytest

from applyfirst.saas import app as app_module
from applyfirst.saas import static_assets
from _journey_css import JOURNEY_CSS, STATIC, decls, gzip_size, iter_rules, read_css
from _saas_client import clean, client_for, count_class, elements, has_class, page_text
from test_saas_pages import CHROME, UAS

LOGIN_SHEETS = ["css/app.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css"]
JOURNEY_THEME = [
    {"name": "theme-color", "content": "#FFFFFF", "media": "(prefers-color-scheme: light)"},
    {"name": "theme-color", "content": "#111B2B", "media": "(prefers-color-scheme: dark)"},
]


def _login_page(cfg, user_agent: str = CHROME) -> str:
    resp = client_for(cfg, user_agent=user_agent).get("/login")
    assert resp.status_code == 200
    return resp.text


def head_urls(markup: str) -> list[str]:
    """The href or src of every <link> and <script>, in document order."""
    urls = []
    for tag in re.findall(r"<(?:link|script)\b[^>]*>", markup):
        m = re.search(r'\s(?:href|src)="([^"]+)"', tag)
        if m:
            urls.append(m.group(1))
    return urls


def assert_journey_head(markup: str) -> None:
    """Spec 4.2: Basecoat then journey.css, both hashed by static_url(), after app.css and
    after the motion head (when the page has one), before the parser-blocking reveal.js."""
    urls = head_urls(markup)
    basecoat = static_assets.static_url("vendor/basecoat-1.0.2-agad.css")
    journey = static_assets.static_url("css/journey.css")
    for url in (basecoat, journey):
        assert re.fullmatch(r"/static/[\w./-]+\?v=[0-9a-f]{12}", url), f"not hashed: {url}"
        assert urls.count(url) == 1, f"{url} linked {urls.count(url)} times"
    order = [urls.index(u) for u in (static_assets.static_url("css/app.css"), basecoat, journey,
                                     static_assets.static_url("js/reveal.js"))]
    assert order == sorted(order), f"head order is app.css, basecoat, journey, reveal.js: {urls}"
    motion = [i for i, u in enumerate(urls)
              if re.search(r"/(?:motion\.css|vt\.js|motion\.js)\?", u)]
    assert all(i < urls.index(basecoat) for i in motion), f"page_css follows motion_head: {urls}"


def meta_attrs(markup: str, name: str) -> list[dict[str, str]]:
    return [e.attrs for e in elements(markup) if e.tag == "meta" and e.attrs.get("name") == name]


def page_region(markup: str, tag: str) -> str:
    """The first <tag>...</tag> of the page (header, main and footer are never nested)."""
    m = re.search(rf"<{tag}\b.*?</{tag}>", markup, re.S)
    assert m, f"the page has no <{tag}>"
    return m.group(0)


def stylesheets(markup: str) -> list[str]:
    """The static path of every stylesheet the page links, in order, without the ?v= hash."""
    return [re.search(r'href="/static/([^"?]+)', tag).group(1)
            for tag in re.findall(r"<link\b[^>]*>", markup) if 'rel="stylesheet"' in tag]


def test_login_links_basecoat_then_journey_css(saas_cfg):
    markup = _login_page(saas_cfg)
    assert_journey_head(markup)
    assert stylesheets(markup) == LOGIN_SHEETS


def test_login_render_blocking_css_fits_the_budget(saas_cfg):
    """Spec 8: app.css plus both new files, gzip 9 with LF endings, at most 30,000 bytes."""
    sheets = stylesheets(_login_page(saas_cfg))
    total = sum(gzip_size(STATIC / rel) for rel in sheets)
    assert total <= 30_000, f"render-blocking CSS on /login is {total} B gzip ({sheets})"


def test_login_follows_the_phone_light_or_dark(saas_cfg):
    markup = _login_page(saas_cfg)
    assert meta_attrs(markup, "color-scheme") == [
        {"name": "color-scheme", "content": "light dark"}]
    assert meta_attrs(markup, "theme-color") == JOURNEY_THEME


@pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
def test_pages_outside_the_journey_keep_one_light_theme_colour(saas_cfg, path):
    markup = client_for(saas_cfg).get(path).text
    assert meta_attrs(markup, "color-scheme") == [{"name": "color-scheme", "content": "light"}]
    assert meta_attrs(markup, "theme-color") == [{"name": "theme-color", "content": "#F3F6FA"}]


def test_login_shows_the_brand_mark_once_in_the_header(saas_cfg):
    markup = _login_page(saas_cfg)
    header, main, footer = (page_region(markup, tag) for tag in ("header", "main", "footer"))
    assert header.startswith('<header class="site-header')
    assert count_class(header, "mark") == 1, "the header carries the brand mark"
    assert count_class(main, "mark") == 0, "the sign-in card no longer repeats it"
    assert count_class(markup, "mark") - count_class(footer, "mark") == 1


# --- section 6 of journey.css, the chrome every journey page shares ------------------------------

_DARK_ONLY = re.compile(r"@media \(prefers-color-scheme:\s*dark\)")


def test_the_short_footer_never_waits_for_a_reveal_it_cannot_get():
    """reveal.js shows a target only once it crosses into the top 90 percent of the window, and
    until then app.css holds every .footer__grid child at opacity 0. Section 6 makes the footer one
    short row, so on a laptop or desktop scrolled to the end the row still sits in that bottom
    tenth, and the Privacy, Terms and contact links would stay invisible. Section 6 shows them
    outright. animation:none matters too: on a phone the row does cross the line, and the reveal's
    fade would blink the links out and back in."""
    reveal = (STATIC / "js" / "reveal.js").read_text(encoding="utf-8")
    assert ".footer__grid > *" in reveal and '"0px 0px -10% 0px"' in reveal, "the premise moved"
    got = {p: _declared(".footer__grid>*", p) for p in ("opacity", "transform", "animation")}
    assert got == {"opacity": "1", "transform": "none", "animation": "none"}


def test_the_header_mark_reads_as_a_tile_in_dark_mode_and_is_unchanged_in_light():
    """The mark is a navy tile drawn by the SVG itself, about 1.1 to 1 on the dark header, so in
    dark mode the tile vanished and the chevron and dot floated loose (plan departure 16). Dark
    mode alone rings the tile with the control-edge token, at least 3 to 1 against both the header
    and the tile, on the tile's own corners. Nothing outside the dark block touches the mark."""
    svg = str(app_module._TEMPLATES.env.get_template("_ui.html").module.mark())
    tile = re.search(r'<rect width="32" height="32" rx="([\d.]+)" fill="(#[0-9A-Fa-f]{6})"', svg)
    size = re.search(r'width="(\d+)" height="\1" viewBox="0 0 32 32"', svg)
    assert tile and size, svg
    rings = [decls(body) for sel, body, chain in RULES
             if len(chain) == 2 and _DARK_ONLY.fullmatch(chain[1])
             and ".site-header .mark" in _parts(sel)]
    assert rings, "the dark header mark has no edge"
    ring = re.fullmatch(r"0 0 0 1px var\((--j-[\w-]+)\)", rings[-1].get("box-shadow", ""))
    assert ring, rings[-1]
    dark = tokens(JOURNEY, "dark")
    assert _declared(".site-header", "background") == "var(--j-surface)"
    assert contrast(dark[ring.group(1)], dark["--j-surface"]) >= 3.0
    assert contrast(dark[ring.group(1)], tile.group(2)) >= 3.0
    radius = float(tile.group(1)) * int(size.group(1)) / 32
    assert abs(float(rings[-1].get("border-radius", "0px").removesuffix("px")) - radius) <= 0.5
    light = [sel for sel, _body, chain in RULES if re.search(r"\.mark(?![\w-])", sel)
             and not (len(chain) == 2 and _DARK_ONLY.fullmatch(chain[1]))]
    assert light == [], "the light mark must stay exactly as the SVG draws it"


def test_login_prints_the_google_button_unchanged(saas_cfg):
    markup = _login_page(saas_cfg)
    ui = app_module._TEMPLATES.env.get_template("_ui.html").module
    button = str(ui.google_button(block=True))
    assert markup.count(button) == 1, "the Google button is printed by the macro, untouched"
    assert "Continue with Google" in markup
    assert markup.count('class="gsi-btn') == 1
    assert 'href="/privacy"' in markup


def test_login_card_reads_in_the_spec_order(saas_cfg):
    markup = _login_page(saas_cfg)
    ui = app_module._TEMPLATES.env.get_template("_ui.html").module
    wanted = ["Sign in to Agad", "New here? The same button sets up your account.",
              "Continue with Google", "We never see your password."]
    if ui.INVITE_ONLY:
        wanted.append("Agad is in a private beta.")
    wanted += ["Signing in shares only your name and email address", "What is Agad?"]
    text = page_text(markup)
    where = [text.find(s) for s in wanted]
    assert -1 not in where and where == sorted(where), dict(zip(wanted, where))
    headings = [clean(e.text) for e in elements(markup) if e.tag == "h1"]
    assert headings == ["Sign in to Agad"]
    sheets = [e for e in elements(markup) if has_class(e, "auth__sheet")]
    assert len(sheets) == 1, "one card"
    assert [c.attrs.get("href") for c in sheets[0].children if has_class(c, "gsi-btn")] == [
        "/auth/login"]
    foot = [e for e in elements(markup) if e.tag == "a" and clean(e.text) == "What is Agad?"]
    assert len(foot) == 1 and foot[0].attrs.get("href") == "/"


def test_login_puts_the_in_app_notice_between_the_lead_and_the_button(saas_cfg):
    text = page_text(_login_page(saas_cfg, user_agent=UAS["Facebook"]))
    lead = text.find("New here?")
    notice = text.find("Open this page in Chrome or Safari")
    button = text.find("Continue with Google")
    assert -1 < lead < notice < button, (lead, notice, button)


# The Google button (spec 3: 40px, #747775 edge, Google Sans Button) is Google's branding. What
# follows is a small selector matcher: it asks, for every journey.css rule, whether the rule can
# reach the button's <a>, <img> or <span> where the button really sits on /login.

class ElementChains(HTMLParser):
    """Every element with its ancestors: [(tag, attrs), ...], outermost first, itself last."""

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.chains: list[list[tuple[str, dict[str, str]]]] = []

    def handle_starttag(self, tag, attrs):
        el = (tag, {k.lower(): (v or "") for k, v in attrs})
        self.chains.append(self.stack + [el])
        if tag not in self._VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.chains.append(self.stack + [(tag, {k.lower(): (v or "") for k, v in attrs})])

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def google_button_chains(markup: str):
    """The Google link's chain, and the chains of its two children (the G image, the label)."""
    parser = ElementChains()
    parser.feed(markup)
    parser.close()
    links = [c for c in parser.chains
             if c[-1][0] == "a" and "gsi-btn" in c[-1][1].get("class", "").split()]
    assert len(links) == 1, "expected one Google button"
    link = links[0]
    kids = [c for c in parser.chains if len(c) == len(link) + 1 and c[:-1] == link]
    assert [k[-1][0] for k in kids] == ["img", "span"], kids
    return link, kids


def sel_split(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside brackets and parentheses."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch in "([") - (ch in ")]")
        if ch == sep and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


def sel_compounds(selector: str) -> list[tuple[str, str]]:
    """[(combinator before it, compound), ...]: '' for the first, then ' ', '>', '+' or '~'."""
    out, cur, comb, depth = [], "", "", 0
    for ch in selector.strip() + " ":
        depth += (ch in "([") - (ch in ")]")
        if depth == 0 and (ch.isspace() or ch in ">+~"):
            if cur:
                out.append((comb, cur))
                cur, comb = "", " "
            if ch in ">+~":
                comb = ch
            continue
        cur += ch
    return out


_SEL_TYPE = re.compile(r"\*|[a-zA-Z][\w-]*")
_SEL_PIECE = re.compile(r"""
    \.(?P<cls>-?[_a-zA-Z][\w-]*)
  | \#(?P<id>-?[_a-zA-Z][\w-]*)
  | \[\s*(?P<attr>[\w-]+)\s*(?:(?P<op>[~|^$*]?=)\s*(?P<val>"[^"]*"|'[^']*'|[^\]\s]+))?\s*[iIsS]?\s*\]
  | ::(?P<pe>[\w-]+)(?:\([^()]*\))?
  | :(?P<pc>[\w-]+)(?:\((?P<arg>(?:[^()]|\([^()]*\))*)\))?
""", re.X)
# States a link, an image or a span can never be in.
_SEL_NEVER = {"disabled", "enabled", "checked", "indeterminate", "placeholder-shown", "invalid",
              "valid", "user-invalid", "user-valid", "required", "optional", "default",
              "in-range", "out-of-range", "empty", "open", "popover-open", "modal"}


def _sel_pieces(compound: str):
    """(type or None, [piece matches]) for one compound selector. Unknown syntax fails loudly."""
    m = _SEL_TYPE.match(compound)
    kind, pos, found = (m.group(0) if m else None), (m.end() if m else 0), []
    while pos < len(compound):
        piece = _SEL_PIECE.match(compound, pos)
        assert piece, f"the test cannot read {compound[pos:]!r} in {compound!r}: simplify it"
        found.append(piece)
        pos = piece.end()
    return kind, found


def _sel_attr_ok(piece, attrs: dict[str, str]) -> bool:
    if piece["attr"] not in attrs:
        return False
    return piece["op"] != "=" or attrs[piece["attr"]] == piece["val"].strip("\"'")


def sel_always(compound: str, el) -> bool:
    """``compound`` matches ``el`` in every state (no pseudo-classes)."""
    tag, attrs = el
    kind, found = _sel_pieces(compound)
    if kind not in (None, "*", tag):
        return False
    for p in found:
        if p["pc"] or p["pe"]:
            return False
        if p["cls"] and p["cls"] not in attrs.get("class", "").split():
            return False
        if p["id"] and attrs.get("id") != p["id"]:
            return False
        if p["attr"] and not _sel_attr_ok(p, attrs):
            return False
    return True


def sel_may(compound: str, el) -> bool:
    """``compound`` can match ``el`` in some state (hover, focus, visited...)."""
    tag, attrs = el
    kind, found = _sel_pieces(compound)
    if kind not in (None, "*", tag):
        return False
    for p in found:
        if p["cls"] and p["cls"] not in attrs.get("class", "").split():
            return False
        if p["id"] and attrs.get("id") != p["id"]:
            return False
        if p["attr"] and not _sel_attr_ok(p, attrs):
            return False
        if p["pe"] and p["pe"] not in ("before", "after"):
            return False
        pc = (p["pc"] or "").lower()
        if pc in _SEL_NEVER or (pc == "root" and tag != "html"):
            return False
        args = sel_split(p["arg"] or "", ",")
        if pc in ("is", "where", "matches") and not any(
                sel_may(sel_compounds(a)[-1][1], el) for a in args):
            return False
        if pc == "not" and any(len(sel_compounds(a)) == 1 and sel_always(a, el) for a in args):
            return False
    return True


def sel_reaches(selector: str, chain) -> bool:
    """``selector`` can match the last element of ``chain`` (its ancestors come before it)."""
    parts = sel_compounds(selector)

    def at(i: int, j: int) -> bool:
        if not sel_may(parts[i][1], chain[j]):
            return False
        if i == 0:
            return True
        comb = parts[i][0]
        if comb == ">":
            return j > 0 and at(i - 1, j - 1)
        if comb == " ":
            return any(at(i - 1, k) for k in range(j - 1, -1, -1))
        return True                  # + and ~: siblings are not tracked, so assume they match

    return at(len(parts) - 1, len(chain) - 1)


def journey_style_rules():
    """(selector list, declarations, enclosing at-rules) for every style rule in journey.css."""
    for selectors, body, at_rules in iter_rules(read_css(JOURNEY_CSS)):
        if selectors.startswith("@") or any(a.startswith(("@keyframes", "@font-face"))
                                            for a in at_rules):
            continue
        yield selectors, decls(body), at_rules


_NOT_GROUP = re.compile(r":not\((?:[^()]|\([^()]*\))*\)")
_FOCUS_PC = re.compile(r":focus(?:-visible)?(?![\w-])")
_OUTLINE_PROPS = {"outline", "outline-color", "outline-offset", "outline-style", "outline-width"}
# Inherited properties the Google button does not set itself: an ancestor's value would reach it.
_GSI_INHERITED = {"text-transform", "word-spacing", "text-shadow", "font-feature-settings",
                  "font-variation-settings"}


def test_the_matcher_reads_the_google_button_the_way_a_browser_would(saas_cfg):
    """Guards the guard: each selector below is known to reach (or miss) the button."""
    link, (img, span) = google_button_chains(_login_page(saas_cfg))
    for sel in ("a", "a:hover", ".gsi-btn", ".auth a", ".auth__action > a", "main :focus-visible",
                ":is(a, button)", "a::after", "*"):
        assert sel_reaches(sel, link), sel
    for sel in ("a:not(.gsi-btn)", "a:not(.btn,.gsi-btn):visited", ".btn", ".alert a", "body",
                ":root", "a::placeholder", ".auth > a", "a:disabled", ".gsi-btn > span > b"):
        assert not sel_reaches(sel, link), sel
    assert sel_reaches(".gsi-btn > span", span) and sel_reaches("img", img)
    assert not sel_reaches(".btn > span", span) and not sel_reaches(".btn img", img)


def test_journey_css_names_the_google_button_only_to_keep_it_light():
    assert "--font-gsi" not in read_css(JOURNEY_CSS), "the Google button reads --font-gsi"
    for selectors, props, at_rules in journey_style_rules():
        if ".gsi-btn" not in _NOT_GROUP.sub("", selectors):
            continue
        assert all(p.startswith("--") or p == "color-scheme" for p in props), (
            f"{selectors} sets {sorted(props)}")


def test_no_journey_rule_restyles_the_google_button(saas_cfg):
    link, kids = google_button_chains(_login_page(saas_cfg))
    hits = []
    for selectors, props, _at in journey_style_rules():
        real = {p for p in props if not p.startswith("--") and p != "color-scheme"}
        if not real:
            continue
        for sel in sel_split(selectors, ","):
            left = real - _OUTLINE_PROPS if _FOCUS_PC.search(sel_compounds(sel)[-1][1]) else real
            hits += [f"{sel} reaches <{chain[-1][0]}>: {sorted(left)}"
                     for chain in (link, *kids) if left and sel_reaches(sel, chain)]
    assert hits == [], ("journey.css must not restyle the Google button; exclude it with "
                        ":not(.gsi-btn) or scope the rule: " + "; ".join(hits))


def test_no_journey_rule_leaks_an_inherited_style_into_the_google_button(saas_cfg):
    link, _ = google_button_chains(_login_page(saas_cfg))
    hits = []
    for selectors, props, _at in journey_style_rules():
        risky = _GSI_INHERITED & set(props)
        if not risky:
            continue
        for sel in sel_split(selectors, ","):
            hits += [f"{sel} on <{link[d - 1][0]}>: {sorted(risky)}"
                     for d in range(1, len(link)) if sel_reaches(sel, link[:d])]
    assert hits == [], "; ".join(hits)


# --- Task 5: the four onboarding steps (spec 6.2, 9) -------------------------------------------
#
# Spec 9 lists the hooks the frozen motion files read: vt.js names the header, the stepper marker,
# the Activate button and every [data-vt-kw]; motion.js reads the Connect Gmail link's direct
# span, the activate form and data-burst-src; motion.css animates the gconf route, the badge, the
# success icon, the letter and the disclosure. Each test below renders a step in the state that
# shows its hooks and pins them by tag, class, attribute and count. The section 8 tests then read
# journey.css: it may recolour and retype those hooks, never move, resize, clip or ring them, and
# the layout still switches only at the frozen 960 and 1100px.

from html.parser import HTMLParser

from applyfirst.saas import app as app_module
from _journey_css import JOURNEY_CSS, JOURNEY_TEMPLATES, TEMPLATES, contrast, decls, iter_rules
from _journey_css import read_css, tokens
from _saas_client import client_for, form_inputs, post_forms, seed_user

OB_GRANT = b"0123456789abcdef0123456789abcdef"      # a stored Gmail grant, as tests/test_saas_motion
OB_TEMPLATES = ["onboarding_connect_gmail.html", "onboarding_profile.html",
                "onboarding_keywords.html", "onboarding_preview.html"]
OB_STEPS = {"/onboarding/connect_gmail": 1, "/onboarding/profile": 2, "/onboarding/keywords": 3,
            "/onboarding/preview": 4}
OB_SHEETS = ["css/app.css", "css/motion.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css"]
OB_SAVED = ("virtual assistant", "data entry")


class _Node:
    """One element: tag, attrs, parent, direct children, and all the text inside it."""

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None") -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.kids: list[_Node] = []
        self.text = ""

    def has(self, cls: str) -> bool:
        return cls in self.attrs.get("class", "").split()

    def walk(self):
        for kid in self.kids:
            yield kid
            yield from kid.walk()

    def find(self, tag: str | None = None, cls: str | None = None, **attrs) -> list["_Node"]:
        return [n for n in self.walk() if (tag is None or n.tag == tag)
                and (cls is None or n.has(cls))
                and all(n.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items())]

    def one(self, tag: str | None = None, cls: str | None = None, **attrs) -> "_Node":
        found = self.find(tag, cls, **attrs)
        assert len(found) == 1, f"want one <{tag or '*'} class={cls} {attrs}>, found {len(found)}"
        return found[0]

    def words(self) -> str:
        return " ".join(self.text.split())

    def chain(self) -> list[tuple[str, dict[str, str]]]:
        """Ancestors first, itself last: the shape Task 4's sel_reaches() reads."""
        out, node = [], self
        while node is not None and node.tag != "#root":
            out.append((node.tag, node.attrs))
            node = node.parent
        return out[::-1]


class _Doc(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = self._at = _Node("#root", {}, None)
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k.lower(): (v or "") for k, v in attrs}, self._at)
        self._at.kids.append(node)
        if tag not in self._VOID:
            self._at = node

    def handle_startendtag(self, tag, attrs):
        self._at.kids.append(_Node(tag, {k.lower(): (v or "") for k, v in attrs}, self._at))

    def handle_endtag(self, tag):
        node = self._at
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self._at = node.parent

    def handle_data(self, data):
        node = self._at
        while node is not None:
            node.text += data
            node = node.parent


def _ob(cfg, path: str, *, sub: str = "ob5", gmail: bool = True, activated: bool = False,
        keywords: tuple[str, ...] = OB_SAVED) -> str:
    """One onboarding page, signed in as a user with a saved profile, in the state asked for."""
    user = seed_user(cfg, sub=sub, email=f"{sub}@example.com", profile=True, keywords=keywords,
                     activated=activated, gmail_key=OB_GRANT if gmail else None)
    resp = client_for(cfg, user).get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.text


def _page(markup: str) -> _Node:
    return _Doc(markup).root


def _section(n: int) -> str:
    """Section ``n`` of journey.css, from its banner to the next, comments removed."""
    raw = JOURNEY_CSS.read_bytes().decode("utf-8").replace("\r\n", "\n")
    start = re.search(rf"/\* ---- {n} [\w-]+ \*/", raw).end()
    end = re.search(rf"/\* ---- {n + 1} [\w-]+ \*/", raw).start()
    return re.sub(r"/\*.*?\*/", "", raw[start:end], flags=re.S)


OB_RULES = list(iter_rules(_section(8)))


def _ob_tokens(scheme: str) -> dict[str, str]:
    """The --ob-* tints section 8 defines on :root, light, or light overlaid with dark."""
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    for sel, body, chain in OB_RULES:
        if sel.strip() != ":root":
            continue
        found = {k: v for k, v in decls(body).items() if k.startswith("--ob-")}
        if not chain:
            light.update(found)
        elif len(chain) == 1 and re.fullmatch(r"@media \(prefers-color-scheme:\s*dark\)", chain[0]):
            dark.update(found)
    return dict(light) if scheme == "light" else {**light, **dark}


# --- the journey head on every step (spec 4.2) ------------------------------------------------

def test_the_four_steps_are_on_the_journey_list():
    assert [t for t in JOURNEY_TEMPLATES if t.startswith("onboarding_")] == OB_TEMPLATES


@pytest.mark.parametrize("path", OB_STEPS)
def test_every_step_loads_the_journey_look_after_the_motion_head(saas_cfg, path):
    markup = _ob(saas_cfg, path)
    assert_journey_head(markup)
    assert stylesheets(markup) == OB_SHEETS
    assert meta_attrs(markup, "color-scheme") == [{"name": "color-scheme", "content": "light dark"}]
    css = read_css(JOURNEY_CSS)
    assert meta_attrs(markup, "theme-color") == [
        {"name": "theme-color", "content": tokens(css, s)["--j-surface"].upper(),
         "media": f"(prefers-color-scheme: {s})"} for s in ("light", "dark")]


# --- spec 9 hooks, on the rendered pages ------------------------------------------------------

@pytest.mark.parametrize("path,step", OB_STEPS.items())
def test_every_step_keeps_one_header_and_stamps_its_step(saas_cfg, path, step):
    page = _page(_ob(saas_cfg, path))
    assert len(page.find(cls="site-header")) == 1
    assert page.one("html").attrs.get("data-step") == str(step)


@pytest.mark.parametrize("path,step", OB_STEPS.items())
def test_onboarding_mode_draws_the_stepper_the_motion_layer_names(saas_cfg, path, step):
    page = _page(_ob(saas_cfg, path))
    nav = page.one("nav", "stepper")
    lists = [k for k in nav.kids if k.tag == "ol" and k.has("stepper__list")]
    assert len(lists) == 1
    items = lists[0].kids
    assert [i.tag for i in items] == ["li"] * 4 and all(i.has("stepper__item") for i in items)
    current = [i for i in items if i.attrs.get("aria-current") == "step"]
    assert current == [items[step - 1]]
    first = current[0].kids[0]
    assert (first.tag, first.has("stepper__marker"), first.attrs.get("aria-hidden")) == (
        "span", True, "true"), "the marker is the first child of the current step"
    assert len(page.find(cls="stepper__marker")) == 1
    assert [i.has("is-passed") for i in items] == [n < step for n in range(1, 5)]
    assert page.find(cls="rail__edit") == []


@pytest.mark.parametrize("path", OB_STEPS)
def test_editing_mode_keeps_the_plain_label_and_the_way_back(saas_cfg, path):
    page = _page(_ob(saas_cfg, path, activated=True))
    assert page.find("nav", "stepper") == [] and page.find(cls="stepper__marker") == []
    assert page.one("p", "rail__edit").words() == "Editing your setup"
    back = page.one("a", "back-link")
    assert (back.attrs.get("href"), back.words()) == ("/dashboard", "Back to dashboard")
    assert page.find("form", "activate") == []
    assert [n.tag for n in page.walk() if "data-burst-src" in n.attrs] == []


@pytest.mark.parametrize("path,query,gmail,variant", [
    ("/onboarding/connect_gmail", "", False, "btn--primary"),
    ("/onboarding/connect_gmail", "?gmail_error=scope", True, "btn--secondary"),
    ("/onboarding/preview", "", False, "btn--primary"),
])
def test_every_connect_gmail_link_keeps_its_label_in_a_direct_span(saas_cfg, path, query, gmail,
                                                                   variant):
    """motion.js swaps the text of `:scope > span:not(.visually-hidden)` for "Opening Google's
    page" and marks the link busy, so the label must stay a direct span of the a.btn."""
    page = _page(_ob(saas_cfg, path + query, gmail=gmail))
    link = page.one("a", href="/auth/connect-gmail")
    assert link.has("btn") and link.has(variant)
    labels = [k for k in link.kids if k.tag == "span" and not k.has("visually-hidden")]
    assert [s.words() for s in labels] == ["Connect Gmail"]


def test_step_one_puts_what_google_asks_in_a_native_disclosure(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/connect_gmail", gmail=False))
    box = page.one("details", "disclose")
    summary = [k for k in box.kids if k.tag == "summary"]
    assert len(summary) == 1 and summary[0].words() == "What will Google ask me?"
    steps = box.one("ol", "numbered")
    assert len(steps.kids) == 4 and "Go to Agad (unsafe)" in steps.words()
    assert page.one(role="group", aria_label="What connecting Gmail means").has("ledger")
    skip = page.one("a", href="/onboarding/profile")
    assert skip.has("text-link") and skip.words() == "Skip for now"
    assert [b.attrs.get("href") for b in page.find(cls="btn--primary")] == ["/auth/connect-gmail"]


def test_step_one_keeps_the_retry_note_above_the_heading(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/connect_gmail?gmail_error=scope", gmail=False)
    note = _page(markup).one(id="gmail-retry")
    assert note.has("alert") and note.has("alert--attention")
    assert (note.attrs.get("role"), note.attrs.get("tabindex")) == ("alert", "-1")
    assert markup.index('id="gmail-retry"') < markup.index("<h1")


def test_step_two_confirms_gmail_with_the_exact_gconf_hooks(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/profile")
    assert markup.count('class="gconf"') == 1, "motion.css and the tests read the exact attribute"
    page = _page(markup)
    arrivals = page.find(data_arrive_gmail="")
    assert len(arrivals) == 1 and arrivals[0].attrs.get("class") == "gconf"
    gconf = arrivals[0]
    track = gconf.one("span", "gconf__track")
    assert [(k.tag, k.attrs.get("class")) for k in track.kids] == [
        ("i", "gconf__line"), ("span", "fromto__node")]
    badge = gconf.one("span", "badge--ok")
    assert badge.has("badge") and badge.words() == "Gmail connected"


def test_step_two_holds_the_four_fields_in_one_card(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/profile", gmail=False))
    card = page.one("form", action="/onboarding/profile")
    assert card.attrs.get("class") == "form sheet" and card.attrs.get("method") == "post"
    fields = [k for k in card.kids if k.has("field")]
    assert [f.kids[0].tag for f in fields] == ["label"] * 4, "every label sits first, above"
    got = [n.attrs["name"] for f in fields for n in f.walk() if n.tag in ("input", "textarea")]
    assert got == ["full_name", "job_type", "standard_subject", "standard_message"]
    for field in fields:                        # the hint follows the label in the DOM, as today
        hint = [k for k in field.kids if k.has("field__hint")]
        assert len(hint) == 1 and field.kids.index(hint[0]) == 1
    area = card.one("textarea", id="f-standard_message")
    assert (area.attrs.get("rows"), area.attrs.get("maxlength")) == ("8", "5000")
    assert len(card.find("details", "disclose")) == 1
    assert [b.words() for b in card.find(cls="btn--primary")] == ["Save and continue"]


@pytest.mark.parametrize("query,links", [("?error=1", []),
                                         ("?error=long_job_type", ["#f-job_type"])])
def test_step_two_error_box_is_amber_at_the_top_of_the_card(saas_cfg, query, links):
    page = _page(_ob(saas_cfg, "/onboarding/profile" + query, gmail=False))
    card = page.one("form", action="/onboarding/profile")
    box = card.one("div", id="form-error")
    assert box.has("alert__lines")
    assert (box.attrs.get("role"), box.attrs.get("tabindex")) == ("alert", "-1")
    alert = box.parent
    while not alert.has("alert"):
        alert = alert.parent
    assert alert.has("alert") and alert.has("alert--attention") and not alert.has("alert--danger")
    top = [k for k in card.kids if not (k.tag == "input" and k.attrs.get("type") == "hidden")]
    assert top[0] is alert, "the amber box opens the card"
    assert [a.attrs["href"] for a in box.find("a")] == links
    invalid = [n.attrs["name"] for n in card.walk() if n.attrs.get("aria-invalid") == "true"]
    assert invalid == [h[3:] for h in links], "only the named field is flagged (saved values)"


def test_step_three_reads_add_form_chips_quick_pills_then_next(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/keywords")
    page = _page(markup)
    add = post_forms(markup, "/onboarding/keywords")[0]
    assert [i.attrs.get("type") for i in form_inputs(add) if i.attrs.get("name") == "keyword"] == [
        "text"]
    row = page.one("div", "add-row")
    assert [(k.tag, k.attrs.get("id") or k.words()) for k in row.kids] == [
        ("input", "f-keyword"), ("button", "Add")], "the field and Add share one row"
    marks = [markup.index(s) for s in ('id="f-keyword"', 'class="chip-list"',
                                       'class="quick-list"', 'href="/onboarding/preview"')]
    assert marks == sorted(marks), "add form, chips, quick adds, then Next (spec 6.2)"
    nxt = page.one("a", href="/onboarding/preview")
    assert nxt.has("btn--primary") and nxt.words() == "Next: see a sample"


def test_step_three_editing_mode_puts_done_after_the_quick_adds(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/keywords", activated=True)
    assert markup.index('class="quick-list"') < markup.index("<span>Done</span>") < \
        markup.index('href="/onboarding/preview"')


def test_step_three_chips_and_pills_keep_their_motion_hooks(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/keywords"))
    chips = page.find("li", "kw")
    assert len(chips) == len(OB_SAVED)
    for chip in chips:
        assert chip.parent.tag == "ul" and chip.parent.has("chip-list")
        label = chip.kids[0]
        assert (label.tag, label.has("kw__text")) == ("span", True)
        assert chip.attrs.get("data-vt-kw") == label.words()
        remove = chip.one("form")
        assert remove.attrs.get("action", "").endswith("/delete")
    quick = page.find("button", "quick")
    suggestions = app_module._TEMPLATES.env.get_template("_ui.html").module.QUICK_KEYWORDS
    assert len(quick) == len(set(suggestions) - set(OB_SAVED))
    for button in quick:
        spans = [k for k in button.kids if k.tag == "span"]
        assert button.attrs.get("data-vt-kw") == spans[-1].words(), "the word is the last span"
        assert button.parent.tag == "form" and button.parent.parent.parent.has("quick-list")
    named = [n for n in page.walk() if "data-vt-kw" in n.attrs]
    assert named == chips + quick, "vt.js names only the chips and the quick-add pills"


def test_step_four_keeps_the_letter_and_the_activate_form_hooks(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/preview"))
    form = page.one("form", "activate")
    assert (form.attrs.get("action"), form.attrs.get("method")) == ("/onboarding/activate", "post")
    assert form.attrs.get("data-burst-src", "").startswith("/static/vendor/canvas-confetti-1.9.4.js")
    assert [(b.tag, b.words(), b.attrs.get("data-busy")) for b in form.find(cls="btn")] == [
        ("button", "Start watching for jobs", "Starting")]
    assert form.one(cls="btn").has("btn--primary")
    success = page.one(cls="alert--success")
    assert "data-arrive-gmail" in success.attrs
    assert (success.kids[0].tag, success.kids[0].has("icon")) == ("svg", True)
    preview = page.one("div", "preview")
    assert [(k.tag, k.attrs.get("class")) for k in preview.kids] == [
        ("section", "sample"), ("div", "preview__link"), ("article", "mailcard")]
    link = preview.kids[1]
    assert link.attrs.get("aria-hidden") == "true" and len(link.find(cls="fromto__node")) == 1
    card = preview.kids[2]
    assert len(card.find(cls="mailcard__head")) == 1 and len(card.find(cls="letter__part")) == 2
    row = card.one("div", "copy-row")
    copy = row.one("button", data_copy="#preview-letter")
    assert "hidden" in copy.attrs
    assert card.one("pre", id="preview-letter").has("letter__text")
    assert len(page.find(id="preview-letter")) == 1


def test_step_four_without_gmail_keeps_its_quiet_start_button(saas_cfg):
    """Today's rule, kept: without Gmail the one primary is Connect Gmail, so the activate form
    holds a secondary button, never celebrates and is never morphed (vt.js needs a primary)."""
    page = _page(_ob(saas_cfg, "/onboarding/preview", gmail=False))
    form = page.one("form", "activate")
    assert form.find(cls="btn--primary") == [] and "data-burst-src" not in form.attrs
    assert [b.words() for b in form.find(cls="btn--secondary")] == ["Start watching without Gmail"]


@pytest.mark.parametrize("path,query,gmail,activated", [
    ("/onboarding/connect_gmail", "", False, False), ("/onboarding/profile", "?error=1", True, False),
    ("/onboarding/keywords", "", True, False), ("/onboarding/keywords", "", True, True),
    ("/onboarding/preview", "", True, False), ("/onboarding/preview", "", False, False),
])
def test_every_post_form_on_every_step_carries_its_csrf_input(saas_cfg, path, query, gmail,
                                                              activated):
    page = _page(_ob(saas_cfg, path + query, gmail=gmail, activated=activated))
    forms = [f for f in page.find("form") if f.attrs.get("method") == "post"]
    assert forms
    for form in forms:
        csrf = [k for k in form.kids if k.tag == "input" and k.attrs.get("name") == "csrf"]
        assert len(csrf) == 1 and csrf[0].attrs.get("type") == "hidden", form.attrs
        assert csrf[0].attrs.get("value"), form.attrs


def test_the_celebrate_switch_is_still_on():
    source = (TEMPLATES / "_ui.html").read_text(encoding="utf-8")
    assert source.count("{% set CELEBRATE = true %}") == 1


@pytest.mark.parametrize("path", OB_STEPS)
def test_no_step_carries_a_dashboard_hook(saas_cfg, path):
    page = _page(_ob(saas_cfg, path))
    for attr in ("data-panel", "data-fresh"):
        assert [n for n in page.walk() if attr in n.attrs] == [], attr
    for cls in ("status", "live", "since", "dash__grid"):
        assert page.find(cls=cls) == [], cls


# --- section 8 of journey.css, read statically -------------------------------------------------

# What the frozen motion files move, resize or clip. Section 8 may set none of these on a hook.
OB_FROZEN = ("stepper", "stepper__list", "stepper__item", "stepper__marker", "gconf",
             "gconf__track", "gconf__line", "fromto__node", "kw", "chip-list", "quick", "preview",
             "preview__link", "mailcard", "mailcard__head", "letter__part", "copy-row", "activate",
             "badge--ok", "disclose", "site-header")
OB_MOVES = re.compile(r"(?:(?:min-|max-)?(?:width|height)|inline-size|block-size|inset(?:-.*)?|top|"
                      r"right|bottom|left|margin(?:-.*)?|position|transform|translate|scale|rotate|"
                      r"display|overflow(?:-.*)?|contain|isolation|z-index|clip-path|opacity|"
                      r"visibility|animation(?:-.*)?|transition(?:-.*)?|view-transition-.*|"
                      r"will-change|grid-.*|order|flex(?:-.*)?|align-self|justify-self|content)$")


def test_section_8_switches_layout_only_at_the_frozen_breakpoints():
    widths = {m for _s, _b, chain in OB_RULES for link in chain
              for m in re.findall(r"\((?:min|max)-width:\s*[^)]*\)", link)}
    assert widths <= {"(min-width:960px)", "(min-width:1100px)"}, widths


def test_section_8_recolours_the_motion_hooks_but_never_moves_them():
    bad = []
    for sel, body, _chain in OB_RULES:
        moved = sorted(p for p in decls(body) if OB_MOVES.match(p))
        for part in sel_split(sel, ","):
            last = sel_compounds(part)[-1][1]
            named = set(re.findall(r"\.([\w-]+)", re.sub(r":not\([^)]*\)", "", last)))
            if moved and named & set(OB_FROZEN):
                bad.append(f"{part}: {moved}")
    assert bad == []


def test_section_8_defines_its_tints_in_both_schemes():
    light, dark = _ob_tokens("light"), _ob_tokens("dark")
    assert set(light) == set(dark) == {"--ob-tint", "--ob-rule", "--ob-alarm"}
    assert all(light[k] != dark[k] for k in light), "dark mode must redefine every tint"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_section_8_tints_keep_text_readable(scheme):
    j, ob = tokens(read_css(JOURNEY_CSS), scheme), _ob_tokens(scheme)
    for fg in ("--j-text", "--j-muted", "--j-link"):          # chips, routes, labels, the Beta tag
        assert contrast(j[fg], ob["--ob-tint"]) >= 4.5, (scheme, fg)
    assert contrast(j["--j-danger-fg"], ob["--ob-alarm"]) >= 4.5, scheme   # the remove button
    assert contrast(j["--j-link"], j["--j-surface"]) >= 3.0, scheme       # the envelope ring


def test_step_4_links_keep_their_whole_tap_band_when_they_stack():
    """Below about 370px the two Step 4 links ("Change my message", "Change keywords") wrap onto
    two rows. Each is one line tall and carries a 44px ::after tap band (section 5) that hangs past
    the line above and below it. Unless the rows sit at least band minus line apart, the lower
    link's band covers the lower part of the upper link's words, and a tap there opens the wrong
    page. Checked for phone text and for computer text (a laptop zoomed to 400 percent)."""
    band = float(_declared(".text-link::after", "height").removesuffix("px"))
    lead = float(_declared("body", "line-height"))
    phone = float(_declared(":root", "--fs-body").removesuffix("rem"))
    computer = float(_declared(":root", "--fs-body", chain_ok=lambda c: c[1:] == (
        f"@media {_COMPUTER}",)).removesuffix("rem"))
    need = max(band - 16 * size * lead for size in (phone, computer))
    gaps = [decls(body)["row-gap"] for sel, body, chain in OB_RULES
            if not chain and ".link-row" in _parts(sel) and "row-gap" in decls(body)]
    assert gaps and float(gaps[-1].removesuffix("px")) >= need, (gaps, need)


def test_high_contrast_shows_the_current_rail_label():
    """Windows high contrast draws the current rail row as HighlightText on the Highlight marker
    (app.css). Chrome paints a Canvas backplate behind forced text, which hides HighlightText
    (white on white, black on black), so the label opts out of forcing and keeps the HighlightText
    it inherits. At 960px and up it is the only place the rail names the current step."""
    app_rules = list(iter_rules(read_css(APP_CSS)))
    assert any(_in(chain, r"forced-colors") and _in(chain, r"min-width:\s*960px")
               and '.stepper__item[aria-current="step"]' in _parts(sel)
               and decls(body).get("color") == "HighlightText"
               for sel, body, chain in app_rules), "the premise moved"
    assert not [sel for sel, body, _chain in app_rules + RULES
                if "color" in decls(body) and any(_subject(p).startswith(".stepper__full")
                                                  for p in _parts(sel))], "it must inherit"
    hits = [sel for sel, body, chain in RULES
            if _in(chain, r"forced-colors:\s*active") and _in(chain, r"min-width:\s*960px")
            and decls(body).get("forced-color-adjust") == "none"
            and ".stepper__item[aria-current=step] .stepper__full" in _parts(sel)]
    assert hits, "the current rail label is a blank box in Windows high contrast"


def _state(selector: str) -> str:
    """Task 4's matcher treats :disabled as a state no element is in; a button can be."""
    return selector.replace(":disabled", "[disabled]").replace(":enabled", ":not([disabled])")


def test_no_journey_rule_changes_the_frozen_activate_button(saas_cfg):
    """motion.css's af-fill morph starts from exactly this button: flat #0B6BC7, 12px corners,
    opacity 1, also while app.js holds it disabled and busy (spec 5.2)."""
    page = _page(_ob(saas_cfg, "/onboarding/preview"))
    button = page.one("form", "activate").one(cls="btn--primary")
    plain = button.chain()
    busy = plain[:-1] + [(plain[-1][0], {**plain[-1][1], "disabled": "", "data-state": "busy"})]
    colours = {"var(--j-primary)", "var(--j-primary-hover)"}
    bad = []
    for sel, props, _at in journey_style_rules():
        for part in sel_split(sel, ","):
            if not any(sel_reaches(_state(part), chain) for chain in (plain, busy)):
                continue
            for prop, value in props.items():
                v = value.replace("!important", "").strip()
                if (prop == "background-image" and v != "none") or \
                        (prop in ("background", "background-color") and v not in colours) or \
                        (prop == "opacity" and v != "1") or \
                        (prop.endswith("radius") and v != "var(--r-md)") or \
                        prop in ("filter", "backdrop-filter", "mix-blend-mode"):
                    bad.append(f"{part} {{{prop}: {value}}}")
    assert bad == []


def _reaching(chain, props: set[str]) -> list[tuple[str, str, str, str]]:
    """(selector, tag, property, value) for every journey declaration of ``props`` that can land
    on the last element of ``chain`` or on one of its ancestors."""
    hits = []
    for sel, found, _at in journey_style_rules():
        for prop in sorted(set(found) & props):
            for part in sel_split(sel, ","):
                hits += [(part, chain[d - 1][0], prop, found[prop])
                         for d in range(1, len(chain) + 1) if sel_reaches(_state(part), chain[:d])]
    return hits


def test_nothing_clips_a_chip_or_rings_it(saas_cfg):
    """Spec 6.2: no overflow:hidden on .kw, .chip-list or any parent, no new box-shadow on .kw.
    motion.css draws the new-chip ring as a box-shadow and a sonar ::after outside the chip."""
    chip = _page(_ob(saas_cfg, "/onboarding/keywords")).find("li", "kw")[0].chain()
    clips = {"overflow", "overflow-x", "overflow-y", "clip-path", "contain"}
    found = [h for h in _reaching(chip, clips)
             if re.search(r"hidden|clip|paint|strict|content|inset|polygon|circle", h[3])]
    assert found == []
    rings = [h for h in _reaching(chip, {"box-shadow"}) if h[1] == "li"]
    assert rings == []


def test_the_message_box_keeps_its_rows_and_fixed_sizing(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/profile")
    area = _page(markup).one("textarea", id="f-standard_message")
    assert area.attrs.get("rows") == "8"
    sizing = {"field-sizing", "height", "block-size", "max-height", "max-block-size"}
    chain = area.chain()
    bad = []
    for sel, props, _at in journey_style_rules():
        for part in sel_split(sel, ","):
            if not sel_reaches(_state(part), chain):
                continue
            for prop in set(props) & sizing:
                if not (prop == "field-sizing" and props[prop] == "fixed") and \
                        not (prop in ("height", "block-size") and props[prop] == "auto"):
                    bad.append(f"{part} {{{prop}: {props[prop]}}}")
    assert bad == []


def test_an_invalid_field_stays_amber_in_every_state(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/profile?error=long_job_type"))
    field = page.one("input", id="f-job_type")
    assert field.attrs.get("aria-invalid") == "true"
    edge = {"border", "border-color", "box-shadow", "outline", "outline-color"}
    found = [h for h in _reaching(field.chain(), edge) if h[1] == "input"]
    own = [h for h in found if "aria-invalid" in h[0]]
    assert own and all("--amber-600" in h[3] for h in own), own
    red = re.compile(r"danger|destructive|--red-|#B3261E|#FF8A80", re.I)
    assert [h for h in found if red.search(h[3])] == []


def test_the_sample_email_takes_no_onboarding_tint(saas_cfg):
    """The light island (section 2) redefines the --j-* tokens only, so an --ob-* tint inside the
    mailcard would turn dark in dark mode. The sample email stays white (spec 3, 5.3)."""
    markup = _ob(saas_cfg, "/onboarding/preview")
    card = _page(markup).one("article", "mailcard")
    bad = []
    for node in [card, *card.walk()]:
        chain = node.chain()
        for sel, props, _at in journey_style_rules():
            tinted = sorted(p for p, v in props.items() if "--ob-" in v)
            if tinted and any(sel_reaches(_state(p), chain) for p in sel_split(sel, ",")):
                bad.append(f"{sel} on <{node.tag} class={node.attrs.get('class')}>: {tinted}")
    assert bad == []


# --- Task 6: the dashboard (spec 6.3, 9) -------------------------------------------------------
#
# The dashboard in every state the route can choose. One status panel on top, chosen as before,
# then three groups of rows that are direct children of .dash__grid (the reveal layer reads
# .dash__grid > *), then a plain help note. The page tests read the rendered HTML, so they hold
# whatever macro prints the markup. The CSS tests read section 9 of journey.css statically.
# Carries its own imports and prefixes every helper with _dash so nothing clashes with the
# helpers Tasks 3 and 4 put in this file.

import dataclasses
import re
from html.parser import HTMLParser

import pytest

from _journey_css import (
    JOURNEY_CSS, JOURNEY_TEMPLATES, TEMPLATES, contrast, decls, iter_rules, read_css, tokens,
)
from _saas_client import clean, client_for, count_class, seed_user

# name: (saved keywords, Gmail connected, applications used today (the cap is 10), query,
#        the panel spec 6.3 chooses, primary buttons (None: at most one), Connect Gmail links)
DASH_STATES = {
    "gmail off": (("virtual assistant", "data entry"), False, 0, "", "gmail", 1, 1),
    "gmail off, retry": (("virtual assistant",), False, 0, "?gmail_error=scope", "gmail", 1, 1),
    "gmail off at the limit": (("virtual assistant",), False, 10, "", "gmail", 1, 1),
    "no keywords": ((), True, 0, "", "empty", 1, 0),
    "daily limit": (("virtual assistant",), True, 10, "", "paused", None, 0),
    "live": (("virtual assistant", "data entry"), True, 3, "", "live", 0, 0),
    "near the limit": (("virtual assistant",), True, 9, "", "live", 0, 0),
    "reconnect failed": (("virtual assistant",), True, 0, "?gmail_error=scope", "live", 0, 1),
}
DASH_TITLES = ["Watching", "Gmail", "Today"]


def _dash(cfg, master_key, state: str) -> str:
    kws, gmail, usage, query, *_ = DASH_STATES[state]
    user = seed_user(cfg, activated=True, keywords=kws, usage=usage,
                     gmail_key=master_key if gmail else None)
    resp = client_for(cfg, user).get("/dashboard" + query)
    assert resp.status_code == 200
    return resp.text


class _DashNode:
    """One element: its direct children, its parent, and all the text inside it."""

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_DashNode | None") -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.kids: list[_DashNode] = []
        self.text = ""

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def walk(self):
        yield self
        for kid in self.kids:
            yield from kid.walk()

    def find(self, pred) -> list["_DashNode"]:
        return [n for n in self.walk() if pred(n)]


class _DashTree(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _DashNode("#root", {}, None)

    def handle_starttag(self, tag, attrs):
        node = _DashNode(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.kids.append(node)
        if tag not in self._VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(_DashNode(tag, {k: v or "" for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node.parent is not None and node.tag != tag:
            node = node.parent
        if node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        node = self.cur
        while node is not None:
            node.text += data
            node = node.parent


def _dash_tree(markup: str) -> _DashNode:
    tree = _DashTree()
    tree.feed(markup)
    tree.close()
    return tree.root


def _dash_groups(markup: str) -> tuple[_DashNode, list[_DashNode]]:
    """The page tree and the direct children of the one .dash__grid."""
    root = _dash_tree(markup)
    grids = root.find(lambda n: "dash__grid" in n.classes)
    assert len(grids) == 1, "one .dash__grid"
    return root, grids[0].kids


def test_the_dashboard_loads_the_journey_look_after_the_motion_head(saas_cfg, master_key):
    """Spec 4.2 and M-1: app.css, the motion head, then Basecoat and journey.css, then reveal.js."""
    assert "dashboard.html" in JOURNEY_TEMPLATES
    markup = _dash(saas_cfg, master_key, "live")
    urls = re.findall(r'<(?:link|script)\b[^>]*?\s(?:href|src)="(/static/[^"?]+)', markup)
    order = ["/static/css/app.css", "/static/css/motion.css", "/static/js/vt.js",
             "/static/js/motion.js", "/static/vendor/basecoat-1.0.2-agad.css",
             "/static/css/journey.css", "/static/js/reveal.js"]
    assert [u for u in urls if u in order] == order
    assert '<meta name="color-scheme" content="light dark">' in markup


@pytest.mark.parametrize("state", DASH_STATES)
def test_each_state_shows_one_panel_chosen_as_before_and_its_primaries(saas_cfg, master_key,
                                                                       state):
    *_, panel, primaries, _connect = DASH_STATES[state]
    markup = _dash(saas_cfg, master_key, state)
    assert count_class(markup, "status") == 1
    assert re.findall(r'data-panel="([^"]*)"', markup) == [panel]
    n = count_class(markup, "btn--primary")
    assert (n <= 1) if primaries is None else (n == primaries), n


@pytest.mark.parametrize("state", DASH_STATES)
def test_three_groups_sit_directly_in_the_grid_in_spec_order(saas_cfg, master_key, state):
    _root, groups = _dash_groups(_dash(saas_cfg, master_key, state))
    assert [g.tag for g in groups] == ["section"] * 3
    assert all({"sheet", "dash__group"} <= set(g.classes) for g in groups)
    heads = [g.kids[0] for g in groups]
    assert [h.tag for h in heads] == ["h2"] * 3
    assert [clean(h.text) for h in heads] == DASH_TITLES
    assert [g.attrs.get("aria-labelledby") for g in groups] == [h.attrs.get("id") for h in heads]


@pytest.mark.parametrize("state,flags", [("live", 2), ("reconnect failed", 0), ("gmail off", 0),
                                         ("no keywords", 1), ("daily limit", 1)])
def test_the_gmail_group_keeps_the_arrival_flag_and_its_stamped_badge(saas_cfg, master_key,
                                                                      state, flags):
    """motion.css stamps [data-arrive-gmail] .badge--ok and pops [data-arrive-gmail] .live i.
    Two flags on a live dashboard (spec 9): the Gmail group and the live panel."""
    flagged = _dash_tree(_dash(saas_cfg, master_key, state)).find(
        lambda n: "data-arrive-gmail" in n.attrs)
    assert len(flagged) == flags
    for node in flagged:
        if "dash__group" in node.classes:
            assert "sheet" in node.classes and clean(node.kids[0].text) == "Gmail"
            assert node.find(lambda n: "badge--ok" in n.classes), "the badge the stamp animates"
        else:
            assert {"status", "status--live"} <= set(node.classes)
            assert node.find(lambda n: n.tag == "i" and "live" in n.parent.classes)


@pytest.mark.parametrize("state", DASH_STATES)
def test_the_limit_phrase_shows_once_at_the_limit_and_never_in_the_panel(saas_cfg, master_key,
                                                                          state):
    capped = DASH_STATES[state][2] >= 10
    markup = _dash(saas_cfg, master_key, state)
    assert markup.count("daily limit reached") == (1 if capped else 0)
    root, groups = _dash_groups(markup)
    panel = root.find(lambda n: "data-panel" in n.attrs)[0]
    assert "daily limit reached" not in panel.text
    assert ("daily limit reached" in groups[2].text) is capped


@pytest.mark.parametrize("state", DASH_STATES)
def test_the_keywords_stay_visible_in_every_state(saas_cfg, master_key, state):
    """The smoke needs them with Gmail off, where no panel names them."""
    kws = DASH_STATES[state][0]
    _root, groups = _dash_groups(_dash(saas_cfg, master_key, state))
    chips = groups[0].find(lambda n: n.tag == "li" and "chip" in n.classes)
    assert sorted(clean(c.text) for c in chips) == sorted(kws)
    if not kws:
        assert "None yet" in clean(groups[0].text)


@pytest.mark.parametrize("state", DASH_STATES)
def test_connect_gmail_shows_once_at_most_with_its_label_in_a_direct_span(saas_cfg, master_key,
                                                                         state):
    """Spec 6.3: the group's duplicate is gone. The one left is the panel primary when Gmail is
    off, or the group's secondary when a reconnect failed (motion.js swaps the direct span)."""
    want = DASH_STATES[state][6]
    markup = _dash(saas_cfg, master_key, state)
    root, groups = _dash_groups(markup)
    links = root.find(lambda n: n.tag == "a" and n.attrs.get("href") == "/auth/connect-gmail")
    assert len(links) == want
    for a in links:
        assert "btn" in a.classes
        assert [clean(k.text) for k in a.kids if k.tag == "span"] == ["Connect Gmail"]
    if state == "reconnect failed":
        assert "btn--secondary" in links[0].classes
        assert links[0] in list(groups[1].walk()), "it lives in the Gmail group"


def test_add_keywords_shows_once_on_an_empty_watch_list(saas_cfg, master_key):
    adds = _dash_tree(_dash(saas_cfg, master_key, "no keywords")).find(
        lambda n: n.tag == "a" and clean(n.text) == "Add keywords")
    assert len(adds) == 1 and "btn--primary" in adds[0].classes


@pytest.mark.parametrize("state", DASH_STATES)
def test_quiet_edit_links_replace_the_old_group_buttons(saas_cfg, master_key, state):
    connected, query = DASH_STATES[state][1], DASH_STATES[state][3]
    _root, (watching, gmail, today) = _dash_groups(_dash(saas_cfg, master_key, state))
    links = watching.find(lambda n: n.tag == "a")
    assert {a.attrs.get("href"): clean(a.text) for a in links} == {
        "/onboarding/keywords": "Edit keywords", "/onboarding/profile": "Edit details"}
    assert all("text-link" in a.classes and "btn" not in a.classes for a in links)
    assert today.find(lambda n: "btn" in n.classes) == []
    buttons = [clean(b.text) for b in gmail.find(lambda n: "btn" in n.classes)]
    want = (["Connect Gmail"] if connected and query else []) + (
        ["Disconnect Gmail"] if connected else [])
    assert buttons == want


@pytest.mark.parametrize("state", DASH_STATES)
def test_the_gmail_group_shows_the_address_its_badge_and_the_disconnect_row(saas_cfg, master_key,
                                                                            state):
    connected = DASH_STATES[state][1]
    _root, groups = _dash_groups(_dash(saas_cfg, master_key, state))
    gmail = groups[1]
    assert "maria@example.com" in clean(gmail.text)
    badges = [(b.classes, clean(b.text)) for b in gmail.find(lambda n: "badge" in n.classes)]
    assert badges == ([(["badge", "badge--ok"], "Connected")] if connected
                      else [(["badge", "badge--attention"], "Not connected")])
    forms = gmail.find(lambda n: n.tag == "form")
    if not connected:
        assert forms == [] and gmail.find(lambda n: n.tag == "details") == []
        return
    details = gmail.find(lambda n: n.tag == "details")
    assert len(details) == 1 and {"disclose", "disconnect"} <= set(details[0].classes)
    assert details[0].kids[0].tag == "summary"
    assert clean(details[0].kids[0].text) == "Disconnect Gmail"
    assert [(f.attrs.get("method"), f.attrs.get("action")) for f in forms] == [
        ("post", "/auth/disconnect-gmail")]
    assert forms[0] in list(details[0].walk())
    fields = forms[0].find(lambda n: n.tag == "input")
    assert [(i.attrs.get("type"), i.attrs.get("name")) for i in fields] == [("hidden", "csrf")]
    button = forms[0].find(lambda n: n.tag == "button")
    assert len(button) == 1 and "btn--danger" in button[0].classes
    assert clean(button[0].text) == "Disconnect Gmail"


@pytest.mark.parametrize("cap,used", [(10, 3), (25, 5)])
def test_usage_is_one_text_node_and_the_meter_widths_are_classes(saas_cfg, master_key, cap, used):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=cap)
    user = seed_user(cfg, activated=True, keywords=("va",), gmail_key=master_key, usage=used)
    markup = client_for(cfg, user).get("/dashboard").text
    assert f'<p class="usage">{used} / {cap}</p>' in markup
    assert not re.search(r"<[a-z][^>]*\sstyle\s*=", markup)
    _root, groups = _dash_groups(markup)
    today = groups[2]
    if cap <= 20:
        meters = today.find(lambda n: n.tag == "ol" and "meter" in n.classes)
        assert len(meters) == 1
        segments = [k for k in meters[0].kids if k.tag == "li"]
        assert len(segments) == cap and sum("on" in s.classes for s in segments) == used
    else:
        assert today.find(lambda n: "bar__fill--20" in n.classes)


def test_when_an_email_arrives_is_a_plain_note_after_the_groups(saas_cfg, master_key):
    root, _groups = _dash_groups(_dash(saas_cfg, master_key, "live"))
    notes = root.find(lambda n: "dash__help" in n.classes)
    assert len(notes) == 1
    note, stack = notes[0], notes[0].parent
    order = [k for k in stack.kids if "dash__grid" in k.classes or k is note]
    assert len(order) == 2 and order[1] is note, "the note follows the groups"
    assert note.find(lambda n: {"sheet", "route", "dash__group"} & set(n.classes)) == []
    assert clean(note.kids[0].text) == "When an email arrives"
    assert len(note.find(lambda n: n.tag == "li")) == 3


# --- section 9 of journey.css ---------------------------------------------------------------

# Classes only dashboard.html prints: its own markup, and the macros only it calls.
DASH_ONLY = {"dash", "dash__stack", "dash__grid", "dash__group", "dash__row", "dash__label",
             "dash__value", "dash__end", "dash__help", "status--live", "status--gmail",
             "status--empty", "status--paused", "status__icon", "status__kw", "chip", "usage",
             "usage-note", "usage-note--near", "usage-note--cap", "meter--full", "bar__fill--100"}
DASH_MACROS = ("ui.chip(", "ui.status_panel(", "ui.meter(")


def _dash_section() -> str:
    """Section 9 of journey.css, comments removed (the banners fence it)."""
    raw = JOURNEY_CSS.read_bytes().decode("utf-8").replace("\r\n", "\n")
    part = raw[raw.index("/* ---- 9 dashboard */"):raw.index("/* ---- 10 signin-failed */")]
    return re.sub(r"/\*.*?\*/", "", part, flags=re.S)


def _dash_split(selectors: str) -> list[str]:
    """One selector list as its selectors, split outside brackets, combinators unspaced."""
    out, depth, cur = [], 0, ""
    for ch in selectors:
        depth += (ch in "([") - (ch in ")]")
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [re.sub(r"\s*([>+~])\s*", r"\1", " ".join(p.split())) for p in out + [cur]]


def _dash_subject(part: str) -> str:
    depth, cut = 0, 0
    for i, ch in enumerate(part):
        depth += (ch in "([") - (ch in ")]")
        if depth == 0 and ch in " >+~":
            cut = i + 1
    return part[cut:]


def test_section_nine_styles_only_what_the_dashboard_prints():
    """Every journey rule beats every app.css rule, so a loose selector here would restyle the
    login or onboarding pages too. Each selector names a class only the dashboard prints."""
    loose, chains = [], set()
    for sel, _body, chain in iter_rules(_dash_section()):
        chains.add(chain)
        loose += [p for p in _dash_split(sel) if not set(re.findall(r"\.([\w-]+)", p)) & DASH_ONLY]
    assert loose == []
    assert chains <= {(), ("@media (prefers-color-scheme:dark)",)}, chains
    for page in TEMPLATES.glob("*.html"):
        if page.name in ("dashboard.html", "_ui.html"):
            continue
        src = page.read_text(encoding="utf-8")
        assert [m for m in DASH_MACROS if m in src] == [], page.name
        used = {c for attr in re.findall(r'class="([^"]*)"', src) for c in attr.split()}
        assert used & DASH_ONLY == set(), page.name


_GROUP = re.compile(r"\.(?:sheet|dash__group)(?![\w-])")
_STILL_PROPS = re.compile(r"(?:opacity|transform|translate|scale|rotate|visibility|clip-path|"
                          r"content-visibility|animation[\w-]*|transition[\w-]*)$")


def test_no_journey_rule_moves_fades_or_clips_a_dashboard_group():
    """reveal.js hides .dash__grid > * with opacity and transform in app.css's screens layer and
    settles it with an animation. journey sits above that layer, so any of these on a group would
    beat the reveal and leave a group stuck or unrevealed. overflow would clip focus rings."""
    bad = []
    for sel, body, _chain in iter_rules(read_css(JOURNEY_CSS)):
        d = decls(body)
        for part in _dash_split(sel):
            subject = re.sub(r":not\([^)]*\)", "", _dash_subject(part))
            if not (_GROUP.search(subject) or part.endswith(".dash__grid>*")):
                continue
            bad += [(part, p) for p in d if _STILL_PROPS.fullmatch(p)]
            bad += [(part, "overflow") for p in ("overflow", "overflow-x", "overflow-y")
                    if re.search(r"hidden|clip", d.get(p, ""))]
    assert bad == []


def _dash_rgba(value: str) -> tuple[float, ...]:
    m = re.fullmatch(r"rgba\(([^)]*)\)", value.replace(" ", ""))
    assert m, value
    return tuple(float(x) for x in m.group(1).split(","))


def test_the_live_panel_gains_an_edge_in_dark_only():
    """Spec 5.2: navy #0B2545 sits close to the dark ground, so it gains a 1px edge at white 12
    percent. The one value is the hairline token: navy on navy in light, white 12% in dark."""
    css = read_css(JOURNEY_CSS)
    touched = {}
    for sel, body, _chain in iter_rules(css):
        if ".status--live" in _dash_split(sel):
            touched.update(decls(body))
    assert touched == {"border-color": "var(--j-hairline)"}
    assert _dash_rgba(tokens(css, "dark")["--j-hairline"]) == (255, 255, 255, 0.12)
    assert _dash_rgba(tokens(css, "light")["--j-hairline"])[:3] == (11, 37, 69)


def _dash_dark() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for sel, body, chain in iter_rules(_dash_section()):
        if chain:
            for part in _dash_split(sel):
                out.setdefault(part, {}).update(decls(body))
    return out


def test_the_dashboard_panels_keep_aa_in_dark():
    t, dark = tokens(read_css(JOURNEY_CSS), "dark"), _dash_dark()
    paused = dark[".status--paused"]["background"]
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", paused), paused
    for fg, floor in (("--j-text", 4.5), ("--j-muted", 4.5), ("--j-link", 4.5), ("--j-edge", 3)):
        assert contrast(t[fg], paused) >= floor, (fg, round(contrast(t[fg], paused), 2))
    # The Gmail panel sits on the surface in dark, so its primary keeps a 3:1 edge (3.24, spec
    # 5.3). On the amber ground #2A2110 the frozen blue would measure 2.98.
    assert dark[".status--gmail"]["background"] == "var(--j-surface)"
    assert contrast(t["--j-primary"], t["--j-surface"]) >= 3


# app.css paints these with a fixed light-page navy, so journey must repaint them from a token.
REDRAWN = [(".chip", "color"), (".chip .icon", "color"), (".usage-note--cap", "color"),
           (".usage-note--near", "color"), (".meter--full li.on", "background"),
           (".bar__fill--100", "background"), (".dash .numbered>li::before", "background")]


@pytest.mark.parametrize("part,prop", REDRAWN, ids=[p for p, _ in REDRAWN])
def test_every_fixed_light_colour_on_the_dashboard_follows_the_scheme(part, prop):
    values = [decls(body)[prop] for sel, body, chain in iter_rules(_dash_section())
              if not chain and part in _dash_split(sel) and prop in decls(body)]
    assert values and values[-1].startswith("var(--j-"), values


# --- review focus: a phone in dark mode opening the dashboard ----------------------------------
#
# Uses Task 4's selector matcher (sel_split, sel_reaches, journey_style_rules) and Task 5's
# _state(), which sit earlier in this file.

# app.css tokens that section 2 re-points at the journey tokens, so they follow dark mode.
_DASH_FOLLOWS = {"--ground", "--surface", "--sunk", "--line", "--line-strong", "--text-strong",
                 "--text", "--text-muted"}
# Colours that already read on both grounds, so they stay in dark mode on purpose: the frozen
# primary blue #0B6BC7 (spec 5.3, 3.24 to 1 on the dark surface) and the amber #B86E00 that also
# marks invalid fields in both schemes (4.33 to 1 on the dark surface). Both fill meter segments.
_DASH_SCHEME_FREE = {"--blue-600", "--amber-600"}
# Painted the same in both schemes on purpose (spec 3, 5.2, 9): the navy live panel, Google's
# button, the white sample email, white text on the blue and red buttons, the navy skip link.
_DASH_ISLANDS = {"status--live", "gsi-btn", "mailcard", "btn--primary", "btn--danger", "skip-link"}
_DASH_PAINT = {"color": "color", "background": "background", "background-color": "background",
               "fill": "fill", "stroke": "stroke", "border-color": "border", "border": "border",
               "border-top": "border", "border-right": "border", "border-bottom": "border",
               "border-left": "border", "border-block": "border", "border-inline": "border"}
_DASH_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\b(?:white|black)\b", re.I)


def _dash_fixed(value: str) -> bool:
    """True when an app.css colour stays the light-page colour in dark mode."""
    names = set(re.findall(r"var\(\s*(--[\w-]+)", value))
    return bool(_DASH_LITERAL.search(value)) or any(
        not n.startswith(("--j-", "--ob-")) for n in names - _DASH_FOLLOWS - _DASH_SCHEME_FREE)


def _dash_chain(node) -> list:
    """The node and its ancestors as Task 4's matcher reads them: outermost first."""
    out = []
    while node is not None and node.tag != "#root":
        out.append((node.tag, node.attrs))
        node = node.parent
    return out[::-1]


# A journey rule that needs a hover, focus, press or visit does not repaint the part at rest.
_DASH_ACTION = re.compile(r":(?:hover|active|visited|focus(?:-visible|-within)?)(?![\w-])")


def _dash_at_rest(at) -> bool:
    """Straight in the journey layer or in its dark block, never behind a width, hover or pointer
    query: the rule holds for a phone at rest."""
    return at[:1] == ("@layer journey",) and len(at) <= 2 and all(
        _DARK_ONLY.fullmatch(a) for a in at[1:])


def _dash_journey(rules) -> list:
    """(selector parts, paint families) of the journey rules that count as a redraw."""
    return [(sel_split(sel, ","), {_DASH_PAINT[p] for p in props if p in _DASH_PAINT})
            for sel, props, at in rules if _dash_at_rest(at)]


def _dash_redrawn(journey, part: str, el, family: str) -> bool:
    """Some journey rule repaints ``family`` on ``el`` wherever app.css selector ``part`` does."""
    acts = set(_DASH_ACTION.findall(part))
    return any(family in fams and any(set(_DASH_ACTION.findall(q)) <= acts
                                      and sel_reaches(_state(q), el) for q in parts)
               for parts, fams in journey)


_DASH_BUTTON = [("html", {}), ("body", {}),
                ("button", {"class": "btn btn--secondary btn--sm", "type": "submit"})]


@pytest.mark.parametrize("planted,counts", [
    (".btn--secondary{color:var(--j-text)}", True),
    ("@media (prefers-color-scheme:dark){.btn--secondary{color:var(--j-text)}}", True),
    ("@media (min-width:960px){.btn--secondary{color:var(--j-text)}}", False),
    ("@media (hover:hover) and (pointer:fine){.btn--secondary{color:var(--j-text)}}", False),
    (".btn--secondary:hover{color:var(--j-text)}", False),
], ids=["at rest", "dark block", "wide screens", "computers", "hover"])
def test_only_a_redraw_a_phone_at_rest_gets_counts_on_the_dashboard(planted, counts):
    """The test below stands for a phone in dark mode. A redraw behind a width, hover or pointer
    query, or one that needs a hover, leaves that phone with app.css's navy on the dark surface."""
    rules = [(s, decls(b), c) for s, b, c in iter_rules(f"@layer journey{{{planted}}}")]
    got = _dash_redrawn(_dash_journey(rules), ".btn--secondary", _DASH_BUTTON, "color")
    assert got is counts


@pytest.mark.parametrize("state", DASH_STATES)
def test_no_light_page_colour_survives_on_the_dashboard_in_dark_mode(saas_cfg, master_key, state):
    """A phone in dark mode opening the dashboard. app.css paints some parts with fixed
    light-page colours (navy text, sky tints, amber edges). Each one that lands on this page,
    including what waits in a closed disclosure such as the Disconnect button, must be redrawn
    by a journey rule, which wins over app.css whatever the specificity, or sit on a part that
    is painted the same in both schemes on purpose."""
    elements = []
    for node in _dash_tree(_dash(saas_cfg, master_key, state)).walk():
        chain = _dash_chain(node)
        classes = {c for _tag, attrs in chain for c in attrs.get("class", "").split()}
        if "body" in [tag for tag, _attrs in chain] and not classes & _DASH_ISLANDS:
            elements.append((node, chain))
    assert len(elements) > 50, "sanity: the page rendered"
    journey = _dash_journey(journey_style_rules())
    missing = []
    for sel, body, chain in iter_rules(read_css(APP_CSS)):
        if sel.startswith("@") or any(re.search(r"forced-colors|print", c) for c in chain):
            continue
        paint = {_DASH_PAINT[p]: v for p, v in decls(body).items()
                 if p in _DASH_PAINT and _dash_fixed(v)}
        if not paint:
            continue
        for part in sel_split(sel, ","):
            for node, el in elements:
                if not sel_reaches(_state(part), el):
                    continue
                for family, value in paint.items():
                    if not _dash_redrawn(journey, part, el, family):
                        missing.append(f"<{node.tag} class='{node.attrs.get('class', '')}'> "
                                       f"{part} {{{family}: {value}}}")
    assert missing == [], "redraw these in journey.css section 9: " + "; ".join(sorted(set(missing)))
