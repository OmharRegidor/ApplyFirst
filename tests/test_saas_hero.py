"""Static guards for the homepage hero, the canvas scene, the CTA gradient and the font.

The hero is the one place on the site where text sits on a surface several layers paint into: two
CSS aura blobs, a live canvas, and a white wash. An earlier draft of this work stacked light
sources without modelling each other and pushed the hero copy under AA, and no existing test could
see it. So the contrast here is COMPUTED from the real declarations rather than trusted: these
tests read the aura alphas out of hero.css and the ink ceiling out of scene.js, composite them the
way a browser does, and fail if the result drops under AA.

They also pin the things that quietly rot. The scene loops, so WCAG 2.2.2 makes a pause control
mandatory and that control has to stop the CSS aura as well as the canvas. The new filenames have
to stay off the onboarding motion layer's list. And the head order the motion layer depends on has
to survive two extra blocks.
"""

from __future__ import annotations

import re

import pytest

from _saas_client import client_for
from test_saas_motion import (
    MOTION_ASSETS, NON_APP_PAGES, STATIC, _five_pages, _gz, _strip_comments, _text,
)

HERO_CSS = STATIC / "css" / "hero.css"
SCENE_JS = STATIC / "js" / "scene.js"
APP_CSS = STATIC / "css" / "app.css"
BASE_HTML = STATIC.parents[0] / "templates" / "base.html"

GROUND = (243, 246, 250)        # --ground, the darkest end of the hero's base gradient
WHITE = (255, 255, 255)
TEXT_STRONG = (11, 37, 69)      # --text-strong, the hero headline
TEXT = (36, 52, 73)             # --text, the hero lead
SKY_400 = (56, 174, 234)        # --sky-400, aura blob one
BLUE_600 = (11, 107, 199)       # --blue-600, aura blob two and every stroke the canvas paints


# --- contrast, computed rather than trusted ---------------------------------------------------

def _lum(rgb) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _over(src, dst, alpha):
    """Source-over compositing, which is how the aura, the canvas and the wash all land."""
    return tuple(s * alpha + d * (1 - alpha) for s, d in zip(src, dst))


def _aura_alphas() -> dict[str, float]:
    """The peak alpha of each aura blob, read out of the real radial gradients."""
    css = _strip_comments(_text(HERO_CSS))
    out = {}
    for name, rgb in (("sky", "56,174,234"), ("blue", "11,107,199")):
        hits = re.findall(r"radial-gradient\([^;]*?rgba\(" + rgb + r",\s*(\.\d+)\)", css)
        assert hits, f"hero.css declares no {name} aura"
        out[name] = max(float(h) for h in hits)
    return out


def _wash_floor() -> float:
    """The WEAKEST value of the white wash, which is the worst case for text sitting on it."""
    css = _strip_comments(_text(HERO_CSS))
    m = re.search(r"\.hero__scrim\s*\{(.*?)\}", css, re.S)
    assert m, "hero.css declares no .hero__scrim"
    vals = [float(a) for a in re.findall(r"rgba\(255,255,255,\s*(\.\d+)\)", m.group(1))]
    assert vals, "the wash paints nothing"
    return min(vals)


def _scene_cap() -> float:
    m = re.search(r"\bCAP\s*=\s*([\d.]+)", _text(SCENE_JS))
    assert m, "scene.js declares no CAP"
    return float(m.group(1))


def _worst_surface():
    """Every layer at its most aggressive, stacked, with the wash at its weakest. The two aura
    blobs actually sit in opposite corners and never fully overlap, so this is pessimistic on
    purpose: if the page passes here it passes anywhere."""
    a = _aura_alphas()
    c = _over(SKY_400, GROUND, a["sky"])
    c = _over(BLUE_600, c, a["blue"])
    c = _over(BLUE_600, c, _scene_cap())
    return _over(WHITE, c, _wash_floor())


def test_the_busiest_the_hero_can_ever_get_still_reads_at_aa():
    surface = _worst_surface()
    head = _ratio(TEXT_STRONG, surface)
    lead = _ratio(TEXT, surface)
    assert head >= 7.0, f"the headline is {head:.2f}:1 on the busiest surface"
    assert lead >= 4.5, f"the lead is {lead:.2f}:1 on the busiest surface"


def test_the_ink_ceilings_the_contrast_maths_assumes_are_the_ones_in_the_code():
    a = _aura_alphas()
    assert a["sky"] <= 0.26 and a["blue"] <= 0.20, f"the aura got heavier than budgeted: {a}"
    assert _scene_cap() <= 0.24, "the canvas ink ceiling the contrast maths assumes"
    assert _wash_floor() >= 0.25, "the wash must never thin out to nothing under the copy"


