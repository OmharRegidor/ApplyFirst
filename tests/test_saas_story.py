"""Static guards for the homepage scroll story (story.css) and the reveal layer's three arrivals.

story.css adds three moments to the homepage: the hero's timing ruler draws itself once, the How it
works line fills as you read down it, and the example email lights one part at a time as it
crosses the middle of the screen. The reveal layer in app.css now gives headings, reading text and
objects three different arrivals instead of one.

None of it may hide content, stutter a phone, outlive the five-second rule, or leave a hole when
JavaScript, scroll-driven animations or motion itself are missing. These tests pin each of those,
read out of the real files. The glows added behind three sections are checked for contrast the
same way the hero is, composited from the alphas actually declared.
"""

from __future__ import annotations

import math
import re

import pytest

from _saas_client import client_for
from test_saas_hero import _over, _ratio
from test_saas_motion import (
    MOTION_ASSETS, NON_APP_PAGES, STATIC, _animation, _decls, _five_pages, _gz, _no_preference,
    _rules, _split_blocks, _strip_comments, _text,
)
from test_saas_reveal import _css_rule, _js_list

STORY_CSS = STATIC / "css" / "story.css"
HERO_CSS = STATIC / "css" / "hero.css"
SCENE_JS = STATIC / "js" / "scene.js"
APP_CSS = STATIC / "css" / "app.css"
REVEAL_JS = STATIC / "js" / "reveal.js"

HOME_HTML = STATIC.parent / "templates" / "home.html"
MOTION_CSS = STATIC / "css" / "motion.css"
STORY_RULES = _rules(_strip_comments(_text(STORY_CSS)))
APP_RULES = _rules(_strip_comments(_text(APP_CSS)))
SUPPORTS = re.compile(r"@supports\s*\(\s*animation-timeline:\s*view\(\)\s*\)")
PSEUDO = re.compile(r"::(?:before|after)\s*$")


def _selectors(prelude: str) -> list[str]:
    """Top-level comma split, so a comma inside :is() or :not() does not split a selector."""
    out, depth, cur = [], 0, ""
    for ch in prelude:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


def _props(rule) -> dict[str, str]:
    return dict(_decls(rule.body))


def _find(rules, selector: str, *, chain_has: str | None = None, chain_lacks: str | None = None):
    hits = [r for r in rules if r.kind == "style" and selector in _selectors(r.prelude)
            and (chain_has is None or any(chain_has in c for c in r.chain))
            and (chain_lacks is None or not any(chain_lacks in c for c in r.chain))]
    assert hits, f"no rule for {selector!r} (chain has {chain_has!r}, lacks {chain_lacks!r})"
    return hits[0]                    # the defining rule, not a later forced-colours override


def _keyframes(rules, name: str):
    hits = [r for r in rules if r.kind == "keyframes" and r.prelude.split()[-1] == name]
    assert hits, f"no @keyframes {name}"
    return hits[-1]


def _frames(body: str) -> dict[str, dict[str, str]]:
    """Each keyframe selector (from, to, 42% ...) mapped to its declarations."""
    out: dict[str, dict[str, str]] = {}
    for prelude, frame in _split_blocks(body):
        for key in prelude.split(","):
            key = {"from": "0%", "to": "100%"}.get(key.strip(), key.strip())
            out.setdefault(key, {}).update(dict(_decls(frame)))
    return out


# --- where the file loads ---------------------------------------------------------------------

def test_no_homepage_asset_name_can_trip_the_public_page_guard():
    """M-2 fails a public page that names motion.css, vt.js, motion.js or canvas-confetti. A file
    called, say, story-motion.css would contain 'motion.css'. Read from the template itself."""
    assets = re.findall(r"static_url\('([^']+)'\)", _text(HOME_HTML))
    assert "css/story.css" in assets, "home.html no longer links story.css"
    bad = [a for a in assets for banned in MOTION_ASSETS if banned in a]
    assert bad == [], f"homepage assets whose names trip M-2: {bad}"


