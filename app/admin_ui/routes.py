import os, secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
import httpx
from typing import Any, Dict, List


router = APIRouter(prefix="/ui", tags=["Admin UI"])
templates = Jinja2Templates(directory="app/admin_ui/templates")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8000")


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

    # Enrichment: format date & days left, guard nulls
    now_utc = datetime.now(timezone.utc)
    tz = ZoneInfo("Europe/Rome")

    def fmt_iso_to_local(iso: str | None) -> str | None:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return iso  # fallback raw

    for it in items:
        exp = it.get("active_token_exp") or it.get("last_token_exp")
        it["token_exp_human"] = fmt_iso_to_local(exp)
        # days left
        days_left = None
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                days_left = (dt - now_utc).days
            except Exception:
                pass
        it["days_left"] = days_left

    return templates.TemplateResponse(
        "clients.html",
        {"request": request, "page_title": "Clients — MF.AI Admin", "items": items},
    )


