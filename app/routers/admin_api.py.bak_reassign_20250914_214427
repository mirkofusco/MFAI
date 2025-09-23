from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

from app.security_admin import verify_admin
from app.db_session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

# ---- Health
@router.get("/health")
async def admin_health(_: dict = Depends(verify_admin)):
    return {"status": "ok"}

# ---- Clients
@router.get("/clients")
async def list_clients(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
):
    q = text("""
        SELECT id, name, email, created_at
        FROM mfai_app.clients
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]

@router.post("/clients")
async def create_client(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    payload: dict = Body(...),
):
    q = text("""
        INSERT INTO mfai_app.clients (name, email)
        VALUES (:name, :email)
        RETURNING id, name, email, created_at
    """)
    row = await db.execute(q, {"name": payload["name"], "email": payload.get("email")})
    await db.commit()
    return dict(row.mappings().one())

# ---- Accounts (schema reale)
@router.get("/accounts")
async def list_accounts(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
):
    q = text("""
        SELECT
            ig_user_id,
            username,
            client_id,
            COALESCE(bot_enabled, true) AS bot_enabled,
            COALESCE(active, true)       AS active,
            created_at
        FROM mfai_app.instagram_accounts
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]

@router.patch("/accounts/{ig_user_id}")
async def toggle_account(
    ig_user_id: str,
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    payload: dict = Body(...),
):
    q = text("""
        UPDATE mfai_app.instagram_accounts
        SET bot_enabled = :b
        WHERE ig_user_id = :id
        RETURNING ig_user_id, bot_enabled
    """)
    res = await db.execute(q, {"b": bool(payload["bot_enabled"]), "id": ig_user_id})
    row = res.mappings().first()
    await db.commit()
    if not row:
        return {"error": "not_found", "ig_user_id": ig_user_id}
    return dict(row)

# ---- Tokens (join con instagram_accounts per avere ig_user_id/username)
@router.get("/tokens")
async def list_tokens(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    active: Optional[bool] = Query(None),
):
    base = """
        SELECT
            t.id,
            t.ig_account_id,
            a.ig_user_id,
            a.username,
            t.active,
            t.expires_at,
            t.long_lived,
            t.created_at
        FROM mfai_app.tokens t
        JOIN mfai_app.instagram_accounts a ON a.id = t.ig_account_id
    """
    if active is None:
        q = text(base + " ORDER BY t.expires_at ASC NULLS LAST")
        rows = await db.execute(q)
    else:
        q = text(base + " WHERE t.active = :a ORDER BY t.expires_at ASC NULLS LAST")
        rows = await db.execute(q, {"a": active})
    return [dict(r) for r in rows.mappings().all()]

# ---- Logs (versione robusta)
@router.get("/logs")
async def list_logs(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
):
    q = text("""
        SELECT ts, direction, payload, raw_json
        FROM mfai_app.message_logs
        ORDER BY ts DESC
        LIMIT :limit
    """)
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]

@router.post("/accounts")
async def create_account(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    payload: dict = Body(...)
):
    # payload: {"client_id": 5, "ig_user_id":"...", "username":"..."}
    exists_q = text("SELECT 1 FROM mfai_app.instagram_accounts WHERE ig_user_id = :ig LIMIT 1")
    if (await db.execute(exists_q, {"ig": payload["ig_user_id"]})).first():
        return {"error": "already_exists", "ig_user_id": payload["ig_user_id"]}

    q = text("""
        INSERT INTO mfai_app.instagram_accounts
            (client_id, ig_user_id, username, active, bot_enabled)
        VALUES
            (:client_id, :ig_user_id, :username, true, true)
        RETURNING id, client_id, ig_user_id, username, active, bot_enabled, created_at
    """)
    row = await db.execute(q, {
        "client_id": payload["client_id"],
        "ig_user_id": payload["ig_user_id"],
        "username": payload["username"],
    })
    await db.commit()
    return dict(row.mappings().one())


# --- PATCH /admin/accounts/{ig_user_id} : aggiorna mapping IG (client_id/active/bot_enabled/username) ---
from fastapi import Path
from sqlalchemy.ext.asyncio import AsyncSession

@router.patch("/accounts/{ig_user_id}")
async def update_account_mapping(
    ig_user_id: str = Path(..., description="Instagram User ID"),
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    fields = []
    params = {"ig_user_id": ig_user_id}

    # campi ammessi
    for k in ("client_id", "active", "bot_enabled", "username"):
        if k in payload:
            fields.append(f"{k} = :{k}")
            params[k] = payload[k]

    if not fields:
        raise HTTPException(status_code=400, detail="Nessun campo valido da aggiornare")

    q = text(f"""
        UPDATE mfai_app.instagram_accounts
        SET {", ".join(fields)}
        WHERE ig_user_id = :ig_user_id
        RETURNING id, client_id, ig_user_id, username, active, bot_enabled, created_at
    """)
    res = await db.execute(q, params)
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Account IG non trovato")

    await db.commit()
    return dict(row)

# --- PATCH /admin/accounts/{ig_user_id} : aggiorna mapping IG (client_id/active/bot_enabled/username) ---
from fastapi import Path, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.security_admin import verify_admin
from app.db_session import get_session

@router.patch("/accounts/{ig_user_id}")
async def update_account_mapping(
    ig_user_id: str = Path(..., description="Instagram User ID"),
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    fields = []
    params = {"ig_user_id": ig_user_id}

    # campi ammessi
    for k in ("client_id", "active", "bot_enabled", "username"):
        if k in payload:
            fields.append(f"{k} = :{k}")
            params[k] = payload[k]

    if not fields:
        raise HTTPException(status_code=400, detail="Nessun campo valido da aggiornare")

    q = text(f"""
        UPDATE mfai_app.instagram_accounts
        SET {", ".join(fields)}
        WHERE ig_user_id = :ig_user_id
        RETURNING id, client_id, ig_user_id, username, active, bot_enabled, created_at
    """)
    res = await db.execute(q, params)
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Account IG non trovato")

    await db.commit()
    return dict(row)
