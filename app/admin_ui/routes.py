# app/admin_ui/routes.py

import os
import secrets
from typing import Any, Dict, List, Optional

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
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8000")  # usato per /tokens/refresh
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

    items: List[Dict[str, Any]] = [
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
        "clients.html",
        {"request": request, "page_title": "Clients — MF.AI Admin", "items": items, "ok": ok, "err": err},
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
    active: Optional[str] = Form(None),
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

    if not name or not instagram_username or len(api_key) < 8:
        return RedirectResponse(url="/ui2/clients?err=invalid_input", status_code=303)

    async with engine.begin() as conn:
        # Unicità instagram_username
        res = await conn.execute(
            text("SELECT 1 FROM clients WHERE instagram_username = :u LIMIT 1"),
            {"u": instagram_username},
        )
        if res.first() is not None:
            return RedirectResponse(url="/ui2/clients?err=duplicate_username", status_code=303)

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

    return RedirectResponse(url="/ui2/clients?ok=created", status_code=303)

# ------------------------
# ------------------------
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
        # Se hai FK senza ON DELETE CASCADE, elimina prima i figli (decommenta se serve):
        # await conn.execute(text("DELETE FROM instagram_accounts WHERE client_id=:id"), {"id": client_id})
        # await conn.execute(text("DELETE FROM tokens WHERE client_id=:id"), {"id": client_id})

        # DELETE cliente
        await conn.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})

    return RedirectResponse(url="/ui2/clients?ok=deleted", status_code=303)



# ------------------------
# Accounts: toggle active (DB diretto)
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
            return RedirectResponse(url="/ui2/clients?err=account_not_found", status_code=303)
    return RedirectResponse(url="/ui2/clients?ok=account_updated", status_code=303)

# ------------------------
# Tokens: refresh via API (se la usi)
# ------------------------
@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    expires_in_days: int = Form(60),
    _: bool = Depends(require_admin),
):
    if not token or not token.strip() or len(token.strip()) < 5:
        return RedirectResponse(url="/ui2/clients?err=missing_token", status_code=303)

    url = f"{ADMIN_BASE_URL}/tokens/refresh"
    payload = {"ig_user_id": ig_user_id.strip(), "token": token.strip(), "expires_in_days": int(expires_in_days)}
    headers = {"x-api-key": ADMIN_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 401:
            return RedirectResponse(url="/ui2/clients?err=api_key_invalid", status_code=303)
        resp.raise_for_status()
    except httpx.HTTPError:
        return RedirectResponse(url="/ui2/clients?err=token_refresh_failed", status_code=303)

    return RedirectResponse(url="/ui2/clients?ok=token_refreshed", status_code=303)
