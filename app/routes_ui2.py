from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db_session import get_session
from app.security_admin import verify_admin

router = APIRouter(prefix="/ui2", tags=["ui2"])
templates = Jinja2Templates(directory="app/templates")

# LISTA CLIENTI
@router.get("")
async def ui2_clients_list(
    request: Request,
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    ok: str | None = None,
    err: str | None = None,
):
    rows = await db.execute(text("""
        SELECT id, name, email, ai_prompt, created_at
        FROM mfai_app.clients
        ORDER BY created_at DESC
    """))
    clients = [dict(r) for r in rows.mappings().all()]
    return templates.TemplateResponse("ui2/clients.html", {
        "request": request,
        "page_title": "Clienti",
        "clients": clients,
        "ok": ok,
        "err": err,
    })

# CREA CLIENTE
@router.post("/clients/create")
async def ui2_clients_create(
    name: str = Form(...),
    email: str | None = Form(None),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    name = (name or "").strip()
    if not name:
        return RedirectResponse(url="/ui2?err=invalid_input", status_code=303)

    row = await db.execute(text("""
        INSERT INTO mfai_app.clients (name, email)
        VALUES (:name, :email)
        RETURNING id
    """), {"name": name, "email": (email or None)})
    await db.commit()
    _ = row.mappings().first()["id"]
    return RedirectResponse(url="/ui2?ok=created", status_code=303)

# ELIMINA CLIENTE
@router.post("/clients/{client_id}/delete")
async def ui2_clients_delete(
    client_id: int,
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    await db.execute(text("DELETE FROM mfai_app.clients WHERE id = :id"), {"id": client_id})
    await db.commit()
    return RedirectResponse(url="/ui2?ok=deleted", status_code=303)
