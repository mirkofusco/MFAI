# app/routers/meta_webhook.py
import os
import json
import logging
from time import time
from typing import Any, Dict, List, Tuple, Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import httpx
from sqlalchemy import text

import asyncio  # <<< AGGIUNGI


from app.db import engine  # async SQLAlchemy engine verso Neon

logger = logging.getLogger("meta_webhook")
logger.setLevel(logging.INFO)

router = APIRouter()

# ------------------------------------------------------------------
# ENV / CONFIG
# ------------------------------------------------------------------
VERIFY_TOKEN      = os.getenv("META_VERIFY_TOKEN", "mfai_meta_verify")
FB_PAGE_ID        = os.getenv("FB_PAGE_ID", "701660883039128")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
INBOX_APP_ID      = 263902037430900  # Facebook Page Inbox
RESPECT_HUMAN     = os.getenv("RESPECT_HUMAN", "true").lower() == "true"
HUMAN_TTL_SEC     = int(os.getenv("HUMAN_TTL_SEC", "900"))  # 15 minuti default

logger.info(f"[DEBUG] OPENAI_API_KEY loaded: {bool(OPENAI_API_KEY)}")


# ---- Conversational memory (in-RAM) ----
# key = f"{ig_user_id}:{user_id}", value = list of {"role":"user/assistant","content": "..."}
_SESS: Dict[str, List[Dict[str, str]]] = {}
_SESS_TTL_SEC = int(os.getenv("SESSION_TTL_SEC", "3600"))  # reset dopo 1h inattività
_SESS_LAST_AT: Dict[str, float] = {}

def _skey(ig_user_id: str, user_id: str) -> str:
    return f"{ig_user_id}:{user_id}"

def _sess_get(ig_user_id: str, user_id: str) -> List[Dict[str, str]]:
    key = _skey(ig_user_id, user_id)
    if _SESS_LAST_AT.get(key, 0) + _SESS_TTL_SEC < time():
        _SESS.pop(key, None)
    _SESS_LAST_AT[key] = time()
    return _SESS.setdefault(key, [])

def _sess_add(ig_user_id: str, user_id: str, role: str, content: str, cap: int = 12):
    s = _sess_get(ig_user_id, user_id)
    s.append({"role": role, "content": content})
    if len(s) > cap:
        del s[: len(s) - cap]
    _SESS_LAST_AT[_skey(ig_user_id, user_id)] = time()

def _sess_clear(ig_user_id: str, user_id: str):
    key = _skey(ig_user_id, user_id)
    _SESS.pop(key, None)
    _SESS_LAST_AT.pop(key, None)

# Stato in-memory per "umano attivo" per thread (chiave = f"{ig_user_id}:{user_id}")
_HUMAN_UNTIL: Dict[str, float] = {}

def _key(ig_user_id: str, user_id: str) -> str:
    return f"{ig_user_id}:{user_id}"

def _human_active(ig_user_id: str, user_id: str) -> bool:
    return _HUMAN_UNTIL.get(_key(ig_user_id, user_id), 0) > time()

def _mark_human(ig_user_id: str, user_id: str, ttl: int | None = None) -> None:
    _HUMAN_UNTIL[_key(ig_user_id, user_id)] = time() + (ttl or HUMAN_TTL_SEC)

def _clear_human(ig_user_id: str, user_id: str) -> None:
    _HUMAN_UNTIL.pop(_key(ig_user_id, user_id), None)

# ------------------------------------------------------------------
# HTTP client condiviso (HTTP/2 + keep-alive) per ridurre latenza
# ------------------------------------------------------------------
_HTTPX: Optional[httpx.AsyncClient] = None
GRAPH_BASE = "https://graph.facebook.com/v21.0"  # v21.0

_HTTPX = None

def _httpx() -> httpx.AsyncClient:
    global _HTTPX
    if _HTTPX is None:
        _HTTPX = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=6.0)
            # niente http2=True
        )
    return _HTTPX


async def _close_httpx():
    global _HTTPX
    if _HTTPX is not None:
        await _HTTPX.aclose()
        _HTTPX = None

