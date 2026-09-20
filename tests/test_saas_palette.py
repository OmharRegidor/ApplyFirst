"""Owner rule, enforced forever: no purple, violet or indigo anywhere a colour is written.

Scans the stylesheet(s), every SaaS template and the delivered email module for every
#rgb / #rgba / #rrggbb / #rrggbbaa, rgb() and rgba() value, and fails on a hue from 230 to 345
with saturation of 8% or more (spec 14.4). Colour words that name a purple, and colour
functions this scanner cannot read, are banned as CSS values. The Google G PNG is binary and
never scanned.
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

import pytest

from applyfirst.notify import compose
from applyfirst.saas import static_assets

SAAS = Path(static_assets.__file__).parent
CSS_FILES = sorted((SAAS / "static" / "css").glob("*.css"))
TEMPLATE_FILES = sorted((SAAS / "templates").glob("*.html"))
SCANNED = CSS_FILES + TEMPLATE_FILES + [Path(compose.__file__)]

# "&#8594;" is an HTML entity, not a colour, hence the (?<![&\w]) guard.
_HEX = re.compile(r"(?<![&\w])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})"
                  r"(?![0-9a-zA-Z_-])")
_RGB = re.compile(r"\brgba?\(\s*(\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(\d{1,3}(?:\.\d+)?)\s*[,\s]\s*"
                  r"(\d{1,3}(?:\.\d+)?)")
BANNED_WORDS = ("purple", "violet", "indigo", "lavender", "lilac", "magenta", "fuchsia",
                "orchid", "plum", "blueviolet", "rebeccapurple", "slateblue")
_UNREADABLE_FN = re.compile(r"(?<![\w-])(hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(", re.I)


def _hue_sat(r: float, g: float, b: float) -> tuple[float, float]:
    h, _l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h * 360, s


def _hex_rgb(digits: str) -> tuple[int, int, int]:
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits[:3])
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _colours(text: str):
    for m in _HEX.finditer(text):
        yield m.group(0), _hex_rgb(m.group(1))
    for m in _RGB.finditer(text):
        yield m.group(0), tuple(float(v) for v in m.groups())


def _is_purple(rgb) -> bool:
    hue, sat = _hue_sat(*rgb)
    return 230 <= hue <= 345 and sat >= 0.08


def _css_values(path: Path, text: str) -> list[str]:
    """The value side of every declaration a file can carry."""
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
    assert len(TEMPLATE_FILES) >= 10


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
    found = sorted({m.group(0).lower() for m in _UNREADABLE_FN.finditer(text)})
    assert found == [], f"{path.name}: use hex or rgb()/rgba() instead of {found}"
