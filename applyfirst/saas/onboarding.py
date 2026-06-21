"""Onboarding state machine — derive the next step from data presence (idempotent).

Steps (SYSTEM-DESIGN §5): connect_gmail (skippable) → profile (required) →
keywords (≥1 required) → preview → activate. We never store a brittle step counter;
the next step is computed from what's actually in the DB, so a half-finished or
resumed onboarding always lands on the right page.
"""

from __future__ import annotations

import sqlite3

from applyfirst.saas import db

# Ordered for display; `next_step` returns the first incomplete required state.
STEPS = ("connect_gmail", "profile", "keywords", "preview", "done")


def status(conn: sqlite3.Connection, user_id: str) -> dict:
    profile = db.get_profile(conn, user_id)
    return {
        "gmail_connected": db.gmail_connected(conn, user_id),
        "profile_complete": profile is not None and profile.is_complete,
        "keyword_count": len(db.list_keywords(conn, user_id)),
        "activated": profile is not None and profile.is_activated,
    }


def next_step(conn: sqlite3.Connection, user_id: str) -> str:
    """The page /onboarding should route to for this user."""
    st = status(conn, user_id)
    if st["activated"]:
        return "done"
    if not st["profile_complete"]:
        # Offer Connect Gmail first (skippable); once they're past it, the profile form.
        return "connect_gmail" if not st["gmail_connected"] else "profile"
    if st["keyword_count"] == 0:
        return "keywords"
    return "preview"
