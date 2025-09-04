import time
from typing import Dict
from sqlalchemy import text
from app.db import engine

# cache semplice per singolo client
_CACHE: Dict[int, Dict[str, str]] = {}
_CACHE_TS: Dict[int, float] = {}
_TTL = 60.0

_DEFAULTS = {
    "GREETING": "Ciao! Come posso aiutarti?",
    "FALLBACK": "Non ho capito bene. Puoi riformulare in modo semplice?",
    "PRIVACY_NOTICE": "Questa chat può essere registrata per migliorare il servizio.",
    "HANDOFF": "Ti metto in contatto con un operatore umano al più presto.",
    "SMALLTALK_GUARD": "Proviamo a restare sull’argomento della richiesta.",
    "OUT_OF_HOURS": "Siamo fuori orario. Ti risponderemo appena possibile.",
    "LEGAL_DISCLAIMER": "Le informazioni fornite hanno scopo informativo e non sostituiscono pareri ufficiali.",
}

async def _load_globals() -> Dict[str, str]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT key, value FROM mfai_app.prompts"))).all()
    return {k: v for k, v in rows} if rows else {}

async def _load_client_overrides(client_id: int) -> Dict[str, str]:
    async with engine.connect() as conn:
        rows = (await conn.execute(
            text("SELECT key, value FROM mfai_app.client_prompts WHERE client_id = :cid"),
            {"cid": client_id}
        )).all()
    return {k: v for k, v in rows} if rows else {}

async def _refresh(client_id: int):
    globals_ = await _load_globals()
    overrides = await _load_client_overrides(client_id)
    merged = dict(_DEFAULTS)
    merged.update(globals_)
    merged.update({k.upper(): v for k, v in overrides.items()})
    _CACHE[client_id] = merged
    _CACHE_TS[client_id] = time.time()

async def list_prompts_for_client(client_id: int) -> Dict[str, str]:
    now = time.time()
    if client_id not in _CACHE or (now - _CACHE_TS.get(client_id, 0)) > _TTL:
        await _refresh(client_id)
    return _CACHE[client_id]

async def upsert_prompt_for_client(client_id: int, key: str, value: str) -> str:
    key = (key or "").strip().upper()
    value = (value or "").strip()
    if not key or not value:
        raise ValueError("key e value sono obbligatori")
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO mfai_app.client_prompts (client_id, key, value)
                VALUES (:cid, :k, :v)
                ON CONFLICT (client_id, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """),
            {"cid": client_id, "k": key, "v": value},
        )
    await _refresh(client_id)
    return key
