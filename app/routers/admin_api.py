from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.security_admin import verify_admin
from app.db import get_session  # adegua se il path è diverso

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/health")
async def admin_health(_: dict = Depends(verify_admin)):
    return {"status": "ok"}

@router.get("/clients")
async def list_clients(_: dict = Depends(verify_admin), db: AsyncSession = Depends(get_session), limit: int = Query(50, ge=1, le=200)):
    q = text("SELECT id, name, email, created_at FROM mfai_app.clients ORDER BY created_at DESC LIMIT :limit")
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]

@router.post("/clients")
async def create_client(_: dict = Depends(verify_admin), db: AsyncSession = Depends(get_session), payload: dict = Body(...)):
    q = text("INSERT INTO mfai_app.clients (name, email) VALUES (:name, :email) RETURNING id, name, email, created_at")
    row = await db.execute(q, {"name": payload["name"], "email": payload.get("email")})
    await db.commit()
    return dict(row.mappings().one())

@router.get("/accounts")
async def list_accounts(_: dict = Depends(verify_admin), db: AsyncSession = Depends(get_session), limit: int = Query(50, ge=1, le=200)):
    q = text("SELECT ig_user_id, client_id, display_name, bot_enabled, created_at FROM mfai_app.instagram_accounts ORDER BY created_at DESC LIMIT :limit")
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]

@router.patch("/accounts/{ig_user_id}")
async def toggle_account(ig_user_id: str, _: dict = Depends(verify_admin), db: AsyncSession = Depends(get_session), payload: dict = Body(...)):
    q = text("UPDATE mfai_app.instagram_accounts SET bot_enabled = :b WHERE ig_user_id = :id RETURNING ig_user_id, bot_enabled")
    row = await db.execute(q, {"b": bool(payload["bot_enabled"]), "id": ig_user_id})
    if row.rowcount == 0:
        return {"error": "not_found", "ig_user_id": ig_user_id}
    await db.commit()
    return dict(row.mappings().one())

@router.get("/tokens")
async def list_tokens(_: dict = Depends(verify_admin), db: AsyncSession = Depends(get_session), active: Optional[bool] = Query(None)):
    base = "SELECT provider, account_id, active, expires_at FROM mfai_app.tokens"
    if active is None:
        q = text(base + " ORDER BY expires_at ASC")
        rows = await db.execute(q)
    else:
        q = text(base + " WHERE active = :a ORDER BY expires_at ASC")
        rows = await db.execute(q, {"a": active})
    return [dict(r) for r in rows.mappings().all()]

@router.get("/logs")
async def list_logs(_: dict = Depends(verify_admin), db: AsyncSession = Depends(get_session), limit: int = Query(50, ge=1, le=200)):
    q = text("SELECT ts, provider, direction, payload, raw_json FROM mfai_app.message_logs ORDER BY ts DESC LIMIT :limit")
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]
