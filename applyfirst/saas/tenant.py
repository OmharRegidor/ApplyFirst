"""Tenant scoping — the ONLY sanctioned way to read per-tenant tables.

Every query against a ``TENANT_TABLES`` table is forced to carry ``AND user_id = ?``
so an engineer cannot hand-write a cross-tenant leak. A missing scope is the single
most dangerous bug class in a multi-tenant app (M1 plan P0-3), and on the SQLite-MVP
there is no Postgres RLS behind it — this helper + the cross-tenant test are the
whole defense.

Lookups that find nothing for the current user return ``None`` → the route turns that
into **404, not 403** (no existence oracle / enumeration).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from applyfirst.saas.db import TENANT_TABLES


class TenantScope:
    """A user_id-bound view over the database. All reads are auto-scoped."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._user_id = user_id

    @property
    def user_id(self) -> str:
        return self._user_id

    def fetch_by_id(self, table: str, row_id: str) -> sqlite3.Row | None:
        """Fetch one row by id, scoped to this tenant. None if not owned/found."""
        if table not in TENANT_TABLES:
            raise ValueError(f"{table!r} is not a tenant-scoped table")
        return self._conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",  # noqa: S608 - table is allow-listed above
            (row_id, self._user_id),
        ).fetchone()

    def list(self, table: str) -> list[sqlite3.Row]:
        """List all rows of a tenant-scoped table owned by this tenant."""
        if table not in TENANT_TABLES:
            raise ValueError(f"{table!r} is not a tenant-scoped table")
        return self._conn.execute(
            f"SELECT * FROM {table} WHERE user_id = ?",  # noqa: S608 - table is allow-listed above
            (self._user_id,),
        ).fetchall()


@contextmanager
def tenant_scope(conn: sqlite3.Connection, user_id: str) -> Iterator[TenantScope]:
    yield TenantScope(conn, user_id)
