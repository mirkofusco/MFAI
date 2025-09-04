import os
from fastapi import Request
from fastapi.templating import Jinja2Templates
import secrets
from typing import Any, Dict, List
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from zoneinfo import ZoneInfo
from sqlalchemy import text
from app.db import engine


router = APIRouter(prefix="/ui", tags=["Admin UI"])
templates = Jinja2Templates(directory="app/admin_ui/templates")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8000")
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

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request, _: bool = Depends(require_admin)) -> HTMLResponse:
    # usa l'endpoint aggregato pubblico /clients
    url = f"{ADMIN_BASE_URL}/clients"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    items: List[Dict[str, Any]] = data.get("items", []) if isinstance(data, dict) else data

    # Enrichment: format date & days left
    now_utc = datetime.now(timezone.utc)
    tz = ZoneInfo("Europe/Rome")

    def fmt_iso_to_local(iso: str | None) -> str | None:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return iso  # fallback

    for it in items:
        exp = it.get("active_token_exp") or it.get("last_token_exp")
        it["token_exp_human"] = fmt_iso_to_local(exp)
        it["days_left"] = None
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                it["days_left"] = (dt - now_utc).days
            except Exception:
                pass

    return templates.TemplateResponse(
        "clients.html",
        {"request": request, "page_title": "Clients — MF.AI Admin", "items": items},
    )

@router.post("/accounts/toggle-active")
async def toggle_active(
    ig_account_id: int = Form(...),
    new_active: int = Form(...),
    _: bool = Depends(require_admin),
):
    """Attiva/Disattiva direttamente su Postgres."""
    active = bool(int(new_active))
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE mfai_app.instagram_accounts SET active = :active WHERE id = :id"),
            {"active": active, "id": ig_account_id},
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account non trovato")
    return RedirectResponse(url="/ui/clients", status_code=303)


@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    expires_in_days: int = Form(60),
    _: bool = Depends(require_admin),
):
    """
    Ruota il token via /tokens/refresh (richiede x-api-key).
    """
    url = f"{ADMIN_BASE_URL}/tokens/refresh"
    payload = {
        "ig_user_id": ig_user_id,
        "token": token,
        "expires_in_days": int(expires_in_days),
    }
    headers = {"x-api-key": ADMIN_API_KEY}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code == 401:
        raise HTTPException(status_code=502, detail="API key non valida lato server")
    resp.raise_for_status()
    return RedirectResponse(url="/ui/clients", status_code=303)

@router.post("/tokens/refresh")
async def ui_refresh_token(
    ig_user_id: str = Form(...),
    token: str = Form(...),
    expires_in_days: int = Form(60),
    _: bool = Depends(require_admin),
):
    """Ruota il token via /tokens/refresh (richiede x-api-key)."""
    # Guardia: token obbligatorio e con lunghezza minima
    if not token or not token.strip() or len(token.strip()) < 5:
        # redirect “soft” alla lista; opzionale puoi aggiungere ?err=missing_token
        return RedirectResponse(url="/ui/clients", status_code=303)

    url = f"{ADMIN_BASE_URL}/tokens/refresh"
    payload = {
        "ig_user_id": ig_user_id,
        "token": token.strip(),
        "expires_in_days": int(expires_in_days),
    }
    headers = {"x-api-key": ADMIN_API_KEY}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code == 401:
        raise HTTPException(status_code=502, detail="API key non valida lato server")
    resp.raise_for_status()
    return RedirectResponse(url="/ui/clients", status_code=303)


# --- Prompts Admin (pagina HTML) ---
from fastapi import Depends
from app.security_admin import verify_admin

@router.get("/admin/prompts-ui", response_class=HTMLResponse, dependencies=[Depends(verify_admin)])
def admin_prompts_ui(request: Request):
    return templates.TemplateResponse("admin_prompts.html", {"request": request})

@router.get("/prompts-ui", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def admin_prompts_ui(request: Request):
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("admin_prompts.html", {"request": request})


@router.get("/clients", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def admin_clients_page(request: Request):
    return templates.TemplateResponse("admin_clients.html", {"request": request})

@router.get("/clients/{client_id}", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def admin_client_detail(request: Request, client_id: int):
    return templates.TemplateResponse("admin_client_detail.html", {"request": request, "client_id": client_id})
