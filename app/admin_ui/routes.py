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

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request, _: bool = Depends(require_admin)):
    # Chiama l’API admin protetta (/admin/clients) con le stesse credenziali Basic
    url = f"{ADMIN_BASE_URL}/admin/clients"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, auth=(ADMIN_USER, ADMIN_PASSWORD))
        if resp.status_code == 401:
            # segnala errore di configurazione credenziali lato server
            raise HTTPException(status_code=502, detail="Admin API unauthorized from UI")
        resp.raise_for_status()
        data = resp.json()

    items: List[Dict[str, Any]] = data if isinstance(data, list) else data.get("items", [])
    return templates.TemplateResponse(
        "clients.html",
        {
            "request": request,
            "page_title": "Clients — MF.AI Admin",
            "items": items,
        },
    )
