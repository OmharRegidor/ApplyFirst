"""Owner rule, enforced forever: no purple, violet or indigo anywhere a colour is written.

Scans every stylesheet under static/ (the trimmed Basecoat file in static/vendor included), every
SaaS template, every static JavaScript file (the vendored canvas-confetti included, now that its
default colours are the brand blues) and the delivered email module for every #rgb / #rgba /
#rrggbb / #rrggbbaa, rgb(), rgba() and oklch() value, and fails on a hue from 230 to 345 with
saturation of 8% or more (spec 14.4, M-7). An oklch() colour is converted to sRGB and judged by
that same test, never by its own hue, because the brand blues sit at OKLCH hue 236 to 255.
color-mix() is allowed in exactly three forms that cannot bring in a new hue (sign-up redesign
spec 7). Colour words that name a purple, and every other colour function, are banned as CSS
values, and in JavaScript as whole string literals. The Google G PNG is binary and never scanned.
"""

from __future__ import annotations

import colorsys
import math
import re
from pathlib import Path

import pytest

from applyfirst.notify import compose
from applyfirst.saas import static_assets

SAAS = Path(static_assets.__file__).parent
CSS_FILES = sorted((SAAS / "static").rglob("*.css"))          # own CSS and the vendored Basecoat
TEMPLATE_FILES = sorted((SAAS / "templates").glob("*.html"))
JS_FILES = sorted((SAAS / "static").rglob("*.js"))          # own JS and the vendored burst (M-7)
SCANNED = CSS_FILES + TEMPLATE_FILES + JS_FILES + [Path(compose.__file__)]

# "&#8594;" is an HTML entity, not a colour, hence the (?<![&\w]) guard.
_HEX = re.compile(r"(?<![&\w])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})"
                  r"(?![0-9a-zA-Z_-])")
_RGB = re.compile(r"\brgba?\(\s*(\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(\d{1,3}(?:\.\d+)?)\s*[,\s]\s*"
                  r"(\d{1,3}(?:\.\d+)?)")
_OKLCH = re.compile(r"(?<![\w-])oklch\(([^()]*)\)", re.I)
BANNED_WORDS = ("purple", "violet", "indigo", "lavender", "lilac", "magenta", "fuchsia",
                "orchid", "plum", "blueviolet", "rebeccapurple", "slateblue")
_UNREADABLE_FN = re.compile(r"(?<![\w-])(hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(", re.I)
# A whole JS string literal that is one bare word, optionally with a bracket: "purple",
# "hsl(280 60% 50%)", "hsl(". Anything with a space or a colon in it is not a colour value.
_JS_VALUE = re.compile(r"""(['"`])\s*([A-Za-z][\w-]*(?:\([^'"`\n]*\)?)?)\s*\1""")

# The three color-mix() forms a stylesheet may use (sign-up redesign spec 7).
# 1. A variable or currentcolor faded towards transparent: it keeps the hue it already had, and
#    the variable's own value is scanned wherever it is defined.
_MIX_FADE = re.compile(r"\s*in\s+[a-z-]+\s*,\s*(?:var\(\s*--[\w-]+\s*\)|currentcolor)\s+"
                       r"\d+(?:\.\d+)?%\s*,\s*transparent\s*", re.I)
# 2. Tailwind's feature test, only as the whole condition of an @supports rule.
_MIX_PROBE = re.compile(r"@supports\s*\(\s*color\s*:\s*color-mix\(\s*in\s+lab\s*,\s*red\s*,"
                        r"\s*red\s*\)\s*\)", re.I)
# 3. Two variables, each defined in the same file, and only ever as a grey (zero chroma).
_MIX_TWO_VARS = re.compile(r"\s*in\s+[a-z-]+\s*,\s*var\(\s*(--[\w-]+)\s*\)(?:\s+\d+(?:\.\d+)?%)?"
                           r"\s*,\s*var\(\s*(--[\w-]+)\s*\)(?:\s+\d+(?:\.\d+)?%)?\s*", re.I)