def test_the_scene_never_paints_a_colour_that_is_not_the_brand():
    src = _text(SCENE_JS)
    assert re.search(r"\bCAP_NVY\s*=\s*0\.\d+", src), "the second ink ceiling is missing"
    for r, g, b in re.findall(r'rgba\((\d+),(\d+),(\d+)', src):
        assert (int(r), int(g), int(b)) in (BLUE_600, TEXT_STRONG), f"stray colour {r},{g},{b}"
    for fn in ("function blu", "function nvy"):
        assert fn in src, f"{fn} is the only way alpha reaches the canvas"
    ink = re.search(r"function ink\([\s\S]*?\n  \}", src)
    assert ink and "> top ? top :" in ink.group(0), "ink() must clamp to the ceiling it is given"


# --- the scene loops, so the pause control is mandatory ---------------------------------------

def test_the_looping_background_ships_the_control_wcag_requires():
    """WCAG 2.2.2. Motion that starts on its own and runs past five seconds needs a way to stop
    it. The aura and the canvas both run indefinitely, so this control is not optional."""
    src = _text(SCENE_JS)
    assert re.search(r"CYCLE\s*=\s*\d+", src), "the scene no longer declares a cycle"
    assert 'className = "hero__pause"' in src, "no pause control is built"
    assert 'aria-pressed' in src and 'aria-label' in src, "the control must announce its state"
    css = _strip_comments(_text(HERO_CSS))
    assert ".hero__pause" in css, "the control has no styling"


def test_the_pause_control_stops_the_css_aura_too_not_just_the_canvas():
    """Half a pause is not a pause. The control sets data-scene on the hero and the stylesheet
    keys the aura's play state off it."""
    assert 'setAttribute("data-scene", "paused")' in _text(SCENE_JS)
    css = _strip_comments(_text(HERO_CSS))
    m = re.search(r'\[data-scene="paused"\][^{]*\{([^}]*)\}', css)
    assert m and "animation-play-state: paused" in m.group(1), (
        "the aura keeps running while the canvas is paused")


def test_the_control_is_built_by_script_so_there_is_none_without_motion():
    """With JavaScript off nothing moves, so a pause button would be a dead control. It must be
    created by scene.js, never sit in the template."""
    src = _text(STATIC.parents[0] / "templates" / "home.html")
    assert "hero__pause" not in src, "the template must not ship a control it cannot power"
    assert 'createElement("button")' in _text(SCENE_JS)


def test_the_scene_stops_when_nobody_is_looking():
    src = _text(SCENE_JS)
    for gate in ("IntersectionObserver", "visibilitychange", "prefers-reduced-motion: reduce",
                 "deviceMemory", "saveData", "effectiveType"):
        assert gate in src, f"scene.js must honour {gate}"
    assert "cancelAnimationFrame" in src


def test_reduced_motion_gets_a_composed_still_frame_not_a_slower_loop():
    src = _text(SCENE_JS)
    assert "function still" in src, "there is no still-frame path"
    still = re.search(r"function still\(\)[\s\S]*?\n  \}", src).group(0)
    assert "draw()" in still and "requestAnimationFrame" not in still, (
        "the still path must paint one frame and never schedule another")
    assert "go()" in src and "if (raf || userPaused || lite) return;" in src, (
        "nothing may start the loop once the reduced-motion path has been taken")


def test_the_aura_is_only_animated_where_motion_is_welcome():
    css = _strip_comments(_text(HERO_CSS))
    m = re.search(r"@media \(prefers-reduced-motion: no-preference\)\s*\{", css)
    assert m, "the aura animation must sit inside a no-preference block"
    for hit in re.finditer(r"animation:\s*hero-aura", css):
        assert hit.start() > m.start(), "an aura animation sits outside the no-preference block"


def test_the_scene_is_deterministic_so_every_visitor_sees_the_same_still_frame():
    assert re.search(r"rs\s*=\s*\d+", _text(SCENE_JS)), "no seeded RNG"
    assert "Math.random" not in _text(SCENE_JS), "Math.random would make the still frame vary"


# --- the new files stay off the onboarding motion layer ---------------------------------------

@pytest.mark.parametrize("name", ["hero.css", "reveal.js", "scene.js"])
def test_the_new_filenames_cannot_trip_the_public_page_guard(name):
    """M-2 forbids these four substrings on the public pages. A file called, say,
    home-motion.css would contain 'motion.css' and fail that test the moment it loaded."""
    for banned in MOTION_ASSETS:
        assert banned not in name, f"{name} contains {banned!r}"


@pytest.mark.parametrize("path", NON_APP_PAGES)
def test_the_public_pages_still_carry_no_onboarding_motion(saas_cfg, path):
    html = client_for(saas_cfg).get(path).text
    assert [a for a in MOTION_ASSETS if a in html] == []


