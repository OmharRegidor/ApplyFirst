"""Tests for the heuristic screening-question detector."""

from __future__ import annotations

from pathlib import Path

from applyfirst.models import RawJob
from applyfirst.screening import detect_screening_hints
from applyfirst.sources.onlinejobsph import parse_detail

FIXTURES = Path(__file__).parent / "fixtures"


def test_detects_real_apply_instructions():
    raw = RawJob(source="onlinejobs.ph", external_id="1663915",
                 url="https://www.onlinejobs.ph/jobseekers/job/x-1663915", title="x")
    detail = parse_detail((FIXTURES / "detail_sample.html").read_text(encoding="utf-8-sig"), raw)
    hints = detect_screening_hints(detail.description)

    joined = " ".join(hints).lower()
    assert "favorite hobby" in joined            # the buried screening question
    assert any("reply" in h.lower() or "apply" in h.lower() for h in hints)
    assert len(hints) >= 2


def test_no_false_positives_on_plain_text():
    assert detect_screening_hints("") == []
    assert detect_screening_hints("We are a small team building great software.") == []
