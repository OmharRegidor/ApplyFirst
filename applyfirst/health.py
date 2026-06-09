"""Liveness for the continuous ``run`` loop (the CLI equivalent of /healthz).

``run`` writes a heartbeat (``last_cycle_at``) to the DB after every cycle. The
``health`` subcommand reads it and reports whether the loop is fresh or has gone
stale, exiting non-zero when stale so an external watchdog (cron, UptimeRobot
heartbeat URL, systemd) can alert.

The staleness decision is a pure function so it is testable without the clock.
"""

from __future__ import annotations

from datetime import datetime, timezone

_FMT = "%Y-%m-%d %H:%M:%S"  # matches store.utcnow_iso()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, _FMT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def health_status(last_cycle_at: datetime | None, now: datetime,
                  max_stale_seconds: float) -> dict:
    """Return {ok, age_seconds, message} for a heartbeat vs. now."""
    if last_cycle_at is None:
        return {"ok": False, "age_seconds": None,
                "message": "UNHEALTHY: no poll cycle has completed yet"}
    age = (now - last_cycle_at).total_seconds()
    ok = age <= max_stale_seconds
    label = "healthy" if ok else "STALE"
    return {
        "ok": ok,
        "age_seconds": age,
        "message": f"{label}: last cycle {int(age)}s ago "
                   f"(threshold {int(max_stale_seconds)}s)",
    }
