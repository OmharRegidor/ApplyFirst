"""Static guards for the public reveal layer (scroll-in components, and the slots surprise).

The reveal layer has one dangerous property: it hides content. If the attribute that gates it is
ever set without the observer arming, or the CSS start state drifts out of step with the selector
list in reveal.js, a reader is left staring at an invisible page. These tests pin the contract:

* the CSS hides a target ONLY inside ``:root[data-rv]`` and only under ``no-preference``,
* the CSS selector list and the JS selector list are the same list,
* the surprise is entirely optional and cannot take the static diagram away,
* and the whole layer stays inside a byte budget, like the motion layer before it.

Nothing here touches a route, a redirect, a CSRF field or the Content-Security-Policy.
"""

from __future__ import annotations

import re

import pytest

from _saas_client import client_for
from test_saas_motion import STATIC, _gz, _rules, _strip_comments, _text

REVEAL_JS = STATIC / "js" / "reveal.js"
APP_CSS = STATIC / "css" / "app.css"


def _js_list(name: str) -> set[str]:
    """The selector list a `const NAME = "a" + "b";` declaration in reveal.js builds."""
    src = _text(REVEAL_JS)
    m = re.search(r"const\s+" + name + r"\s*=\s*(.*?);", src, re.S)
    assert m, f"reveal.js declares no {name}"
    joined = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    return {s.strip() for s in joined.split(",") if s.strip()}


def _css_rule() -> tuple[str, str]:
    """The reveal start-state rule: its :is(...) target list and its :not(...) skip list."""
    css = _strip_comments(_text(APP_CSS))
    m = re.search(r":root\[data-rv\]\s*:is\((.*?)\)\s*:not\((.*?)\)\s*\{", css, re.S)
    assert m, "app.css has no :root[data-rv] :is(...):not(...) start-state rule"
    return m.group(1), m.group(2)


# --- R-1 ------------------------------------------------------------------------------------

def test_the_css_and_the_js_agree_on_which_elements_reveal():
    """If these drift, either an element is hidden and never revealed, or it is observed and
    never hidden, and both failures are silent."""
    targets_css, _ = _css_rule()
    css_set = {s.strip() for s in targets_css.split(",") if s.strip()}
    assert css_set == _js_list("TARGETS"), (
        "app.css and reveal.js disagree.\n"
        f"  only in CSS: {sorted(css_set - _js_list('TARGETS'))}\n"
        f"  only in JS:  {sorted(_js_list('TARGETS') - css_set)}")


def test_the_css_and_the_js_agree_on_which_elements_are_skipped():
    _, skip_css = _css_rule()
    # closest() matches the element itself OR an ancestor, so the CSS must exclude both the
    # skipped element and everything inside it. That is two :is() groups over the same list.
    groups = re.findall(r":is\((.*?)\)", skip_css, re.S)
    assert len(groups) == 2, f"expected the element form and the descendant form, got {groups}"
    assert groups[0].strip() == groups[1].strip(), "the two skip groups must hold the same list"
    css_set = {s.strip() for s in groups[0].split(",") if s.strip()}
    assert css_set == _js_list("SKIP")
    assert skip_css.strip().endswith("*"), "the second skip group must end in ' *' (descendants)"


# --- R-2, the guarantee that matters ---------------------------------------------------------

def test_nothing_is_ever_hidden_without_the_attribute_reveal_js_sets():
    """Every rule in app.css that sets opacity: 0 for the reveal must be gated on
    :root[data-rv]. reveal.js is the only thing that sets it, and it removes it on any bail,
    so a reader with no JavaScript, a blocked file or a slow parse sees a complete page."""
    offenders = []
    for rule in _rules(_strip_comments(_text(APP_CSS))):
        body = rule.body if hasattr(rule, "body") else rule[-1]
        sel = rule.selector if hasattr(rule, "selector") else rule[0]
        if "data-rv" not in sel and "rv-in" not in sel and "rv-pop" not in sel:
            continue
        if re.search(r"opacity:\s*0\b", body) and "[data-rv]" not in sel:
            offenders.append(sel)
    assert offenders == [], f"reveal rules hiding content without the gate: {offenders}"


def test_the_reveal_start_state_only_applies_when_motion_is_welcome():
    css = _strip_comments(_text(APP_CSS))
    m = re.search(r"@media screen and \(prefers-reduced-motion: no-preference\)\s*\{", css)
    assert m, "the reveal block must sit inside a screen + no-preference media query"
    start = css.index(":root[data-rv] :is(")
    assert start > m.start(), "the start-state rule must be inside that media query"