def test_only_the_homepage_pays_for_the_story(saas_cfg):
    pages = {path: client_for(saas_cfg).get(path).text for path in NON_APP_PAGES}
    pages.update(_five_pages(saas_cfg))
    for path, html in pages.items():
        assert ("css/story.css" in html) is (path == "/"), f"{path} story.css presence is wrong"


def test_the_story_loads_after_the_hero_and_before_the_reveal_script(saas_cfg):
    """story.css restates the layer order with `story` last, so it has to arrive after hero.css
    and, like every stylesheet, before the parser-blocking reveal script."""
    tags = re.findall(r"<(?:link|script)\b[^>]*>", client_for(saas_cfg).get("/").text)
    at = {a: next(i for i, t in enumerate(tags) if a in t)
          for a in ("css/app.css", "css/hero.css", "css/story.css", "js/reveal.js")}
    assert at["css/app.css"] < at["css/hero.css"] < at["css/story.css"] < at["js/reveal.js"], at


def test_the_story_layer_wins_over_the_hero_without_important():
    story = re.search(r"@layer\s+([^;{]+);", _strip_comments(_text(STORY_CSS)))
    hero = re.search(r"@layer\s+([^;{]+);", _strip_comments(_text(HERO_CSS)))
    assert story and hero, "both files must restate the layer order"
    s = [x.strip() for x in story.group(1).split(",")]
    h = [x.strip() for x in hero.group(1).split(",")]
    assert s[:len(h)] == h and s[-1] == "story", f"story.css layer order is {s}"
    assert "!important" not in _text(STORY_CSS)


# --- motion that respects the reader ----------------------------------------------------------

def test_everything_that_moves_waits_for_no_preference():
    """Reduced motion must get a still page, not a faster one."""
    loose = [r.prelude for r in STORY_RULES if r.kind == "style"
             and any((p.startswith("animation") and v != "none") or p == "transition" for p, v in _decls(r.body))
             and not _no_preference(r.chain)]
    assert loose == [], f"story.css animates outside prefers-reduced-motion: no-preference: {loose}"


def test_every_scroll_driven_rule_sits_inside_the_supports_block():
    """A browser without scroll-driven animations must skip the whole moment, not half of it."""
    loose = [r.prelude for r in STORY_RULES if r.kind == "style"
             and any(p in ("animation-timeline", "animation-range", "view-timeline-name") for p in _props(r))
             and not any(SUPPORTS.search(c) for c in r.chain)]
    assert loose == [], f"scroll-driven rules outside @supports (animation-timeline: view()): {loose}"


def test_scroll_driven_rules_never_use_the_animation_shorthand():
    """The shorthand resets animation-duration to 0s, and a progress timeline needs auto."""
    bad = [r.prelude for r in STORY_RULES if r.kind == "style"
           and any(SUPPORTS.search(c) for c in r.chain) and "animation" in _props(r)]
    assert bad == [], f"shorthand inside the scroll-driven block: {bad}"


def test_keyframes_move_only_transform_and_opacity():
    """Compositor-only, so no scroll frame is ever painted on a mid-range phone. Covers the story
    and every reveal arrival in app.css."""
    bad = []
    for rule in STORY_RULES + [r for r in APP_RULES if r.kind == "keyframes"
                               and r.prelude.split()[-1].startswith("rv-")]:
        if rule.kind != "keyframes":
            continue
        for frame in _frames(rule.body).values():
            bad += [f"{rule.prelude}: {p}" for p in frame if p not in ("transform", "opacity")]
    assert bad == [], f"keyframes animate a property that repaints: {bad}"


