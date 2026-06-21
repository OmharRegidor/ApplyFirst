"""ApplyFirst SaaS (V2) — multi-tenant auth foundation.

A separate FastAPI app + separate SQLite database (``applyfirst-saas.db``) from the
single-user CLI. The CLI and its ``applyfirst.db`` are deliberately left untouched.

See ``docs/SYSTEM-DESIGN.md`` and ``docs/plans/M1-auth-foundation.md``.
"""
