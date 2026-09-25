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

import hashlib
import importlib.util
import re

import pytest
from fontTools.ttLib import TTFont

from _saas_client import client_for
from test_saas_motion import (
    MOTION_ASSETS, NON_APP_PAGES, REPO, STATIC, TEMPLATES, _five_pages, _gz, _strip_comments,
    _text,
)

HERO_CSS = STATIC / "css" / "hero.css"
SCENE_JS = STATIC / "js" / "scene.js"
APP_CSS = STATIC / "css" / "app.css"
BASE_HTML = STATIC.parents[0] / "templates" / "base.html"
JOURNEY_CSS = STATIC / "css" / "journey.css"
INTER = STATIC / "fonts" / "inter-4.1-latin-wght.woff2"
INTER_SHA256 = "effa0eae43e76b7d0f6ebfb74c77db701a420ae30a24c14b09a3fc82646b1fd0"
INTER_LICENCE = STATIC / "licenses" / "OFL-inter.txt"
BUILD_INTER = REPO / "tools" / "fonts" / "build_inter.py"

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

@pytest.mark.parametrize("name", ["hero.css", "reveal.js", "scene.js", "journey.css",
                                  "inter-4.1-latin-wght.woff2"])
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
# The homepage, privacy and terms keep the device's own font. The sign-up journey adds Inter for
# Android and Windows (spec D5): one subset file, declared in journey.css only, never preloaded,
# with a metric-matched local fallback so the swap barely moves text.

def _builder():
    """tools/fonts/build_inter.py, loaded by path, so the tests and the build share one formula."""
    spec = importlib.util.spec_from_file_location("build_inter", BUILD_INTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _faces(css: str) -> dict[str, dict[str, str]]:
    """Every @font-face in a stylesheet, by family, as {descriptor: value} with spaces collapsed."""
    out: dict[str, dict[str, str]] = {}
    for body in re.findall(r"@font-face\s*\{([^}]*)\}", _strip_comments(css)):
        d = {k: " ".join(v.split()) for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body)}
        out[d["font-family"].strip("\"'")] = d
    return out


def _tnum_advances(font: TTFont) -> set[int]:
    """The advance of each digit 0-9 after the tnum substitution."""
    gsub = font["GSUB"].table
    wanted = {i for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == "tnum"
              for i in r.Feature.LookupListIndex}
    mapping: dict[str, str] = {}
    for i in wanted:
        for sub in gsub.LookupList.Lookup[i].SubTable:
            mapping.update(getattr(getattr(sub, "ExtSubTable", sub), "mapping", None) or {})
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    return {hmtx[mapping.get(cmap[c], cmap[c])][0] for c in range(0x30, 0x3A)}


def test_app_css_keeps_the_device_font_and_never_asks_for_inter():
    css = _text(APP_CSS)
    faces = re.findall(r"@font-face\s*\{[^}]*\}", css)
    assert not any("Jakarta" in f for f in faces), "a Plus Jakarta face is still declared"
    assert len(faces) == 1 and "Google Sans Button" in faces[0], (
        "only Google's own button face may be downloaded by app.css")
    m = re.search(r"--font-sans:\s*([^;]+);", css)
    assert m and m.group(1).strip().startswith("system-ui"), (
        f"--font-sans must lead with system-ui, got {m and m.group(1)!r}")
    for sheet in (APP_CSS, HERO_CSS, STATIC / "css" / "story.css", STATIC / "css" / "motion.css"):
        src = _text(sheet)
        assert "Inter Agad" not in src and INTER.name not in src, f"{sheet.name} asks for Inter"


def test_no_page_preloads_a_font_the_stylesheet_never_asks_for():
    base = _text(BASE_HTML)
    assert "plus-jakarta" not in base, "base.html still preloads a deleted font on every page"
    fonts = sorted(p.name for p in (STATIC / "fonts").glob("*.woff2"))
    assert fonts == ["google-sans-button-500.woff2", INTER.name], f"unexpected fonts: {fonts}"


def test_no_template_preloads_or_names_inter():
    """Spec 4.5: never preloaded. Apple devices match -apple-system first and must download
    nothing, and a preload would fetch the file on every iPhone. Only journey.css names it."""
    for tpl in sorted(TEMPLATES.glob("*.html")):
        src = _text(tpl)
        assert INTER.name not in src and "Inter Agad" not in src, f"{tpl.name} names Inter"
        for tag in re.findall(r"<link\b[^>]*>", src):
            assert not ("preload" in tag and "inter" in tag.lower()), f"{tpl.name}: {tag}"


