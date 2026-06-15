"""Read-only web dashboard for ApplyFirst.

A tiny FastAPI + Jinja2 app that shows the caught jobs and their persisted
AI-tailored packages. It is deliberately READ-ONLY: it opens the catcher's
SQLite DB with ``PRAGMA query_only=ON`` so it can never write to (let alone
corrupt) the live poller's database, while still reading a WAL database safely
whether or not the poller is currently running.

  python -m uvicorn applyfirst.web.app:app --host 127.0.0.1 --port 8000

It is meant to run privately — bound to 127.0.0.1 and reached over Tailscale.
No writes, no accounts: single-user, private-network tool (see deploy/oracle/).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from applyfirst.config import load_settings

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_STALE_SECONDS = 15 * 60  # a poll cycle older than this is "may be stalled"

app = FastAPI(title="ApplyFirst Dashboard", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# --- read-only data access ---------------------------------------------------

def _db_path() -> str:
    return load_settings().db


def _connect_ro() -> sqlite3.Connection:
    """Open the catcher DB read-only. Raises if the DB file does not exist.

    We use a normal connection + ``query_only`` rather than ``?mode=ro`` because
    a strict read-only connection cannot read a WAL database when the writer
    (poller) is stopped and the -wal file is non-empty. ``query_only`` gives the
    same "no writes" guarantee without that fragility.
    """
    p = Path(_db_path()).resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    conn = sqlite3.connect(str(p), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA query_only=ON;")
    return conn


def _get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row is not None else None


def _keywords(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT keyword FROM saved_search WHERE active=1 ORDER BY id").fetchall()
    return [r["keyword"] for r in rows]


def _age_human(age: int | None) -> str:
    if age is None:
        return "never"
    if age < 90:
        return f"{age}s ago"
    if age < 5400:
        return f"{age // 60}m ago"
    if age < 172800:
        return f"{age // 3600}h ago"
    return f"{age // 86400}d ago"


def _health(conn: sqlite3.Connection) -> dict:
    last = _get_meta(conn, "last_cycle_at")
    total = int(conn.execute("SELECT COUNT(*) FROM job").fetchone()[0])
    rows = conn.execute("SELECT status, COUNT(*) AS c FROM job GROUP BY status").fetchall()
    by_status = {r["status"]: r["c"] for r in rows}
    age: int | None = None
    stale = True
    if last:
        try:
            dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            age = int((datetime.now(timezone.utc) - dt).total_seconds())
            stale = age > _STALE_SECONDS
        except ValueError:
            pass
    return {
        "last_cycle_at": last, "age_seconds": age, "age_human": _age_human(age),
        "stale": stale, "total_jobs": total, "by_status": by_status,
    }


def _list_jobs(conn: sqlite3.Connection, status: str | None, q: str | None, limit: int):
    sql = [
        "SELECT j.*, (SELECT 1 FROM tailored t WHERE t.job_id = j.id) AS has_tailored",
        "FROM job j",
    ]
    where: list[str] = []
    params: list = []
    if status:
        where.append("j.status = ?")
        params.append(status)
    if q:
        where.append("j.title LIKE ?")
        params.append(f"%{q}%")
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY j.scraped_at DESC, j.id DESC LIMIT ?")
    params.append(limit)
    return conn.execute(" ".join(sql), params).fetchall()


# --- routes ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    status: str | None = Query(default=None, max_length=40),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
):
    try:
        conn = _connect_ro()
    except (FileNotFoundError, sqlite3.Error):
        return _TEMPLATES.TemplateResponse(
            request, "list.html",
            {"jobs": [], "health": None, "keywords": [],
             "db_error": True, "status": status, "q": q},
        )
    try:
        jobs = _list_jobs(conn, status, q, limit)
        health = _health(conn)
        keywords = _keywords(conn)
    finally:
        conn.close()
    return _TEMPLATES.TemplateResponse(
        request, "list.html",
        {"jobs": jobs, "health": health, "keywords": keywords,
         "db_error": False, "status": status, "q": q},
    )


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str):
    if not job_id.isdigit():
        raise HTTPException(status_code=404)
    jid = int(job_id)
    try:
        conn = _connect_ro()
    except (FileNotFoundError, sqlite3.Error):
        raise HTTPException(status_code=503, detail="catcher database unavailable")
    try:
        job = conn.execute("SELECT * FROM job WHERE id=?", (jid,)).fetchone()
        if job is None:
            raise HTTPException(status_code=404)
        trow = conn.execute("SELECT * FROM tailored WHERE job_id=?", (jid,)).fetchone()
        health = _health(conn)
    finally:
        conn.close()

    package = None
    if trow is not None and trow["package_json"]:
        try:
            package = json.loads(trow["package_json"])
        except (ValueError, TypeError):
            package = None
    return _TEMPLATES.TemplateResponse(
        request, "detail.html",
        {"job": job, "package": package, "tailored": trow, "health": health},
    )


@app.get("/api/health")
def api_health():
    try:
        conn = _connect_ro()
    except (FileNotFoundError, sqlite3.Error):
        return JSONResponse({"ok": False, "error": "database unavailable"}, status_code=503)
    try:
        h = _health(conn)
    finally:
        conn.close()
    h["ok"] = not h["stale"]
    return h


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
