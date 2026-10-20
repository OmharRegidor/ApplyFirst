"""Plain-words cleanup run on every AI-written package.

The prompt already asks for simple everyday words, but the model still copies stiff
words straight from the job post ("scalable", "leverage"). This swaps the common ones
for plain words after the AI writes, so a busy owner gets the point in a few seconds.
Only the digest, the drafted answers and the cover letter are touched; the subject
line keeps its "<positioning> – <name>" separator.
"""

from __future__ import annotations

import re

from applyfirst.tailor.contract import TailoredPackage

# (pattern, replacement). Order matters: phrases before their single words.
_SWAPS: list[tuple[str, str]] = [
    (r"\bis seeking\b", "wants"),
    (r"\bare seeking\b", "want"),
    (r"\bseeking\b", "looking for"),
    (r",\s*scalable\b", ""),
    (r"\bscalable\s+", ""),
    (r"\bscalable\b", "able to grow"),
    (r"\bleveraging\b", "using"),
    (r"\bleverages\b", "uses"),
    (r"\bleveraged\b", "used"),
    (r"\bleverage\b", "use"),
    (r"\butilizing\b", "using"),
    (r"\butilizes\b", "uses"),
    (r"\butilized\b", "used"),
    (r"\butilize\b", "use"),
    (r"\bproficient (in|with)\b", r"good \1"),
    (r"\bproficiency (in|with)\b", r"skill \1"),
    (r"\bproficiency\b", "skill"),
    (r"\bproficient\b", "skilled"),
    (r"\bcutting-edge\b", "modern"),
    (r"\brobust\b", "solid"),
    (r"\bseamlessly\b", "smoothly"),
    (r"\bseamless\b", "smooth"),
    (r"\bstreamlining\b", "simplifying"),
    (r"\bstreamlines\b", "simplifies"),
    (r"\bstreamlined\b", "simpler"),
    (r"\bstreamline\b", "simplify"),
    (r"\bfacilitates\b", "helps with"),
    (r"\bfacilitate\b", "help with"),
    (r"\benhancing\b", "improving"),
    (r"\benhances\b", "improves"),
    (r"\benhanced\b", "improved"),
    (r"\benhance\b", "improve"),
    (r"\boptimizing\b", "improving"),
    (r"\boptimizes\b", "improves"),
    (r"\boptimized\b", "improved"),
    (r"\boptimization\b", "speed-up"),
    (r"\boptimize\b", "improve"),
    (r"\baccelerating\b", "speeding up"),
    (r"\baccelerates\b", "speeds up"),
    (r"\baccelerate\b", "speed up"),
    (r"\bensuring\b", "making sure"),
    (r"\bensures\b", "makes sure"),
    (r"\bensure\b", "make sure"),
    (r"\bstakeholders\b", "the team"),
    (r"\bsynergy\b", "teamwork"),
    (r"\s+[—–]\s+", ", "),  # a dash between words in a sentence
    (r"—", ", "),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _SWAPS]
_URL = re.compile(r"\S+\.\S+/\S*|https?://\S+")


def _keep_case(match: re.Match, repl: str) -> str:
    out = match.expand(repl)
    first = match.group(0)[:1]
    return out[:1].upper() + out[1:] if first.isupper() and out else out


def plain_words(text: str) -> str:
    """Swap stiff words for plain ones. Links are left exactly as written."""
    if not text:
        return text
    parts = _URL.split(text)
    links = _URL.findall(text)
    for i, part in enumerate(parts):
        for pattern, repl in _COMPILED:
            part = pattern.sub(lambda m, r=repl: _keep_case(m, r), part)
        parts[i] = part
    out = parts[0]
    for link, part in zip(links, parts[1:]):
        out += link + part
    return out


def _plain_letter(letter: str, token: str | None) -> str:
    """The post's required opening word or phrase must stay exactly as the employer wrote it."""
    if token and letter.startswith(token):
        return token + plain_words(letter[len(token):])
    return plain_words(letter)


def plain_package(package: TailoredPackage) -> TailoredPackage:
    return package.model_copy(update={
        "digest": plain_words(package.digest),
        "cover_letter": _plain_letter(package.cover_letter, package.compliance_token),
        "screening_questions": [
            qa.model_copy(update={"drafted_answer": plain_words(qa.drafted_answer)})
            for qa in package.screening_questions
        ],
    })