def test_the_inter_file_is_the_pinned_subset_under_its_cap():
    data = INTER.read_bytes()
    assert data[:4] == b"wOF2", "the Inter file must be WOFF2"
    assert len(data) <= 50_000, f"{INTER.name} is {len(data)} B, over the 50,000 B cap (spec 8)"
    assert hashlib.sha256(data).hexdigest() == INTER_SHA256, (
        "the Inter file changed: rebuild it only with tools/fonts/build_inter.py, then re-pin")


def test_the_inter_file_name_carries_the_version_from_its_name_table():
    """journey.css loads it without ?v, so a new Inter must arrive under a new name."""
    b = _builder()
    assert INTER.name == b.font_name(b.version_of(TTFont(INTER)))


def test_the_inter_subset_keeps_what_the_journey_pages_print():
    font = TTFont(INTER)
    axes = [(a.axisTag, a.minValue, a.maxValue) for a in font["fvar"].axes]
    assert axes == [("wght", 400, 600)], f"opsz must be pinned and wght limited to 400-600: {axes}"
    cmap = font.getBestCmap()
    need = [*range(0x20, 0x7F), *range(0xA0, 0xAD), *range(0xAE, 0x100),   # U+00AD has no glyph
            0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x20B1]
    missing = [f"U+{c:04X}" for c in need if c not in cmap]
    assert not missing, f"the subset lost characters the pages print: {missing}"
    assert set(cmap) <= set(_builder().unicodes()), "the file holds more than its unicode-range"
    gpos = {r.FeatureTag for r in font["GPOS"].table.FeatureList.FeatureRecord}
    assert "kern" in gpos, "kerning was dropped"
    digits = {font["hmtx"][cmap[c]][0] for c in range(0x30, 0x3A)}
    assert len(digits) > 1 and len(_tnum_advances(font)) == 1, (
        "tnum must give all ten digits one width (usage counts and times line up)")


def test_the_inter_face_is_declared_in_journey_css_only():
    faces = _faces(_text(JOURNEY_CSS))
    assert set(faces) == {"Inter Agad", "Inter Agad Fallback"}, sorted(faces)
    inter = faces["Inter Agad"]
    assert inter["font-display"] == "swap" and inter["font-style"] == "normal"
    assert inter["font-weight"] == "400 600", "the face must declare the weight range it ships"
    one_url = r'url\("\.\./fonts/' + re.escape(INTER.name) + r'"\) format\("woff2"\)'
    assert re.fullmatch(one_url, inter["src"]), (
        f"one url and no ?v, the name carries the version: {inter['src']}")
    assert inter["unicode-range"].replace(" ", "") == _builder().unicode_range_css()


def test_the_fallback_face_is_tuned_to_the_served_inter():
    """Segoe UI on Windows and Roboto on Android, scaled to Inter's average width and line box
    (spec 4.5). The expected numbers come from the served file through the formula the build
    script prints, so a new Inter without retuned numbers fails here."""
    fb = _faces(_text(JOURNEY_CSS))["Inter Agad Fallback"]
    assert "url(" not in fb["src"], "the fallback face must never download anything"
    names = re.findall(r'local\("([^"]+)"\)', fb["src"])
    assert "Segoe UI" in names and "Roboto" in names, names
    want = _builder().fallback_descriptors(TTFont(INTER))
    assert {k: fb.get(k) for k in want} == want, f"retune Inter Agad Fallback to {want}"


def test_the_inter_licence_ships_beside_the_font():
    lic = _text(INTER_LICENCE)
    assert "SIL OPEN FONT LICENSE Version 1.1" in lic and "The Inter Project Authors" in lic
    assert "Modified by Agad" in lic and INTER.name in lic and _builder().COMMIT in lic


def test_the_build_script_pins_one_commit_one_hash_and_the_spec_settings():
    b = _builder()
    assert re.fullmatch(r"[0-9a-f]{40}", b.COMMIT) and b.COMMIT in b.SOURCE_URL
    assert "/main/" not in b.SOURCE_URL and re.fullmatch(r"[0-9a-f]{64}", b.SOURCE_SHA256)
    assert (b.OPSZ, b.WGHT, b.MAX_BYTES) == (14, (400, 600), 50_000)
    assert "tnum" in b.FEATURES and (0x20B1, 0x20B1) in b.UNICODE_RANGES


def test_the_inter_file_is_served_as_a_cached_font(saas_cfg):
    """A first visit on a slow Android connection. Text paints at once in the tuned fallback
    (font-display swap, tested above) while the file comes from our own origin as a font, and a
    second visit reuses it: no ?v on its url, so a day of caching plus an ETag, and a new Inter
    arrives under a new file name."""
    r = client_for(saas_cfg).get(f"/static/fonts/{INTER.name}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "font/woff2"
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert r.headers.get("etag")
    assert r.content == INTER.read_bytes()


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