def _hue_sat(r: float, g: float, b: float) -> tuple[float, float]:
    h, _l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h * 360, s


def _hex_rgb(digits: str) -> tuple[int, int, int]:
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits[:3])
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _oklch_parts(args: str) -> tuple[float, float, float] | None:
    """Lightness (0 to 1), chroma and hue of oklch() arguments, or None if they are not plain
    numbers (relative colour syntax, var(), 'none')."""
    parts = args.split("/")[0].split()
    if len(parts) != 3:
        return None
    try:
        lightness = float(parts[0][:-1]) / 100 if parts[0].endswith("%") else float(parts[0])
        chroma = float(parts[1][:-1]) * 0.004 if parts[1].endswith("%") else float(parts[1])
        hue = float(parts[2].lower().removesuffix("deg"))
    except ValueError:
        return None
    return lightness, chroma, hue


def _oklch_rgb(args: str) -> tuple[float, float, float] | None:
    """The sRGB colour (0 to 255 per channel, clipped to the gamut) of oklch() arguments."""
    parts = _oklch_parts(args)
    if parts is None:
        return None
    lightness, chroma, hue = parts
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
              -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
              -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)

    def encode(x: float) -> float:
        x = min(max(x, 0.0), 1.0)
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return tuple(encode(x) * 255 for x in linear)


def _colours(text: str):
    for m in _HEX.finditer(text):
        yield m.group(0), _hex_rgb(m.group(1))
    for m in _RGB.finditer(text):
        yield m.group(0), tuple(float(v) for v in m.groups())
    for m in _OKLCH.finditer(text):
        rgb = _oklch_rgb(m.group(1))
        if rgb is not None:                     # unparseable oklch() fails as unreadable instead
            yield m.group(0), rgb


def _is_purple(rgb) -> bool:
    hue, sat = _hue_sat(*rgb)
    return 230 <= hue <= 345 and sat >= 0.08


def _is_grey(value: str) -> bool:
    """True when a custom property's value is a colour with zero chroma."""
    value = value.strip()
    m = _OKLCH.fullmatch(value)
    if m:
        parts = _oklch_parts(m.group(1))
        return parts is not None and parts[1] == 0
    m = _HEX.fullmatch(value)
    if m:
        r, g, b = _hex_rgb(m.group(1))
        return r == g == b
    m = _RGB.match(value)
    return bool(m) and len(set(float(v) for v in m.groups())) == 1


def _arguments(text: str, start: int) -> str:
    """The text from start up to the ')' that closes the '(' just before start."""
    depth, i = 1, start
    while depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1]


def _mix_of_greys(css: str, args: str) -> bool:
    m = _MIX_TWO_VARS.fullmatch(args)
    if not m:
        return False
    for name in m.groups():
        values = re.findall(rf"(?<![\w-]){re.escape(name)}\s*:\s*([^;{{}}]+)", css)
        if not values or not all(_is_grey(v) for v in values):
            return False
    return True


def _unreadable(css: str) -> list[str]:
    """Colour functions in a stylesheet (comments removed) that the guard cannot judge."""
    css = _MIX_PROBE.sub("@supports (probe)", css)                       # form 2
    bad = []
    for m in _UNREADABLE_FN.finditer(css):
        name, args = m.group(1).lower(), _arguments(css, m.end())
        if name == "oklch" and _oklch_rgb(args) is not None:
            continue                                  # judged in sRGB by the hue test instead
        if name == "color-mix" and (_MIX_FADE.fullmatch(args) or _mix_of_greys(css, args)):
            continue                                  # forms 1 and 3
        bad.append(f"{name}({args})")
    return sorted(set(bad))


def _css_problems(text: str) -> list[str]:
    """Everything the guard rejects in one stylesheet: a purple hue, a purple word, a colour
    function it cannot read. The planted-purple tests below run through this."""
    css = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    purple = sorted({raw for raw, rgb in _colours(css) if _is_purple(rgb)})
    words = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.I)
    named = sorted({m.group(1).lower() for v in re.findall(r"[\w-]+\s*:\s*([^;{}]+)", css)
                    for m in words.finditer(v)})
    return purple + named + _unreadable(css)


