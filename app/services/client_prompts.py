import os, time, asyncio
from typing import Dict
from sqlalchemy import text
from app.db import engine

_TTL = float(os.getenv("PROMPTS_CACHE_TTL", "60"))
_CACHE: Dict[int, Dict[str, str]] = {}
_CACHE_TS: Dict[int, float] = {}
_LOCKS: Dict[int, asyncio.Lock] = {}

_DEFAULTS: Dict[str, str] = {
    "GREETING": "Ciao! Come posso aiutarti?",
    "FALLBACK": "Non ho capito bene. Puoi riformulare in modo semplice?",
    "PRIVACY_NOTICE": "Questa chat può essere registrata per migliorare il servizio.",
    "HANDOFF": "Ti metto in contatto con un operatore umano al più presto.",
    "SMALLTALK_GUARD": "Proviamo a restare sull’argomento della richiesta.",
    "OUT_OF_HOURS": "Siamo fuori orario. Ti risponderemo appena possibile.",
    "LEGAL_DISCLAIMER": "Le informazioni fornite hanno scopo informativo e non sostituiscono pareri ufficiali.",
}

def _lock_for(client_id: int) -> asyncio.Lock:
    if client_id not in _LOCKS:
        _LOCKS[client_id] = asyncio.Lock()
    return _LOCKS[client_id]

async def _load_globals() -> Dict[str, str]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT key, value FROM mfai_app.prompts"))).all()
    return {str(k).upper() if k is not None else "" : v for k, v in rows} if rows else {}

async def _load_client_overrides(client_id: int) -> Dict[str, str]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT key, value FROM mfai_app.client_prompts WHERE client_id = :cid"
        ), {"cid": client_id})).all()
    return {str(k).upper() if k is not None else "" : v for k, v in rows} if rows else {}

async def _refresh(client_id: int) -> None:
    async with _lock_for(client_id):
        globals_ = await _load_globals()
        overrides = await _load_client_overrides(client_id)
        merged = dict(_DEFAULTS)
        merged.update(globals_)
        merged.update(overrides)
        _CACHE[client_id] = merged
        _CACHE_TS[client_id] = time.time()

def _expired(client_id: int) -> bool:
    ts = _CACHE_TS.get(client_id, 0.0)
    return (time.time() - ts) > _TTL

async def list_prompts_for_client(client_id: int) -> Dict[str, str]:
    if client_id not in _CACHE or _expired(client_id):
        await _refresh(client_id)
    return dict(_CACHE[client_id])

async def upsert_prompt_for_client(client_id: int, key: str, value: str) -> str:
    k = (key or "").strip().upper()
    v = (value or "")
    if not k:
        raise ValueError("key è obbligatoria")
    if "/" in k or len(k) > 120:
        raise ValueError("key non valida")
    if len(v) == 0:
        raise ValueError("value è obbligatorio")
    if len(v) > 5000:
        raise ValueError("value troppo lungo (max 5000)")
    async with engine.begin() as conn:
        chk = await conn.execute(text("SELECT 1 FROM mfai_app.clients WHERE id=:id"), {"id": client_id})
        if chk.scalar_one_or_none() is None:
            raise ValueError("Client not found")
        await conn.execute(text("""
            INSERT INTO mfai_app.client_prompts (client_id, key, value)
            VALUES (:cid, :k, :v)
            ON CONFLICT (client_id, key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """), {"cid": client_id, "k": k, "v": v})
    await _refresh(client_id)
    return k