# ------------------------------------------------------------------
# DB HELPERS (client_id, system prompt, bot flag, tokens, logs)
# ------------------------------------------------------------------
async def _get_client_id_by_ig(ig_user_id: str) -> int | None:
    q = text("SELECT client_id FROM mfai_app.instagram_accounts WHERE ig_user_id = :ig LIMIT 1")
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"ig": ig_user_id})).first()
    return int(row[0]) if row else None

async def _get_system_prompt(client_id: int) -> str | None:
    q = text("""
      SELECT value FROM mfai_app.client_prompts
      WHERE client_id = :cid AND key = 'system'
      LIMIT 1
    """)
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"cid": client_id})).first()
    return str(row[0]) if row else None

async def _bot_is_enabled(ig_user_id: str) -> bool:
    q = text("SELECT bot_enabled FROM mfai_app.instagram_accounts WHERE ig_user_id = :ig LIMIT 1")
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"ig": ig_user_id})).first()
    return bool(row[0]) if row else False

async def _get_ig_account_id(ig_user_id: str) -> int | None:
    q = text("SELECT id FROM mfai_app.instagram_accounts WHERE ig_user_id = :ig LIMIT 1")
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"ig": ig_user_id})).first()
    return int(row[0]) if row else None

async def _get_active_page_token(ig_user_id: str) -> str | None:
    q = text("""
        SELECT t.access_token
        FROM mfai_app.tokens t
        JOIN mfai_app.instagram_accounts ia ON ia.id = t.ig_account_id
        WHERE ia.ig_user_id = :ig AND t.active = TRUE
        LIMIT 1
    """)
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"ig": ig_user_id})).first()
    return row[0] if row else None

async def _log_message(ig_account_id: int | None, direction: str, payload: Any):
    q = text("""
        INSERT INTO mfai_app.message_logs (ig_account_id, direction, payload)
        VALUES (:ig_account_id, :direction, :payload)
    """)
    async with engine.begin() as conn:
        await conn.execute(q, {
            "ig_account_id": ig_account_id,
            "direction": direction,
            "payload": json.dumps(payload, ensure_ascii=False)
        })

def _needs_takeover(resp: Dict[str, Any]) -> bool:
    try:
        err = (resp or {}).get("error", {})
        return err.get("code") == 100 and err.get("error_subcode") == 2534037
    except Exception:
        return False

# ------------------------------------------------------------------
# VERIFY
# ------------------------------------------------------------------
@router.get("/webhook/meta")
async def meta_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    # 🔍 DEBUG: vediamo cosa arriva
    logger.info(f"[VERIFY] mode={mode}, token={token}, challenge={challenge}")
    logger.info(f"[VERIFY] VERIFY_TOKEN={VERIFY_TOKEN}")
    
    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        logger.info(f"[VERIFY] OK, returning challenge")
        return PlainTextResponse(challenge)
    
    logger.warning(f"[VERIFY] FAILED: mode={mode!r}, token_match={token==VERIFY_TOKEN}, challenge={challenge!r}")
    raise HTTPException(status_code=403, detail="Forbidden")

