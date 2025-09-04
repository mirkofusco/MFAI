from typing import Dict
import time
from sqlalchemy import text
from app.db import engine  # async engine verso Neon

_CACHE: Dict[str, str] = {}
_CACHE_TS: float = 0.0
_TTL_SEC = 60.0

_DEFAULTS = {
    "GREETING": "Ciao! Come posso aiutarti?",
    "FALLBACK": "Non ho capito bene. Puoi riformulare in modo semplice?",
    "PRIVACY_NOTICE": "Questa chat può essere registrata per migliorare il servizio.",
    "HANDOFF": "Ti metto in contatto con un operatore umano al più presto.",
    "SMALLTALK_GUARD": "Proviamo a restare sull’argomento della richiesta.",
    "OUT_OF_HOURS": "Siamo fuori orario. Ti risponderemo appena possibile.",
    "LEGAL_DISCLAIMER": "Le informazioni fornite hanno scopo informativo e non sostituiscono pareri ufficiali.",
}

async def _refresh_cache():
    global _CACHE, _CACHE_TS
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT key, value FROM mfai_app.prompts"))).all()
    _CACHE = {k: v for k, v in rows} if rows else {}
    _CACHE_TS = time.time()

async def get_prompt(key: str) -> str:
    now = time.time()
    if not _CACHE or (now - _CACHE_TS) > _TTL_SEC:
        await _refresh_cache()
    return _CACHE.get(key) or _DEFAULTS.get(key, "")

async def list_prompts() -> Dict[str, str]:
    now = time.time()
    if not _CACHE or (now - _CACHE_TS) > _TTL_SEC:
        await _refresh_cache()
    merged = dict(_DEFAULTS)
    merged.update(_CACHE)
    return merged

async def upsert_prompt(key: str, value: str) -> str:
    key = key.strip().upper()
    value = value.strip()
    if not key or not value:
        raise ValueError("key e value sono obbligatori")
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO mfai_app.prompts(key, value)
                VALUES (:k, :v)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """),
            {"k": key, "v": value},
        )
    await _refresh_cache()
    return key