def test_time_based_moments_finish_inside_five_seconds():
    """WCAG 2.2.2. Anything that moves on its own for more than five seconds needs a pause
    control. A rule that only moves a delay is measured against the animation it delays."""
    over = []
    for r in STORY_RULES:
        if r.kind != "style" or "animation-timeline" in _props(r) or any(SUPPORTS.search(c) for c in r.chain):
            continue
        anim = _animation(_decls(r.body))
        if anim is None:
            continue
        assert anim.iterations != math.inf, f"{r.prelude} runs forever"
        duration = anim.duration
        if duration is None:
            target = re.findall(r"\.[\w-]+", r.prelude)[-1]
            known = [a.duration * a.iterations for a in (
                _animation(_decls(x.body)) for x in APP_RULES + STORY_RULES
                if x.kind == "style" and x.prelude.rstrip().endswith(target))
                if a is not None and a.duration is not None]
            assert known, f"{r.prelude} delays an animation this test cannot find"
            duration = max(known)
        if anim.delay + duration * anim.iterations > 5000:
            over.append(f"{r.prelude} ({anim.delay + duration * anim.iterations:.0f} ms)")
    assert over == [], f"moments past 5,000 ms: {over}"


# --- nothing is ever hidden -------------------------------------------------------------------

def test_the_story_only_ever_fades_its_own_decorations():
    """Every opacity: 0 in story.css lands on a ::before or ::after that holds no text. Real
    content never fades, so nothing can be left invisible."""
    bad = []
    for r in STORY_RULES:
        if r.kind == "style" and re.search(r"(^|;)\s*opacity:\s*0\b", r.body):
            bad += [s for s in _selectors(r.prelude) if not PSEUDO.search(s)]
    # ...and through keyframes. Anything whose animation starts at opacity 0 must be a decoration,
    # or the FAQ answer the reader has just opened ([open]), which fades for 280ms and ends visible.
    starts_hidden = {r.prelude.split()[-1] for r in STORY_RULES if r.kind == "keyframes"
                     and _frames(r.body).get("0%", {}).get("opacity") == "0"}
    assert starts_hidden, "no story keyframe starts hidden, so this half of the test is looking at nothing"
    for r in STORY_RULES:
        anim = _animation(_decls(r.body)) if r.kind == "style" else None
        if anim and anim.name in starts_hidden:
            bad += [s for s in _selectors(r.prelude) if not PSEUDO.search(s) and "[open]" not in s]
    assert bad == [], f"story.css hides something that is not a decoration: {bad}"
    for r in STORY_RULES:
        props = _props(r)
        if r.kind == "style" and "content" in props:
            assert props["content"] == '""', f"{r.prelude} carries text: {props['content']}"


def test_keyboard_focus_never_lands_inside_an_invisible_target():
    """The observer trims 10% off the bottom of the screen, so a target can sit on screen at
    opacity 0. Tabbing into it must show it, or the focus ring is drawn invisibly (WCAG 2.4.7)."""
    m = re.search(r'addEventListener\("focusin".*?\}\);', _text(REVEAL_JS), re.S)
    assert m, "reveal.js does not reveal on focus"
    handler = m.group(0)
    # Pinned by shape, not by pieces, so an inverted skip check or a lost climb cannot hide.
    assert re.search(r"for\s*\(\s*let\s+t\s*=\s*e\.target\s*;\s*t\s*&&\s*\(\s*t\s*=\s*t\.closest\(TARGETS\)\s*\)"
                     r"\s*;\s*t\s*=\s*t\.parentElement\s*\)", handler), "the handler no longer climbs every target"
    assert re.search(r'if\s*\(\s*!\s*t\.closest\(SKIP\)\s*\)\s*\{\s*t\.dataset\.rvItem\s*=\s*"in"\s*;'
                     r"\s*io\.unobserve\(t\)", handler), "the handler must reveal every target not under SKIP"


