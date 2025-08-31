# app/routers/meta_webhook.py
import os
import json
import logging
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import httpx
from sqlalchemy import text

from app.db import engine  # async SQLAlchemy engine verso Neon

logger = logging.getLogger("meta_webhook")
logger.setLevel(logging.INFO)

router = APIRouter()

# ------------------------------------------------------------------
# Config ENV
# ------------------------------------------------------------------
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "mfai_meta_verify")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "701660883039128")  # <-- metti anche su Koyeb
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------------------------------------------
# VERIFY
# ------------------------------------------------------------------
@router.get("/webhook/meta")
async def meta_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Forbidden")

# ------------------------------------------------------------------
# RECEIVER
# ------------------------------------------------------------------
@router.post("/webhook/meta")
async def meta_webhook(request: Request):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("[IG_WEBHOOK] %s", json.dumps(body, ensure_ascii=False))

    if body.get("object") != "instagram":
        return JSONResponse({"status": "ignored"}, status_code=200)

    entries: List[Dict[str, Any]] = body.get("entry", [])
    for entry in entries:
        ig_user_id = str(entry.get("id") or "")  # es. 1784...
        messaging_list = entry.get("messaging", []) or []

        ig_account_id = await _get_ig_account_id(ig_user_id)

        for evt in messaging_list:
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

            # --- SOLO messaggi di testo non-echo ---
            if not isinstance(message, dict):
                continue
            if message.get("is_echo"):
                continue
            text_msg = message.get("text")
            if not isinstance(text_msg, str) or not text_msg.strip():
                continue
            if sender_id == ig_user_id:
                continue

            # --- Reply (AI con fallback) ---
            try:
                reply_text = await ai_reply(text_msg)
            except Exception as e:
                logger.error("AI error: %s", e)
                reply_text = _fallback_reply(text_msg)

            # --- Page Token attivo ---
            page_token = await _get_active_page_token(ig_user_id)
            if not page_token:
                logger.warning("No active PAGE TOKEN for IG %s", ig_user_id)
                continue

            # --- Invio via /me/messages ---
            ok, resp = await _send_dm_via_me(page_token, sender_id, reply_text)

            # --- AUTO TAKEOVER + RETRY UNA VOLTA ---
            if (not ok) and _needs_takeover(resp):
                took = await _take_thread_control(page_token, FB_PAGE_ID, sender_id)
                logger.info("take_thread_control took=%s", took)
                if took:
                    ok, resp = await _send_dm_via_me(page_token, sender_id, reply_text)

            # Log OUT (best-effort)
            try:
                out_payload = {"request": {"to": sender_id, "text": reply_text}, "response": resp}
                await _log_message(ig_account_id, "out", out_payload)
            except Exception as e:
                logger.warning("DB log(out) failed: %s", e)

            logger.info("Send result ok=%s resp=%s", ok, resp)

    return JSONResponse({"status": "ok"})

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

async def ai_reply(user_text: str) -> str:
    # Se non hai messo la chiave -> fallback
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY assente: uso fallback")
        return _fallback_reply(user_text)

    sys = ("Sei l’assistente MF.AI. Rispondi in italiano, tono amichevole, breve e utile. "
           "Se manca contesto, fai UNA sola domanda chiarificatrice.")
    payload = {
        "model": "gpt-4o-mini",  # scegli il tuo modello
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    timeout = httpx.Timeout(12.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions",
                              headers=headers, json=payload)
        if r.status_code != 200:
            logger.error("OpenAI HTTP %s: %s", r.status_code, r.text)
            return _fallback_reply(user_text)
        j = r.json()
        try:
            txt = (j["choices"][0]["message"]["content"]).strip()
            return txt or _fallback_reply(user_text)
        except Exception as e:
            logger.error("OpenAI parse error: %s | payload=%s", e, j)
            return _fallback_reply(user_text)

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
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
        err = resp.get("error", {})
        return err.get("code") == 100 and err.get("error_subcode") == 2534037
    except Exception:
        return False

async def _take_thread_control(page_token: str, page_id: str, recipient_id: str) -> bool:
    url = f"https://graph.facebook.com/v20.0/{page_id}/take_thread_control"
    params = {"access_token": page_token}
    payload = {"recipient": {"id": recipient_id}, "metadata": "mf.ai auto-take"}
    timeout = httpx.Timeout(12.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, params=params, json=payload)
        try:
            j = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
        except Exception:
            j = {}
        return r.status_code == 200 and j.get("success") is True

async def _send_dm_via_me(page_token: str, recipient_id: str, text: str) -> Tuple[bool, Dict[str, Any]]:
    url = "https://graph.facebook.com/v20.0/me/messages"
    params = {"access_token": page_token}
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    timeout = httpx.Timeout(12.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, params=params, json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        return (r.status_code == 200, data)