def test_reveal_js_gives_up_rather_than_leaving_the_page_hidden():
    src = _text(REVEAL_JS)
    assert "removeAttribute" in src, "reveal.js must be able to drop the gate"
    assert re.search(r"setTimeout\(\s*off\s*,\s*3000\s*\)", src), "the 3s watchdog is missing"
    assert "IntersectionObserver" in src and "prefers-reduced-motion: reduce" in src
    for bail in ("deviceMemory", "saveData", "effectiveType"):
        assert bail in src, f"reveal.js must bail on {bail}"


def test_the_hero_never_reveals_so_the_headline_stays_an_lcp_candidate():
    targets_css, _ = _css_rule()
    assert ".hero" not in targets_css, "a hidden hero headline would wreck Largest Contentful Paint"


# --- R-3 and R-4, the surprise is optional ---------------------------------------------------

def test_the_slots_surprise_is_entirely_inside_a_supports_block():
    """Firefox does not ship scroll-driven animations. The whole effect must be skipped there,
    leaving today's static diagram, rather than half-applying and losing the picture."""
    css = _strip_comments(_text(APP_CSS))
    m = re.search(r"@supports \(animation-timeline: view\(\)\)\s*\{", css)
    assert m, "no @supports (animation-timeline: view()) block"
    depth, end = 0, None
    for i in range(m.end() - 1, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end, "unbalanced @supports block"
    inside = css[m.start():end]
    for hit in re.finditer(r"^\s*(\.slots[^{]*)\{", css, re.M):
        assert hit.group(1) in inside, f"`{hit.group(1).strip()}` sits outside the @supports block"


def test_the_surprise_never_uses_the_animation_shorthand():
    """The shorthand sets duration to 0s, and a progress timeline needs the initial `auto`.
    Longhands also keep iteration-count at 1, which is what keeps these out of the
    "runs forever" list in the motion tests."""
    css = _strip_comments(_text(APP_CSS))
    for hit in re.finditer(r"(\.slots[^{]*)\{([^}]*)\}", css):
        assert not re.search(r"(^|;)\s*animation:", hit.group(2)), (
            f"`{hit.group(1).strip()}` uses the animation shorthand")


def test_the_stage_the_surprise_animates_still_exists(saas_cfg):
    """The ranges are written per :nth-child, so the count is load-bearing."""
    html = client_for(saas_cfg).get("/").text
    block = re.search(r'<ol class="slots"[^>]*>(.*?)</ol>', html, re.S)
    assert block, "the homepage no longer renders <ol class=\"slots\">"
    items = re.findall(r"<li([^>]*)>", block.group(1))
    assert len(items) == 16, f"expected 16 slots, found {len(items)}"
    assert sum("early" in a for a in items) == 3
    assert sum("full" in a for a in items) == 1
    assert 'aria-hidden="true"' in block.group(0), "the diagram must stay invisible to screen readers"


# --- R-BUDGET ---------------------------------------------------------------------------------

def test_the_reveal_layer_stays_inside_its_gzip_cap():
    """Modelled on the motion layer's cap. Roughly 12% headroom: an accidental doubling fails,
    an honest fix does not."""
    assert _gz(REVEAL_JS) <= 1400, f"reveal.js gzip {_gz(REVEAL_JS)} B"


@pytest.mark.parametrize("path", ["/", "/login", "/privacy", "/terms"])
def test_the_public_pages_load_reveal_and_not_the_onboarding_motion_layer(saas_cfg, path):
    html = client_for(saas_cfg).get(path).text
    assert "js/reveal.js" in html, f"{path} does not load the reveal layer"
    for banned in ("motion.css", "vt.js", "motion.js", "canvas-confetti"):
        assert banned not in html, f"{path} leaked {banned}"


def test_reveal_js_is_parser_blocking_so_the_start_state_beats_the_first_paint(saas_cfg):
    html = client_for(saas_cfg).get("/").text
    tag = re.search(r"<script[^>]*js/reveal\.js[^>]*>", html)
    assert tag, "reveal.js is not loaded"
    assert not re.search(r"\s(?:async|defer|type)\b", tag.group(0)), (
        f"reveal.js must be classic and parser-blocking, got {tag.group(0)}")