def test_the_draw_list_is_kept_apart_from_the_reveal_targets():
    """The ruler lives inside the hero, so the reveal fade must never reach it. reveal.js marks it
    with its own attribute, and the start-state rule never names it."""
    draw, targets = _js_list("DRAW"), _js_list("TARGETS")
    assert draw, "reveal.js declares an empty DRAW list"
    assert draw.isdisjoint(targets), f"{draw & targets} would be faded as well as drawn"
    targets_css, _ = _css_rule()
    assert all(d not in targets_css for d in draw), "a drawn element is in the reveal start state"
    src = _text(REVEAL_JS)
    assert re.search(r'matches\(DRAW\)\s*\?\s*"rvDraw"\s*:\s*"rvItem"', src), (
        "reveal.js must mark drawn elements with data-rv-draw, never data-rv-item")


def test_the_draw_start_state_is_gated_like_the_reveal_layer():
    """No JavaScript, a bail or a watchdog means no :root[data-rv], so the finished picture shows.
    That only holds if every rule keyed on the draw mark is gated on the same attribute."""
    loose = [s for r in STORY_RULES if r.kind == "style"
             for s in _selectors(r.prelude) if "data-rv-draw" in s and not s.startswith(":root[data-rv]")]
    assert loose == [], f"draw rules not gated on :root[data-rv]: {loose}"


def test_the_spotlit_parts_are_no_longer_faded_in():
    """The spotlight owns the email's parts now. A fade on the same elements would fight it."""
    assert ".mail__parts > div" not in _js_list("TARGETS")
    assert ".mail" in _js_list("TARGETS"), "the email itself should settle in as one object"


def test_every_arrival_clears_the_start_offset():
    """The start state lifts a target 12px. An arrival whose frames leave out transform keeps
    that offset for good, so a fade-only arrival still has to say transform: none."""
    names = {v.strip() for r in APP_RULES if r.kind == "style" and 'data-rv-item="in"' in r.prelude
             for p, v in _decls(r.body) if p == "animation-name"}
    names |= {m for r in APP_RULES if r.kind == "style" and 'data-rv-item="in"' in r.prelude
              for m in re.findall(r"(?<![\w-])(rv-[\w-]+)",
                                  re.sub(r"var\([^)]*\)", "", _props(r).get("animation", "")))}
    assert {"rv-in", "rv-fade", "rv-settle"} <= names, f"arrivals found: {names}"
    for name in names:
        frames = _frames(_keyframes(APP_RULES, name).body)
        for key in ("0%", "100%"):
            assert "transform" in frames.get(key, {}), f"@keyframes {name} {key} leaves the offset on"


# --- the moments line up with the page they sit on --------------------------------------------

ROW_GO = ":root[data-rv] .arrival__stage[data-rv-draw] .mail-row--new"


def test_the_whole_picture_is_what_starts_the_draw():
    """The thin ruler can be skipped entirely by a restored scroll position or an anchor jump,
    which left the letter and the new row waiting on screen forever. The picture cannot be."""
    assert _js_list("DRAW") == {".arrival__stage"}, "the draw must be triggered by the whole picture"
    for sel in (":root[data-rv] .arrival__stage:not([data-rv-draw]) .ruler::after", ROW_GO,
                ":root[data-rv] .arrival__stage[data-rv-draw] .ruler::after"):
        _find(STORY_RULES, sel)


def test_the_email_row_lands_when_the_ruler_says_it_does():
    ring = _animation(_decls(_find(STORY_RULES, ":root[data-rv] .arrival__stage[data-rv-draw] .ruler li.is-now::after").body))
    row = _animation(_decls(_find(STORY_RULES, ROW_GO).body))
    assert ring and row and ring.delay == row.delay, "the inbox row and the landing ring are out of step"
    paused = _props(_find(STORY_RULES, ":root[data-rv] .arrival__stage:not([data-rv-draw]) .mail-row--new"))
    assert paused.get("animation-play-state") == "paused", "the row must wait for the line"


