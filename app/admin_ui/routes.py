# app/admin_ui/routes.py
# ------------------------------------------------------------
# Admin UI (UI2) — Dashboard + CREATE/DELETE clienti + Token IG
# - Basic Auth (ADMIN_USER / ADMIN_PASSWORD)
# - /ui2  (dashboard)
# - POST /ui2/clients/create  -> crea cliente
# - POST /ui2/clients/delete  -> elimina cliente
# - POST /ui2/accounts/toggle-active -> attiva/disattiva account IG
# - POST /ui2/tokens/refresh  -> SALVA/AGGIORNA token IG direttamente su DB
# ------------------------------------------------------------

import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Form, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

# --- DB engine: tenta app.db, poi app.database; altrimenti None (gestito a runtime)
try:
    from app.db import engine
except Exception:
    try:
        from app.database import engine  # fallback
    except Exception:
        engine = None

router = APIRouter(prefix="/ui2", tags=["Admin UI"])
templates = Jinja2Templates(directory="app/admin_ui/templates")
security = HTTPBasic()

# --- Config da env
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

CLIENTS_TABLE = os.getenv("CLIENTS_TABLE", "clients")                      # es. "mfai_app.clients"
ACCOUNTS_TABLE = os.getenv("ACCOUNTS_TABLE", "instagram_accounts")         # es. "mfai_app.instagram_accounts"
TOKENS_TABLE = os.getenv("TOKENS_TABLE", "tokens")                         # es. "mfai_app.tokens"

# ------------------------------------------------------------
# Auth: Basic
# ------------------------------------------------------------
def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    user_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    pwd_ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (user_ok and pwd_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

# ------------------------------------------------------------
# Health minimale
# ------------------------------------------------------------
@router.get("/ping", response_class=HTMLResponse)
def ping(_: bool = Depends(require_admin)) -> HTMLResponse:
    return HTMLResponse("<h1>MF.AI Admin UI: OK</h1>")

# ------------------------------------------------------------
# Dashboard: /ui2
# ------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    ok: Optional[str] = Query(None),
    err: Optional[str] = Query(None),
    _: bool = Depends(require_admin),
) -> HTMLResponse:
    items: List[Dict[str, Any]] = []
    if engine is None:
        # Mostra la pagina anche senza DB
        return templates.TemplateResponse(
            "home.html",
            {"request": request, "page_title": "MF.AI — Admin UI", "ok": ok, "err": err, "items": items},
        )

    async with engine.begin() as conn:
        res = await conn.execute(
            text(f"""
                SELECT id, name, instagram_username, active, ai_prompt
                FROM {CLIENTS_TABLE}
                ORDER BY id DESC
            """)
        )
        rows = res.mappings().all()

    items = [
        {
            "id": r["id"],
            "name": r["name"],
            "instagram_username": r["instagram_username"],
            "active": bool(r["active"]),
            "ai_prompt": r["ai_prompt"],
        }
        for r in rows
    ]

    return templates.TemplateResponse(
        "home.html",
        {"request": request, "page_title": "MF.AI — Admin UI", "ok": ok, "err": err, "items": items},
    )

# ------------------------------------------------------------
# CREATE cliente (POST)
# ------------------------------------------------------------
@router.post("/clients/create")
async def ui_create_client(
    name: str = Form(...),
    instagram_username: str = Form(...),
    api_key: str = Form(...),
    active: Optional[str] = Form(None),      # checkbox -> 'on' oppure None
    ai_prompt: Optional[str] = Form(None),
    _: bool = Depends(require_admin),
):
    if engine is None:
        return RedirectResponse(url="/ui2?err=db_unavailable", status_code=303)

    name = name.strip()
    instagram_username = instagram_username.strip().lstrip("@")
    api_key = api_key.strip()
    ai_prompt = (ai_prompt.strip() if ai_prompt else None)
    active_bool = bool(active)

    if not name or not instagram_username or len(api_key) < 8:
        return RedirectResponse(url="/ui2?err=invalid_input", status_code=303)

    async with engine.begin() as conn:
        # Unicità instagram_username
        res = await conn.execute(
            text(f"SELECT 1 FROM {CLIENTS_TABLE} WHERE instagram_username = :u LIMIT 1"),
            {"u": instagram_username},
        )
        if res.first() is not None:
            return RedirectResponse(url="/ui2?err=duplicate_username", status_code=303)

        await conn.execute(
            text(f"""
                INSERT INTO {CLIENTS_TABLE} (name, instagram_username, api_key, active, ai_prompt)
                VALUES (:name, :username, :api_key, :active, :ai_prompt)
            """),
            {
                "name": name,
                "username": instagram_username,
                "api_key": api_key,
                "active": 1 if active_bool else 0,
                "ai_prompt": ai_prompt,
            }
        )

    return RedirectResponse(url="/ui2?ok=created", status_code=303)

# ------------------------------------------------------------
# DELETE cliente (POST)
# ------------------------------------------------------------
@router.post("/clients/delete")
async def ui_delete_client(
    client_id: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine is None:
        return RedirectResponse(url="/ui2?err=db_unavailable", status_code=303)

    async with engine.begin() as conn:
        await conn.execute(text(f"DELETE FROM {CLIENTS_TABLE} WHERE id = :id"), {"id": client_id})

    return RedirectResponse(url="/ui2?ok=deleted", status_code=303)

# ------------------------------------------------------------
# Accounts — Toggle active (opzionale)
# ------------------------------------------------------------
@router.post("/accounts/toggle-active")
async def toggle_active(
    ig_account_id: int = Form(...),
    new_active: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine is None:
        return RedirectResponse(url="/ui2?err=db_unavailable", status_code=303)

    active = bool(int(new_active))
    async with engine.begin() as conn:
        res = await conn.execute(
            text(f"UPDATE {ACCOUNTS_TABLE} SET active = :active WHERE id = :id"),
            {"active": 1 if active else 0, "id": ig_account_id},
        )
        if getattr(res, "rowcount", 0) == 0:
            return RedirectResponse(url="/ui2?err=account_not_found", status_code=303)

    return RedirectResponse(url="/ui2?ok=account_updated", status_code=303)

# ------------------------------------------------------------
# Tokens — REFRESH: salva direttamente su DB (niente chiamata HTTP)
# ------------------------------------------------------------
@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    expires_in_days: int = Form(60),
    _: bool = Depends(require_admin),
):
    if engine is None:
        return RedirectResponse(url="/ui2?err=db_unavailable", status_code=303)

    ig_user_id = (ig_user_id or "").strip()
    token = (token or "").strip()

    try:
        days = int(expires_in_days)
    except Exception:
        days = 60

    if not ig_user_id or not token or len(token) < 10:
        return RedirectResponse(url="/ui2?err=missing_token", status_code=303)

    expires_at = datetime.utcnow() + timedelta(days=days)

    upsert_sql = text(f"""
        INSERT INTO {TOKENS_TABLE} (ig_user_id, token, expires_at, updated_at)
        VALUES (:ig_user_id, :token, :expires_at, NOW())
        ON CONFLICT (ig_user_id)
        DO UPDATE SET token=EXCLUDED.token,
                      expires_at=EXCLUDED.expires_at,
                      updated_at=NOW()
    """)

    try:
        async with engine.begin() as conn:
            await conn.execute(upsert_sql, {
                "ig_user_id": ig_user_id,
                "token": token,
                "expires_at": expires_at,
            })
    except Exception:
        return RedirectResponse(url="/ui2?err=token_refresh_failed", status_code=303)

    return RedirectResponse(url="/ui2?ok=token_refreshed", status_code=303)