def _js_values(text: str) -> list[str]:
    """Every string literal in a .js file that is a colour on its own.

    A colour written in JavaScript is always the whole literal: "rebeccapurple",
    "hsl(280 60% 50%)", or the open "hsl(" of a concatenation. Requiring the literal to be
    exactly one word, optionally with a bracket, is what keeps prose out, so the word "plum"
    in a comment or in a sentence is never mistaken for a colour value.
    """
    return [m.group(2) for m in _JS_VALUE.finditer(text)]


def _css_values(path: Path, text: str) -> list[str]:
    """The value side of every declaration a file can carry."""
    if path.suffix == ".js":
        return _js_values(text)
    if path.suffix == ".css":
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.findall(r"[\w-]+\s*:\s*([^;{}]+)", text)
    values = re.findall(r"""\bstyle\s*=\s*(["'])(.*?)\1""", text, flags=re.S)
    values = [v for _, v in values]
    values += re.findall(r"<style\b[^>]*>(.*?)</style>", text, flags=re.S | re.I)
    values += [v for _, v in re.findall(r"""\b(?:color|fill|stroke|bgcolor|stop-color)\s*=\s*
                                            (["'])(.*?)\1""", text, flags=re.X)]
    return values


def test_there_is_something_to_scan():
    assert CSS_FILES, "static/css/app.css must exist"
    assert [p.name for p in CSS_FILES if p.parent.name == "vendor"], "vendored CSS is scanned"
    assert len(TEMPLATE_FILES) >= 10
    assert len(JS_FILES) >= 3, "static/js/*.js and the vendored burst library must be scanned"
    assert [p.name for p in JS_FILES if p.parent.name == "vendor"], "the vendor file is scanned"


def test_the_guard_catches_purple_and_passes_the_brand_colours():
    assert _is_purple(_hex_rgb("7c3aed")) and _is_purple(_hex_rgb("6366f1"))   # violet, indigo
    assert _is_purple((128, 0, 128))
    for brand in ("0B2545", "0B6BC7", "EEF7FD", "DCEFFB", "F3F6FA", "2563eb", "111827"):
        assert not _is_purple(_hex_rgb(brand))
    assert not _is_purple((11, 37, 69))
    assert list(_colours("&#8594; &#9733;")) == []                 # entities are not colours


# --- T37 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_no_colour_in_the_banned_hue_band(path):
    text = path.read_text(encoding="utf-8")
    bad = sorted({raw for raw, rgb in _colours(text) if _is_purple(rgb)})
    assert bad == [], f"{path.name}: hue 230-345 colours {bad}"


# --- T38 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_no_purple_colour_words_as_css_values(path):
    text = path.read_text(encoding="utf-8")
    words = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.I)
    bad = sorted({m.group(1).lower() for v in _css_values(path, text) for m in words.finditer(v)})
    assert bad == [], f"{path.name}: banned colour words {bad}"


@pytest.mark.parametrize("path", CSS_FILES, ids=lambda p: p.name)
def test_stylesheet_uses_only_colours_the_guard_can_read(path):
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    found = _unreadable(text)
    assert found == [], (f"{path.name}: use hex, rgb()/rgba(), a numeric oklch() or one of the "
                         f"three color-mix() forms instead of {found}")


# --- sign-up redesign spec 7: oklch() and color-mix() ---------------------------------------

# #0B6BC7, #38AEEA and #0B2545 written as oklch(). Their OKLCH hues (254, 236, 255) sit inside
# 230-345, which is why the guard converts to sRGB (hues 209, 200, 213) instead of reading them.
BRAND_OKLCH = ("oklch(53.0% 0.164 254.0)", "oklch(71.2% 0.134 235.8)", "oklch(26.4% 0.068 255.3)")
PURPLE_OKLCH = "oklch(54.1% 0.247 293.0)"                       # #7c3aed