# ------------------------------------------------------------------
# RECEIVER
# ------------------------------------------------------------------
@router.post("/webhook/meta")
async def meta_webhook(request: Request):
    # --- Parse body ---
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("[IG_WEBHOOK] %s", json.dumps(body, ensure_ascii=False))

    # Accetta sia object=instagram che object=page
    if body.get("object") not in ("instagram", "page"):
        logger.info("Webhook object ignored: %s", body.get("object"))
        return JSONResponse({"status": "ignored"}, status_code=200)

    entries: List[Dict[str, Any]] = body.get("entry", []) or []
    if not entries:
        logger.info("No entries in payload")
        return JSONResponse({"status": "ok", "note": "no entries"}, status_code=200)

    # === Loop sugli entry (uno per pagina/ig_user_id) ===
    for entry in entries:
        ig_user_id = str(entry.get("id") or "")
        if not ig_user_id:
            logger.info("Entry senza ig_user_id: %s", entry)
            continue

        # Costruisci una lista unificata di eventi "messaging"
        messaging_list: List[Dict[str, Any]] = entry.get("messaging", []) or []

             # Se vuota, prova il formato Instagram moderno con 'changes'
        if not messaging_list:
            changes = entry.get("changes", []) or []

            # === LOG COMMENTI IG (SOLO LOG, NIENTE DM) ===
            for ch in changes:
                _mfai_log_ig_comment_change(ch)

            for ch in changes:
                val = ch.get("value") or {}
                # IG-style: value.messages = [{from: "...", text: {"body": "..."}}]
                for m in val.get("messages", []) or []:
                    sender_from = str(m.get("from") or "")
                    text_body = (m.get("text") or {}).get("body")
                    if sender_from and isinstance(text_body, str) and text_body.strip():
                        messaging_list.append({
                            "sender": {"id": sender_from},
                            "recipient": {"id": ig_user_id},
                            "message": {"text": text_body}
                        })
                # fallback Messenger-like
                for m in val.get("messaging", []) or []:
                    snd = ((m.get("sender") or {}).get("id"))
                    txt = ((m.get("message") or {}).get("text"))
                    if snd and isinstance(txt, str) and txt.strip():
                        messaging_list.append(m)


        if not messaging_list:
            logger.info("No messaging/changes messages for ig_user_id=%s", ig_user_id)
            continue

        ig_account_id = await _get_ig_account_id(ig_user_id)

        # === Loop sugli eventi messaggio ===
        for evt in messaging_list:
            # --- HANDOVER: pausa/riprendi AI quando l'umano prende/lascia il thread ---
            handover = evt.get("pass_thread_control") or evt.get("take_thread_control")
            if isinstance(handover, dict):
                try:
                    new_owner = handover.get("new_owner_app_id") or handover.get("recipient_app_id")
                    prev_owner = handover.get("previous_owner_app_id")
                    sender_id = str((evt.get("sender") or {}).get("id") or "")
                    recipient_id = str((evt.get("recipient") or {}).get("id") or "")
                    user_id = sender_id if sender_id and sender_id != ig_user_id else recipient_id
                    if new_owner == INBOX_APP_ID:
                        _mark_human(ig_user_id, user_id)
                        logger.info("Handover to INBOX: pause AI for %s", _key(ig_user_id, user_id))
                    elif prev_owner == INBOX_APP_ID:
                        _clear_human(ig_user_id, user_id)
                        logger.info("Handover from INBOX: resume AI for %s", _key(ig_user_id, user_id))
                except Exception as e:
                    logger.warning("handover parse err: %s", e)
                continue

            sender = (evt.get("sender") or {})
            recipient = (evt.get("recipient") or {})
            message = evt.get("message")

            sender_id = str(sender.get("id") or "")
            recipient_id = str(recipient.get("id") or "")

            # Log IN (best-effort)
            try:
                await _log_message(ig_account_id, "in", evt)
            except Exception as e:
                logger.warning("DB log(in) failed: %s", e)

            # --- SOLO messaggi di testo non-echo da UTENTE ---
            if not isinstance(message, dict):
                logger.info("Skip: message not dict")
                continue
            if message.get("is_echo"):
                logger.info("Skip: echo")
                continue
            text_msg = message.get("text")
            if not isinstance(text_msg, str) or not text_msg.strip():
                logger.info("Skip: not text")
                continue
            if sender_id == ig_user_id:
                logger.info("Skip: page echo")
                continue

            # Rispetto umano attivo?
            if RESPECT_HUMAN and _human_active(ig_user_id, sender_id):
                logger.info("Human active: skip AI reply for %s", _key(ig_user_id, sender_id))
                continue

            # Bot abilitato?
            if not await _bot_is_enabled(ig_user_id):
                logger.info("Bot disabled for ig_user_id=%s, skip reply", ig_user_id)
                try:
                    await _log_message(ig_account_id, "out", {"skip": "bot disabled"})
                except Exception:
                    pass
                continue

            # Page token (servirà per typing+invio)
            page_token = await _get_active_page_token(ig_user_id)
            if not page_token:
                logger.warning("No active PAGE TOKEN for IG %s", ig_user_id)
                continue

            # Typing immediato (non blocca)
            try:
                asyncio.create_task(_send_typing_via_me(page_token, sender_id))
            except Exception as e:
                logger.warning("typing_on schedule failed: %s", e)

            # Memoria conversazionale: append input utente
            _sess_add(ig_user_id, sender_id, "user", text_msg)

            # System prompt per cliente (se presente)
            system_override: Optional[str] = None
            try:
                cid = await _get_client_id_by_ig(ig_user_id)
                if cid:
                    system_override = await _get_system_prompt(cid)
            except Exception as e:
                logger.warning("system prompt load failed: %s", e)
                
                            # Chiamata AI (con history) + fallback
            try:
                reply_text = await ai_reply_with_history(
                    ig_user_id, sender_id, system_override=system_override
                )
            except Exception as e:
                logger.error("AI error: %s", e)
                reply_text = _fallback_reply(text_msg)

            # Takeover preventivo se non vogliamo rispettare l'umano
            if not RESPECT_HUMAN:
                try:
                    took_pre = await _take_thread_control(page_token, FB_PAGE_ID, sender_id)
                    logger.info("take_thread_control (pre-send) took=%s", took_pre)
                except Exception as e:
                    logger.warning("take_thread_control (pre-send) error: %s", e)

            # Invio messaggio (primo tentativo)
            ok, resp = await _send_dm_via_me(page_token, sender_id, reply_text)

            # Se fallisce per ownership, prova takeover/rispetto umano e ritenta
            if not ok and _needs_takeover(resp):
                if RESPECT_HUMAN:
                    _mark_human(ig_user_id, sender_id)
                    logger.info("Got 2534037: respect human -> pause AI for %s", _key(ig_user_id, sender_id))
                else:
                    try:
                        took_retry = await _take_thread_control(page_token, FB_PAGE_ID, sender_id)
                        logger.info("take_thread_control (retry) took=%s", took_retry)
                        if took_retry:
                            ok, resp = await _send_dm_via_me(page_token, sender_id, reply_text)
                    except Exception as e:
                        logger.warning("take_thread_control (retry) error: %s", e)

            # Se inviato con successo, append risposta in memoria
            if ok:
                _sess_add(ig_user_id, sender_id, "assistant", reply_text)

            # Log OUT (best-effort)
            try:
                out_payload = {"request": {"to": sender_id, "text": reply_text}, "response": resp}
                await _log_message(ig_account_id, "out", out_payload)
            except Exception as e:
                logger.warning("DB log(out) failed: %s", e)

            logger.info("Send result ok=%s resp=%s", ok, resp)


      

    return JSONResponse({"status": "ok"}, status_code=200)

