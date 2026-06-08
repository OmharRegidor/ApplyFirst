"""Parser tests against saved live fixtures (no network)."""

from __future__ import annotations

from pathlib import Path

from applyfirst.models import RawJob
from applyfirst.sources.onlinejobsph import parse_detail, parse_search

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8-sig")


def test_parse_search_finds_unique_jobs():
    jobs = parse_search(_read("search_sample.html"))
    assert len(jobs) >= 25  # ~30 per page
    ids = [j.external_id for j in jobs]
    assert len(ids) == len(set(ids)), "job ids must be unique"
    for j in jobs:
        assert j.external_id.isdigit()
        assert j.url.startswith("https://www.onlinejobs.ph/jobseekers/job/")
        assert j.title  # never empty


def test_parse_search_extracts_fields():
    jobs = parse_search(_read("search_sample.html"))
    assert any(j.posted_at is not None for j in jobs), "should parse post timestamps"
    assert any(j.salary_text for j in jobs), "should parse salary"
    assert any(j.employment_type for j in jobs), "should parse employment type"
    # title should not still contain the employment-type badge text
    for j in jobs:
        if j.employment_type:
            assert j.employment_type not in j.title


def test_parse_detail_has_description_and_screening_question():
    raw = RawJob(
        source="onlinejobs.ph",
        external_id="1663915",
        url="https://www.onlinejobs.ph/jobseekers/job/x-1663915",
        title="x",
    )
    detail = parse_detail(_read("detail_sample.html"), raw)
    assert "ABOUT THE ROLE" in detail.description
    # the buried screening question — the killer-feature signal
    assert "favorite hobby" in detail.description.lower()
    # <ojfilter> word-wrapping should be flattened back into normal text
    assert "emails" in detail.description.lower()
