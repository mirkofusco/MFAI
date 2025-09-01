import os, secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
import httpx
from typing import Any, Dict, List
from fastapi import Form
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo



router = APIRouter(prefix="/ui", tags=["Admin UI"])
templates = Jinja2Templates(directory="app/admin_ui/templates")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8000")
ADMIN_API_KEY = os.getenv("API_KEY", "")



def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
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
def ping(_: bool = Depends(require_admin)):
    return HTMLResponse("<h1>MF.AI Admin UI: OK</h1>")

@router.get("/", response_class=HTMLResponse)
def home(request: Request, _: bool = Depends(require_admin)):
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "page_title": "MF.AI — Admin UI"},
    )

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request, _: bool = Depends(require_admin)):
    url = f"{ADMIN_BASE_URL}/clients"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    items: List[Dict[str, Any]] = data.get("items", []) if isinstance(data, dict) else data

    # Enrichment: date leggibili e giorni residui
    now_utc = datetime.now(timezone.utc)
    tz = ZoneInfo("Europe/Rome")

    def fmt_iso_to_local(iso: str | None) -> str | None:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return iso

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
    """
    Attiva/Disattiva un IG account via Admin API:
    PATCH /admin/accounts/{ig_account_id}  body: {"active": true/false}
    """
    url = f"{ADMIN_BASE_URL}/admin/accounts/{ig_account_id}"
    payload = {"active": bool(int(new_active))}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(url, json=payload, auth=(ADMIN_USER, ADMIN_PASSWORD))
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Account non trovato")
        if resp.status_code == 401:
            raise HTTPException(status_code=502, detail="Admin API unauthorized")
        resp.raise_for_status()
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