def test_oklch_is_judged_in_srgb_not_by_its_own_hue():
    for colour in BRAND_OKLCH:
        (raw, rgb), = _colours(colour)
        assert 230 <= _oklch_parts(colour[6:-1])[2] <= 345, "the OKLCH hue alone would fail"
        assert not _is_purple(rgb), f"{raw} is a brand blue"
        assert _css_problems(f"a{{color:{colour}}}") == []
    for grey in ("oklch(97% 0 0)", "oklch(14.5% 0 0)", "oklch(100% 0 0/.1)"):
        assert _css_problems(f"a{{color:{grey}}}") == [], grey
    assert _css_problems(f"a{{color:{PURPLE_OKLCH}}}") == [PURPLE_OKLCH]
    assert _css_problems("a{color:oklch(from var(--x) l c h)}") != [], "unreadable oklch() fails"


def test_color_mix_is_allowed_in_exactly_three_forms():
    fade = ("a{box-shadow:0 0 0 3px color-mix(in oklab, var(--color-ring) 50%, transparent);"
            "border-color:color-mix(in oklab, currentcolor 20%, transparent)}")
    probe = "@supports (color:color-mix(in lab, red, red)){a{color:red}}"
    greys = (":root{--g1:oklch(97% 0 0);--g2:#252525}"
             "a{background:color-mix(in oklch,var(--g1),var(--g2) 5%)}")
    for css in (fade, probe, greys):
        assert _css_problems(css) == [], css


@pytest.mark.parametrize("css", [
    # form 1 with a colour where the variable belongs, or a purple behind the variable
    "a{color:color-mix(in oklab, #7c3aed 50%, transparent)}",
    "a{color:color-mix(in oklab, rebeccapurple 50%, transparent)}",
    f"a{{color:color-mix(in oklab, {PURPLE_OKLCH} 50%, transparent)}}",
    ":root{--x:#7c3aed}a{color:color-mix(in oklab, var(--x) 50%, transparent)}",
    # form 2 with a purple probe, or the probe used as a colour outside @supports
    "@supports (color:color-mix(in lab, purple, purple)){a{color:red}}",
    "@supports (color:color-mix(in lab, #7c3aed, #7c3aed)){a{color:red}}",
    "a{color:color-mix(in lab, red, red)}",
    # form 3 with a chromatic purple variable, or variables this file never defines
    f":root{{--a:{PURPLE_OKLCH};--b:oklch(20% 0 0)}}"
    "a{color:color-mix(in oklch,var(--a),var(--b) 5%)}",
    ":root{--a:#7c3aed;--b:#111111}a{color:color-mix(in oklch,var(--a),var(--b) 5%)}",
    "a{color:color-mix(in oklch,var(--a),var(--b) 5%)}",
    # anything else still fails
    "a{color:color-mix(in srgb, #0B6BC7, #7c3aed)}",
    "a{color:hsl(280 60% 50%)}",
])
def test_a_planted_purple_fails_in_every_colour_form(css):
    assert _css_problems(css) != [], css


# --- M-7 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_javascript_uses_only_colours_the_guard_can_read(path):
    values = _js_values(path.read_text(encoding="utf-8"))
    found = sorted({m.group(0).lower() for v in values for m in _UNREADABLE_FN.finditer(v)})
    assert found == [], f"{path.name}: use hex or rgb()/rgba() instead of {found}"


def test_the_javascript_scan_reads_colour_values_and_not_prose():
    assert "rebeccapurple" in _js_values('el.style.color = "rebeccapurple";')
    assert "hsl(280 60% 50%)" in _js_values("const c = `hsl(280 60% 50%)`;")
    assert "hsl(" in _js_values("const c = 'hsl(' + h + ', 60%, 50%)';")   # concatenated
    prose = '// a plum-coloured note, do not use violet\nconst k = "af:gmail", t = "use strict";'
    assert not [v for v in _js_values(prose) if v in BANNED_WORDS]
    assert [raw for raw, rgb in _colours('const c = "#a25afd";') if _is_purple(rgb)] == ["#a25afd"]