def test_the_letter_is_opened_after_it_lands_and_never_hidden():
    """The opened letter used to rise in before the inbox row said the email had arrived. It now
    waits for the line and follows the row, and it only moves. The move is declared WITHOUT the
    reveal gate and the gate changes only its delay, so losing the attribute (no JavaScript, a
    bail, the 3s watchdog) can never swap in app.css's fading arrive, and print turns it off."""
    base = _find(STORY_RULES, ".arrival__stage .letter", chain_lacks="print")
    assert _no_preference(base.chain) and any("screen" in c for c in base.chain)
    letter = _animation(_decls(base.body))
    frames = _frames(_keyframes(STORY_RULES, letter.name).body)
    assert all("opacity" not in f for f in frames.values()), "the hero letter must never fade"
    gated = _props(_find(STORY_RULES, ":root[data-rv] .arrival__stage .letter"))
    assert set(gated) == {"animation-delay"}, f"the gate may only move the timing, it sets {sorted(gated)}"
    row = _animation(_decls(_find(STORY_RULES, ROW_GO).body))
    assert _animation(_decls(_find(STORY_RULES, ":root[data-rv] .arrival__stage .letter").body)).delay > row.delay, (
        "the letter opens before the email lands")
    paused = _find(STORY_RULES, ":root[data-rv] .arrival__stage:not([data-rv-draw]) .letter")
    assert _props(paused).get("animation-play-state") == "paused", "the letter must wait for the line"
    printed = _find(STORY_RULES, ".arrival__stage .letter", chain_has="print")
    assert _props(printed).get("animation") == "none", "a printed page must show the letter at rest"


def test_on_a_phone_each_step_lights_as_the_line_arrives_on_any_screen():
    """Each step's timeline is inset to a thin line across the screen, so the timing is in pixels
    of the step itself, not in shares of the screen. A step's line fills over its own height plus
    the list's gap, which is exactly when the next step's top reaches the same line."""
    li = _props(_find(STORY_RULES, ".how .route > li"))
    m = re.fullmatch(r"calc\((\d+)% - 1px\) calc\((\d+)% - 1px\)", li.get("view-timeline-inset", ""))
    assert m and int(m.group(1)) + int(m.group(2)) == 100, "the step timeline must be inset to a 2px line"
    ring = _props(_find(STORY_RULES, ".how .route > li > h3::after", chain_lacks="min-width"))["animation-range"]
    fill = _props(_find(STORY_RULES, ".how .route > li:not(:last-child) > h3::before", chain_lacks="min-width"))["animation-range"]
    r = re.fullmatch(r"cover 0px cover (\d+px)", ring)
    assert r, f"a step should light as its top reaches the line, got {ring!r}"
    assert fill.startswith(f"cover {r.group(1)} "), "the line should start where the ring finishes"
    gap = _props(_find(APP_RULES, ".route"))["gap"]
    assert fill.endswith(f"cover calc(100% + {gap} - 2px)"), f"the fill must end one gap past the step, got {fill!r}"


def test_the_spotlit_card_is_not_a_scroll_container():
    """A view timeline follows the nearest scroll container. overflow hidden, auto or scroll on the
    email card, or on anything between it and the page, would make every part track a box that
    never scrolls, and the spotlight would sit frozen on one part."""
    fix = [r for r in STORY_RULES if r.kind == "style" and ".mail" in _selectors(r.prelude)
           and any(SUPPORTS.search(c) for c in r.chain)]
    assert fix and _props(fix[-1]).get("overflow") == "clip", "story.css must set .mail { overflow: clip }"
    between = (".mail__parts", ".mail__parts > div", ".anatomy__grid", ".anatomy", ".container",
               "main", ".is-home main", "body", "html")
    scrollers = [f"{r.prelude} {{ {p}: {v} }}" for r in APP_RULES + STORY_RULES if r.kind == "style"
                 for s in _selectors(r.prelude) if s in between
                 for p, v in _decls(r.body)
                 if p.startswith("overflow") and re.search(r"\b(hidden|auto|scroll)\b", v)]
    assert scrollers == [], f"a scroll container sits between the parts and the page: {scrollers}"