# ------------------------------------------------------------------
# AI + FALLBACK
# ------------------------------------------------------------------
def _fallback_reply(text_msg: str) -> str:
    t = (text_msg or "").strip()
    if t.lower() in {"ping", "ping777", "test"}:
        return "pong ✅"
    if len(t) > 240:
        t = t[:240] + "…"
    return f"MF.AI: ho ricevuto “{t}”"

def _system_prompt_for_thread(has_history: bool) -> str:
    base = (
        "Sei l’assistente MF.AI. Rispondi in ITALIANO, tono amichevole e sintetico. "
        "Mantieni il CONTINUUM della conversazione: non ri-iniziare con saluti se c’è già contesto. "
        "Se l’utente risponde con una parola breve (es. 'Roma'), interpretala come risposta alla tua ultima domanda. "
        "Fai al massimo UNA domanda di chiarimento per volta."
    )
    if has_history:
        base += " NON ripetere domande già fatte; usa le informazioni appena fornite dall’utente."
    return base

async def ai_reply_with_history(ig_user_id: str, user_id: str, system_override: str | None = None) -> str:
    """Costruisce i messaggi includendo history in-RAM e system override per cliente."""
    sess = _sess_get(ig_user_id, user_id)
    use_history = len(sess) > 1  # c'è già almeno 1 turno precedente

    # Se esiste un system personalizzato, usalo; altrimenti usa quello base
    sys = (system_override or _system_prompt_for_thread(use_history)).strip()
    # Se abbiamo history e il system personalizzato NON lo menziona, rinforza il vincolo.
    if use_history and system_override:
        sys += "\nNon ripetere domande già fatte; usa le informazioni già emerse nel thread."

    # Costruisci i messaggi per OpenAI: system + history (max 10) + ultimo user già appeso in sess
    history = sess[-10:]
    messages = [{"role": "system", "content": sys}] + history

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY assente: uso fallback (con history)")
        # fallback: rispondi usando l'ultimo user
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return _fallback_reply(last_user)

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 220,
    }
    # Nota: qui lasciamo l'AsyncClient locale per non toccare altri pezzi;
    # se vuoi, possiamo poi migrare anche questa chiamata al pool _httpx().
    timeout = httpx.Timeout(12.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions",
                              headers=headers, json=payload)
        if r.status_code != 200:
            logger.error("OpenAI HTTP %s: %s", r.status_code, r.text)
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return _fallback_reply(last_user)
        j = r.json()
        try:
            txt = (j["choices"][0]["message"]["content"]).strip()
            return txt or _fallback_reply(messages[-1]["content"])
        except Exception as e:
            logger.error("OpenAI parse error: %s | payload=%s", e, j)
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return _fallback_reply(last_user)

