"""The legal pages are restyled only: every sentence from the baseline (7159bde) survives.

The fixtures hold the text of each block (paragraph, list item, heading) of the baseline
privacy.html and terms.html, tags stripped and whitespace collapsed. Additions are allowed
(the "On this page" nav, h2 ids, the visually hidden "(opens in a new tab)"); rewording is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _saas_client import client_for, page_text

FIXTURES = Path(__file__).parent / "fixtures"


def _golden(name: str) -> list[str]:
    lines = (FIXTURES / f"legal_{name}.txt").read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.strip()]


@pytest.mark.parametrize("name,path,minimum", [("privacy", "/privacy", 25),
                                               ("terms", "/terms", 15)])
def test_every_baseline_legal_sentence_is_still_rendered(saas_cfg, name, path, minimum):
    golden = _golden(name)
    assert len(golden) >= minimum                       # the fixture itself is intact
    r = client_for(saas_cfg).get(path)
    assert r.status_code == 200
    text = re.sub(r"\s*\(opens in a new tab\)", "", page_text(r.text))
    missing = [line for line in golden if line not in text]
    assert missing == []


def test_legal_fixtures_hold_the_verification_critical_sentences():
    privacy = "\n".join(_golden("privacy"))
    for must in ("We never read, download, list, modify, or delete any of your existing emails.",
                 "Google API Services User Data Policy", "Limited Use", "gmail.send",
                 "We do not sell your data"):
        assert must in privacy
    assert "Terms of Service" in _golden("terms")[0]
