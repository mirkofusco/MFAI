from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/c", tags=["Public UI"])

@router.get("/ping", response_class=HTMLResponse)
async def ping():
    return HTMLResponse("<h1>Public UI: OK</h1>")

@router.get("/{slug}", response_class=HTMLResponse)
async def space(slug: str):
    return HTMLResponse(f"<h1>Spazio pubblico: {slug}</h1><p>Stub: {slug}</p>")
