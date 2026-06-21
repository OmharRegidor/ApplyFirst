"""The SaaS FastAPI app — Google sign-in + a gated dashboard (M1).

Run it:
    APPLYFIRST_SAAS_SECURE_COOKIES=1 python -m uvicorn applyfirst.saas.app:app \
        --host 127.0.0.1 --port 8000 --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem

Routes:
    GET  /                       → redirect to /dashboard (authed) or /login
    GET  /login                  → "Continue with Google" landing
    GET  /auth/login             → 302 to Google (sets the signed oauth-txn cookie)
    GET  /auth/callback          → validate state+nonce, upsert user, set session
    POST /auth/logout            → clear session
    GET  /me                     → JSON identity (401 if not authed)
    GET  /dashboard              → gated page
    GET  /api/oauth-credentials/{id} → tenant-scoped fetch (404 if not owned)
    GET  /healthz                → "ok"
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from applyfirst.saas import crypto, db, google_oauth, onboarding, preview, session
from applyfirst.saas.config import SaaSConfig, load_saas_config
from applyfirst.saas.tenant import tenant_scope

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(config: SaaSConfig | None = None) -> FastAPI:
    cfg = config or load_saas_config()
    app = FastAPI(title="ApplyFirst", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg

    # Ensure the schema exists before serving.
    db.init_db(cfg.db_path).close()

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        return resp

    # --- dependencies --------------------------------------------------------

    def get_cfg(request: Request) -> SaaSConfig:
        return request.app.state.cfg

    def get_conn(request: Request):
        conn = db.connect(request.app.state.cfg.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def current_user(request: Request, conn=Depends(get_conn)) -> db.User | None:
        cfg_ = request.app.state.cfg
        uid = session.read_session(request, cfg_.session_secret, cfg_.secure_cookies)
        return db.get_user(conn, uid) if uid else None

    def require_user(user: db.User | None = Depends(current_user)) -> db.User:
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return user

    # --- pages ---------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def root(request: Request, user: db.User | None = Depends(current_user)):
        if user:
            return RedirectResponse("/dashboard", status_code=302)
        # Public landing page (the homepage Google verification points at).
        return _TEMPLATES.TemplateResponse(request, "home.html", {})

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, user: db.User | None = Depends(current_user)):
        if user:
            return RedirectResponse("/dashboard", status_code=302)
        return _TEMPLATES.TemplateResponse(request, "login.html", {})

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy(request: Request):
        # Public, no auth — Google verification requires a login-free privacy URL.
        return _TEMPLATES.TemplateResponse(request, "privacy.html", {})

    @app.get("/terms", response_class=HTMLResponse)
    def terms(request: Request):
        return _TEMPLATES.TemplateResponse(request, "terms.html", {})

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, user: db.User | None = Depends(current_user),
                  conn=Depends(get_conn)):
        if user is None:
            return RedirectResponse("/login", status_code=302)
        profile = db.get_profile(conn, user.id)
        if profile is None or not profile.is_activated:
            return RedirectResponse("/onboarding", status_code=302)
        return _TEMPLATES.TemplateResponse(request, "dashboard.html", {
            "user": user,
            "profile": profile,
            "gmail_connected": db.gmail_connected(conn, user.id),
            "keywords": db.list_keywords(conn, user.id),
        })

    # --- auth ----------------------------------------------------------------

    @app.get("/auth/login")
    def auth_login(cfg_: SaaSConfig = Depends(get_cfg)):
        if not cfg_.google_client_id:
            raise HTTPException(status_code=503, detail="Google sign-in is not configured")
        state = google_oauth.make_state()
        nonce = google_oauth.make_nonce()
        verifier, challenge = google_oauth.make_pkce()
        url = google_oauth.build_auth_url(cfg_, state=state, nonce=nonce, code_challenge=challenge)
        resp = RedirectResponse(url, status_code=302)
        session.set_oauth_txn(resp, cfg_.session_secret, cfg_.secure_cookies,
                              state=state, nonce=nonce, verifier=verifier)
        return resp

    @app.get("/auth/callback")
    def auth_callback(request: Request, cfg_: SaaSConfig = Depends(get_cfg),
                      conn=Depends(get_conn)):
        params = request.query_params
        if params.get("error"):
            return _fail(cfg_)

        txn = session.read_oauth_txn(request, cfg_.session_secret, cfg_.secure_cookies)
        returned_state = params.get("state", "")
        # Validate state BEFORE touching the code (defeats login-CSRF / token replay).
        if not txn or not returned_state or returned_state != txn.get("state"):
            return _fail(cfg_)

        code = params.get("code")
        if not code:
            return _fail(cfg_)

        try:
            identity = google_oauth.fetch_identity(
                cfg_, code=code, code_verifier=txn["verifier"], expected_nonce=txn["nonce"],
            )
        except google_oauth.OAuthError:
            return _fail(cfg_)

        user = db.upsert_user_by_google(conn, **identity)
        resp = RedirectResponse("/dashboard", status_code=302)
        session.set_session(resp, cfg_.session_secret, cfg_.secure_cookies, user.id)
        session.clear_oauth_txn(resp, cfg_.secure_cookies)
        return resp

    @app.post("/auth/logout")
    def auth_logout(cfg_: SaaSConfig = Depends(get_cfg)):
        resp = RedirectResponse("/login", status_code=302)
        session.clear_session(resp, cfg_.secure_cookies)
        return resp

    # --- api -----------------------------------------------------------------

    @app.get("/me")
    def me(user: db.User = Depends(require_user)):
        return {"user_id": user.id, "email": user.email,
                "display_name": user.display_name, "plan": user.plan}

    @app.get("/api/oauth-credentials/{cred_id}")
    def get_oauth_credential(cred_id: str, user: db.User = Depends(require_user),
                             conn=Depends(get_conn)):
        """Tenant-scoped fetch. A credential owned by another user → 404, never 403."""
        with tenant_scope(conn, user.id) as scope:
            row = scope.fetch_by_id("oauth_credentials", cred_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        # Never return token material — only safe metadata.
        return {"id": row["id"], "provider": row["provider"],
                "gmail_scope_granted": bool(row["gmail_scope_granted"])}

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz():
        return "ok"

    # --- onboarding wizard ---------------------------------------------------

    @app.get("/onboarding")
    def onboarding_root(user: db.User = Depends(require_user), conn=Depends(get_conn)):
        step = onboarding.next_step(conn, user.id)
        if step == "done":
            return RedirectResponse("/dashboard", status_code=302)
        return RedirectResponse(f"/onboarding/{step}", status_code=302)

    @app.get("/onboarding/connect_gmail", response_class=HTMLResponse)
    def onboarding_connect_gmail(request: Request, user: db.User = Depends(require_user),
                                 conn=Depends(get_conn)):
        return _TEMPLATES.TemplateResponse(request, "onboarding_connect_gmail.html", {
            "user": user, "gmail_connected": db.gmail_connected(conn, user.id),
        })

    @app.get("/onboarding/profile", response_class=HTMLResponse)
    def onboarding_profile_form(request: Request, user: db.User = Depends(require_user),
                                conn=Depends(get_conn)):
        profile = db.get_profile(conn, user.id)
        return _TEMPLATES.TemplateResponse(request, "onboarding_profile.html", {
            "user": user, "profile": profile,
            "default_name": (profile.full_name if profile else "") or user.display_name or "",
        })

    @app.post("/onboarding/profile")
    def onboarding_profile_save(
        user: db.User = Depends(require_user), conn=Depends(get_conn),
        full_name: str = Form(""), job_type: str = Form(""),
        standard_subject: str = Form(""), standard_message: str = Form(""),
    ):
        if not all(v.strip() for v in (full_name, job_type, standard_subject, standard_message)):
            return RedirectResponse("/onboarding/profile?error=1", status_code=302)
        db.upsert_profile(conn, user.id, full_name=full_name.strip(), job_type=job_type.strip(),
                          standard_subject=standard_subject.strip(),
                          standard_message=standard_message.strip())
        return RedirectResponse("/onboarding/keywords", status_code=302)

    @app.get("/onboarding/keywords", response_class=HTMLResponse)
    def onboarding_keywords_page(request: Request, user: db.User = Depends(require_user),
                                 conn=Depends(get_conn)):
        profile = db.get_profile(conn, user.id)
        if profile is None or not profile.is_complete:
            return RedirectResponse("/onboarding/profile", status_code=302)
        return _TEMPLATES.TemplateResponse(request, "onboarding_keywords.html", {
            "user": user, "keywords": db.list_keywords(conn, user.id),
        })

    @app.post("/onboarding/keywords")
    def onboarding_keywords_add(user: db.User = Depends(require_user), conn=Depends(get_conn),
                                keyword: str = Form("")):
        db.add_keyword(conn, user.id, keyword)
        return RedirectResponse("/onboarding/keywords", status_code=302)

    @app.post("/onboarding/keywords/{keyword_id}/delete")
    def onboarding_keywords_delete(keyword_id: str, user: db.User = Depends(require_user),
                                   conn=Depends(get_conn)):
        db.delete_keyword(conn, user.id, keyword_id)
        return RedirectResponse("/onboarding/keywords", status_code=302)

    @app.get("/onboarding/preview", response_class=HTMLResponse)
    def onboarding_preview_page(request: Request, user: db.User = Depends(require_user),
                                conn=Depends(get_conn)):
        profile = db.get_profile(conn, user.id)
        if profile is None or not profile.is_complete:
            return RedirectResponse("/onboarding/profile", status_code=302)
        if not db.list_keywords(conn, user.id):
            return RedirectResponse("/onboarding/keywords", status_code=302)
        pv = preview.build_preview(
            full_name=profile.full_name, job_type=profile.job_type,
            standard_subject=profile.standard_subject, standard_message=profile.standard_message,
        )
        return _TEMPLATES.TemplateResponse(request, "onboarding_preview.html", {
            "user": user, "preview": pv,
            "gmail_connected": db.gmail_connected(conn, user.id),
        })

    @app.post("/onboarding/activate")
    def onboarding_activate(user: db.User = Depends(require_user), conn=Depends(get_conn)):
        profile = db.get_profile(conn, user.id)
        if profile is None or not profile.is_complete or not db.list_keywords(conn, user.id):
            return RedirectResponse("/onboarding", status_code=302)
        db.set_activated(conn, user.id)
        return RedirectResponse("/dashboard", status_code=302)

    # --- connect / disconnect Gmail (incremental gmail.send authorization) ----

    @app.get("/auth/connect-gmail")
    def connect_gmail(cfg_: SaaSConfig = Depends(get_cfg), user: db.User = Depends(require_user)):
        if not cfg_.google_client_id:
            raise HTTPException(status_code=503, detail="Google is not configured")
        state = google_oauth.make_state()
        verifier, challenge = google_oauth.make_pkce()
        url = google_oauth.build_connect_gmail_url(cfg_, state=state, code_challenge=challenge)
        resp = RedirectResponse(url, status_code=302)
        session.set_oauth_txn(resp, cfg_.session_secret, cfg_.secure_cookies,
                              state=state, nonce="n/a", verifier=verifier)
        return resp

    @app.get("/auth/gmail-callback")
    def gmail_callback(request: Request, cfg_: SaaSConfig = Depends(get_cfg),
                       user: db.User = Depends(require_user), conn=Depends(get_conn)):
        params = request.query_params
        if params.get("error"):
            return _fail(cfg_)
        txn = session.read_oauth_txn(request, cfg_.session_secret, cfg_.secure_cookies)
        returned_state = params.get("state", "")
        if not txn or not returned_state or returned_state != txn.get("state"):
            return _fail(cfg_)
        code = params.get("code")
        if not code:
            return _fail(cfg_)
        try:
            refresh_token = google_oauth.exchange_code_for_gmail(
                cfg_, code=code, code_verifier=txn["verifier"])
            db.store_gmail_credential(conn, user.id, refresh_token=refresh_token,
                                      master_key=crypto.load_master_key())
        except (google_oauth.OAuthError, crypto.CryptoError):
            return _fail(cfg_)
        resp = RedirectResponse("/onboarding", status_code=302)
        session.clear_oauth_txn(resp, cfg_.secure_cookies)
        return resp

    @app.post("/auth/disconnect-gmail")
    def disconnect_gmail(user: db.User = Depends(require_user), conn=Depends(get_conn)):
        try:
            token = db.get_gmail_refresh_token(conn, user.id, crypto.load_master_key())
            if token:
                google_oauth.revoke_token(token)
        except crypto.CryptoError:
            pass  # still clear locally even if we cannot decrypt to revoke
        db.clear_gmail_credential(conn, user.id)
        return RedirectResponse("/dashboard", status_code=302)

    def _fail(cfg_: SaaSConfig) -> JSONResponse:
        # One generic message for every failure mode — no oracle that distinguishes
        # bad-state vs missing-code vs verify-failure. Always clears the oauth txn.
        resp = JSONResponse({"error": "sign-in failed; please try again"}, status_code=400)
        session.clear_oauth_txn(resp, cfg_.secure_cookies)
        return resp

    return app


def __getattr__(name: str):
    """Lazily build the ASGI app on first attribute access (PEP 562).

    Lets uvicorn target ``applyfirst.saas.app:app`` (which loads config from the
    environment) without forcing config to load merely on ``import`` — so tests can
    ``from applyfirst.saas.app import create_app`` and pass their own config.
    """
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
