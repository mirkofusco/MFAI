# app/admin_ui/routes.py

import os
import secrets
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status, Form, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

# --- DB engine: supporta sia app.db che app.database ---
try:
    from app.db import engine
except Exception:
    try:
        from app.database import engine  # fallback
    except Exception:
        engine = None  # verrà gestito dove serve

router = APIRouter(prefix="/ui2", tags=["Admin UI"])
templates = Jinja2Templates(directory="app/admin_ui/templates")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8000")  # lasciato per future use
ADMIN_API_KEY = os.getenv("API_KEY", "")

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

# ------------------------
# Ping & Home
# ------------------------
@router.get("/ping", response_class=HTMLResponse)
def ping(_: bool = Depends(require_admin)) -> HTMLResponse:
    return HTMLResponse("<h1>MF.AI Admin UI: OK</h1>")

@router.get("/", response_class=HTMLResponse)
def home(request: Request, _: bool = Depends(require_admin)) -> HTMLResponse:
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "page_title": "MF.AI — Admin UI"},
    )

# ------------------------
# Clients: LIST (pagina) — query diretta su DB
# ------------------------
@router.get("/clients", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    ok: Optional[str] = Query(None),
    err: Optional[str] = Query(None),
    _: bool = Depends(require_admin),
) -> HTMLResponse:
    """
    Mostra l'elenco clienti leggendo direttamente dalla tabella `clients`.
    Colonne attese: id, name, instagram_username, api_key, active, ai_prompt
    """
    if engine is None:
        raise HTTPException(status_code=500, detail="Engine DB non disponibile (import fallito)")

    async with engine.begin() as conn:
        res = await conn.execute(
            text("""
                SELECT id, name, instagram_username, active, ai_prompt
                FROM clients
                ORDER BY id DESC
            """)
        )
        rows = res.mappings().all()

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append({
            "id": r["id"],
            "name": r["name"],
            "instagram_username": r["instagram_username"],
            "active": bool(r["active"]),
            "ai_prompt": r["ai_prompt"],
        })

    return templates.TemplateResponse(
        "clients.html",
        {
            "request": request,
            "page_title": "Clients — MF.AI Admin",
            "items": items,
            "ok": ok,
            "err": err,
        },
    )

# ------------------------
# Clients: CREATE (POST form) — INSERT diretto
# ------------------------
@router.post("/clients/create")
async def ui_create_client(
    request: Request,
    name: str = Form(...),
    instagram_username: str = Form(...),
    api_key: str = Form(...),
    active: Optional[str] = Form(None),          # "on" se spuntata, None se non spuntata
    ai_prompt: Optional[str] = Form(None),
    _: bool = Depends(require_admin),
):
    if engine is None:
        raise HTTPException(status_code=500, detail="Engine DB non disponibile (import fallito)")

    name = name.strip()
    instagram_username = instagram_username.strip()
    api_key = api_key.strip()
    ai_prompt = (ai_prompt.strip() if ai_prompt else None)
    active_bool = bool(active)

    # Validazioni minime
    if not name or not instagram_username or len(api_key) < 8:
        return RedirectResponse(url="/ui/clients?err=invalid_input", status_code=303)

    async with engine.begin() as conn:
        # Unicità instagram_username
        res = await conn.execute(
            text("SELECT 1 FROM clients WHERE instagram_username = :u LIMIT 1"),
            {"u": instagram_username},
        )
        exists = res.first() is not None
        if exists:
            return RedirectResponse(url="/ui/clients?err=duplicate_username", status_code=303)

        # INSERT
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

    return RedirectResponse(url="/ui/clients?ok=created", status_code=303)

# ------------------------
# Clients: DELETE (POST form) — DELETE diretto
# ------------------------
@router.post("/clients/delete")
async def ui_delete_client(
    client_id: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine is None:
        raise HTTPException(status_code=500, detail="Engine DB non disponibile (import fallito)")

    async with engine.begin() as conn:
        # Se hai FK verso instagram_accounts/tokens/logs senza ON DELETE CASCADE,
        # elimina prima i figli qui (facoltativo):
        # await conn.execute(text("DELETE FROM instagram_accounts WHERE client_id=:id"), {"id": client_id})
        # await conn.execute(text("DELETE FROM tokens WHERE client_id=:id"), {"id": client_id})
        res = await conn.execute(
            text("DELETE FROM clients WHERE id = :id"),
            {"id": client_id},
        )
        if getattr(res, "rowcount", 0) == 0:
            return RedirectResponse(url="/ui/clients?err=not_found", status_code=303)

    return RedirectResponse(url="/ui/clients?ok=deleted", status_code=303)

# ------------------------
# Accounts: toggle active (DB diretto) — già esisteva nel tuo file
# ------------------------
@router.post("/accounts/toggle-active")
async def toggle_active(
    ig_account_id: int = Form(...),
    new_active: int = Form(...),
    _: bool = Depends(require_admin),
):
    if engine is None:
        raise HTTPException(status_code=500, detail="Engine DB non disponibile (import fallito)")
    active = bool(int(new_active))
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE instagram_accounts SET active = :active WHERE id = :id"),
            {"active": 1 if active else 0, "id": ig_account_id},
        )
        if getattr(res, "rowcount", 0) == 0:
            return RedirectResponse(url="/ui/clients?err=account_not_found", status_code=303)
    return RedirectResponse(url="/ui/clients?ok=account_updated", status_code=303)

# ------------------------
# Tokens: refresh tramite Admin API esistente (se la usi)
# ------------------------
@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    expires_in_days: int = Form(60),
    _: bool = Depends(require_admin),
):
    if not token or not token.strip() or len(token.strip()) < 5:
        return RedirectResponse(url="/ui/clients?err=missing_token", status_code=303)

    # Se la tua /tokens/refresh è già attiva lato API
    url = f"{ADMIN_BASE_URL}/tokens/refresh"
    payload = {
        "ig_user_id": ig_user_id.strip(),
        "token": token.strip(),
        "expires_in_days": int(expires_in_days),
    }
    headers = {"x-api-key": ADMIN_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 401:
            return RedirectResponse(url="/ui/clients?err=api_key_invalid", status_code=303)
        resp.raise_for_status()
    except httpx.HTTPError:
        return RedirectResponse(url="/ui/clients?err=token_refresh_failed", status_code=303)

    return RedirectResponse(url="/ui/clients?ok=token_refreshed", status_code=303)
