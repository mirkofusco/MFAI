from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/c", tags=["Public UI"])

@router.get("/ping", response_class=HTMLResponse)
async def ping():
    return HTMLResponse("<h1>Public UI: OK</h1>")

@router.get("/{slug}", response_class=HTMLResponse)
async def space(slug: str):
    return HTMLResponse(f"<h1>Spazio pubblico: {slug}</h1><p>Stub: {slug}</p>")
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/c", tags=["Public UI"])
templates = Jinja2Templates(directory="app/public_ui/templates")

# Config minimale degli spazi (poi verrà da DB)
SPACES = {
    "dietologa-demo": {
        "title": "Dietologa — Demo",
        "intro": "Benvenuto nello spazio demo della Dietologa.",
    }
}

@router.get("/ping", response_class=HTMLResponse)
async def ping():
    return HTMLResponse("<h1>Public UI: OK</h1>")

@router.get("/{slug}", response_class=HTMLResponse)
async def space(slug: str, request: Request):
    space = SPACES.get(slug, {"title": f"Spazio: {slug}", "intro": "Spazio generico."})
    return templates.TemplateResponse(
        "space.html",
        {"request": request, "slug": slug, "space": space, "title": space["title"]}
    )
