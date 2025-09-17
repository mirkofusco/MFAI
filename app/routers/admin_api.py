# app/routers/admin_api.py
from typing import Optional

from fastapi import APIRouter, Depends, Query, Body, Path, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.security_admin import verify_admin
from app.db_session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------- Health ----------------
@router.get("/health")
async def admin_health(_: dict = Depends(verify_admin)):
    return {"status": "ok"}

# --------------- Clients ----------------
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
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or None)
    if not name:
        raise HTTPException(status_code=400, detail="Il campo 'name' è obbligatorio")

    q = text("""
        INSERT INTO mfai_app.clients (name, email)
        VALUES (:name, :email)
        RETURNING id, name, email, created_at
    """)
    res = await db.execute(q, {"name": name, "email": email})
    await db.commit()
    return dict(res.mappings().one())

async def _delete_client_tx(db: AsyncSession, client_id: int):
    # esiste il client?
    r = await db.execute(text("SELECT 1 FROM mfai_app.clients WHERE id=:id"), {"id": client_id})
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Client not found")

    # elimina dipendenze (tokens -> instagram_accounts) poi client
    await db.execute(text("""
        DELETE FROM mfai_app.tokens
        WHERE ig_account_id IN (
          SELECT id FROM mfai_app.instagram_accounts WHERE client_id=:id
        )
    """), {"id": client_id})
    await db.execute(text("DELETE FROM mfai_app.instagram_accounts WHERE client_id=:id"), {"id": client_id})
    await db.execute(text("DELETE FROM mfai_app.clients WHERE id=:id"), {"id": client_id})

@router.delete("/clients/{client_id}")
async def delete_client_by_path(
    client_id: int = Path(..., ge=1),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    async with db.begin():
        await _delete_client_tx(db, client_id)
    return {"status": "deleted", "id": client_id}

@router.delete("/clients")
async def delete_client_by_body(
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    try:
        client_id = int(payload.get("id", 0))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid 'id'")
    if client_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid 'id'")

    async with db.begin():
        await _delete_client_tx(db, client_id)
    return {"status": "deleted", "id": client_id}

# --------------- Accounts ---------------
@router.get("/accounts")
async def list_accounts(
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
):
    q = text("""
        SELECT
            id,
            client_id,
            ig_user_id,
            username,
            COALESCE(bot_enabled, true) AS bot_enabled,
            COALESCE(active, true)       AS active,
            created_at
        FROM mfai_app.instagram_accounts
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    rows = await db.execute(q, {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]

@router.post("/accounts")
async def create_account(
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    # payload atteso: {"client_id": 5, "ig_user_id":"...", "username":"..."}
    ig_user_id = (payload.get("ig_user_id") or "").strip()
    username = (payload.get("username") or "").strip()
    client_id = payload.get("client_id")

    if not ig_user_id or not username or not client_id:
        raise HTTPException(status_code=400, detail="client_id, ig_user_id e username sono obbligatori")

    # esistenza dup IG
    exists_q = text("SELECT 1 FROM mfai_app.instagram_accounts WHERE ig_user_id = :ig LIMIT 1")
    if (await db.execute(exists_q, {"ig": ig_user_id})).first():
        raise HTTPException(status_code=409, detail="Instagram account già presente")

    q = text("""
        INSERT INTO mfai_app.instagram_accounts
            (client_id, ig_user_id, username, active, bot_enabled)
        VALUES
            (:client_id, :ig_user_id, :username, true, true)
        RETURNING id, client_id, ig_user_id, username, active, bot_enabled, created_at
    """)
    res = await db.execute(q, {
        "client_id": client_id,
        "ig_user_id": ig_user_id,
        "username": username,
    })
    await db.commit()
    return dict(res.mappings().one())

@router.patch("/accounts/{ig_user_id}")
async def update_account_mapping(
    ig_user_id: str = Path(..., description="Instagram User ID"),
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    # campi ammessi per update
    fields = []
    params = {"ig_user_id": ig_user_id}

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

# ---------------- Tokens ----------------
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

@router.post("/tokens")
async def save_token(
    payload: dict = Body(...),
    _: dict = Depends(verify_admin),
    db: AsyncSession = Depends(get_session),
):
    # payload atteso: {"ig_user_id":"...", "access_token":"...", "long_lived":true, "expires_at":"2025-11-01T12:00:00Z"}
    ig_user_id = (payload.get("ig_user_id") or "").strip()
    access_token = payload.get("access_token") or payload.get("token")
    long_lived = bool(payload.get("long_lived", True))
    expires_at = payload.get("expires_at")  # opzionale, ISO8601 o NULL

    if not ig_user_id or not access_token:
        raise HTTPException(status_code=400, detail="ig_user_id e access_token sono obbligatori")

    # risolvi ig_account_id
    r = await db.execute(text("SELECT id FROM mfai_app.instagram_accounts WHERE ig_user_id=:ig"), {"ig": ig_user_id})
    ig_account_id = r.scalar_one_or_none()
    if ig_account_id is None:
        raise HTTPException(status_code=404, detail="Instagram account non mappato")

    async with db.begin():
        # disattiva token precedenti
        await db.execute(text("UPDATE mfai_app.tokens SET active=false WHERE ig_account_id=:aid"), {"aid": ig_account_id})
        # inserisci nuovo token attivo
        res = await db.execute(text("""
            INSERT INTO mfai_app.tokens (ig_account_id, access_token, active, long_lived, expires_at)
            VALUES (:aid, :tok, true, :ll, :exp)
            RETURNING id, ig_account_id, active, long_lived, expires_at, created_at
        """), {"aid": ig_account_id, "tok": access_token, "ll": long_lived, "exp": expires_at})
    return dict(res.mappings().one())

# ---------------- Logs ----------------
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
