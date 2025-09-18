# app/admin_ui/routes.py
# ------------------------------------------------------------
# Admin UI (UI2) — Dashboard unica su /ui2
# - Basic Auth (ADMIN_USER / ADMIN_PASSWORD)
# - /ui2  (dashboard)  -> mostra eventuale lista clienti (se il template la usa) + alert ok/err
# - POST /ui2/clients/create  -> crea cliente e torna su /ui2
# - POST /ui2/clients/delete  -> elimina cliente e torna su /ui2
# - (opzionali) toggle-active account IG, refresh token
#
# NOTE DB:
# - Usa "engine" async SQLAlchemy (tenta app.db, poi app.database)
# - Tabelle attese (senza schema): clients, instagram_accounts, tokens
#   Se usi schema (es. mfai_app.clients), adatta le query.
# ------------------------------------------------------------

import os
import secrets
from typing import Any, Dict, List, Optional

import httpx
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
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8000")
ADMIN_API_KEY = os.getenv("API_KEY", "")

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
# Dashboard: /ui2  (UNICA pagina che usi)
# - Accetta ok/err per mostrare alert in home.html
# - (Facoltativo) Fornisce 'items' con i clienti, se il template vuole listarli
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
        # non blocchiamo la pagina: mostriamo la home comunque
        return templates.TemplateResponse(
            "home.html",
            {"request": request, "page_title": "MF.AI — Admin UI", "ok": ok, "err": err, "items": items},
        )
    # ------------------------------------------------------------
# Pagina Clienti: /ui2/clients
# ------------------------------------------------------------
@router.get("/clients", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    _: bool = Depends(require_admin),
) -> HTMLResponse:
    # La pagina è client-side driven: il JS chiama /admin/clients
    return templates.TemplateResponse(
        "clients.html",
        {"request": request, "page_title": "Clienti · Admin"}
    )


    # Se vuoi una lista clienti nel pannello (sidebar, widget, ecc.)
    async with engine.begin() as conn:
        res = await conn.execute(
            text("""
                SELECT id, name, instagram_username, active, ai_prompt
                FROM clients
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
# CREATE cliente (POST) -> torna su /ui2 con ok/err
# Campi form: name, instagram_username, api_key, (active opzionale), ai_prompt
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
    instagram_username = instagram_username.strip()
    api_key = api_key.strip()
    ai_prompt = (ai_prompt.strip() if ai_prompt else None)
    active_bool = bool(active)

    if not name or not instagram_username or len(api_key) < 8:
        return RedirectResponse(url="/ui2?err=invalid_input", status_code=303)

    async with engine.begin() as conn:
        # Unicità instagram_username
        res = await conn.execute(
            text("SELECT 1 FROM clients WHERE instagram_username = :u LIMIT 1"),
            {"u": instagram_username},
        )
        if res.first() is not None:
            return RedirectResponse(url="/ui2?err=duplicate_username", status_code=303)

        await conn.execute(
            text("""
                INSERT INTO clients (name, instagram_username, api_key, active, ai_prompt)
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
# DELETE cliente (POST) -> torna su /ui2 con ok=deleted
# Campo form: client_id (hidden)
# ------------------------------------------------------------
@router.post("/clients/delete")
async def ui_delete_client(
    client_id: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine is None:
        return RedirectResponse(url="/ui2?err=db_unavailable", status_code=303)

    async with engine.begin() as conn:
        # Se NON hai ON DELETE CASCADE sulle FK, elimina prima eventuali figli:
        # await conn.execute(text("DELETE FROM instagram_accounts WHERE client_id=:id"), {"id": client_id})
        # await conn.execute(text("DELETE FROM tokens WHERE client_id=:id"), {"id": client_id})

        await conn.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})

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
            text("UPDATE instagram_accounts SET active = :active WHERE id = :id"),
            {"active": 1 if active else 0, "id": ig_account_id},
        )
        if getattr(res, "rowcount", 0) == 0:
            return RedirectResponse(url="/ui2?err=account_not_found", status_code=303)

    return RedirectResponse(url="/ui2?ok=account_updated", status_code=303)

# ------------------------------------------------------------
# Tokens — Refresh via API (opzionale)
# ------------------------------------------------------------
@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    expires_in_days: int = Form(60),
    _: bool = Depends(require_admin),
):
    token = (token or "").strip()
    if not token or len(token) < 5:
        return RedirectResponse(url="/ui2?err=missing_token", status_code=303)

    url = f"{ADMIN_BASE_URL.rstrip('/')}/tokens/refresh"
    payload = {"ig_user_id": ig_user_id.strip(), "token": token, "expires_in_days": int(expires_in_days)}
    headers = {"x-api-key": ADMIN_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 401:
            return RedirectResponse(url="/ui2?err=api_key_invalid", status_code=303)
        resp.raise_for_status()
    except httpx.HTTPError:
        return RedirectResponse(url="/ui2?err=token_refresh_failed", status_code=303)

    return RedirectResponse(url="/ui2?ok=token_refreshed", status_code=303)
