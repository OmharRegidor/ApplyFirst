"""Cheap, pre-AI detector for an employer's embedded application instructions.

Employers bury "to apply, answer these…" traps in posts to filter mass-appliers.
This heuristic flags the likely instruction/question lines so the alert email can
say "make sure you answer these". The real, AI-drafted answers arrive in Milestone 4;
this is just a no-cost head start that also seeds that feature.

It is *section-aware* on purpose: it grabs explicit compliance tricks anywhere, plus
the question/numbered lines inside the application-instructions block — NOT every
bullet in the job's duties/requirements lists (which would crowd out the real asks).
"""

from __future__ import annotations

import re

# Lines that begin the "how to apply" block.
_SECTION_START = re.compile(
    r"\b(to apply\b|how to apply|please (reply|send|answer|include)|answer the following|"
    r"application (instructions|process|questions)|in your (reply|application|message)|"
    r"when (you )?apply)",
    re.IGNORECASE,
)

# Explicit "prove you read this" compliance tricks — captured wherever they appear.
_COMPLIANCE = re.compile(
    r"(start (your|the) (reply|message|application|email|response)|begin your (reply|message)|"
    r"include the (word|phrase|code)|to show (you|that you)[^.]*\bread|use the word|"
    r"type the word|in the subject line|first word)",
    re.IGNORECASE,
)

# A numbered / lettered / bulleted item.
_ITEM = re.compile(r"^(\d+[\.\)]|q\d[\.\):]?|[-*•])\s+\S", re.IGNORECASE)


def detect_screening_hints(description: str, limit: int = 15) -> list[str]:
    """Return likely application-instruction/question lines (deduped, capped)."""
    if not description:
        return []
    lines = [ln.strip() for ln in description.splitlines()]
    hints: list[str] = []

    def add(line: str) -> None:
        if line and len(line) <= 240 and line not in hints:
            hints.append(line)

    # 1) explicit compliance tricks, wherever they appear in the post
    for ln in lines:
        if ln and _COMPLIANCE.search(ln):
            add(ln)

    # 2) the application-instructions block: questions / numbered items after a marker
    in_section = False
    blanks = 0
    for ln in lines:
        if not ln:
            if in_section:
                blanks += 1
                if blanks >= 3:  # a real gap ends the block
                    in_section = False
            continue
        blanks = 0
        if _SECTION_START.search(ln):
            in_section = True
            add(ln)
        elif in_section:
            if _ITEM.match(ln) or ln.endswith("?"):
                add(ln)
            elif len(ln) > 160:  # a long prose paragraph ⇒ block has ended
                in_section = False

    return hints[:limit]
