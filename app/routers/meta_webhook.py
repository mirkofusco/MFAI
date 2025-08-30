import os, json, hmac, hashlib, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError
import httpx

from app.db_session import async_session_maker

router = APIRouter()

VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "changeme")
APP_SECRET   = os.environ.get("META_APP_SECRET", "")
GRAPH_VER    = os.environ.get("META_GRAPH_VERSION", "v23.0")  # restiamo su v23.0

@router.get("/webhook/meta")
async def meta_verify(request: Request):
    qp = request.query_params
    if qp.get("hub.mode") == "subscribe" and qp.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(qp.get("hub.challenge", ""), status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")

def _valid_sig(sig_header: str | None, body: bytes) -> bool:
    # In dev: se non c'è APP_SECRET non bloccare
    if not APP_SECRET:
        return True
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    received = sig_header.split("=", 1)[1]
    expected = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)

async def _get_active_token(session: AsyncSession, ig_user_id: str) -> str | None:
    # Prova più nomi colonna senza far fallire l’endpoint
    for col in ("token", "access_token", "value"):
        q = f"""
        SELECT {col}
        FROM mfai_app.tokens
        WHERE active = TRUE AND ig_user_id = :ig_user_id
        ORDER BY id DESC
        LIMIT 1
        """
        try:
            res = await session.execute(sql_text(q), {"ig_user_id": ig_user_id})
            row = res.first()
            if row and row[0]:
                return row[0]
        except ProgrammingError:
            await session.rollback()
            continue
    return None

async def _send_ig_text(ig_user_id: str, recipient_id: str, text_body: str, token: str) -> dict:
    """
    Instagram Messaging: POST /{IG_USER_ID}/messages
    Inviamo JSON; se mai servisse, esiste anche la variante form-data.
    """
    url = f"https://graph.facebook.com/{GRAPH_VER}/{ig_user_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message":   {"text": text_body},
        "messaging_type": "RESPONSE",
        "messaging_product": "instagram",
    }
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(url, params={"access_token": token}, json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        return {"ok": r.status_code == 200, "status": r.status_code, "data": data}

@router.post("/webhook/meta")
async def meta_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256") or request.headers.get("X-Hub-Signature-256")
    if not _valid_sig(sig, raw):
        # in produzione potresti usare 401; in dev non bloccare
        raise HTTPException(status_code=401, detail="Invalid signature")

    text = raw.decode("utf-8", errors="ignore")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logging.warning("Webhook non-JSON, body=%s", text[:500])
        return JSONResponse({"status": "ignored_non_json"}, 200)

    # log compatto + log completo IG
    logging.info("WEBHOOK EVENT: %s", text[:1000])
    try:
        print("[IG_WEBHOOK]", json.dumps(payload, ensure_ascii=False), flush=True)
    except Exception:
        pass

    events: list[dict] = []

    # A) Test console Meta: {"field":"messages" | "messaging_seen", "value":{...}}
    if isinstance(payload.get("field"), str):
        field = payload["field"]
        v = payload.get("value", {}) or {}
        if field == "messages":
            sender_id    = (v.get("sender") or {}).get("id")
            recipient_id = (v.get("recipient") or {}).get("id")
            msg_text     = (v.get("message") or {}).get("text")
            events.append({
                "ts": datetime.now(timezone.utc),
                "ig_user_id": recipient_id or "",
                "sender_id": sender_id,
                "text": msg_text,
                "raw": payload,
                "test_event": True,
            })
        elif field == "messaging_seen":
            # non rispondiamo ai "seen"
            return {"status": "ok", "received": 0}

    # B) Formato Instagram Messaging “entry/changes/...”
    for e in (payload.get("entry") or []):
        ig_user_id = e.get("id") or ""  # IG business destinatario (es. 1784...)
        for ch in (e.get("changes") or []):
            val = ch.get("value") or {}
            # Alcuni payload IG includono messaging_product
            if val.get("messaging_product") in (None, "instagram"):
                for m in (val.get("messages") or []):
                    ts_ms     = m.get("timestamp")
                    ts        = datetime.fromtimestamp(int(ts_ms)/1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
                    # <<< FIX: estraiamo l'ID stringa del mittente IG >>>
                    sender_id = (m.get("from") or {}).get("id")
                    # testo: se object, usa 'body'; se stringa, usa così com’è
                    text_obj  = m.get("text")
                    msg_text  = text_obj.get("body") if isinstance(text_obj, dict) else text_obj
                    events.append({
                        "ts": ts,
                        "ig_user_id": ig_user_id,
                        "sender_id": sender_id,
                        "text": msg_text,
                        "raw": val,
                        "test_event": False
                    })

        # C) Fallback “entry/messaging” stile Messenger
        for m in (e.get("messaging") or []):
            sender_id = (m.get("sender") or {}).get("id")
            msg       = m.get("message") or {}
            msg_text  = msg.get("text")
            events.append({
                "ts": datetime.now(timezone.utc),
                "ig_user_id": ig_user_id,
                "sender_id": sender_id,
                "text": msg_text,
                "raw": m,
                "test_event": False
            })

    if not events:
        return {"status": "ok", "received": 0}

    async with async_session_maker() as session:  # type: AsyncSession
        for ev in events:
            # log IN (testo se presente, altrimenti raw)
            payload_text = ev["text"] or json.dumps(ev["raw"], ensure_ascii=False)
            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, direction, payload, raw_json)
                    VALUES (:ts, 'in', :payload, CAST(:raw_json AS JSONB))
                """),
                {"ts": ev["ts"], "payload": payload_text, "raw_json": json.dumps(ev["raw"])}
            )

            # invio risposta: solo per eventi reali con sender e IG id valido
            out_resp = {"ok": False, "status": 0, "data": {"info": "skipped"}}
            out_payload = "skipped"

            if not ev.get("test_event") and ev.get("sender_id"):
                ig_id = (ev.get("ig_user_id") or "").strip()
                if ig_id and ig_id not in ("0", "null"):
                    token = await _get_active_token(session, ig_id)
                    if token:
                        reply = "Grazie per il messaggio. Ti risponderemo a breve."
                        out_resp = await _send_ig_text(ig_id, ev["sender_id"], reply, token)
                        out_payload = reply if out_resp.get("ok") else f"ERROR {out_resp.get('status')}"
                    else:
                        out_payload = "ERROR no_active_token"
                else:
                    out_payload = "skipped_invalid_ig_user_id"

            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, direction, payload, raw_json)
                    VALUES (now(), 'out', :payload, CAST(:raw_json AS JSONB))
                """),
                {"payload": out_payload, "raw_json": json.dumps(out_resp)}
            )

        await session.commit()

    return {"status": "ok", "received": len(events)}