def test_the_ruler_line_ends_exactly_on_the_second_dot():
    ruler = _props(_find(APP_RULES, ".ruler"))
    assert re.match(r"repeat\(3,", ruler["grid-template-columns"]), "the ruler is no longer three columns"
    track = _props(_find(APP_RULES, ".ruler::before"))
    fill = _props(_find(STORY_RULES, ".ruler::after"))
    assert fill["left"] == track["left"] and fill["top"] == track["top"], "the fill left the track"
    assert fill["width"] == "33.33%", "one column wide, from the first dot's centre to the second's"


@pytest.mark.parametrize("wide", [False, True])
def test_the_route_fill_sits_exactly_on_the_grey_connector(wide):
    if wide:
        conn = _props(_find(APP_RULES, ".route--h > li:not(:last-child)::after", chain_has="min-width: 960px"))
        fill = _props(_find(STORY_RULES, ".how .route > li:not(:last-child) > h3::before", chain_has="min-width: 960px"))
        keys = ("left", "right", "top", "height")
    else:
        conn = _props(_find(APP_RULES, ".route > li:not(:last-child)::after"))
        fill = _props(_find(STORY_RULES, ".how .route > li:not(:last-child) > h3::before", chain_lacks="min-width"))
        keys = ("left", "top", "bottom", "width")
    drift = {k: (conn.get(k), fill.get(k)) for k in keys if conn.get(k) != fill.get(k)}
    assert drift == {}, f"the blue fill no longer covers the connector: {drift}"


def test_forced_colours_drop_every_decoration_the_story_draws():
    """High contrast keeps the page's own shapes. A tint or ring left behind would turn into a
    solid system-colour block."""
    drawn = {s for r in STORY_RULES if r.kind == "style" and "content" in _props(r)
             for s in _selectors(r.prelude)}
    hidden = {s for r in STORY_RULES if r.kind == "style" and any("forced-colors" in c for c in r.chain)
              and _props(r).get("display") == "none" for s in _selectors(r.prelude)}
    assert drawn, "story.css draws nothing, so this test is looking at the wrong file"
    assert drawn - hidden == set(), f"forced colours keep these decorations: {drawn - hidden}"
    # A mask is decoration too, and in high contrast it fades real text towards nothing.
    masked = {s for r in STORY_RULES if r.kind == "style" and not any("forced-colors" in c for c in r.chain)
              and any(p.endswith("mask-image") and v != "none" for p, v in _decls(r.body)) for s in _selectors(r.prelude)}
    unmasked = {s for r in STORY_RULES if r.kind == "style" and any("forced-colors" in c for c in r.chain)
                and _props(r).get("mask-image") == "none" and _props(r).get("-webkit-mask-image") == "none"
                for s in _selectors(r.prelude)}
    assert masked - unmasked == set(), f"forced colours keep these masks: {masked - unmasked}"


# --- contrast, computed from the real glows ---------------------------------------------------

RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d*\.?\d+)\s*\)")


def _tokens() -> dict[str, str]:
    css = _strip_comments(_text(APP_CSS))
    m = re.search(r"@layer tokens\s*\{\s*:root\s*\{(.*?)\}", css, re.S)
    assert m, "app.css has no tokens block"
    return {p: v for p, v in _decls(m.group(1)) if p.startswith("--")}


TOKENS = _tokens()


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    m = re.fullmatch(r"var\((--[\w-]+)\)", value)
    if m:
        value = TOKENS[m.group(1)].strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    assert m, f"cannot resolve the colour {value!r}"
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))


def _worst_surface(selector: str):
    """The section's own ground, read from its rule, with every glow layer stacked on top at its
    peak alpha, which is where text sitting right under the brightest point would be."""
    rules = [r for r in APP_RULES if r.kind == "style" and selector in _selectors(r.prelude)
             and not any("forced-colors" in c or "print" in c for c in r.chain)]
    base, glows = None, {}
    for r in rules:
        for p, v in _decls(r.body):
            if p not in ("background", "background-color", "background-image"):
                continue
            for *rgb, a in RGBA.findall(v):
                key = tuple(int(x) for x in rgb)
                glows[key] = max(glows.get(key, 0.0), float(a))
            if p != "background-image":
                base = _rgb(_selectors(v)[-1])       # the last background layer is the colour
    assert base and glows, f"{selector} declares no ground or no glow"
    surface = base
    for rgb, alpha in glows.items():
        surface = _over(rgb, surface, alpha)
    return surface


