# app/admin_ui/routes.py
# ------------------------------------------------------------
# Admin UI (UI2) — Dashboard + CREATE/DELETE clienti + Token IG
# - Basic Auth (ADMIN_USER / ADMIN_PASSWORD)
# - /ui2  (dashboard)
# - POST /ui2/clients/create  -> crea cliente
# - POST /ui2/clients/delete  -> elimina cliente
# - POST /ui2/accounts/toggle-active -> attiva/disattiva account IG
# - POST /ui2/tokens/refresh  -> salva/aggiorna token IG tramite /save-token
# - GET  /ui2/connect -> redirect a /login (Meta Login) con Basic Auth
# ------------------------------------------------------------

import os
import secrets
import httpx
from typing import Any, Dict, List, Optional

import os
from fastapi import APIRouter, Depends, HTTPException, Request, status, Form, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from app.security_admin import verify_admin  # protezione admin

# --- DB engine
try:
    from app.db import engine
except Exception:
    engine = None

# --- Router protetto
router = APIRouter(prefix="/ui2", tags=["Admin UI"])
router.dependencies = [Depends(verify_admin)]  # richiede login Basic
templates = Jinja2Templates(directory="app/admin_ui/templates")
security = HTTPBasic()

# --- Config
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
CLIENTS_TABLE = os.getenv("CLIENTS_TABLE", "mfai_app.clients")
ACCOUNTS_TABLE = os.getenv("ACCOUNTS_TABLE", "mfai_app.instagram_accounts")


# ------------------------------------------------------------
# Auth
# ------------------------------------------------------------
def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    if not (
        secrets.compare_digest(credentials.username, ADMIN_USER)
        and secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

# ------------------------------------------------------------
# Health
# ------------------------------------------------------------
@router.get("/ping", response_class=HTMLResponse)
def ping(_: bool = Depends(require_admin)) -> HTMLResponse:
    return HTMLResponse("<h1>MF.AI Admin UI: OK</h1>")

# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    ok: Optional[str] = Query(None),
    err: Optional[str] = Query(None),
    _: bool = Depends(require_admin),
) -> HTMLResponse:
    items: List[Dict[str, Any]] = []
    if engine:
        async with engine.begin() as conn:
            res = await conn.execute(
                text(f"""
                    SELECT
                      c.id,
                      c.name,
                      COALESCE(
                        (SELECT a.username
                           FROM {ACCOUNTS_TABLE} a
                          WHERE a.client_id = c.id
                          ORDER BY a.created_at DESC
                          LIMIT 1),
                        ''
                      ) AS instagram_username,
                      EXISTS(
                        SELECT 1
                        FROM {ACCOUNTS_TABLE} a
                        WHERE a.client_id = c.id AND a.active = true
                      ) AS active
                    FROM {CLIENTS_TABLE} c
                    ORDER BY c.id DESC
                """)
            )
            rows = res.mappings().all()
            items = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "instagram_username": r["instagram_username"],
                    "active": bool(r["active"]),
                    "ai_prompt": None,
                }
                for r in rows
            ]

    # URL rapido per il Meta Login (mostrato nel template come bottone)
    connect_url = "/login"  # alias a /meta/login definito in main.py

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "page_title": "MF.AI — Admin UI",
            "ok": ok,
            "err": err,
            "items": items,
            "connect_url": connect_url,
        },
    )

# ------------------------------------------------------------
# Scorciatoia autenticata verso il Meta Login (comoda per lo screencast)
# ------------------------------------------------------------
@router.get("/connect")
async def ui_connect(_: bool = Depends(require_admin)):
    # Protegge il redirect con Basic Auth, poi rimanda al flusso /meta/login
    return RedirectResponse(url="/login", status_code=302)

# ------------------------------------------------------------
# CREATE client
# ------------------------------------------------------------
@router.post("/clients/create")
async def ui_create_client(
    name: str = Form(...),
    email: Optional[str] = Form(None),
    _: bool = Depends(require_admin),
):
    if engine is None:
        return RedirectResponse(url="/ui2?err=db_unavailable", status_code=303)

    name = name.strip()
    email = email.strip() if email else None
    if not name:
        return RedirectResponse(url="/ui2?err=invalid_input", status_code=303)

    async with engine.begin() as conn:
        await conn.execute(
            text(f"INSERT INTO {CLIENTS_TABLE} (name, email) VALUES (:n, :e)"),
            {"n": name, "e": email},
        )

    return RedirectResponse(url="/ui2?ok=created", status_code=303)

# ------------------------------------------------------------
# DELETE client
# ------------------------------------------------------------
@router.post("/clients/delete")
async def ui_delete_client(
    client_id: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine:
        async with engine.begin() as conn:
            await conn.execute(text(f"DELETE FROM {CLIENTS_TABLE} WHERE id = :i"), {"i": client_id})
    return RedirectResponse(url="/ui2?ok=deleted", status_code=303)

# ------------------------------------------------------------
# Toggle IG account
# ------------------------------------------------------------
@router.post("/accounts/toggle-active")
async def toggle_active(
    ig_account_id: int = Form(...),
    new_active: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"UPDATE {ACCOUNTS_TABLE} SET active = :a WHERE id = :i"),
                {"a": 1 if new_active else 0, "i": ig_account_id},
            )
    return RedirectResponse(url="/ui2?ok=account_updated", status_code=303)

# ------------------------------------------------------------
# Tokens — Refresh (chiama /save-token)
# ------------------------------------------------------------
@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    username: Optional[str] = Form(None),
    client_name: Optional[str] = Form("Default Client"),
    client_email: Optional[str] = Form(None),
    _: bool = Depends(require_admin),
):
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        return RedirectResponse(url="/ui2?err=missing_api_key", status_code=303)

    if not ig_user_id or not token or len(token) < 10:
        return RedirectResponse(url="/ui2?err=missing_token", status_code=303)

    if not username and engine:
        async with engine.begin() as conn:
            r = await conn.execute(
                text(f"SELECT username FROM {ACCOUNTS_TABLE} WHERE ig_user_id = :i LIMIT 1"),
                {"i": ig_user_id},
            )
            row = r.first()
            username = row[0] if row and row[0] else "unknown"

    payload = {
        "token": token,
        "ig_user_id": ig_user_id,
        "username": username or "unknown",
        "client_name": client_name,
        "client_email": client_email,
    }

    try:
        async with httpx.AsyncClient(base_url=os.getenv("BASE_URL", ""), timeout=10.0) as client:
            resp = await client.post(
                "/save-token",
                json=payload,
                headers={"x-api-key": api_key},
            )
        if resp.status_code >= 400:
            return RedirectResponse(url=f"/ui2?err=token_refresh_failed_{resp.status_code}", status_code=303)
    except Exception:
        return RedirectResponse(url="/ui2?err=token_refresh_failed", status_code=303)

    return RedirectResponse(url="/ui2?ok=token_refreshed", status_code=303)