def test_only_the_homepage_pays_for_the_hero(saas_cfg):
    for path in NON_APP_PAGES:
        html = client_for(saas_cfg).get(path).text
        want = path == "/"
        assert ("css/hero.css" in html) is want, f"{path} hero.css presence should be {want}"
        assert ("js/scene.js" in html) is want, f"{path} scene.js presence should be {want}"


# --- the head contract, with two new blocks in it ---------------------------------------------

def test_the_locked_head_order_survives_the_new_blocks(saas_cfg):
    """app.css, then the page stylesheet, then the parser-blocking reveal script. On the five
    signed-in pages the onboarding motion head still sits between them, untouched."""
    pages = dict(_five_pages(saas_cfg))
    for path in NON_APP_PAGES:
        pages[path] = client_for(saas_cfg).get(path).text
    for path, html in pages.items():
        tags = re.findall(r"<(?:link|script)\b[^>]*>", html)
        at = {}
        for i, tag in enumerate(tags):
            for asset in ("css/app.css", "css/hero.css", "js/reveal.js", "js/app.js"):
                if asset in tag:
                    at.setdefault(asset, i)
        assert "css/app.css" in at and "js/reveal.js" in at, path
        assert at["css/app.css"] < at["js/reveal.js"], f"{path}: app.css must come first"
        assert at["js/reveal.js"] < at["js/app.js"], f"{path}: reveal.js must precede app.js"
        if "css/hero.css" in at:
            assert at["css/app.css"] < at["css/hero.css"] < at["js/reveal.js"], path


# --- the gradient -----------------------------------------------------------------------------

def test_exactly_one_button_carries_a_gradient():
    """The house rule is one primary per view, so one gradient per view. If a second .btn
    variant grows a background-image the hierarchy stops reading."""
    css = _strip_comments(_text(APP_CSS))
    grads = set()
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if "background-image" in body and "grad-" in body and ".btn" in sel:
            for part in sel.split(","):
                m = re.search(r"\.btn--[a-z]+", part)
                if m:
                    grads.add(m.group(0))
    assert grads == {".btn--primary"}, f"gradients on {sorted(grads)}"


def test_no_sheen_survives_on_a_light_button():
    """Measured when the hero was dark: a white sweep over the light gradient drops the white
    label to 3.33:1 for the whole pass. The hero is light now, so the sheen has no home."""
    css = _strip_comments(_text(APP_CSS))
    assert "cta-sheen" not in css, "the sheen is back on a surface that cannot carry it"
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if ".btn--primary::after" in sel:
            assert "content:" not in body, f"a sheen box on a light button: {sel.strip()}"


# --- the font contract ------------------------------------------------------------------------

def test_the_site_uses_the_device_own_font_and_downloads_none_of_it():
    css = _text(APP_CSS)
    faces = re.findall(r"@font-face\s*\{[^}]*\}", css)
    assert not any("Jakarta" in f for f in faces), "a Plus Jakarta face is still declared"
    assert len(faces) == 1 and "Google Sans Button" in faces[0], (
        "only Google's own button face may be downloaded")
    m = re.search(r"--font-sans:\s*([^;]+);", css)
    assert m and m.group(1).strip().startswith("system-ui"), (
        f"--font-sans must lead with system-ui, got {m and m.group(1)!r}")


def test_no_page_preloads_a_font_the_stylesheet_never_asks_for():
    base = _text(BASE_HTML)
    assert "plus-jakarta" not in base, "base.html still preloads a deleted font on every page"
    fonts = sorted(p.name for p in (STATIC / "fonts").glob("*.woff2"))
    assert fonts == ["google-sans-button-500.woff2"], f"unexpected fonts on disk: {fonts}"


def test_the_headline_measure_is_font_relative_not_glyph_relative():
    """1ch is 0.732em in Plus Jakarta and 0.539em in Segoe UI, a 26% collapse. A ch-based cap on
    the hero headline would wrap it to three lines on every phone after the font swap."""
    css = _strip_comments(_text(APP_CSS))
    m = re.search(r"\.hero h1\s*\{([^}]*)\}", css)
    assert m, "the hero headline rule is gone"
    mw = re.search(r"max-width:\s*([^;]+);", m.group(1))
    assert mw and mw.group(1).strip().endswith("em"), (
        f"the headline cap must be em-based, got {mw and mw.group(1)!r}")


# --- budget -------------------------------------------------------------------------------------

def test_the_hero_layer_stays_inside_its_gzip_cap():
    """Same headroom policy as the motion caps: an accidental doubling fails, a fix does not."""
    hero, scene = _gz(HERO_CSS), _gz(SCENE_JS)
    assert hero <= 2780, f"hero.css gzip {hero} B"
    assert scene <= 4970, f"scene.js gzip {scene} B"
    assert hero + scene <= 7750, f"the homepage-only pair is {hero + scene} B"
