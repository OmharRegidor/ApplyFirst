"""Rebuild the Inter subset the sign-up journey serves, and its licence file.

Run by hand, only when Inter is upgraded. Nothing runs this on deploy.

    .venv/Scripts/python.exe -m pip install brotli          # dev only, WOFF2 needs it
    .venv/Scripts/python.exe tools/fonts/build_inter.py     # downloads the pinned source

Offline, with copies of the two pinned files:

    .venv/Scripts/python.exe tools/fonts/build_inter.py --src Inter.ttf --licence OFL.txt

The source is the variable Inter from google/fonts (axes opsz 14-32, wght 100-900), pinned to
one commit and one sha256, so a moved or edited upstream file fails loudly instead of quietly
changing what we serve. The script:

1. pins opsz at 14 (the text optical size) and limits wght to 400-600 with the instancer,
2. keeps Basic Latin, Latin-1 Supplement, General Punctuation and U+20B1 (the peso sign),
3. keeps the default-on shaping features plus tnum (tabular figures for counts and times),
4. writes WOFF2 named after the version in the font's own name table (Inter writes 4.1 as
   "4.001"), and licenses/OFL-inter.txt with the upstream licence under a note of what changed,
5. prints the descriptors journey.css must give "Inter Agad Fallback" for this Inter.

The output is byte-for-byte reproducible for a given fontTools and brotli (4.63.0 and 1.2.0
built the committed file): head.modified is carried over from the source, not stamped with today.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

COMMIT = "e1d6480102fed30739fead0faee463101f892c8f"
BASE_URL = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/inter/"
SOURCE_URL = BASE_URL + "Inter%5Bopsz%2Cwght%5D.ttf"
SOURCE_SHA256 = "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031"
LICENCE_URL = BASE_URL + "OFL.txt"
LICENCE_SHA256 = "5b9321a4298cfeb6b34354164a1c3afc3db114569984c502b9b35d988fd58c57"

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "applyfirst" / "saas" / "static"

OPSZ = 14
WGHT = (400, 600)
# The @font-face unicode-range in journey.css is built from these same ranges.
UNICODE_RANGES = ((0x0020, 0x007E), (0x00A0, 0x00FF), (0x2000, 0x206F), (0x20B1, 0x20B1))
FEATURES = ["ccmp", "locl", "mark", "mkmk", "kern", "calt", "liga", "clig", "rvrn", "tnum"]
MAX_BYTES = 50_000

# Average-width method for the fallback face (Capsize's xWidthAvg weighting): the
# advance of each of a-z and the space, weighted by English letter frequency with the space at
# 18.18 per cent, in em. Measured with fontTools from C:/Windows/Fonts/segoeui.ttf (Segoe UI
# 5.62) and google/fonts ofl/roboto/Roboto[wdth,wght].ttf (3.015) at its default instance.
FREQ = {
    " ": 22.22, "a": 8.2, "b": 1.5, "c": 2.8, "d": 4.3, "e": 12.7, "f": 2.2, "g": 2.0, "h": 6.1,
    "i": 7.0, "j": 0.15, "k": 0.77, "l": 4.0, "m": 2.4, "n": 6.7, "o": 7.5, "p": 1.9, "q": 0.095,
    "r": 6.0, "s": 6.3, "t": 9.1, "u": 2.8, "v": 0.98, "w": 2.4, "x": 0.15, "y": 2.0, "z": 0.074,
}
FALLBACK_AVG_EM = {"Segoe UI": 0.44251, "Roboto": 0.44247}

LICENCE_NOTE = """\
Inter {version}, served by Agad as applyfirst/saas/static/fonts/{name}.
Source: google/fonts ofl/inter/Inter[opsz,wght].ttf at commit {commit}.
Modified by Agad with tools/fonts/build_inter.py: optical size pinned at 14, weight limited to
400-600, characters limited to Basic Latin, Latin-1 Supplement, General Punctuation and U+20B1.
No glyph was redrawn. The licence below covers the modified font unchanged.

