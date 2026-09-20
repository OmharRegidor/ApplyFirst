"""check_every_min / apps_per_day reach every render from the serving app's own config, never
collide with a route's context, and "Back to dashboard" follows the activated flag."""

from __future__ import annotations

import dataclasses

import jinja2
import pytest
from fastapi import Request

from applyfirst.notify.compose import build_job_email, build_tailored_email
from applyfirst.saas import app as app_module
from applyfirst.saas.app import create_app
from applyfirst.tailor.contract import TailoredPackage
from _saas_client import client_for, clean, elements, page_text, seed_user

PROCESSOR_KEYS = {"check_every_min", "apps_per_day"}


def _record_renders(monkeypatch) -> list[tuple[str, dict]]:
    """Every TemplateResponse from here on, as (template name, route context before rendering)."""
    seen: list[tuple[str, dict]] = []
    original = app_module._TEMPLATES.TemplateResponse

    def recording(request, name, context=None, *args, **kwargs):
        seen.append((name, dict(context or {})))
        return original(request, name, context, *args, **kwargs)

    monkeypatch.setattr(app_module._TEMPLATES, "TemplateResponse", recording)
    return seen


def _probe_client(cfg, monkeypatch):
    env = app_module._TEMPLATES.env
    monkeypatch.setattr(env, "loader", jinja2.ChoiceLoader([
        jinja2.DictLoader({"probe.html": "every {{ check_every_min }} min, "
                                         "{{ apps_per_day }} a day"}), env.loader]))
    app = create_app(cfg)

    @app.get("/probe")
    def probe(request: Request):
        return app_module._TEMPLATES.TemplateResponse(request, "probe.html", {})

    return client_for(cfg, app=app)


# --- T31 / T32 ----------------------------------------------------------------------------

def test_each_app_renders_its_own_interval_and_cap(saas_cfg, monkeypatch):
    fly = _probe_client(saas_cfg, monkeypatch)
    oracle = _probe_client(dataclasses.replace(saas_cfg, worker_interval=330,
                                               daily_tailor_cap=7), monkeypatch)
    assert fly.get("/probe").text == "every 10 min, 10 a day"
    assert oracle.get("/probe").text == "every 6 min, 7 a day"
    assert fly.get("/probe").text == "every 10 min, 10 a day"   # no last-app-wins global


@pytest.mark.parametrize("interval,minutes", [(600, 10), (330, 6)])
def test_live_dashboard_quotes_the_real_interval(saas_cfg, master_key, interval, minutes):
    """T31 page half: needs Jazelei's live status panel."""
    cfg = dataclasses.replace(saas_cfg, worker_interval=interval)
    user = seed_user(cfg, activated=True, keywords=("va",), gmail_key=master_key)
    text = page_text(client_for(cfg, user).get("/dashboard").text)
    assert f"about every {minutes} minutes" in text


def test_home_faq_quotes_the_real_daily_cap(saas_cfg):
    """T32: needs Jazelei's home FAQ 5 bound to apps_per_day."""
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=7)
    text = page_text(client_for(cfg).get("/").text)
    assert "up to 7 applications a day" in text
    assert "up to 10 applications a day" not in text


# --- T33 ----------------------------------------------------------------------------------

def test_processor_keys_never_collide_with_route_context(saas_cfg, master_key, monkeypatch):
    seen = _record_renders(monkeypatch)
    anon = client_for(saas_cfg)
    for path in ("/", "/login", "/privacy", "/terms"):
        anon.get(path)
    fresh = client_for(saas_cfg, seed_user(saas_cfg, sub="a", email="a@x.com"))
    fresh.get("/onboarding/connect_gmail")
    fresh.get("/onboarding/profile")
    fresh.get("/auth/gmail-callback", params={"error": "access_denied"})
    done = client_for(saas_cfg, seed_user(saas_cfg, sub="b", email="b@x.com", activated=True,
                                          keywords=("va",)))
    for path in ("/onboarding/keywords", "/onboarding/preview", "/dashboard"):
        done.get(path)
    assert {name for name, _ in seen} == {
        "home.html", "login.html", "privacy.html", "terms.html", "onboarding_connect_gmail.html",
        "onboarding_profile.html", "onboarding_keywords.html", "onboarding_preview.html",
        "dashboard.html"}
    for name, context in seen:
        keys = set(context)
        assert not keys & PROCESSOR_KEYS, f"{name} route context sets {keys & PROCESSOR_KEYS}"


# --- T34 ----------------------------------------------------------------------------------

def _has_back_link(markup: str) -> bool:
    return any(e.tag == "a" and e.attrs.get("href") == "/dashboard"
               and clean(e.text) == "Back to dashboard" for e in elements(markup))


@pytest.mark.parametrize("path", ["/onboarding/connect_gmail", "/onboarding/profile",
                                  "/onboarding/keywords"])
def test_back_to_dashboard_only_when_activated(saas_cfg, path):
    """Needs Jazelei's Steps 1 to 3 ("Back to dashboard" behind the activated flag)."""
    active = client_for(saas_cfg, seed_user(saas_cfg, sub="a", email="a@x.com", activated=True,
                                            keywords=("va",)))
    onboarding = client_for(saas_cfg, seed_user(saas_cfg, sub="b", email="b@x.com",
                                                profile=True))
    assert _has_back_link(active.get(path).text)
    assert not _has_back_link(onboarding.get(path).text)
    assert "Back to dashboard" not in onboarding.get(path).text


def test_preview_context_carries_the_activated_flag(saas_cfg, monkeypatch):
    """F-006: Step 4 needs "activated" to adapt for users who already finished setup."""
    seen = _record_renders(monkeypatch)
    for sub, activated in (("a", True), ("b", False)):
        user = seed_user(saas_cfg, sub=sub, email=f"{sub}@x.com", profile=True,
                         keywords=("va",), activated=activated)
        assert client_for(saas_cfg, user).get("/onboarding/preview").status_code == 200
    assert [context.get("activated", "missing") for name, context in seen
            if name == "onboarding_preview.html"] == [True, False]


# --- T39 (delivered email) ------------------------------------------------------------------

def test_delivered_email_uses_sky_and_navy_not_indigo():
    job = {"title": "VA", "url": "https://x", "employment_type": "FT", "salary_text": "$1",
           "posted_at": "2026-09-01", "matched_keyword": "va", "raw_description": "d"}
    pkg = TailoredPackage(application_subject="S", compliance_token="banana", cover_letter="c")
    html = build_tailored_email(job, pkg, ai_available=True)[2] + build_job_email(job, ["h"])[2]
    low = html.lower()
    for old in ("#2563eb", "#eef2ff", "#c7d2fe", "#fee2e2", "#fecaca", "#fff7ed", "#fed7aa"):
        assert old not in low
    for new in ("#0b6bc7", "#eef7fd", "#bfe3f8", "#dceffb", "#86cbf2", "#fff6e6", "#f0c274",
                "#0b2545"):
        assert new in low
    assert "Apply on onlinejobs.ph</a>" in html and "→</a>" not in html