# ------------------------------------------------------------------
# GRAPH HELPERS (v21.0 + client riusato)
# ------------------------------------------------------------------
async def _take_thread_control(page_token: str, page_id: str, recipient_id: str) -> bool:
    url = f"{GRAPH_BASE}/{page_id}/take_thread_control"  # v21.0
    params = {"access_token": page_token}
    payload = {"recipient": {"id": recipient_id}, "metadata": "mf.ai auto-take"}
    try:
        r = await _httpx().post(url, params=params, json=payload)
        j = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
        return (r.status_code == 200) and (j.get("success") is True)
    except Exception as e:
        logger.exception("take_thread_control error: %s", e)
        return False

async def _send_typing_via_me(page_token: str, recipient_id: str) -> Tuple[bool, Dict[str, Any]]:
    url = f"{GRAPH_BASE}/me/messages"  # v21.0
    params = {"access_token": page_token}
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": "typing_on",
    }
    try:
        r = await _httpx().post(url, params=params, json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        return (200 <= r.status_code < 300, data)
    except Exception as e:
        return (False, {"error": str(e)})

async def _send_dm_via_me(page_token: str, recipient_id: str, text: str) -> Tuple[bool, Dict[str, Any]]:
    url = f"{GRAPH_BASE}/me/messages"  # v21.0
    params = {"access_token": page_token}
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    try:
        r = await _httpx().post(url, params=params, json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        return (200 <= r.status_code < 300, data)
    except Exception as e:
        return (False, {"error": str(e)})
    
    
    
    # === MF.AI — STEP 1: LOG COMMENTI IG (SOLO LOG, NIENTE DM) ===
import logging
from typing import Any, Dict

_logger = logging.getLogger("meta_webhook")

def _mfai_log_ig_comment_change(change: Dict[str, Any]) -> None:
    """
    Riconosce un evento 'commento' IG dal webhook e lo scrive nei log.
    Non invia messaggi: serve solo per verificare che arrivino gli eventi.
    """
    if not isinstance(change, dict):
        return

    field = change.get("field")
    value = change.get("value", {}) if isinstance(change.get("value"), dict) else {}

    comment_id = value.get("id") or value.get("comment_id")
    media_id   = (value.get("media", {}) or {}).get("id") if isinstance(value.get("media"), dict) else value.get("media_id")
    text       = value.get("text") or value.get("message") or ""
    from_user  = (value.get("from", {}) or {}).get("username") or (value.get("from", {}) or {}).get("id")

    # Log solo se sembra davvero un commento
    if field == "comments" or comment_id or text:
        _logger.info(
            "[IG-WEBHOOK][COMMENT] field=%s comment_id=%s media_id=%s from=%s text=%r",
            field, comment_id, media_id, from_user, text
        )