"""


def unicodes() -> list[int]:
    return [cp for lo, hi in UNICODE_RANGES for cp in range(lo, hi + 1)]


def unicode_range_css() -> str:
    return ",".join(f"U+{lo:04X}" if lo == hi else f"U+{lo:04X}-{hi:04X}"
                    for lo, hi in UNICODE_RANGES)


def version_of(font: TTFont) -> str:
    """'Version 4.001;git-66647c0bb' -> '4.1'. Inter writes the minor version as three digits."""
    raw = font["name"].getDebugName(5) or ""
    m = re.search(r"(\d+)\.(\d{3})", raw)
    if not m:
        raise ValueError(f"no version in name ID 5: {raw!r}")
    return f"{int(m.group(1))}.{int(m.group(2))}"


def font_name(version: str) -> str:
    return f"inter-{version}-latin-wght.woff2"


def avg_em(font: TTFont) -> float:
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    total = sum(FREQ.values())
    return sum(hmtx[cmap[ord(c)]][0] * w for c, w in FREQ.items()) / total / font["head"].unitsPerEm


def _pct(x: float) -> str:
    return f"{round(x * 10000) / 100:.2f}".rstrip("0").rstrip(".") + "%"


def fallback_descriptors(font: TTFont) -> dict[str, str]:
    """What "Inter Agad Fallback" needs so Segoe UI or Roboto takes Inter's width and line box.

    size-adjust scales the local font so its average width matches Inter's. The overrides are
    then Inter's own ascent, descent and line gap divided by that scale, because browsers apply
    size-adjust to the overrides too. The ascent gets 1/1024 em more than Inter's: Chrome rounds
    ascent to whole pixels, Inter's is exactly 15.5px at 16px (1984/2048 = 31/32 em), and
    Chrome's scaled size lands a hair short, so an exact copy rounds to 15 and drops the
    fallback's baseline a pixel at the phone body size. Measured in Chrome 153: 90.52 and
    90.53 per cent round down at 16px, 90.55 to 90.6 round up like Inter, 91 overshoots at 17px.
    """
    upm, hhea = font["head"].unitsPerEm, font["hhea"]
    fallback = sum(FALLBACK_AVG_EM.values()) / len(FALLBACK_AVG_EM)
    size = round(avg_em(font) / fallback * 10000) / 10000
    return {
        "size-adjust": _pct(size),
        "ascent-override": _pct((hhea.ascent / upm + 1 / 1024) / size),
        "descent-override": _pct(-hhea.descent / upm / size),
        "line-gap-override": _pct(hhea.lineGap / upm / size),
    }


def build(src: bytes) -> TTFont:
    digest = hashlib.sha256(src).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"source sha256 {digest} is not the pinned {SOURCE_SHA256}")
    font = TTFont(io.BytesIO(src), recalcTimestamp=False)
    font = instancer.instantiateVariableFont(font, {"opsz": OPSZ, "wght": WGHT})
    buf = io.BytesIO()              # compile and reload: the instancer leaves glyphs that have
    font.save(buf)                  # no deltas out of gvar, and the subsetter needs every one
    font = TTFont(io.BytesIO(buf.getvalue()), recalcTimestamp=False)
    opts = subset.Options()
    opts.layout_features = FEATURES
    opts.name_IDs = ["*"]           # keep the copyright, licence, version and axis names
    opts.name_languages = [0x0409]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes())
    sub.subset(font)
    font.flavor = "woff2"
    font.recalcTimestamp = False
    return font


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild the Inter subset and its licence.")
    ap.add_argument("--src", type=Path, help="a local copy of the pinned source TTF")
    ap.add_argument("--licence", type=Path, help="a local copy of the pinned OFL.txt")
    ap.add_argument("--static", type=Path, default=STATIC, help="the static folder to write into")
    a = ap.parse_args()

    font = build(a.src.read_bytes() if a.src else fetch(SOURCE_URL))
    version = version_of(font)
    out = a.static / "fonts" / font_name(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(out)

    licence = a.licence.read_bytes() if a.licence else fetch(LICENCE_URL)
    if hashlib.sha256(licence).hexdigest() != LICENCE_SHA256:
        sys.exit("OFL.txt is not the pinned licence file")
    note = LICENCE_NOTE.format(version=version, name=out.name, commit=COMMIT)
    lic = a.static / "licenses" / "OFL-inter.txt"
    lic.parent.mkdir(parents=True, exist_ok=True)
    lic.write_bytes(note.encode("ascii") + licence.replace(b"\r\n", b"\n"))

    size = out.stat().st_size
    print(f"{out.name}: {size} bytes, sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")
    print(f"source {SOURCE_URL}\nsource sha256 {SOURCE_SHA256}")
    print(f"unicode-range:{unicode_range_css()}")
    print("fallback:" + ";".join(f"{k}:{v}" for k, v in fallback_descriptors(font).items()))
    if size > MAX_BYTES:
        sys.exit(f"{out.name} is {size} bytes, over the {MAX_BYTES} cap")


if __name__ == "__main__":
    main()
