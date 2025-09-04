from typing import Dict
import time
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Prompt

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

def _refresh_cache(db: Session):
    global _CACHE, _CACHE_TS
    rows = db.execute(select(Prompt.key, Prompt.value)).all()
    _CACHE = {k: v for k, v in rows} if rows else {}
    _CACHE_TS = time.time()

def get_prompt(db: Session, key: str) -> str:
    now = time.time()
    if not _CACHE or (now - _CACHE_TS) > _TTL_SEC:
        _refresh_cache(db)
    return _CACHE.get(key) or _DEFAULTS.get(key, "")

def list_prompts(db: Session) -> Dict[str, str]:
    now = time.time()
    if not _CACHE or (now - _CACHE_TS) > _TTL_SEC:
        _refresh_cache(db)
    merged = dict(_DEFAULTS)
    merged.update(_CACHE)
    return merged

def upsert_prompt(db: Session, key: str, value: str) -> str:
    key = key.strip().upper()
    value = value.strip()
    if not key or not value:
        raise ValueError("key e value sono obbligatori")
    existing = db.execute(select(Prompt).where(Prompt.key == key)).scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db.add(Prompt(key=key, value=value))
    db.commit()
    _refresh_cache(db)
    return key