@pytest.mark.parametrize("selector, texts", [
    (".gmail", {"body": "var(--navy-100)", "heading": "#FFFFFF", "link": "var(--sky-300)"}),
    (".closing", {"body": "var(--text)", "muted": "var(--text-muted)", "trial note": "var(--navy-900)"}),
    (".site-footer", {"body": "var(--navy-100)", "link": "var(--sky-200)"}),
])
def test_the_glows_behind_three_sections_keep_their_text_at_aa(selector, texts):
    """Computed from the ground and the glows the rules actually declare, so a darker ground or a
    second glow layer is seen as well as a stronger alpha."""
    surface = _worst_surface(selector)
    low = {name: round(_ratio(_rgb(c), surface), 2) for name, c in texts.items()
           if _ratio(_rgb(c), surface) < 4.5}
    assert low == {}, f"{selector} under its glow: {low}"


def _shade_rule():
    hits = [r for r in APP_RULES if r.kind == "style" and "+ .section:not(" in r.prelude]
    assert len(hits) == 1, "expected exactly one section shade rule"
    return hits[0]


def test_the_shade_under_a_white_section_keeps_muted_text_at_aa():
    alpha = max(float(a) for *_, a in RGBA.findall(_shade_rule().body))
    ratio = _ratio(_rgb("var(--text-muted)"), _over(_rgb("var(--navy-900)"), _rgb("var(--ground)"), alpha))
    assert ratio >= 4.5, f"muted text in the shade is {ratio:.2f}:1"


def test_the_shade_never_lands_on_a_section_that_has_its_own_glow():
    """The shade sets background-image at a higher specificity than a section's own class, so on a
    section that paints its own gradient it silently wipes that gradient out. It did, once, to the
    Gmail band. Every homepage section with a gradient ground must be in the :not() list."""
    excluded = re.search(r"\+\s*\.section:not\(([^)]*)\)", _shade_rule().prelude).group(1)
    excluded = {x.strip() for x in excluded.split(",")}
    classes = {c for attr in re.findall(r'<section class="([^"]+)"', _text(HOME_HTML)) for c in attr.split()}
    glowing = {f".{c}" for c in classes
               for r in APP_RULES if r.kind == "style" and f".{c}" in _selectors(r.prelude)
               and not any("forced-colors" in ch for ch in r.chain)
               for p, v in _decls(r.body)
               if p in ("background", "background-image") and "gradient(" in v}
    assert glowing, "no homepage section paints a gradient, so this test is looking at nothing"
    assert glowing <= excluded, f"the shade would wipe out the gradient on {glowing - excluded}"


def test_no_token_is_silently_redefined_by_the_onboarding_motion_layer():
    """motion.css loads after app.css on the signed-in pages and its layer wins, so a token with
    the same name would quietly change there. --ease-settle collided once."""
    motion = set(re.findall(r"(--[\w-]+)\s*:", _strip_comments(_text(MOTION_CSS))))
    assert set(TOKENS) & motion == set(), f"redefined by motion.css: {set(TOKENS) & motion}"


# --- budget -----------------------------------------------------------------------------------

def test_the_story_stays_inside_its_gzip_cap():
    """Same headroom policy as the other caps: an accidental doubling fails, an honest fix does
    not. The homepage-only trio is capped as a whole too, so the budget cannot creep file by file."""
    story = _gz(STORY_CSS)
    assert story <= 3700, f"story.css gzip {story} B"
    trio = _gz(HERO_CSS) + _gz(SCENE_JS) + story
    assert trio <= 11000, f"the homepage-only hero, scene and story together are {trio} B"
