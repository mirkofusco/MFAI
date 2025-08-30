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

# ------------------ VERIFY ------------------
@router.get("/webhook/meta")
async def meta_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "mfai_meta_verify")
    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Forbidden")

# ------------------ RECEIVER ------------------
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
        messaging_list = entry.get("messaging", [])

        ig_account_id = await _get_ig_account_id(ig_user_id)

        for evt in messaging_list:
            # --- riconosci i vari tipi di evento ---
            message   = evt.get("message")
            delivery  = evt.get("delivery")
            read      = evt.get("read")
            reaction  = evt.get("reaction")
            postback  = evt.get("postback")
            standby   = evt.get("standby")

            sender_id = str((evt.get("sender") or {}).get("id") or "")
            recipient_id = str((evt.get("recipient") or {}).get("id") or "")

            # Log IN (best effort)
            try:
                await _log_message(ig_account_id, "in", evt)
            except Exception as e:
                logger.warning("DB log(in) failed: %s", e)

            # --- ANTI-LOOP GUARDS ---
            # 1) ignora eventi non di messaggio (delivery/read/reaction/standby)
            if delivery or read or reaction or standby:
                continue

            # 2) se non c'è message, non rispondere
            if not message:
                continue

            # 3) ignora echo dei nostri messaggi (Facebook/IG usa is_echo)
            if isinstance(message, dict) and message.get("is_echo"):
                continue

            # 4) ignora messaggi senza testo (es. solo media) per evitare risposte generiche
            text_msg = message.get("text") if isinstance(message, dict) else None
            if not isinstance(text_msg, str) or not text_msg.strip():
                continue

            # 5) ulteriore protezione: se per qualsiasi motivo l'ID mittente coincide con l'IG business, salta
            if sender_id == ig_user_id:
                continue

            # --- prepara risposta SOLO per messaggi di testo umani ---
            reply_text = _build_reply(text_msg, postback)

            # recupera Page Token attivo
            page_token = await _get_active_page_token(ig_user_id)
            if not page_token:
                logger.warning("No active PAGE TOKEN for IG %s", ig_user_id)
                continue

            # invia via /me/messages (quella che funziona nel tuo setup)
            ok, resp = await _send_dm_via_me(page_token, sender_id, reply_text)

            # log OUT (best effort)
            try:
                out_payload = {"request": {"to": sender_id, "text": reply_text}, "response": resp}
                await _log_message(ig_account_id, "out", out_payload)
            except Exception as e:
                logger.warning("DB log(out) failed: %s", e)

            logger.info("Send result ok=%s resp=%s", ok, resp)

    return JSONResponse({"status": "ok"})

# ------------------ HELPERS ------------------
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

def _build_reply(text_msg: str | None, postback: Dict[str, Any] | None) -> str:
    t = (text_msg or "").strip()
    if t.lower() in {"ping", "ping777", "test"}:
        return "pong ✅"
    if len(t) > 240:
        t = t[:240] + "…"
    return f"MF.AI: ho ricevuto “{t}”"

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
